import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, Optional

from sqlalchemy.orm import Session

import prompt as prompts
from database import Resume, User
from experience_parser import merge_experience_into_analysis
from gemini_client import GeminiQuotaError, generate_json
from job_fetcher import fetch_live_job_listings
from job_link_builder import build_platform_search_url
from job_matcher import compute_job_match
from job_role_utils import align_jobs_to_role, clean_job_title, title_matches_role
from resume_context import build_job_search_context, extract_locations_from_analysis

PLATFORMS = ["LinkedIn", "Naukri", "Indeed", "Internshala"]
PLATFORM_FILTER_OPTIONS = ["All platforms", *PLATFORMS, "Other websites"]
_LLM_SEARCH_TIMEOUT = int(os.getenv("JOB_SEARCH_LLM_TIMEOUT", "12"))
_USE_LLM_JOB_SEARCH = os.getenv("USE_LLM_JOB_SEARCH", "false").lower() in ("1", "true", "yes")
_USE_LIVE_JOB_FETCH = os.getenv("USE_LIVE_JOB_FETCH", "true").lower() in ("1", "true", "yes")
_ALLOW_SEARCH_LINK_FALLBACK = os.getenv("ALLOW_SEARCH_LINK_FALLBACK", "false").lower() in (
    "1",
    "true",
    "yes",
)

# Minimal fallback only when explicitly enabled and live fetch returns nothing
def _load_resume_bundle(db: Session, user: User) -> tuple[dict, str]:
    resume = db.query(Resume).filter(Resume.user_id == user.id).first()
    if not resume or not resume.analysis_json:
        return {}, ""
    analysis = json.loads(resume.analysis_json)
    raw_text = resume.raw_text or ""
    if raw_text and not analysis.get("experience"):
        analysis = merge_experience_into_analysis(raw_text, analysis)
        resume.analysis_json = json.dumps(analysis)
        db.commit()
    return analysis, raw_text


def _load_analysis(db: Session, user: User) -> dict:
    analysis, _ = _load_resume_bundle(db, user)
    return analysis


def _build_profile_summary(analysis: dict) -> str:
    exp = analysis.get("experience") or {}
    parts = [
        f"Summary: {analysis.get('summary', 'N/A')}",
        f"Skills: {', '.join(analysis.get('skills', [])[:25])}",
        f"Experience: {exp.get('formatted') or analysis.get('experience_years', 0)} years",
        f"Experience detail: {json.dumps(exp.get('breakdown', {}))}",
        f"Past titles: {', '.join(analysis.get('job_titles', [])[:8])}",
        f"Suggested roles: {', '.join(analysis.get('suggested_roles', [])[:8])}",
        f"Education: {', '.join(analysis.get('education', [])[:5])}",
    ]
    positions = [p for p in (exp.get("positions") or []) if p.get("title")]
    if positions:
        parts.append(
            "Work history: "
            + "; ".join(
                f"{p.get('title')} ({p.get('start', '')} - {p.get('end', '')})"
                for p in positions[:5]
            )
        )
    return "\n".join(parts)


def _normalize_job(
    raw: dict,
    index: int,
    analysis: dict | None = None,
    user_role: str | None = None,
) -> dict:
    platform = raw.get("platform") or PLATFORMS[index % len(PLATFORMS)]
    if platform not in PLATFORMS:
        for p in PLATFORMS:
            if p.lower() in str(platform).lower():
                platform = p
                break
        else:
            platform = PLATFORMS[0]

    job_id = raw.get("id") or f"ai-{uuid.uuid4().hex[:8]}"
    score = raw.get("match_score", 70)
    try:
        score = int(score)
    except (TypeError, ValueError):
        score = 70
    score = max(0, min(100, score))

    location = raw.get("location") or "India"
    company = raw.get("company") or "Various employers"
    if company.lower() not in ("various employers", "multiple employers", "various companies"):
        fake_markers = ("labs", "corp", "pvt", "tech", "solutions", "hub", "dynamics", "hireco", "partner")
        if any(m in company.lower() for m in fake_markers) and len(company.split()) <= 3:
            company = "Various employers"

    listing_type = raw.get("listing_type") or "platform_search"
    direct_url = (raw.get("apply_url") or raw.get("url") or "").strip()

    if listing_type == "job" and direct_url.startswith("http"):
        title = clean_job_title(raw.get("title") or "Open Position")
        search_kw = clean_job_title(raw.get("search_keywords") or title)
        return {
            "id": str(job_id),
            "platform": platform,
            "title": title,
            "company": company if company != "Various employers" else raw.get("company", company),
            "location": location,
            "type": raw.get("type") or "Full-time",
            "description": raw.get("description") or f"{title} at {company} on {platform}.",
            "search_keywords": search_kw,
            "match_score": score,
            "match_reason": raw.get("match_reason") or "Live job posting from platform",
            "url": direct_url,
            "apply_url": direct_url,
            "listing_type": "job",
            "source": raw.get("source", "live"),
        }

    # Search-portal fallback only when live listings are unavailable.
    search_kw = clean_job_title(raw.get("search_keywords") or raw.get("title") or "Open Position")
    if user_role and user_role.strip() and not title_matches_role(search_kw, user_role):
        search_kw = clean_job_title(user_role)
    title = search_kw
    search_url = build_platform_search_url(platform, search_kw, location)

    return {
        "id": str(job_id),
        "platform": platform,
        "title": title,
        "company": company,
        "location": location,
        "type": raw.get("type") or "Full-time",
        "description": raw.get("description")
        or f"Opens a live {platform} search for \"{search_kw}\" in {location}. Pick a listing from the results to apply.",
        "search_keywords": search_kw,
        "match_score": score,
        "match_reason": raw.get("match_reason") or "Matched to your resume profile",
        "url": search_url,
        "apply_url": search_url,
        "listing_type": "platform_search",
        "source": raw.get("source", "llm"),
    }


def _search_jobs_with_llm(
    analysis: dict,
    user_role: Optional[str],
    platform: Optional[str],
) -> tuple[list[dict], Optional[str]]:
    profile = _build_profile_summary(analysis)
    role_query = (user_role or "").strip()
    if not role_query:
        roles = analysis.get("suggested_roles") or analysis.get("job_titles") or []
        role_query = roles[0] if roles else "roles from my resume"

    prompt = prompts.DYNAMIC_JOB_SEARCH_PROMPT.format(
        profile_summary=profile,
        user_role=role_query,
        platform_filter=platform or "",
    )

    result = generate_json(prompt, system=prompts.JOB_SEARCH_SYSTEM)
    if isinstance(result, list):
        jobs_raw = result
        interpretation = None
    elif isinstance(result, dict):
        jobs_raw = result.get("jobs") or result.get("results") or []
        interpretation = result.get("search_interpretation")
    else:
        jobs_raw = []
        interpretation = None

    jobs = [
        _normalize_job(j, i, analysis, user_role=role_query)
        for i, j in enumerate(jobs_raw)
        if isinstance(j, dict)
    ]
    jobs = align_jobs_to_role(jobs, role_query, analysis, platform)
    return jobs, interpretation


def _enrich_and_rank_jobs(
    jobs: list[dict],
    analysis: dict,
    user_role: Optional[str],
) -> list[dict]:
    """Blend LLM scores with resume-based scoring; keep every job."""
    enriched = []
    for job in jobs:
        computed = compute_job_match(job, analysis, user_role=user_role)
        llm_score = job.get("match_score", 0)
        blended = int(round(llm_score * 0.55 + computed["match_score"] * 0.45))
        blended = max(40, min(100, blended))
        reason = job.get("match_reason") or computed["match_reason"]
        if computed["match_reason"] and computed["match_reason"] not in reason:
            reason = f"{reason}. {computed['match_reason']}"
        enriched.append({
            **job,
            "match_score": blended,
            "match_reason": reason,
        })
    enriched.sort(key=lambda x: x["match_score"], reverse=True)
    return enriched


def _search_jobs_fallback(
    analysis: dict,
    user_role: Optional[str],
    platform: Optional[str],
) -> list[dict]:
    """Expanded fallback — many roles from resume skills."""
    role_title = (user_role or "").strip()
    suggested = analysis.get("suggested_roles") or []
    if not role_title:
        role_title = suggested[0] if suggested else "Professional"

    titles = list(dict.fromkeys([role_title] + suggested[:4]))
    skills = analysis.get("skills", [])[:8]
    exp = (analysis.get("experience") or {}).get("formatted", "")
    skill_str = ", ".join(skills[:6]) if skills else "relevant skills"

    catalog: list[dict] = []
    platforms_cycle = PLATFORMS
    idx = 0
    for title in titles:
        variants = [title]
        if "junior" not in title.lower():
            variants.append(f"Junior {title}")
        if "senior" not in title.lower():
            variants.append(f"Senior {title}")
        for variant, loc, jtype in [
            (variants[0], "Bangalore", "Full-time"),
            (variants[1] if len(variants) > 1 else title, "Remote", "Full-time"),
            (variants[2] if len(variants) > 2 else title, "Hyderabad", "Full-time"),
        ]:
            plat = platforms_cycle[idx % len(platforms_cycle)]
            catalog.append({
                "id": f"fb-{idx:03d}",
                "platform": plat,
                "title": variant,
                "company": "Various employers",
                "location": loc,
                "type": jtype,
                "description": f"Find {variant} roles matching your skills ({skill_str}). Typical requirements align with {exp} work experience.",
                "search_keywords": variant,
            })
            idx += 1

    for i, skill in enumerate(skills[:6]):
        plat = platforms_cycle[idx % len(platforms_cycle)]
        catalog.append({
            "id": f"fb-s{i}",
            "platform": plat,
            "title": f"{role_title}",
            "company": "Various employers",
            "location": "Pune" if i % 2 else "Remote",
            "type": "Full-time",
            "description": f"Search for {role_title} positions requiring {skill}. Fits profile with {exp} experience.",
            "search_keywords": role_title,
        })
        idx += 1

    results = []
    for i, job in enumerate(catalog):
        if platform and job["platform"].lower() != platform.lower():
            continue
        normalized = _normalize_job(
            {**job, "source": "fallback"},
            i,
            analysis,
            user_role=role_title,
        )
        match = compute_job_match(normalized, analysis, user_role=user_role)
        results.append({**normalized, **match})
    results.sort(key=lambda x: x["match_score"], reverse=True)
    return align_jobs_to_role(results, role_title, analysis, platform)


def suggest_role(db: Session, user: User, user_role: str = "") -> dict:
    analysis = _load_analysis(db, user)
    if not analysis:
        raise ValueError("Upload and analyze resume first")

    exp_fmt = (analysis.get("experience") or {}).get(
        "formatted", f"{analysis.get('experience_years', 0)} years"
    )

    prompt = prompts.ROLE_SUGGESTION_PROMPT.format(
        analysis_json=json.dumps(analysis, default=str),
        user_role=user_role or "",
    )
    try:
        result = generate_json(prompt)
        if isinstance(result, dict):
            result.setdefault("experience_summary", exp_fmt)
            result.setdefault("filtered_by_user", bool(user_role.strip()))
            return result
    except GeminiQuotaError:
        pass
    except Exception:
        pass

    suggested = analysis.get("suggested_roles", ["Professional"])
    primary = user_role.strip() if user_role.strip() else suggested[0]
    return {
        "primary_role": primary,
        "alternative_roles": suggested[1:4],
        "reasoning": (
            f"Based on {exp_fmt} and skills ({', '.join(analysis.get('skills', [])[:6])}). "
            + (f"Searching for: {user_role}." if user_role.strip() else "Inferred from resume.")
        ),
        "filtered_by_user": bool(user_role.strip()),
        "experience_summary": exp_fmt,
        "_fallback": True,
    }


def _fallback_search_response(
    analysis: dict,
    role: Optional[str],
    platform: Optional[str],
    reason: str,
) -> dict[str, Any]:
    jobs = _search_jobs_fallback(analysis, role, platform)
    return {
        "jobs": jobs,
        "total": len(jobs),
        "search_interpretation": reason,
        "disclaimer": (
            "Each card is a live job-board search (not a single posting). "
            "The link uses the exact role and location shown on the card. "
            "Apply on the platform first, then use \"I've applied\" to track it here."
        ),
        "source": "fallback",
    }


def _live_jobs_response(
    jobs: list[dict],
    role: Optional[str],
    analysis: dict,
    raw_text: str = "",
    platform_key: Optional[str] = None,
) -> dict[str, Any]:
    ctx = build_job_search_context(analysis, role or "", raw_text)
    role_label = ctx["search_role"]
    locs = ctx["locations"]
    enriched = _enrich_and_rank_jobs(jobs, analysis, role_label)
    exp_fmt = (analysis.get("experience") or {}).get("formatted", "")
    loc_note = ", ".join(locs[:5])
    if len(locs) > 5:
        loc_note += f" (+{len(locs) - 5} more)"
    platform_note = f" Platform: {platform_key}." if platform_key else " Platforms: all (LinkedIn, Naukri, Indeed, Internshala, Other websites)."
    interpretation = (
        f"Found {len(enriched)} real job postings for \"{role_label}\" "
        f"in {loc_note}, filtered by your skills and experience.{platform_note}"
    )
    if exp_fmt:
        interpretation += f" Experience: {exp_fmt}."
    return {
        "jobs": enriched,
        "total": len(enriched),
        "search_interpretation": interpretation,
        "search_role": role_label,
        "search_locations": locs,
        "disclaimer": (
            "Each card opens that exact job on the platform (same title and company). "
            "Use the platform filter for LinkedIn, Naukri, Indeed, Internshala, or Other websites "
            "(Google Jobs, Jooble, Glassdoor, company career pages). "
            "Locations are based on cities and remote work mentioned in your resume."
        ),
        "source": "live",
    }


def search_jobs(
    db: Session,
    user: User,
    role: Optional[str] = None,
    platform: Optional[str] = None,
) -> dict[str, Any]:
    analysis, raw_text = _load_resume_bundle(db, user)
    if not analysis:
        return {"jobs": [], "search_interpretation": None, "source": "none"}

    platform_key = _normalize_platform_filter(platform)

    if _USE_LIVE_JOB_FETCH:
        live_jobs = fetch_live_job_listings(
            role or "",
            analysis,
            platform_key,
            raw_text=raw_text,
        )
        if live_jobs:
            return _live_jobs_response(live_jobs, role, analysis, raw_text, platform_key)

        locs = extract_locations_from_analysis(analysis, raw_text)
        return {
            "jobs": [],
            "total": 0,
            "search_interpretation": (
                f"No live postings matched your role in {', '.join(locs[:4])} right now. "
                "Try a broader role title or check again in a few minutes."
            ),
            "disclaimer": (
                "Only real job postings are shown (no search pages). "
                "Ensure the backend can reach LinkedIn/Naukri from your network."
            ),
            "source": "live_empty",
        }

    if not _USE_LLM_JOB_SEARCH:
        if _ALLOW_SEARCH_LINK_FALLBACK:
            return _fallback_search_response(
                analysis,
                role,
                platform,
                "Live fetch disabled. Showing search links from your resume.",
            )
        return {
            "jobs": [],
            "total": 0,
            "search_interpretation": "Enable USE_LIVE_JOB_FETCH=true in backend/.env.",
            "source": "none",
        }

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(_search_jobs_with_llm, analysis, role, platform)
    try:
        jobs, interpretation = future.result(timeout=_LLM_SEARCH_TIMEOUT)

        if platform:
            jobs = [j for j in jobs if j["platform"].lower() == platform.lower()] or jobs
        jobs = _enrich_and_rank_jobs(jobs, analysis, role)
        exp_fmt = (analysis.get("experience") or {}).get("formatted", "")
        if interpretation and exp_fmt:
            interpretation = f"{interpretation} (Your work experience: {exp_fmt})"
        elif exp_fmt:
            interpretation = f"Matched to your resume. Work experience: {exp_fmt}."
        if jobs:
            return {
                "jobs": jobs,
                "total": len(jobs),
                "search_interpretation": interpretation,
                "disclaimer": (
                    "Each card opens a live search on that platform using the exact role and location on the card. "
                    "Pick a listing from the results and apply there. Only confirm in Applications after you submit on the site."
                ),
                "source": "llm",
            }
    except FuturesTimeoutError:
        return _fallback_search_response(
            analysis,
            role,
            platform,
            f"AI search took longer than {_LLM_SEARCH_TIMEOUT}s. Showing fast resume-based search links instead.",
        )
    except GeminiQuotaError:
        return _fallback_search_response(
            analysis,
            role,
            platform,
            "AI job search unavailable (API quota). Showing resume-based search links. "
            "Enable Gemini billing for full dynamic search.",
        )
    except Exception as e:
        return _fallback_search_response(
            analysis,
            role,
            platform,
            f"Resume-based search recommendations. ({e})",
        )
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    return _fallback_search_response(
        analysis,
        role,
        platform,
        "No AI listings returned. Showing resume-based search links for your role.",
    )


def _normalize_platform_filter(platform: Optional[str]) -> Optional[str]:
    if not platform or platform.strip().lower() in ("", "all", "all platforms"):
        return None
    p = platform.strip()
    if p == "Other websites":
        return "Other websites"
    for known in PLATFORMS:
        if known.lower() == p.lower():
            return known
    return None


def get_platforms() -> list[str]:
    return PLATFORM_FILTER_OPTIONS

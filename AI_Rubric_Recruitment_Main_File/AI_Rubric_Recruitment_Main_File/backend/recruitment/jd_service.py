import json
import re
from typing import Any

from sqlalchemy.orm import Session

from database import JobPosting, User
from gemini_client import GeminiError, generate_json
from prompt import GENERATE_JD_PROMPT

_SKILL_SPLIT = re.compile(r",|\band\b|/|\||;|\+", re.IGNORECASE)
_SKILL_NOISE = {
    "years", "year", "experience", "exp", "with", "using", "knowledge",
    "skills", "skill", "required", "must", "have", "the", "a", "an",
    "in", "of", "for", "to", "or", "etc", "plus", "minimum", "at", "least",
}


def _normalize_skill(s: str) -> str:
    s = s.strip().strip(".")
    if not s or len(s) < 2:
        return ""
    if s.lower() in _SKILL_NOISE:
        return ""
    return s[0].upper() + s[1:] if len(s) > 1 else s.upper()


def _extract_skills_from_text(text: str) -> list[str]:
    """Pull skill-like tokens from natural language input."""
    found: list[str] = []
    seen: set[str] = set()

    # Phrases after "skills:", "tech stack:", "technologies:"
    for match in re.finditer(
        r"(?:skills?|technologies|tech stack|stack|expertise in|proficient in|knowledge of)"
        r"\s*[:\-]?\s*([^.;\n]+)",
        text,
        re.IGNORECASE,
    ):
        chunk = match.group(1)
        for part in _SKILL_SPLIT.split(chunk):
            skill = _normalize_skill(part)
            key = skill.lower()
            if skill and key not in seen:
                seen.add(key)
                found.append(skill)

    # Known tech tokens in full text (camelCase, dotted, hash-suffixed)
    for match in re.finditer(
        r"\b([A-Z][a-zA-Z0-9+#.]*(?:\.[a-z]+)?|\b(?:Python|Java|JavaScript|TypeScript|React|Node|AWS|Azure|GCP|Docker|Kubernetes|SQL|MongoDB|PostgreSQL|FastAPI|Django|Flask|Spring|Angular|Vue|Git|Linux|HTML|CSS|C\+\+|C#|Go|Rust|Ruby|PHP|Swift|Kotlin)\b)",
        text,
    ):
        skill = _normalize_skill(match.group(1))
        key = skill.lower()
        if skill and key not in seen and key not in _SKILL_NOISE:
            seen.add(key)
            found.append(skill)

    return found


def _merge_skills_into_jd(jd: dict[str, Any], natural_language: str) -> dict[str, Any]:
    """Ensure every skill from recruiter input appears in the generated JD."""
    extracted = _extract_skills_from_text(natural_language)
    if not extracted:
        return jd

    required = list(jd.get("required_skills") or [])
    preferred = list(jd.get("preferred_skills") or [])
    existing = {s.lower() for s in required + preferred}

    for skill in extracted:
        if skill.lower() not in existing:
            required.append(skill)
            existing.add(skill.lower())

    jd["required_skills"] = required
    jd["preferred_skills"] = preferred
    return jd


def generate_jd_from_natural_language(natural_language: str) -> dict[str, Any]:
    prompt = GENERATE_JD_PROMPT.format(user_input=natural_language)
    try:
        jd = generate_json(prompt)
        if isinstance(jd, dict):
            return _merge_skills_into_jd(jd, natural_language)
        return _merge_skills_into_jd(_fallback_jd(natural_language), natural_language)
    except GeminiError:
        return _merge_skills_into_jd(_fallback_jd(natural_language), natural_language)


def _fallback_jd(text: str) -> dict[str, Any]:
    words = text.split()
    title = " ".join(words[:4]).title() if words else "Software Engineer"
    extracted = _extract_skills_from_text(text)
    required = extracted if extracted else ["Communication", "Problem solving", "Teamwork"]
    return {
        "title": title,
        "company": "Our Company",
        "location": "Remote",
        "employment_type": "Full-time",
        "experience_level": "2-5 years",
        "salary_range": "",
        "summary": text[:300] if text else "We are hiring for an exciting role.",
        "responsibilities": [
            "Design and develop high-quality solutions",
            "Collaborate with cross-functional teams",
            "Participate in code reviews and mentoring",
            "Deliver features on schedule",
        ],
        "required_skills": required,
        "preferred_skills": ["Leadership", "Agile methodologies"],
        "qualifications": ["Bachelor's degree in relevant field or equivalent experience"],
        "benefits": ["Health insurance", "Flexible hours", "Remote work options"],
        "about_company": "We are a growing company committed to innovation.",
    }


def create_job_posting(
    db: Session, recruiter: User, natural_language: str, jd: dict[str, Any]
) -> JobPosting:
    posting = JobPosting(
        recruiter_id=recruiter.id,
        title=jd.get("title", "Untitled Role"),
        jd_json=json.dumps(jd),
        natural_language_input=natural_language,
        status="draft",
    )
    db.add(posting)
    db.commit()
    db.refresh(posting)
    return posting


def update_job_posting(db: Session, posting: JobPosting, jd: dict[str, Any]) -> JobPosting:
    posting.title = jd.get("title", posting.title)
    posting.jd_json = json.dumps(jd)
    db.commit()
    db.refresh(posting)
    return posting


def jd_to_text(jd: dict[str, Any]) -> str:
    lines = [
        jd.get("title", "Job Title"),
        "=" * len(jd.get("title", "Job Title")),
        "",
        f"Company: {jd.get('company', 'N/A')}",
        f"Location: {jd.get('location', 'N/A')}",
        f"Employment Type: {jd.get('employment_type', 'N/A')}",
        f"Experience: {jd.get('experience_level', 'N/A')}",
    ]
    salary = (jd.get("salary_range") or "").strip()
    if salary:
        lines.append(f"Salary: {salary}")
    lines += [
        "",
        "SUMMARY",
        "-" * 7,
        jd.get("summary", ""),
        "",
        "RESPONSIBILITIES",
        "-" * 16,
    ]
    for item in jd.get("responsibilities", []):
        lines.append(f"  • {item}")

    lines += ["", "REQUIRED SKILLS", "-" * 15]
    for item in jd.get("required_skills", []):
        lines.append(f"  • {item}")

    if jd.get("preferred_skills"):
        lines += ["", "PREFERRED SKILLS", "-" * 17]
        for item in jd.get("preferred_skills", []):
            lines.append(f"  • {item}")

    lines += ["", "QUALIFICATIONS", "-" * 14]
    for item in jd.get("qualifications", []):
        lines.append(f"  • {item}")

    if jd.get("benefits"):
        lines += ["", "BENEFITS", "-" * 8]
        for item in jd.get("benefits", []):
            lines.append(f"  • {item}")

    if jd.get("about_company"):
        lines += ["", "ABOUT THE COMPANY", "-" * 18, jd.get("about_company", "")]

    return "\n".join(lines)

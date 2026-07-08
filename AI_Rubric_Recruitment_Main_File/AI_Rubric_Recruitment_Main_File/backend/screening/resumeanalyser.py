import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

from sentence_transformers import SentenceTransformer
from models import (
    JobRole,
    CandidateEvaluation,
    ATSBreakdown,
    TopCandidatesResult,
    TopCandidateEntry,
    RubricWeights,
    DEFAULT_RUBRIC_WEIGHTS,
)
from ats_engine import build_jd_text, run_ats_pipeline, get_jd_profile

logger = logging.getLogger(__name__)

_ON_RAILWAY = bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_SERVICE_NAME"))
PARALLEL_WORKERS = int(os.getenv("SCREENING_WORKERS", "1" if _ON_RAILWAY else "12"))
BATCH_ENCODE_SIZE = int(os.getenv("SCREENING_ENCODE_BATCH", "4" if _ON_RAILWAY else "64"))

try:
    logger.info("Loading SentenceTransformer model 'all-MiniLM-L6-v2'...")
    embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
except Exception as e:
    logger.error(f"Failed to load embedding model: {e}")
    embedding_model = None

_jd_embedding_cache: Dict[str, object] = {}


def _jd_key(job_role: JobRole) -> str:
    return f"{job_role.job_role or ''}|{(job_role.responsibilities or '')[:500]}"


def _encode_jd_once(job_role: JobRole):
    key = _jd_key(job_role)
    if key not in _jd_embedding_cache and embedding_model:
        jd_text = build_jd_text(job_role)[:3000]
        if jd_text.strip():
            _jd_embedding_cache[key] = embedding_model.encode(
                jd_text,
                show_progress_bar=False,
                normalize_embeddings=True,
            )
    return _jd_embedding_cache.get(key)


def _compute_similarity(resume_content: str, job_role: JobRole) -> float:
    jd_emb = _encode_jd_once(job_role)
    if jd_emb is None or not embedding_model:
        return 0.5
    jd_text = build_jd_text(job_role)
    if not jd_text.strip():
        return 0.5
    res_emb = embedding_model.encode(
        resume_content[:3000],
        show_progress_bar=False,
        normalize_embeddings=True,
    )
    return float(max(0.0, min(1.0, res_emb @ jd_emb)))


def compute_similarities_batch(contents: List[str], job_role: JobRole) -> List[float]:
    """Encode many resumes against one cached JD embedding in a single model call."""
    jd_emb = _encode_jd_once(job_role)
    if jd_emb is None or not embedding_model or not contents:
        return [0.5] * len(contents)

    texts = [c[:3000] for c in contents]
    try:
        res_embs = embedding_model.encode(
            texts,
            show_progress_bar=False,
            normalize_embeddings=True,
            batch_size=BATCH_ENCODE_SIZE,
        )
        scores = res_embs @ jd_emb
        return [float(max(0.0, min(1.0, s))) for s in scores]
    except Exception as e:
        logger.warning(f"Batch encode failed, falling back to single encode: {e}")
        return [_compute_similarity(c, job_role) for c in contents]


def _recommendation_from_score(score: int) -> str:
    if score >= 85:
        return "Highly Recommended"
    if score >= 70:
        return "Recommended"
    if score >= 50:
        return "Borderline"
    return "Not Recommended"


def _build_evaluation(
    resume_name: str,
    resume_content: str,
    job_role: JobRole,
    result: dict,
    profile,
) -> CandidateEvaluation:
    rubric = result["rubric"]
    total_score = result["total_score"]

    strengths = []
    if result["matched_skills"]:
        strengths.append(
            f"Skills matched ({len(result['matched_skills'])}/{len(profile.skills)}): "
            f"{', '.join(result['matched_skills'][:8])}."
        )
    if result["matched_responsibilities"]:
        strengths.append(
            f"JD responsibilities met ({len(result['matched_responsibilities'])}): "
            f"{result['matched_responsibilities'][0][:80]}..."
        )
    if result["matched_education"]:
        strengths.append(f"Education matched: {', '.join(result['matched_education'])}.")
    if result["semantic_score"] >= 70:
        strengths.append(f"Strong overall JD alignment ({result['semantic_score']}%).")
    if not strengths:
        strengths.append("Review rubric breakdown for partial alignment details.")

    improvements = []
    if result["missing_skills"]:
        improvements.append(f"Missing JD skills: {', '.join(result['missing_skills'][:10])}.")
    if result.get("partial_skills"):
        improvements.append(f"Partial skill matches: {', '.join(result['partial_skills'][:8])}.")
    if result["missing_responsibilities"]:
        improvements.append(
            f"Missing JD responsibilities: {result['missing_responsibilities'][0][:80]}..."
        )
    if result["missing_education"]:
        improvements.append(f"Missing education: {', '.join(result['missing_education'])}.")
    if result["experience_score"] < 70:
        improvements.append("Experience below JD requirement.")
    if not improvements:
        improvements.append("Minor gaps — see rubric dimension details.")

    summary = (
        f"Rubric {total_score}/100 | "
        f"Skills {result['skill_score']}% | "
        f"Responsibilities {result.get('responsibility_score', 0)}% | "
        f"Semantic {result['semantic_score']}%"
        + (f" | Domain: {result.get('resume_domain')} vs {result.get('jd_domain')}" if result.get("jd_domain") else "")
    )

    return CandidateEvaluation(
        resume_id="local_file",
        candidate_name=resume_name,
        job_title=job_role.job_role,
        dimension_scores=rubric,
        total_score=total_score,
        ats_breakdown=ATSBreakdown(
            skill_score=result["skill_score"],
            semantic_score=result["semantic_score"],
            experience_score=result["experience_score"],
            education_score=result["education_score"],
            ats_score=result["ats_score"],
            jd_skills=result["jd_skills"],
            resume_skills=result["resume_skills"],
            matched_skills=result["matched_skills"],
            missing_skills=result["missing_skills"],
            partial_skills=result.get("partial_skills", []),
            skill_details=result.get("skill_details", []),
            extra_skills=result.get("extra_skills", []),
            jd_responsibilities=result.get("jd_responsibilities", []),
            matched_responsibilities=result.get("matched_responsibilities", []),
            missing_responsibilities=result.get("missing_responsibilities", []),
            matched_education=result.get("matched_education", []),
            missing_education=result.get("missing_education", []),
            responsibility_score=result.get("responsibility_score", 0),
            resume_domain=result.get("resume_domain"),
            jd_domain=result.get("jd_domain"),
            domain_penalty=result.get("domain_penalty", 0.0),
            scoring_trace=result.get("scoring_trace", []),
            tech_experience_notes=result.get("tech_experience_notes", []),
        ),
        overall_summary=summary,
        strengths=strengths,
        areas_for_improvement=improvements,
        recommendation=_recommendation_from_score(total_score),
    )


def analyse_candidate_with_rubric(
    resume_name: str,
    resume_content: str,
    job_role: JobRole,
    weights: RubricWeights = DEFAULT_RUBRIC_WEIGHTS,
    similarity: Optional[float] = None,
) -> CandidateEvaluation:
    """Full JD → Resume rubric pipeline (regex/fuzzy matching; one semantic score only)."""
    profile = get_jd_profile(job_role)
    if similarity is None:
        similarity = _compute_similarity(resume_content, job_role)
    result = run_ats_pipeline(resume_content, job_role, similarity, embedding_model, weights)
    return _build_evaluation(resume_name, resume_content, job_role, result, profile)


def analyse_resumes_parallel(
    candidates: List[dict],
    job_role: JobRole,
    weights: RubricWeights = DEFAULT_RUBRIC_WEIGHTS,
) -> List[CandidateEvaluation]:
    """Score many resumes in parallel with batched semantic encoding."""
    return list(analyse_resumes_stream(candidates, job_role, weights))


def analyse_resumes_stream(
    candidates: List[dict],
    job_role: JobRole,
    weights: RubricWeights = DEFAULT_RUBRIC_WEIGHTS,
):
    """Yield scored evaluations as each resume finishes (fastest time-to-first-result)."""
    if not candidates:
        return

    profile = get_jd_profile(job_role)
    _encode_jd_once(job_role)

    if _ON_RAILWAY and PARALLEL_WORKERS <= 1:
        for candidate in candidates:
            try:
                sim = _compute_similarity(candidate["content"], job_role)
                result = run_ats_pipeline(
                    candidate["content"], job_role, sim, embedding_model, weights
                )
                yield _build_evaluation(
                    candidate["name"], candidate["content"], job_role, result, profile
                )
            except Exception as e:
                logger.error(f"Sequential analysis failed for {candidate.get('name')}: {e}")
                raise
        return

    contents = [c["content"] for c in candidates]
    similarities: List[float] = []
    for i in range(0, len(contents), BATCH_ENCODE_SIZE):
        similarities.extend(compute_similarities_batch(contents[i : i + BATCH_ENCODE_SIZE], job_role))

    def _score_one(item: tuple) -> CandidateEvaluation:
        candidate, sim = item
        result = run_ats_pipeline(candidate["content"], job_role, sim, embedding_model, weights)
        return _build_evaluation(candidate["name"], candidate["content"], job_role, result, profile)

    work_items = list(zip(candidates, similarities))

    errors: List[str] = []
    yielded = 0
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
        futures = [executor.submit(_score_one, item) for item in work_items]
        for fut in as_completed(futures):
            try:
                yield fut.result()
                yielded += 1
            except Exception as e:
                logger.error(f"Parallel analysis failed: {e}")
                errors.append(str(e))

    if yielded == 0 and candidates:
        detail = errors[0] if errors else "unknown scoring error"
        raise RuntimeError(f"All {len(candidates)} resume(s) in batch failed to score: {detail}")


def bulk_analyse_uploaded_resumes(candidates: List[dict], job_role: JobRole):
    get_jd_profile(job_role)
    batch_size = 50
    total_candidates = len(candidates)
    logger.info(
        f"--- Rubric Processing {total_candidates} resumes "
        f"(JD: {len(get_jd_profile(job_role).skills)} skills, "
        f"{len(get_jd_profile(job_role).responsibilities)} responsibilities) ---"
    )

    for i in range(0, total_candidates, batch_size):
        batch = candidates[i : i + batch_size]
        batch_evals = analyse_resumes_parallel(batch, job_role)
        if batch_evals:
            sorted_evals = sorted(batch_evals, key=lambda x: x.total_score, reverse=True)
            yield sorted_evals[:5]


def select_top_candidates(
    job_role: JobRole, evaluations: List[CandidateEvaluation], top_n: int = 5
) -> TopCandidatesResult:
    sorted_evals = sorted(evaluations, key=lambda e: e.total_score, reverse=True)
    top_n_evals = sorted_evals[:top_n]
    top_candidates = [
        TopCandidateEntry(
            rank=i + 1,
            candidate_name=ev.candidate_name,
            total_score=ev.total_score,
            reason=f"Rubric {ev.total_score}/100 — ranked by JD skill + responsibility + experience match.",
        )
        for i, ev in enumerate(top_n_evals)
    ]
    return TopCandidatesResult(job_title=job_role.job_role, top_candidates=top_candidates)


def bulk_analyse_candidates(candidates, job_role):
    for c in candidates:
        text = f"{c.summary} {c.technical_skills} {c.work_experience} {c.project} {c.education}"
        yield [analyse_candidate_with_rubric(c.name, text, job_role)]

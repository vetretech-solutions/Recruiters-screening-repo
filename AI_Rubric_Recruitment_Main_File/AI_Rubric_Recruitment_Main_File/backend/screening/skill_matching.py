"""
Enhanced skill matching: evidence, confidence, section weights, mandatory-skill rules,
category-specific embedding thresholds, and weighted skill scoring.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

# Imported from ats_engine — shared primitives only (no circular import at module load).
from ats_engine import (
    SKILL_CANONICAL,
    SKILL_REGEX,
    STOPWORDS,
    TECH_REGEX,
    _fuzzy_score,
    canonicalize_skill,
    display_skill,
    normalize_text,
    sort_alpha,
)

FUZZY_SKILL_THRESHOLD = 78
FUZZY_HIGH_CONFIDENCE = 88
MANDATORY_FUZZY_MIN = 85
SEMANTIC_PARTIAL_CREDIT = 0.45

MANDATORY_TECH_CANON: Set[str] = {
    ".net", "c#", "asp.net", "angular", "react", "sql", "aws", "azure",
    "gcp", "docker", "kubernetes", "devops",
}

SKILL_CATEGORY_MAP: Dict[str, str] = {}
for _cat, _skills in {
    "language": {".net", "c#", "python", "java", "javascript", "typescript", "c++"},
    "framework": {"react", "angular", "vue.js", "django", "flask", "fastapi", "spring boot", ".net"},
    "cloud": {"aws", "azure", "gcp"},
    "devops": {"docker", "kubernetes", "devops", "ci/cd"},
    "database": {"sql", "mysql", "postgresql", "mongodb", "oracle"},
    "soft": {
        "communication", "leadership", "agile", "scrum", "collaboration",
        "teamwork", "problem solving", "analytical",
    },
}.items():
    for s in _skills:
        SKILL_CATEGORY_MAP[s] = _cat

EMBED_THRESHOLDS = {
    "language": 0.72,
    "framework": 0.68,
    "cloud": 0.70,
    "devops": 0.68,
    "database": 0.70,
    "soft": 0.52,
    "default": 0.60,
}

PRIORITY_WEIGHT = {"high": 1.5, "medium": 1.0, "low": 0.6}

HIGH_PRIORITY_CANON: Set[str] = {
    ".net", "c#", "python", "java", "javascript", "react", "angular", "sql",
    "aws", "azure", "gcp", "docker", "kubernetes", "devops", "node.js",
}
LOW_PRIORITY_CANON: Set[str] = {
    "communication", "excel", "agile", "scrum", "leadership", "teamwork",
    "problem solving", "analytical",
}

SECTION_WEIGHTS = {
    "experience": 1.0,
    "projects": 0.95,
    "summary": 0.75,
    "skills": 0.65,
    "certifications": 0.50,
    "education": 0.60,
    "other": 0.65,
}

DOMAIN_SIGNALS: Dict[str, List[str]] = {
    "Software Engineering": [
        "software engineer", "developer", "programming", ".net", "api", "backend",
        "frontend", "full stack", "microservices", "coding",
    ],
    "Technical Training": [
        "technical trainer", "trainer", "instructor", "training", "teaching",
        "facilitator", "corporate training", "learning and development",
    ],
    "Data & Analytics": [
        "data analyst", "data scientist", "business intelligence", "analytics",
        "tableau", "power bi", "etl", "data warehouse",
    ],
    "DevOps & Cloud": [
        "devops", "sre", "site reliability", "cloud engineer", "infrastructure",
        "kubernetes", "terraform", "ci/cd",
    ],
    "Management": [
        "project manager", "product manager", "team lead", "engineering manager",
        "scrum master", "delivery manager",
    ],
}

SECTION_HEADERS = [
    (r"(?:work\s+)?experience|employment|professional\s+experience", "experience"),
    (r"projects?|personal\s+projects?", "projects"),
    (r"(?:professional\s+)?summary|objective|profile", "summary"),
    (r"(?:technical\s+)?skills|technologies|tech\s+stack|competencies", "skills"),
    (r"certifications?|licenses?", "certifications"),
    (r"education|academic", "education"),
]


@dataclass
class SkillMatchDetail:
    skill_name: str
    status: str  # Matched | Partial | Missing
    match_type: str  # Exact | Alias | Fuzzy | Semantic | None
    confidence: float
    evidence: str = ""
    section: str = ""
    reason: str = ""
    priority: str = "medium"
    credit: float = 0.0


@dataclass
class ResumeSections:
    experience: str = ""
    projects: str = ""
    summary: str = ""
    skills: str = ""
    certifications: str = ""
    education: str = ""
    other: str = ""
    full_text: str = ""

    def as_dict(self) -> Dict[str, str]:
        return {
            "experience": self.experience,
            "projects": self.projects,
            "summary": self.summary,
            "skills": self.skills,
            "certifications": self.certifications,
            "education": self.education,
            "other": self.other,
        }


def get_skill_priority(skill: str) -> str:
    canon = canonicalize_skill(skill)
    if canon in LOW_PRIORITY_CANON or any(w in normalize_text(skill) for w in ("communication", "soft")):
        return "low"
    if canon in HIGH_PRIORITY_CANON or canon in MANDATORY_TECH_CANON:
        return "high"
    return "medium"


def get_skill_category(skill: str) -> str:
    canon = canonicalize_skill(skill)
    return SKILL_CATEGORY_MAP.get(canon, "default")


def is_mandatory_tech(skill: str) -> bool:
    canon = canonicalize_skill(skill)
    if canon in MANDATORY_TECH_CANON:
        return True
    norm = normalize_text(skill)
    return any(m in norm for m in ("asp.net", "asp net", "dotnet", "c sharp", "csharp"))


def parse_resume_sections(resume_text: str) -> ResumeSections:
    sections = ResumeSections(full_text=resume_text)
    if not resume_text.strip():
        return sections

    lines = resume_text.split("\n")
    current = "other"
    buckets: Dict[str, List[str]] = {k: [] for k in SECTION_WEIGHTS}

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        header_hit = False
        for pat, name in SECTION_HEADERS:
            if re.match(rf"^{pat}\s*[:\-]?\s*$", stripped, re.I) or re.match(
                rf"^{pat}\s*[:\-]", stripped, re.I
            ):
                current = name
                header_hit = True
                rest = re.sub(rf"^{pat}\s*[:\-]\s*", "", stripped, flags=re.I).strip()
                if rest:
                    buckets[current].append(rest)
                break
        if not header_hit:
            buckets[current].append(stripped)

    for key, lines_list in buckets.items():
        text = "\n".join(lines_list).strip()
        setattr(sections, key, text)

    if not sections.experience and not sections.skills:
        sections.other = resume_text
    return sections


def _split_sentences(text: str) -> List[str]:
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip() for p in parts if len(p.strip()) >= 12]


def _skill_regex_match(canon: str, text: str) -> bool:
    pattern = SKILL_REGEX.get(canon)
    if pattern and pattern.search(text):
        return True
    aliases = SKILL_CANONICAL.get(canon, [canon])
    for alias in aliases:
        escaped = re.escape(alias).replace(r"\ ", r"\s+")
        if re.search(rf"\b{escaped}\b", text, re.I):
            return True
    return False


def _find_evidence(
    skill: str,
    canon: str,
    sections: ResumeSections,
) -> Tuple[str, str, float]:
    """Return (evidence_sentence, section_name, section_weight)."""
    search_order = [
        ("experience", sections.experience),
        ("projects", sections.projects),
        ("summary", sections.summary),
        ("skills", sections.skills),
        ("certifications", sections.certifications),
        ("education", sections.education),
        ("other", sections.other or sections.full_text),
    ]
    item_norm = normalize_text(skill)
    for sec_name, sec_text in search_order:
        if not sec_text:
            continue
        weight = SECTION_WEIGHTS.get(sec_name, 0.65)
        for sent in _split_sentences(sec_text):
            if _skill_regex_match(canon, sent):
                return sent[:220], sec_name, weight
            if item_norm and len(item_norm) >= 3 and item_norm in normalize_text(sent):
                return sent[:220], sec_name, weight
            for alias in SKILL_CANONICAL.get(canon, [canon]):
                if alias in normalize_text(sent):
                    return sent[:220], sec_name, weight
        if _skill_regex_match(canon, sec_text):
            first = _split_sentences(sec_text)
            return (first[0][:220] if first else sec_text[:220]), sec_name, weight
    return "", "", SECTION_WEIGHTS["other"]


_CORPUS_LIMIT = 35


def _encode_corpus(
    corpus: List[Tuple[str, str]],
    embedding_model: Any,
):
    """Encode resume sentence corpus once; reused for all skill/responsibility semantic checks."""
    if not embedding_model or not corpus:
        return None
    try:
        texts = [t[:200] for _, t in corpus[:_CORPUS_LIMIT]]
        return embedding_model.encode(
            texts, show_progress_bar=False, normalize_embeddings=True
        )
    except Exception:
        return None


def _semantic_best(
    skill: str,
    corpus: List[Tuple[str, str]],
    embedding_model: Any,
    threshold: float,
    corpus_embs: Any = None,
) -> Tuple[float, str, str]:
    if not embedding_model or not corpus:
        return 0.0, "", ""
    try:
        query = skill[:200]
        if corpus_embs is not None:
            q_emb = embedding_model.encode(
                [query], show_progress_bar=False, normalize_embeddings=True
            )[0]
            sims = corpus_embs @ q_emb
        else:
            texts = [query] + [t[:200] for _, t in corpus[:_CORPUS_LIMIT]]
            embs = embedding_model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
            sims = embs[1:] @ embs[0]
        best_i = int(sims.argmax())
        best_sim = float(sims[best_i])
        if best_sim >= threshold:
            sec, sent = corpus[best_i]
            return best_sim, sent[:220], sec
        return best_sim, "", ""
    except Exception:
        return 0.0, "", ""


def _batch_semantic_skills(
    skills: List[str],
    corpus: List[Tuple[str, str]],
    corpus_embs: Any,
    embedding_model: Any,
    thresholds: List[float],
) -> List[Tuple[float, str, str]]:
    """Encode all pending skill queries in one model call."""
    if not skills or corpus_embs is None or not embedding_model:
        return [(0.0, "", "")] * len(skills)
    try:
        queries = [s[:200] for s in skills]
        q_embs = embedding_model.encode(
            queries, show_progress_bar=False, normalize_embeddings=True, batch_size=32
        )
        results: List[Tuple[float, str, str]] = []
        for i, threshold in enumerate(thresholds):
            sims = corpus_embs @ q_embs[i]
            best_i = int(sims.argmax())
            best_sim = float(sims[best_i])
            if best_sim >= threshold:
                sec, sent = corpus[best_i]
                results.append((best_sim, sent[:220], sec))
            else:
                results.append((best_sim, "", ""))
        return results
    except Exception:
        return [(0.0, "", "")] * len(skills)


def _build_embed_corpus(sections: ResumeSections) -> List[Tuple[str, str]]:
    corpus: List[Tuple[str, str]] = []
    for sec_name, sec_text in sections.as_dict().items():
        for sent in _split_sentences(sec_text):
            corpus.append((sec_name, sent))
    return corpus


def _match_skill_non_semantic(
    skill: str,
    resume_text: str,
    resume_skills: List[str],
    resume_canon: Set[str],
    sections: ResumeSections,
) -> Tuple[Optional[SkillMatchDetail], float, str, str, float, int]:
    """Returns (detail or None, best_fuzzy, evidence, section, sec_weight, embed_threshold context)."""
    canon = canonicalize_skill(skill)
    priority = get_skill_priority(skill)
    mandatory = is_mandatory_tech(skill)
    category = get_skill_category(skill)
    embed_threshold = EMBED_THRESHOLDS.get(category, EMBED_THRESHOLDS["default"])
    display = display_skill(skill)

    evidence, section, sec_weight = _find_evidence(skill, canon, sections)

    if evidence and section in ("experience", "projects"):
        conf = min(100.0, 95 + sec_weight * 5)
        return SkillMatchDetail(
            skill_name=display, status="Matched", match_type="Exact",
            confidence=round(conf, 1), evidence=evidence, section=section,
            reason=f"Exact/regex match in {section} section (weight {sec_weight:.2f}).",
            priority=priority, credit=round(sec_weight, 2),
        ), 0, evidence, section, sec_weight, embed_threshold

    if _skill_regex_match(canon, resume_text) or (canon and canon in resume_canon):
        if not evidence:
            evidence, section, sec_weight = _find_evidence(skill, canon, sections)
        conf = min(100.0, 88 + sec_weight * 10)
        return SkillMatchDetail(
            skill_name=display, status="Matched", match_type="Exact",
            confidence=round(conf, 1),
            evidence=evidence or f"Found in resume ({section or 'body'})",
            section=section or "other",
            reason="Canonical/regex match in resume text.",
            priority=priority, credit=round(max(0.85, sec_weight), 2),
        ), 0, evidence, section, sec_weight, embed_threshold

    item_norm = normalize_text(skill)
    resume_norm = normalize_text(resume_text)
    if item_norm and len(item_norm) >= 3 and re.search(rf"\b{re.escape(item_norm)}\b", resume_norm):
        if not evidence:
            evidence, section, sec_weight = _find_evidence(skill, canon, sections)
        return SkillMatchDetail(
            skill_name=display, status="Matched", match_type="Exact",
            confidence=round(90 + sec_weight * 8, 1),
            evidence=evidence or f"Literal token '{skill}' in resume",
            section=section or "other", reason="Exact token match in resume.",
            priority=priority, credit=round(max(0.85, sec_weight), 2),
        ), 0, evidence, section, sec_weight, embed_threshold

    for alias in SKILL_CANONICAL.get(canon, [canon]):
        if alias in resume_norm:
            if not evidence:
                evidence, section, sec_weight = _find_evidence(skill, canon, sections)
            return SkillMatchDetail(
                skill_name=display, status="Matched", match_type="Alias",
                confidence=round(88 + sec_weight * 8, 1),
                evidence=evidence or f"Alias '{alias}' found",
                section=section or "other",
                reason=f"Alias match via known synonym '{alias}'.",
                priority=priority, credit=round(max(0.80, sec_weight * 0.95), 2),
            ), 0, evidence, section, sec_weight, embed_threshold

    best_fuzzy = 0
    best_rs = ""
    for rs in resume_skills:
        rs_canon = canonicalize_skill(rs)
        if rs_canon == canon:
            if not evidence:
                evidence, section, sec_weight = _find_evidence(skill, canon, sections)
            return SkillMatchDetail(
                skill_name=display, status="Matched", match_type="Alias",
                confidence=95.0, evidence=evidence or f"Resume skill pool: {rs}",
                section=section or "skills",
                reason="Resume skill list contains canonical equivalent.",
                priority=priority, credit=round(max(0.80, sec_weight), 2),
            ), 0, evidence, section, sec_weight, embed_threshold
        score = _fuzzy_score(canon, rs)
        if score > best_fuzzy:
            best_fuzzy, best_rs = score, rs

    for alias in SKILL_CANONICAL.get(canon, [canon]):
        for rs in resume_skills:
            score = _fuzzy_score(alias, rs)
            if score > best_fuzzy:
                best_fuzzy, best_rs = score, rs

    fuzzy_min = MANDATORY_FUZZY_MIN if mandatory else FUZZY_SKILL_THRESHOLD
    if best_fuzzy >= fuzzy_min:
        if not evidence:
            evidence, section, sec_weight = _find_evidence(skill, canon, sections)
        high_conf = best_fuzzy >= FUZZY_HIGH_CONFIDENCE
        status = "Matched" if high_conf or not mandatory else "Partial"
        credit = round(sec_weight * (0.95 if high_conf else 0.75), 2)
        return SkillMatchDetail(
            skill_name=display, status=status, match_type="Fuzzy",
            confidence=float(best_fuzzy),
            evidence=evidence or f"Fuzzy match to resume skill '{best_rs}' ({best_fuzzy}%)",
            section=section or "skills",
            reason=(
                f"Fuzzy match score {best_fuzzy}% "
                f"({'high confidence' if high_conf else 'moderate — partial credit'})."
            ),
            priority=priority,
            credit=credit if status == "Matched" else round(credit * 0.7, 2),
        ), best_fuzzy, evidence, section, sec_weight, embed_threshold

    return None, best_fuzzy, evidence, section, sec_weight, embed_threshold


def _build_semantic_skill_detail(
    skill: str,
    sem_sim: float,
    sem_ev: str,
    sem_sec: str,
    best_fuzzy: int,
    embed_threshold: float,
) -> SkillMatchDetail:
    canon = canonicalize_skill(skill)
    priority = get_skill_priority(skill)
    mandatory = is_mandatory_tech(skill)
    category = get_skill_category(skill)
    display = display_skill(skill)
    sec_weight = SECTION_WEIGHTS.get(sem_sec, 0.55)

    if sem_sim >= embed_threshold:
        if mandatory:
            return SkillMatchDetail(
                skill_name=display, status="Partial", match_type="Semantic",
                confidence=round(sem_sim * 100, 1),
                evidence=sem_ev or "Semantic similarity only — no exact/alias/fuzzy proof",
                section=sem_sec or "other",
                reason=(
                    f"Mandatory tech skill '{display}' — semantic similarity {sem_sim:.2f} "
                    f"is insufficient alone; marked Partial (no full credit)."
                ),
                priority=priority, credit=0.0,
            )
        partial_credit = round(SEMANTIC_PARTIAL_CREDIT * sec_weight, 2)
        return SkillMatchDetail(
            skill_name=display, status="Partial", match_type="Semantic",
            confidence=round(sem_sim * 100, 1),
            evidence=sem_ev or "Semantic similarity to resume context",
            section=sem_sec or "other",
            reason=(
                f"Semantic match ({sem_sim:.2f} ≥ {embed_threshold} for {category}); "
                f"partial credit {partial_credit:.0%}."
            ),
            priority=priority, credit=partial_credit,
        )

    return SkillMatchDetail(
        skill_name=display, status="Missing", match_type="None",
        confidence=max(float(best_fuzzy), round(sem_sim * 100, 1)),
        evidence="", section="",
        reason=(
            f"No exact, alias, or high-confidence fuzzy match"
            + (f"; best fuzzy {best_fuzzy}%" if best_fuzzy else "")
            + (f"; semantic {sem_sim:.2f} below {embed_threshold}" if sem_sim else "")
            + "."
        ),
        priority=priority, credit=0.0,
    )


def match_skill_enhanced(
    skill: str,
    resume_text: str,
    resume_skills: List[str],
    resume_canon: Set[str],
    sections: ResumeSections,
    embed_corpus: List[Tuple[str, str]],
    embedding_model: Any = None,
    corpus_embs: Any = None,
) -> SkillMatchDetail:
    non_sem, best_fuzzy, _, _, _, embed_threshold = _match_skill_non_semantic(
        skill, resume_text, resume_skills, resume_canon, sections
    )
    if non_sem is not None:
        return non_sem

    sem_sim, sem_ev, sem_sec = _semantic_best(
        skill, embed_corpus, embedding_model, embed_threshold, corpus_embs
    )
    return _build_semantic_skill_detail(
        skill, sem_sim, sem_ev, sem_sec, best_fuzzy, embed_threshold
    )


def compute_weighted_skill_pct(details: List[SkillMatchDetail]) -> float:
    if not details:
        return 0.0
    total_w = sum(PRIORITY_WEIGHT.get(d.priority, 1.0) for d in details)
    earned = sum(d.credit * PRIORITY_WEIGHT.get(d.priority, 1.0) for d in details)
    return round(min(100.0, earned / total_w * 100), 1) if total_w else 0.0


def detect_domain(text: str) -> str:
    norm = normalize_text(text)
    scores: Dict[str, int] = {}
    for domain, signals in DOMAIN_SIGNALS.items():
        scores[domain] = sum(1 for s in signals if s in norm)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "General"


def compute_domain_penalty(resume_domain: str, jd_domain: str) -> Tuple[float, str]:
    if resume_domain == jd_domain or resume_domain == "General" or jd_domain == "General":
        return 0.0, f"Domain alignment: resume={resume_domain}, JD={jd_domain}."
    # Related domains (e.g. DevOps vs Software Engineering) — smaller penalty
    related = {
        frozenset({"Software Engineering", "DevOps & Cloud"}),
        frozenset({"Software Engineering", "Data & Analytics"}),
        frozenset({"Management", "Software Engineering"}),
    }
    pair = frozenset({resume_domain, jd_domain})
    if pair in related:
        return 4.0, (
            f"Related domains: resume '{resume_domain}' vs JD '{jd_domain}' "
            f"(minor penalty -4 ATS pts)."
        )
    return 8.0, (
        f"Domain mismatch: resume '{resume_domain}' vs JD '{jd_domain}' "
        f"(-8 ATS pts applied)."
    )


def extract_tech_experience_years(resume_text: str, tech_canon: str) -> float:
    """Years of experience with a specific technology when stated in resume."""
    if not tech_canon:
        return 0.0
    aliases = SKILL_CANONICAL.get(tech_canon, [tech_canon])
    alias_pat = "|".join(re.escape(a) for a in aliases[:6])
    patterns = [
        rf"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:experience\s+)?(?:with|in|using)\s+(?:{alias_pat})",
        rf"(?:{alias_pat}).{{0,40}}(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)",
        rf"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s+(?:{alias_pat})",
    ]
    best = 0.0
    for pat in patterns:
        for m in re.finditer(pat, resume_text, re.I):
            try:
                val = float(m.group(1))
                if 0 < val <= 45:
                    best = max(best, val)
            except ValueError:
                pass
    return best


def score_experience_with_tech(
    profile_experience_years: float,
    resume_text: str,
    sections: ResumeSections,
    jd_skills: List[str],
    scoring_trace: List[str],
) -> Tuple[float, List[str], List[str]]:
    """Enhance experience scoring with per-technology years when available."""
    from ats_engine import extract_years_experience, sort_alpha as _sort

    resume_years = extract_years_experience(resume_text)
    jd_years = profile_experience_years
    present, missing = [], []

    tech_notes: List[str] = []
    exp_context = f"{sections.experience}\n{sections.projects}"
    for skill in jd_skills[:12]:
        canon = canonicalize_skill(skill)
        if canon in MANDATORY_TECH_CANON or get_skill_priority(skill) == "high":
            ty = extract_tech_experience_years(exp_context or resume_text, canon)
            if ty > 0:
                tech_notes.append(f"{display_skill(skill)}: {ty:g} years stated")
                scoring_trace.append(
                    f"Experience rule: {display_skill(skill)} — {ty:g} years found in work/projects."
                )

    if tech_notes:
        present.extend(tech_notes)

    if jd_years <= 0:
        if resume_years > 0:
            present.append(f"{resume_years:g} years total experience")
            score = min(100.0, 70 + resume_years * 4)
            scoring_trace.append(f"Experience rule: total years {resume_years:g} → raw {score}%.")
            return score, _sort(present), missing
        if re.search(r"\b(?:experience|worked|employed|developer|engineer)\b", normalize_text(resume_text)):
            present.append("Relevant work experience described")
            scoring_trace.append("Experience rule: work history keywords → 80%.")
            return 80.0, _sort(present), ["Explicit experience years not stated"]
        scoring_trace.append("Experience rule: no years stated → 65%.")
        return 65.0, [], ["Experience years not stated in resume"]

    present.append(f"JD requires: {jd_years:g}+ years")
    if resume_years > 0:
        present.append(f"Resume shows: {resume_years:g} years total")
    else:
        missing.append(f"No explicit total years (JD needs {jd_years:g}+)")

    if resume_years >= jd_years:
        score = 100.0
    elif resume_years >= jd_years * 0.75:
        missing.append(f"~{jd_years - resume_years:g} year gap vs JD minimum")
        score = 70.0
    else:
        missing.append(f"{jd_years - resume_years:g} years below JD minimum")
        score = max(30.0, 50 + (resume_years / jd_years) * 40)

    # Boost/trim based on key tech years vs JD minimum
    if tech_notes and jd_years > 0:
        avg_tech = sum(
            extract_tech_experience_years(exp_context or resume_text, canonicalize_skill(s))
            for s in jd_skills[:8]
        ) / max(1, min(8, len(jd_skills)))
        if avg_tech >= jd_years:
            score = min(100.0, score + 5)
            scoring_trace.append(
                f"Experience rule: tech-specific years meet JD ({avg_tech:.1f}y) → +5%."
            )
        elif avg_tech > 0 and avg_tech < jd_years * 0.5:
            score = max(30.0, score - 8)
            scoring_trace.append(
                f"Experience rule: tech years below half of JD minimum → −8%."
            )

    scoring_trace.append(f"Experience rule: final raw score {score}%.")
    return score, _sort(present), _sort(missing)


def match_all_jd_skills(
    jd_skills: List[str],
    resume_text: str,
    resume_skills: List[str],
    resume_canon: Set[str],
    embedding_model: Any = None,
    sections: Optional[ResumeSections] = None,
) -> Tuple[List[SkillMatchDetail], List[str], List[str], List[str]]:
    """Return (details, matched, partial, missing) display names."""
    if sections is None:
        sections = parse_resume_sections(resume_text)
    embed_corpus = _build_embed_corpus(sections)
    corpus_embs = _encode_corpus(embed_corpus, embedding_model) if embedding_model else None

    details: List[Optional[SkillMatchDetail]] = [None] * len(jd_skills)
    pending_semantic: List[Tuple[int, str, int, float]] = []

    for i, skill in enumerate(jd_skills):
        non_sem, best_fuzzy, _, _, _, embed_threshold = _match_skill_non_semantic(
            skill, resume_text, resume_skills, resume_canon, sections
        )
        if non_sem is not None:
            details[i] = non_sem
        else:
            pending_semantic.append((i, skill, best_fuzzy, embed_threshold))

    if pending_semantic and embedding_model:
        skills_to_check = [s for _, s, _, _ in pending_semantic]
        thresholds = [t for _, _, _, t in pending_semantic]
        if corpus_embs is not None:
            batch_results = _batch_semantic_skills(
                skills_to_check, embed_corpus, corpus_embs, embedding_model, thresholds
            )
        else:
            batch_results = [
                _semantic_best(s, embed_corpus, embedding_model, t, corpus_embs)
                for s, t in zip(skills_to_check, thresholds)
            ]
        for (idx, skill, best_fuzzy, embed_threshold), (sem_sim, sem_ev, sem_sec) in zip(
            pending_semantic, batch_results
        ):
            details[idx] = _build_semantic_skill_detail(
                skill, sem_sim, sem_ev, sem_sec, best_fuzzy, embed_threshold
            )
    elif pending_semantic:
        for idx, skill, best_fuzzy, embed_threshold in pending_semantic:
            details[idx] = _build_semantic_skill_detail(skill, 0.0, "", "", best_fuzzy, embed_threshold)

    matched, partial, missing = [], [], []
    final_details: List[SkillMatchDetail] = []
    for d in details:
        if d is None:
            continue
        final_details.append(d)
        if d.status == "Matched":
            matched.append(d.skill_name)
        elif d.status == "Partial":
            partial.append(d.skill_name)
        else:
            missing.append(d.skill_name)

    return final_details, sort_alpha(matched), sort_alpha(partial), sort_alpha(missing)

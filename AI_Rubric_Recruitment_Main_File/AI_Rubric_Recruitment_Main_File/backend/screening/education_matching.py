"""
UG/PG grouped education matching with field-aware rules.

Rules:
- UG degrees (B.Tech, B.E, B.Sc, Bachelor's, etc.) are interchangeable within the same field.
- PG degrees (M.Tech, MCA, MBA, Master's, PhD, etc.) are interchangeable within the same field.
- Engineering JD → any engineering UG satisfies UG requirement (B.Tech, B.E, BE, CSE, IT, etc.).
- PG required → candidate must have PG on resume; PG alone is acceptable (UG assumed).
- PG required + UG only on resume → reject / missing PG.
- UG required only → any matching-field UG or higher (PG) satisfies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Set, Tuple, Optional


def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s\#\.\+]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def sort_alpha(items: List[str]) -> List[str]:
    return sorted(items, key=lambda x: x.lower())

# (regex, display label, level, field)
# level: ug | pg | phd | diploma
# field: engineering | science | business | general
DEGREE_DEFINITIONS: List[Tuple[str, str, str, str]] = [
    (r"\bb\.?\s*tech(?:nology)?\b", "B.Tech", "ug", "engineering"),
    (r"\bb\.?\s*e\.?\b", "B.E", "ug", "engineering"),
    (r"\bb\.?\s*eng(?:ineering)?\b", "B.Eng", "ug", "engineering"),
    (r"\bbca\b", "BCA", "ug", "engineering"),
    (r"\bb\.?\s*sc(?:ience)?\b", "B.Sc", "ug", "science"),
    (r"\bbba\b", "BBA", "ug", "business"),
    (r"\bbachelor(?:'?s)?(?:\s+of)?(?:\s+(?:technology|engineering|science|computer|arts|commerce))?\b", "Bachelor's Degree", "ug", "general"),
    (r"\bunder\s*graduate\b", "Undergraduate", "ug", "general"),
    (r"\bgraduate\s+degree\b", "Graduate Degree", "ug", "general"),
    (r"\bm\.?\s*tech\b", "M.Tech", "pg", "engineering"),
    (r"\bm\.?\s*e\.?\b", "M.E", "pg", "engineering"),
    (r"\bmca\b", "MCA", "pg", "engineering"),
    (r"\bm\.?\s*sc\b", "M.Sc", "pg", "science"),
    (r"\bmba\b", "MBA", "pg", "business"),
    (r"\bmaster(?:'?s)?(?:\s+of)?(?:\s+(?:technology|engineering|science|computer|business|arts))?\b", "Master's Degree", "pg", "general"),
    (r"\bpost\s*graduate\b", "Post Graduate", "pg", "general"),
    (r"\bpostgraduate\b", "Postgraduate", "pg", "general"),
    (r"\bphd\b", "PhD", "phd", "science"),
    (r"\bdoctorate\b", "Doctorate", "phd", "science"),
    (r"\bdiploma\b", "Diploma", "diploma", "general"),
    (r"\bengineering\b", "Engineering", "ug", "engineering"),
    (r"\bcomputer\s+science\b", "Computer Science", "ug", "engineering"),
    (r"\binformation\s+technology\b", "Information Technology", "ug", "engineering"),
]

ENGINEERING_FIELD_SIGNALS = [
    "engineering", "software", "developer", "programmer", "computer science",
    "information technology", "b.tech", "b.e", "m.tech", "mca", "bca", "cse", "it ",
    "electronics", "electrical", "mechanical", "civil", "ece", "eee", "full stack",
    "backend", "frontend", ".net", "java", "python", "react", "angular",
]

SCIENCE_FIELD_SIGNALS = ["science", "physics", "chemistry", "mathematics", "biology", "b.sc", "m.sc"]
BUSINESS_FIELD_SIGNALS = ["mba", "business", "management", "finance", "marketing", "bba"]

PG_LEVEL_PHRASES = [
    r"\bpost\s*graduate\b", r"\bpostgraduate\b", r"\bpg\s+degree\b", r"\bpg\s+required\b",
    r"\bmasters?\s+(?:degree\s+)?required\b", r"\bmaster(?:'?s)?\s+(?:degree\s+)?(?:required|preferred|mandatory)\b",
]
UG_LEVEL_PHRASES = [
    r"\bunder\s*graduate\b", r"\bundergraduate\b", r"\bgraduate\s+degree\b",
    r"\bbachelor(?:'?s)?\s+(?:degree\s+)?(?:required|mandatory)\b",
    r"\bug\s+degree\b",
]

UG_LEVELS = frozenset({"ug", "diploma"})
PG_LEVELS = frozenset({"pg", "phd"})


@dataclass
class ParsedDegree:
    label: str
    level: str
    field: str


@dataclass
class EducationRequirement:
    requires_ug: bool = False
    requires_pg: bool = False
    fields: Set[str] = field(default_factory=set)
    explicit_degrees: List[ParsedDegree] = field(default_factory=list)
    summary: str = ""

    def display_requirements(self) -> List[str]:
        if not self.requires_ug and not self.requires_pg and not self.fields:
            return []
        parts: List[str] = []
        field_label = _format_fields(self.fields) if self.fields else "Any"
        if self.requires_pg:
            parts.append(f"PG ({field_label})")
        if self.requires_ug and not self.requires_pg:
            parts.append(f"UG ({field_label})")
        elif self.requires_ug and self.requires_pg:
            parts.append(f"UG ({field_label}) - implied with PG")
        return parts or [self.summary] if self.summary else []


@dataclass
class ResumeEducationProfile:
    degrees: List[ParsedDegree] = field(default_factory=list)
    ug_degrees: List[ParsedDegree] = field(default_factory=list)
    pg_degrees: List[ParsedDegree] = field(default_factory=list)
    ug_fields: Set[str] = field(default_factory=set)
    pg_fields: Set[str] = field(default_factory=set)

    @property
    def has_ug(self) -> bool:
        return bool(self.ug_degrees)

    @property
    def has_pg(self) -> bool:
        return bool(self.pg_degrees)


@dataclass
class EducationMatchResult:
    score_pct: float
    matched: List[str]
    missing: List[str]
    traces: List[str]
    all_met: bool


def _format_fields(fields: Set[str]) -> str:
    if not fields:
        return "Any"
    order = ["engineering", "science", "business", "general"]
    labels = {"engineering": "Engineering", "science": "Science", "business": "Business", "general": "General"}
    ordered = [labels[f] for f in order if f in fields]
    return ", ".join(ordered) if ordered else "Any"


def _infer_fields_from_text(text: str) -> Set[str]:
    norm = normalize_text(text)
    fields: Set[str] = set()
    if any(s in norm for s in ENGINEERING_FIELD_SIGNALS):
        fields.add("engineering")
    if any(s in norm for s in SCIENCE_FIELD_SIGNALS):
        fields.add("science")
    if any(s in norm for s in BUSINESS_FIELD_SIGNALS):
        fields.add("business")
    if not fields:
        fields.add("general")
    return fields


def _refine_field_from_context(label: str, level: str, field: str, context: str) -> str:
    if field != "general":
        return field
    ctx = normalize_text(context)
    if any(s in ctx for s in ENGINEERING_FIELD_SIGNALS):
        return "engineering"
    if any(s in ctx for s in SCIENCE_FIELD_SIGNALS):
        return "science"
    if any(s in ctx for s in BUSINESS_FIELD_SIGNALS):
        return "business"
    return field


def parse_degrees_from_text(text: str) -> List[ParsedDegree]:
    """Extract all degree mentions from text, grouped by level and field."""
    if not text or not text.strip():
        return []

    norm = normalize_text(text)
    found: List[ParsedDegree] = []
    seen: Set[Tuple[str, str, str]] = set()

    for pattern, label, level, fld in DEGREE_DEFINITIONS:
        for m in re.finditer(pattern, text, re.I):
            start = max(0, m.start() - 80)
            end = min(len(text), m.end() + 80)
            context = text[start:end]
            refined_field = _refine_field_from_context(label, level, fld, context)
            key = (level, refined_field, label.lower())
            if key not in seen:
                seen.add(key)
                found.append(ParsedDegree(label=label, level=level, field=refined_field))

    # Branch-of-engineering signals without explicit degree acronym
    branch_patterns = [
        (r"\b(?:computer|software|information)\s+(?:science|technology|engineering)\b", "Computer Science", "ug", "engineering"),
        (r"\b(?:electronics|electrical|mechanical|civil)\s+engineering\b", "Engineering", "ug", "engineering"),
    ]
    for pattern, label, level, fld in branch_patterns:
        if re.search(pattern, text, re.I):
            key = (level, fld, label.lower())
            if key not in seen:
                seen.add(key)
                found.append(ParsedDegree(label=label, level=level, field=fld))

    return found


def parse_resume_education(resume_text: str) -> ResumeEducationProfile:
    degrees = parse_degrees_from_text(resume_text)
    ug = [d for d in degrees if d.level in UG_LEVELS]
    pg = [d for d in degrees if d.level in PG_LEVELS]
    return ResumeEducationProfile(
        degrees=degrees,
        ug_degrees=ug,
        pg_degrees=pg,
        ug_fields={d.field for d in ug},
        pg_fields={d.field for d in pg},
    )


def parse_jd_education_requirement(jd_text: str, full_jd_text: str = "") -> EducationRequirement:
    """Build structured UG/PG requirements from JD education mentions."""
    combined = f"{jd_text or ''} {full_jd_text or ''}".strip()
    if not combined:
        return EducationRequirement()

    explicit = parse_degrees_from_text(combined)
    norm = normalize_text(combined)

    requires_pg = any(d.level in PG_LEVELS for d in explicit)
    requires_ug = any(d.level in UG_LEVELS for d in explicit)

    for pat in PG_LEVEL_PHRASES:
        if re.search(pat, combined, re.I):
            requires_pg = True
            break

    for pat in UG_LEVEL_PHRASES:
        if re.search(pat, combined, re.I):
            requires_ug = True
            break

    # Generic "degree" without post-graduate context → UG
    if re.search(r"\b(?:any\s+)?degree\b", norm) and not requires_pg:
        requires_ug = True

    fields: Set[str] = {d.field for d in explicit if d.field != "general"}
    if not fields:
        fields = _infer_fields_from_text(combined)

    # Engineering-heavy JD with education mention but no explicit level → UG in that field
    if explicit and not requires_pg and not requires_ug:
        requires_ug = True

    if requires_pg and not requires_ug:
        requires_ug = True  # PG implies UG pathway; satisfied by PG on resume

    if not explicit and not requires_pg and not requires_ug:
        if "engineering" in fields or "science" in fields:
            requires_ug = True

    summary_parts = []
    if requires_pg:
        summary_parts.append(f"PG ({_format_fields(fields)})")
    elif requires_ug:
        summary_parts.append(f"UG ({_format_fields(fields)})")

    return EducationRequirement(
        requires_ug=requires_ug,
        requires_pg=requires_pg,
        fields=fields,
        explicit_degrees=explicit,
        summary="; ".join(summary_parts),
    )


def _fields_compatible(candidate_fields: Set[str], required_fields: Set[str]) -> bool:
    if not required_fields or required_fields == {"general"}:
        return bool(candidate_fields) or True
    if not candidate_fields:
        return False
    if "general" in candidate_fields:
        return True
    if "engineering" in required_fields:
        return bool(candidate_fields & {"engineering", "science"})
    if "science" in required_fields:
        return bool(candidate_fields & {"science", "engineering"})
    if "business" in required_fields:
        return bool(candidate_fields & {"business", "general"})
    return bool(candidate_fields & required_fields)


def _ug_satisfied(req: EducationRequirement, resume: ResumeEducationProfile) -> Tuple[bool, List[str], List[str]]:
    present: List[str] = []
    missing: List[str] = []

    ug_ok = resume.has_ug and _fields_compatible(resume.ug_fields, req.fields)
    pg_covers_ug = resume.has_pg and _fields_compatible(resume.pg_fields, req.fields)

    if ug_ok:
        present.extend(d.label for d in resume.ug_degrees)
        return True, present, missing

    if pg_covers_ug:
        present.append("PG satisfies UG requirement")
        present.extend(d.label for d in resume.pg_degrees)
        if resume.has_ug:
            present.extend(d.label for d in resume.ug_degrees)
        return True, present, missing

    if resume.has_ug:
        missing.append(f"UG field mismatch - need {_format_fields(req.fields)}")
        present.extend(d.label for d in resume.ug_degrees)
    else:
        missing.append(f"UG degree required ({_format_fields(req.fields)})")
    return False, present, missing


def _pg_satisfied(req: EducationRequirement, resume: ResumeEducationProfile) -> Tuple[bool, List[str], List[str]]:
    present: List[str] = []
    missing: List[str] = []

    if resume.has_pg and _fields_compatible(resume.pg_fields, req.fields):
        present.extend(d.label for d in resume.pg_degrees)
        if resume.has_ug:
            present.extend(d.label for d in resume.ug_degrees)
        else:
            present.append("PG present (UG assumed)")
        return True, present, missing

    if resume.has_pg:
        missing.append(f"PG field mismatch - need {_format_fields(req.fields)}")
        present.extend(d.label for d in resume.pg_degrees)
        return False, present, missing

    if resume.has_ug and not resume.has_pg:
        missing.append("PG degree required - candidate has UG only")
        present.extend(d.label for d in resume.ug_degrees)
        return False, present, missing

    missing.append(f"PG degree required ({_format_fields(req.fields)})")
    return False, present, missing


def evaluate_education_match(
    requirement: Optional[EducationRequirement],
    resume_text: str,
    jd_full_text: str = "",
) -> EducationMatchResult:
    """Evaluate resume education against grouped UG/PG JD requirements."""
    if requirement is None:
        requirement = parse_jd_education_requirement(jd_full_text, jd_full_text)
    resume = parse_resume_education(resume_text)
    traces: List[str] = []
    present: List[str] = []
    missing: List[str] = []

    if not requirement.requires_ug and not requirement.requires_pg:
        if resume.degrees:
            labels = sort_alpha(list(dict.fromkeys(d.label for d in resume.degrees)))
            traces.append(f"Education: no JD requirement; resume has {', '.join(labels)}.")
            return EducationMatchResult(
                score_pct=100.0,
                matched=labels,
                missing=[],
                traces=traces,
                all_met=True,
            )
        level = _highest_level(resume)
        if level >= 3:
            traces.append("Education: no JD requirement; bachelor's+ detected.")
            return EducationMatchResult(score_pct=100.0, matched=["Degree detected"], missing=[], traces=traces, all_met=True)
        traces.append("Education: no JD requirement; limited education signals.")
        return EducationMatchResult(score_pct=70.0, matched=[], missing=[], traces=traces, all_met=True)

    req_label = requirement.summary or _format_fields(requirement.fields)
    traces.append(
        f"Education requirement: {req_label} "
        f"(UG={'yes' if requirement.requires_ug else 'no'}, PG={'yes' if requirement.requires_pg else 'no'})."
    )

    # PG requirement takes precedence for rejection logic
    if requirement.requires_pg:
        pg_ok, pg_present, pg_missing = _pg_satisfied(requirement, resume)
        present.extend(pg_present)
        missing.extend(pg_missing)
        if pg_ok:
            traces.append("Education: PG requirement satisfied.")
            return EducationMatchResult(
                score_pct=100.0,
                matched=sort_alpha(list(dict.fromkeys(present))),
                missing=[],
                traces=traces,
                all_met=True,
            )
        traces.append("Education: PG requirement NOT met.")
        return EducationMatchResult(
            score_pct=25.0,
            matched=sort_alpha(list(dict.fromkeys(present))),
            missing=sort_alpha(list(dict.fromkeys(missing))),
            traces=traces,
            all_met=False,
        )

    # UG only requirement
    ug_ok, ug_present, ug_missing = _ug_satisfied(requirement, resume)
    present.extend(ug_present)
    missing.extend(ug_missing)
    if ug_ok:
        traces.append("Education: UG requirement satisfied.")
        return EducationMatchResult(
            score_pct=100.0,
            matched=sort_alpha(list(dict.fromkeys(present))),
            missing=[],
            traces=traces,
            all_met=True,
        )

    traces.append("Education: UG requirement NOT met.")
    score = 35.0 if present else 20.0
    return EducationMatchResult(
        score_pct=score,
        matched=sort_alpha(list(dict.fromkeys(present))),
        missing=sort_alpha(list(dict.fromkeys(missing))),
        traces=traces,
        all_met=False,
    )


def _highest_level(resume: ResumeEducationProfile) -> int:
    if resume.has_pg:
        return 4
    if resume.has_ug:
        return 3
    if any(d.level == "diploma" for d in resume.degrees):
        return 2
    return 0


def extract_jd_education_labels(jd_text: str, full_jd_text: str = "") -> List[str]:
    """Human-readable education requirements for JD profile display."""
    req = parse_jd_education_requirement(jd_text, full_jd_text)
    labels = req.display_requirements()
    return sort_alpha(labels) if labels else []


def detect_resume_education_level(resume_text: str) -> Tuple[int, str]:
    """Fallback when JD has no education requirement."""
    resume = parse_resume_education(resume_text)
    if resume.has_pg:
        best = resume.pg_degrees[0]
        return 4, best.label
    if resume.has_ug:
        best = resume.ug_degrees[0]
        return 3, best.label
    if any(d.level == "diploma" for d in resume.degrees):
        return 2, "Diploma"
    return 0, "not specified"

"""
ATS + Rubric Engine
- Parses FULL uploaded JD (skills, responsibilities, education, experience, keywords)
- Maps each resume against every JD requirement with high-accuracy multi-pass matching
- Canonical skill aliases + regex + fuzzy (resume pool only) + embeddings
- Rubric scores driven by real JD ↔ resume comparison
"""

import re
import logging
import os
from typing import List, Tuple, Dict, Optional, Any, Set
from dataclasses import dataclass, field
from models import JobRole, RubricScores, RubricDimension, RubricWeights, DEFAULT_RUBRIC_WEIGHTS

logger = logging.getLogger(__name__)

FAST_SCORING = os.getenv("FAST_SCORING", "1").strip().lower() not in ("0", "false", "no")

try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    from difflib import SequenceMatcher
    HAS_RAPIDFUZZ = False

FUZZY_SKILL_THRESHOLD = 78
FUZZY_RESP_THRESHOLD = 72
EMBED_SKILL_THRESHOLD = 0.52
EMBED_RESP_THRESHOLD = 0.46

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with",
    "by", "from", "as", "is", "was", "are", "were", "be", "been", "being", "have", "has",
    "had", "do", "does", "did", "will", "would", "could", "should", "may", "might", "must",
    "can", "not", "no", "so", "if", "then", "this", "that", "these", "those", "it", "we",
    "they", "you", "your", "our", "their", "all", "any", "each", "every", "both", "few",
    "more", "most", "other", "some", "such", "than", "too", "very", "just", "also", "now",
    "role", "position", "job", "work", "working", "experience", "years", "year", "required",
    "requirements", "responsibilities", "description", "summary", "candidate", "looking",
    "seeking", "join", "team", "company", "based", "using", "including", "ability",
    "strong", "good", "excellent", "minimum", "preferred", "plus", "etc", "able", "well",
    "hands", "hand", "proficient", "skilled", "knowledge", "understanding", "familiar",
}

# Canonical skill → aliases (all lowercase)
SKILL_CANONICAL: Dict[str, List[str]] = {
    ".net": [".net", "dotnet", "dot net", "asp.net", "aspnet", "asp net", ".net core", "net core",
             "c#", "csharp", "c sharp", "entity framework", "ef core", "linq", "blazor", "wpf",
             "web api", "webapi", "mvc", "wcf", "silverlight"],
    "python": ["python", "py", "django", "flask", "fastapi", "pandas", "numpy"],
    "java": ["java", "spring boot", "springboot", "hibernate", "j2ee"],
    "javascript": ["javascript", "js", "jquery", "typescript", "ts", "node.js", "nodejs", "node js", "react.js", "reactjs"],
    "react": ["react", "react.js", "reactjs", "redux", "next.js", "nextjs"],
    "angular": ["angular", "angularjs"],
    "sql": ["sql", "t-sql", "tsql", "pl/sql", "plsql", "sql server", "sqlserver", "mssql"],
    "mysql": ["mysql"],
    "postgresql": ["postgresql", "postgres", "postgre sql"],
    "mongodb": ["mongodb", "mongo db"],
    "aws": ["aws", "amazon web services", "ec2", "s3", "lambda", "rds"],
    "azure": ["azure", "microsoft azure"],
    "gcp": ["gcp", "google cloud", "google cloud platform"],
    "docker": ["docker", "containerization"],
    "kubernetes": ["kubernetes", "k8s"],
    "devops": ["devops", "ci/cd", "cicd", "jenkins", "terraform"],
    "machine learning": ["machine learning", "ml", "deep learning", "tensorflow", "pytorch", "nlp", "llm", "gpt", "rag"],
    "power bi": ["power bi", "powerbi", "ssrs", "ssis", "ssas"],
    "tableau": ["tableau"],
    "excel": ["excel", "ms excel", "spreadsheet"],
    "data analysis": ["data analysis", "data analytics", "data analyst", "business intelligence", "bi"],
    "html": ["html", "html5"],
    "css": ["css", "css3", "bootstrap", "tailwind"],
    "git": ["git", "github", "gitlab", "bitbucket"],
    "agile": ["agile", "scrum", "jira"],
    "rest api": ["rest api", "restful", "restful api", "web api", "api integration"],
    "microservices": ["microservices", "micro services", "microservice"],
    "sharepoint": ["sharepoint"],
    "oracle": ["oracle"],
    "sap": ["sap"],
    "salesforce": ["salesforce"],
    "selenium": ["selenium"],
    "linux": ["linux"],
    "redis": ["redis"],
    "kafka": ["kafka"],
    "spark": ["spark", "pyspark"],
    "graphql": ["graphql"],
    "vue.js": ["vue.js", "vuejs", "vue"],
}

_ALIAS_TO_CANONICAL: Dict[str, str] = {}
for _canon, _aliases in SKILL_CANONICAL.items():
    for _alias in _aliases:
        _ALIAS_TO_CANONICAL[_alias.lower()] = _canon

SKILL_REGEX: Dict[str, re.Pattern] = {
    ".net": re.compile(
        r"\b(?:\.net|asp\.?net|dotnet|dot\s*net|c#|csharp|entity\s*framework|ef\s*core|linq|blazor|wpf|mvc|wcf)\b", re.I
    ),
    "python": re.compile(r"\b(?:python|django|flask|fastapi|pandas|numpy)\b", re.I),
    "java": re.compile(r"\b(?:java|spring\s*boot|hibernate)\b", re.I),
    "javascript": re.compile(r"\b(?:javascript|typescript|jquery|node\.?js)\b", re.I),
    "react": re.compile(r"\b(?:react(?:\.js)?|redux|next\.?js)\b", re.I),
    "angular": re.compile(r"\bangular(?:js)?\b", re.I),
    "sql": re.compile(r"\b(?:sql|t-?sql|pl/?sql|sql\s*server|mssql)\b", re.I),
    "mysql": re.compile(r"\bmysql\b", re.I),
    "postgresql": re.compile(r"\b(?:postgresql|postgres)\b", re.I),
    "mongodb": re.compile(r"\bmongodb?\b", re.I),
    "aws": re.compile(r"\b(?:aws|amazon\s*web\s*services|ec2|lambda)\b", re.I),
    "azure": re.compile(r"\bazure\b", re.I),
    "docker": re.compile(r"\bdocker\b", re.I),
    "kubernetes": re.compile(r"\b(?:kubernetes|k8s)\b", re.I),
    "devops": re.compile(r"\b(?:devops|ci/?cd|jenkins|terraform)\b", re.I),
    "machine learning": re.compile(r"\b(?:machine\s*learning|deep\s*learning|tensorflow|pytorch|nlp|llm|gpt|rag)\b", re.I),
    "power bi": re.compile(r"\b(?:power\s*bi|powerbi|ssrs|ssis|ssas)\b", re.I),
    "tableau": re.compile(r"\btableau\b", re.I),
    "excel": re.compile(r"\bexcel\b", re.I),
    "data analysis": re.compile(r"\b(?:data\s*analys[ti]s|business\s*intelligence)\b", re.I),
    "html": re.compile(r"\bhtml5?\b", re.I),
    "css": re.compile(r"\b(?:css3?|bootstrap|tailwind)\b", re.I),
    "git": re.compile(r"\b(?:git|github|gitlab)\b", re.I),
    "agile": re.compile(r"\b(?:agile|scrum|jira)\b", re.I),
    "rest api": re.compile(r"\b(?:rest\s*api|restful|web\s*api)\b", re.I),
    "microservices": re.compile(r"\bmicro\s*services?\b", re.I),
}

TECH_REGEX = re.compile(
    r"\b(?:\.net|asp\.?net|c#|c\+\+|python|java|javascript|typescript|react|angular|vue\.?js|"
    r"node\.?js|sql|mysql|postgresql|postgres|mongodb|aws|azure|gcp|docker|kubernetes|k8s|"
    r"fastapi|django|flask|spring\s*boot|hibernate|graphql|rest\s*api|microservices|devops|"
    r"ci/?cd|jenkins|git|github|agile|scrum|html|css|bootstrap|entity\s*framework|linq|mvc|"
    r"web\s*api|blazor|wpf|redis|kafka|spark|tensorflow|pytorch|machine\s*learning|"
    r"deep\s*learning|nlp|llm|gpt|rag|power\s*bi|tableau|selenium|jira|linux|terraform|"
    r"sharepoint|oracle|sap|salesforce|wcf|silverlight|dotnet|dot\s*net|pandas|numpy|excel)\b",
    re.IGNORECASE,
)

_jd_cache: Dict[str, "JDProfile"] = {}


@dataclass
class JDProfile:
    full_text: str = ""
    skills: List[str] = field(default_factory=list)
    responsibilities: List[str] = field(default_factory=list)
    education: List[str] = field(default_factory=list)
    education_requirement: Any = None
    experience_years: float = 0.0
    experience_text: str = ""
    keywords: List[str] = field(default_factory=list)
    culture_keywords: List[str] = field(default_factory=list)


@dataclass
class ResumeMatch:
    matched_skills: List[str] = field(default_factory=list)
    missing_skills: List[str] = field(default_factory=list)
    partial_skills: List[str] = field(default_factory=list)
    skill_details: List[Any] = field(default_factory=list)
    matched_responsibilities: List[str] = field(default_factory=list)
    missing_responsibilities: List[str] = field(default_factory=list)
    matched_education: List[str] = field(default_factory=list)
    missing_education: List[str] = field(default_factory=list)
    matched_keywords: List[str] = field(default_factory=list)
    missing_keywords: List[str] = field(default_factory=list)
    extra_skills: List[str] = field(default_factory=list)
    resume_skills: List[str] = field(default_factory=list)
    skill_pct: float = 0.0
    resp_pct: float = 0.0
    keyword_pct: float = 0.0
    resume_domain: str = ""
    jd_domain: str = ""
    domain_penalty: float = 0.0
    scoring_trace: List[str] = field(default_factory=list)
    tech_experience_notes: List[str] = field(default_factory=list)
    experience_raw: float = 0.0
    experience_present: List[str] = field(default_factory=list)
    experience_missing: List[str] = field(default_factory=list)

    def trace(self, msg: str) -> None:
        if not FAST_SCORING:
            self.scoring_trace.append(msg)


def sort_alpha(items: List[str]) -> List[str]:
    return sorted(items, key=lambda x: x.lower())


def _fuzzy_score(a: str, b: str) -> int:
    a, b = a.lower().strip(), b.lower().strip()
    if not a or not b:
        return 0
    if a == b:
        return 100
    if HAS_RAPIDFUZZ:
        return max(
            fuzz.ratio(a, b),
            fuzz.partial_ratio(a, b),
            fuzz.token_set_ratio(a, b),
            fuzz.token_sort_ratio(a, b),
        )
    return int(SequenceMatcher(None, a, b).ratio() * 100)


def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s\#\.\+]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def canonicalize_skill(skill: str) -> str:
    s = normalize_text(skill)
    if not s:
        return ""
    if s in _ALIAS_TO_CANONICAL:
        return _ALIAS_TO_CANONICAL[s]
    for alias, canon in sorted(_ALIAS_TO_CANONICAL.items(), key=lambda x: -len(x[0])):
        if alias in s or s in alias:
            return canon
    for m in TECH_REGEX.finditer(skill):
        found = normalize_text(m.group(0))
        if found in _ALIAS_TO_CANONICAL:
            return _ALIAS_TO_CANONICAL[found]
        return found
    return s


def display_skill(skill: str) -> str:
    canon = canonicalize_skill(skill)
    DISPLAY_LABELS = {
        ".net": ".NET", "sql": "SQL", "mysql": "MySQL", "html": "HTML", "css": "CSS",
        "aws": "AWS", "api": "API", "nlp": "NLP", "llm": "LLM", "gpt": "GPT", "rag": "RAG",
        "mvc": "MVC", "c#": "C#", "ci/cd": "CI/CD",
    }
    if canon in DISPLAY_LABELS:
        return DISPLAY_LABELS[canon]
    if canon in SKILL_CANONICAL:
        if len(canon) <= 4:
            return canon.upper()
        return canon.title()
    raw = skill.strip()
    return raw.upper() if len(raw) <= 4 else raw.title()


def _clean_skill_token(token: str) -> str:
    token = token.strip()
    token = re.sub(r"^[\d\.\)\(\-\•\*\u2022]+\s*", "", token)
    token = re.sub(r"\s+", " ", token).strip(".,;:- ")
    if not token or len(token) < 2 or len(token) > 60:
        return ""
    lower = token.lower()
    if lower in STOPWORDS or lower.isdigit():
        return ""
    if not re.search(r"[a-zA-Z]", token):
        return ""
    return token


def _is_valid_skill(token: str) -> bool:
    lower = token.lower()
    if canonicalize_skill(token) in SKILL_CANONICAL:
        return True
    if TECH_REGEX.search(token):
        return True
    if len(lower) < 3 or lower in STOPWORDS:
        return False
    if re.match(r"^[a-z0-9\.\#\+\-]+$", lower) and len(lower) <= 25:
        return True
    return False


def _extract_skill_sections(text: str) -> List[str]:
    sections = []
    patterns = [
        r"(?:technical\s+)?skills?\s*[:\-]\s*(.+?)(?:\n\n|\n[A-Z][a-z]+\s*[:\-]|\Z)",
        r"(?:technologies|tools|platforms|tech\s+stack)\s*[:\-]\s*(.+?)(?:\n\n|\n[A-Z][a-z]+\s*[:\-]|\Z)",
        r"(?:requirements?|qualifications?|must\s+have|key\s+skills?)\s*[:\-]\s*(.+?)(?:\n\n|\n[A-Z][a-z]+\s*[:\-]|\Z)",
        r"(?:proficien(?:t|cy)\s+in|experience\s+with|knowledge\s+of)\s+(.+?)(?:\.|,|\n)",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, re.I | re.S):
            sections.append(m.group(1))
    return sections


def parse_jd_skills(jd: JobRole, full_text: str) -> List[str]:
    """Extract JD skills from explicit lists + tech patterns — no noise words."""
    seen_canon: Set[str] = set()
    skills: List[str] = []

    def add(raw: str):
        cleaned = _clean_skill_token(raw)
        if not cleaned or not _is_valid_skill(cleaned):
            return
        canon = canonicalize_skill(cleaned)
        if canon and canon not in seen_canon:
            seen_canon.add(canon)
            skills.append(display_skill(cleaned))

    if jd.skills:
        for tok in re.split(r"[,;|/\n•]+", jd.skills):
            add(tok)

    for section in _extract_skill_sections(full_text):
        for tok in re.split(r"[,;|/\n•]+", section):
            add(tok)

    for source in [jd.skills or "", full_text]:
        for m in TECH_REGEX.finditer(source):
            add(m.group(0))

    return sort_alpha(skills)


def extract_resume_skills(resume_text: str) -> Tuple[List[str], Set[str]]:
    """Return (display skills list, canonical set) from resume."""
    seen_canon: Set[str] = set()
    skills: List[str] = []

    def add(raw: str):
        cleaned = _clean_skill_token(raw)
        if not cleaned:
            return
        canon = canonicalize_skill(cleaned)
        if not canon:
            return
        if canon not in seen_canon:
            seen_canon.add(canon)
            skills.append(display_skill(cleaned))

    for m in TECH_REGEX.finditer(resume_text):
        add(m.group(0))

    for line in resume_text.split("\n"):
        if line.count(",") >= 2 or re.search(r"skills?|technologies|tools", line, re.I):
            for tok in re.split(r"[,;|/]+", line):
                if _is_valid_skill(tok):
                    add(tok)

    for section in _extract_skill_sections(resume_text):
        for tok in re.split(r"[,;|/\n•]+", section):
            if _is_valid_skill(tok):
                add(tok)

    for m in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b", resume_text):
        if _is_valid_skill(m.group(1)):
            add(m.group(1))

    return sort_alpha(skills), seen_canon


def _skill_regex_match(canon: str, resume_text: str) -> bool:
    pattern = SKILL_REGEX.get(canon)
    if pattern and pattern.search(resume_text):
        return True
    aliases = SKILL_CANONICAL.get(canon, [canon])
    for alias in aliases:
        escaped = re.escape(alias).replace(r"\ ", r"\s+")
        if re.search(rf"\b{escaped}\b", resume_text, re.I):
            return True
    return False


def _embedding_match(
    query: str, corpus: List[str], embedding_model: Any, threshold: float
) -> bool:
    if not embedding_model or not corpus:
        return False
    try:
        from sklearn.metrics.pairwise import cosine_similarity
        texts = [query[:200]] + [c[:200] for c in corpus[:40]]
        emb = embedding_model.encode(texts)
        sims = cosine_similarity([emb[0]], emb[1:])[0]
        return float(max(sims)) >= threshold
    except Exception:
        return False


def match_skill_to_resume(
    skill: str,
    resume_text: str,
    resume_skills: List[str],
    resume_canon: Set[str],
    embedding_model: Any = None,
) -> Tuple[bool, int]:
    """High-accuracy skill match: regex → canonical → pool fuzzy → embedding."""
    canon = canonicalize_skill(skill)
    if not canon:
        return False, 0

    if _skill_regex_match(canon, resume_text):
        return True, 100

    if canon in resume_canon:
        return True, 100

    item_norm = normalize_text(skill)
    resume_norm = normalize_text(resume_text)
    if item_norm and len(item_norm) >= 3 and re.search(rf"\b{re.escape(item_norm)}\b", resume_norm):
        return True, 98

    best = 0
    for rs in resume_skills:
        rs_canon = canonicalize_skill(rs)
        if rs_canon == canon:
            return True, 100
        score = _fuzzy_score(canon, rs)
        best = max(best, score)
        if score >= FUZZY_SKILL_THRESHOLD:
            return True, score

    for alias in SKILL_CANONICAL.get(canon, []):
        if alias in resume_norm:
            return True, 95
        score = max(_fuzzy_score(alias, rs) for rs in resume_skills) if resume_skills else 0
        best = max(best, score)
        if score >= FUZZY_SKILL_THRESHOLD:
            return True, score

    return False, best

def _extract_resp_key_terms(resp: str) -> List[str]:
    terms = []
    for m in TECH_REGEX.finditer(resp):
        terms.append(canonicalize_skill(m.group(0)))
    action_nouns = re.findall(
        r"\b(?:develop|design|build|implement|maintain|manage|create|lead|support|integrate|deploy|optimize|"
        r"architect|automate|analyze|test|write|deliver)\w*\s+[\w\s]{3,30}",
        resp, re.I,
    )
    for phrase in action_nouns[:5]:
        for w in phrase.lower().split():
            if len(w) > 4 and w not in STOPWORDS:
                terms.append(w)
    return list(dict.fromkeys(t for t in terms if t))


def match_responsibility_to_resume(
    resp: str,
    resume_text: str,
    resume_skills: List[str],
    embedding_model: Any = None,
    resp_corpus: Optional[List[Tuple[str, str]]] = None,
    resp_corpus_embs: Any = None,
) -> Tuple[bool, int]:
    """Match JD responsibility against resume using key terms + fuzzy + embedding."""
    resume_norm = normalize_text(resume_text)
    key_terms = _extract_resp_key_terms(resp)

    if key_terms:
        hits = sum(1 for t in key_terms if t in resume_norm or _skill_regex_match(t, resume_text))
        if hits >= max(1, len(key_terms) * 0.5):
            return True, 90

    resp_short = normalize_text(resp)[:120]
    words = [w for w in resp_short.split() if len(w) > 3 and w not in STOPWORDS]
    if words:
        overlap = sum(1 for w in words if w in resume_norm)
        if overlap >= max(2, len(words) * 0.45):
            return True, 85

    for rs in resume_skills:
        score = _fuzzy_score(resp_short, normalize_text(rs))
        if score >= FUZZY_RESP_THRESHOLD:
            return True, score

    for chunk in _text_chunks(resume_text, 120)[:8]:
        score = _fuzzy_score(resp_short, normalize_text(chunk))
        if score >= FUZZY_RESP_THRESHOLD:
            return True, score

    if embedding_model:
        if resp_corpus is None:
            chunks = _text_chunks(resume_text, 100)[:12]
            resp_corpus = [("experience", c) for c in chunks]
        from skill_matching import _encode_corpus, _semantic_best
        if resp_corpus_embs is None and resp_corpus:
            resp_corpus_embs = _encode_corpus(resp_corpus, embedding_model)
        sim, _, _ = _semantic_best(
            resp, resp_corpus, embedding_model, EMBED_RESP_THRESHOLD, resp_corpus_embs
        )
        if sim >= EMBED_RESP_THRESHOLD:
            return True, int(sim * 85)

    return False, 0


def _text_chunks(text: str, size: int) -> List[str]:
    words = text.split()
    return [" ".join(words[i:i + size]) for i in range(0, len(words), max(1, size // 2))]


def extract_jd_responsibilities(text: str) -> List[str]:
    items: List[str] = []
    seen: set = set()

    def add(s: str):
        s = s.strip()
        if len(s) < 8 or len(s) > 300:
            return
        key = s.lower()[:60]
        if key not in seen:
            seen.add(key)
            items.append(s)

    for line in text.split("\n"):
        line = line.strip()
        if re.match(r"^[\-\•\*\u2022]\s+", line):
            add(re.sub(r"^[\-\•\*\u2022]\s+", "", line))
        elif re.match(r"^\d+[\.\)]\s+", line):
            add(re.sub(r"^\d+[\.\)]\s+", "", line))

    for m in re.finditer(
        r"(?:responsible\s+for|duties\s+include|you\s+will|must\s+be\s+able|should\s+have|"
        r"required\s+to|looking\s+for|experience\s+(?:in|with))\s+([^.!\n;]{12,200})",
        text, re.I,
    ):
        add(m.group(1).strip())

    for sentence in re.split(r"[.!?\n]+", text):
        s = sentence.strip()
        if len(s) > 10 and any(kw in s.lower() for kw in [
            "develop", "design", "manage", "build", "implement", "maintain",
            "create", "lead", "support", "work", "using", "knowledge", "experience",
            "write", "test", "deploy", "analyze", "coordinate", "deliver", "review",
        ]):
            add(s)

    return sort_alpha(items[:40])


def extract_jd_education(text: str, full_jd_text: str = "") -> List[str]:
    from education_matching import extract_jd_education_labels
    return extract_jd_education_labels(text, full_jd_text)


def extract_years_experience(text: str) -> float:
    patterns = [
        r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s*(?:of)?\s*(?:experience|exp)",
        r"(?:minimum|min|at\s+least)\s+(\d+(?:\.\d+)?)\s*(?:years?|yrs?)",
        r"(\d+(?:\.\d+)?)\s*\+\s*(?:years?|yrs?)",
        r"experience\s*(?:of)?\s*(\d+(?:\.\d+)?)\s*(?:years?|yrs?)",
        r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b",
    ]
    best = 0.0
    for pat in patterns:
        for m in re.finditer(pat, text, re.I):
            try:
                val = float(m.group(1))
                if 0 < val <= 45:
                    best = max(best, val)
            except ValueError:
                pass
    return best


def _merge_jd_responsibility_field(jd_resp: str, items: List[str]) -> List[str]:
    """Include explicit JD responsibility lines even when heuristic extraction misses them."""
    seen = {i.lower()[:60] for i in items}
    for part in re.split(r"[\n;|•]+|(?<=[.!?])\s+", jd_resp or ""):
        part = part.strip()
        if len(part) < 8:
            continue
        key = part.lower()[:60]
        if key not in seen:
            seen.add(key)
            items.append(part)
    return sort_alpha(items[:40])


def extract_culture_from_jd(text: str) -> List[str]:
    markers = [
        "team", "collaboration", "agile", "scrum", "leadership", "mentor",
        "innovation", "integrity", "communication", "problem solving", "analytical",
        "self motivated", "fast paced", "cross functional", "stakeholder",
    ]
    found = []
    norm = normalize_text(text)
    for m in markers:
        if m in norm:
            found.append(m.title())
    return sort_alpha(found)


def parse_jd_full(jd: JobRole) -> JDProfile:
    full_text = (jd.responsibilities or "").strip()
    if len(full_text) < 50:
        full_text = " ".join(filter(None, [
            jd.job_role, jd.skills, jd.responsibilities, jd.experience,
            jd.bonus, jd.project,
        ]))

    skills = parse_jd_skills(jd, full_text)
    responsibilities = _merge_jd_responsibility_field(
        jd.responsibilities or "", extract_jd_responsibilities(full_text)
    )
    education = extract_jd_education(full_text, full_text)
    from education_matching import parse_jd_education_requirement
    education_req = parse_jd_education_requirement(full_text, full_text)
    exp_years = extract_years_experience(full_text)
    if not exp_years and jd.experience:
        exp_years = extract_years_experience(jd.experience)

    exp_text = jd.experience or ""
    if exp_years > 0:
        exp_text = f"Minimum {exp_years:g} years experience"

    keywords = sort_alpha(list(dict.fromkeys(
        [canonicalize_skill(s) for s in skills] +
        [normalize_text(r)[:60] for r in responsibilities[:20]]
    )))
    culture = extract_culture_from_jd(full_text)

    return JDProfile(
        full_text=full_text,
        skills=skills,
        responsibilities=responsibilities,
        education=education,
        education_requirement=education_req,
        experience_years=exp_years,
        experience_text=exp_text,
        keywords=keywords[:60],
        culture_keywords=culture,
    )


def get_jd_profile(jd: JobRole) -> JDProfile:
    key = (jd.job_role or "") + "|" + (jd.responsibilities or "")[:500]
    if key not in _jd_cache:
        _jd_cache[key] = parse_jd_full(jd)
    return _jd_cache[key]


def match_resume_to_jd(profile: JDProfile, resume_text: str, embedding_model: Any = None) -> ResumeMatch:
    from skill_matching import (
        match_all_jd_skills,
        compute_weighted_skill_pct,
        detect_domain,
        compute_domain_penalty,
        parse_resume_sections,
        score_experience_with_tech,
    )

    resume_skills, resume_canon = extract_resume_skills(resume_text)
    result = ResumeMatch(resume_skills=resume_skills)
    sections = parse_resume_sections(resume_text)

    skill_details, matched, partial, missing = match_all_jd_skills(
        profile.skills, resume_text, resume_skills, resume_canon, embedding_model, sections
    )
    result.skill_details = skill_details
    result.matched_skills = matched
    result.partial_skills = partial
    result.missing_skills = missing
    result.skill_pct = compute_weighted_skill_pct(skill_details)
    result.trace(
        f"Technical skills: weighted match {result.skill_pct}% "
        f"({len(matched)} matched, {len(partial)} partial, {len(missing)} missing)."
    )

    resp_chunks = _text_chunks(resume_text, 100)[:12]
    resp_corpus = [("experience", c) for c in resp_chunks]
    resp_corpus_embs = None
    if embedding_model and resp_corpus:
        from skill_matching import _encode_corpus
        resp_corpus_embs = _encode_corpus(resp_corpus, embedding_model)

    for resp in profile.responsibilities:
        ok, conf = match_responsibility_to_resume(
            resp, resume_text, resume_skills, embedding_model, resp_corpus, resp_corpus_embs
        )
        trace = f"Responsibility '{resp[:50]}...': {'matched' if ok else 'missing'} (conf {conf})."
        result.trace(trace)
        (result.matched_responsibilities if ok else result.missing_responsibilities).append(resp)

    from education_matching import evaluate_education_match

    edu_result = evaluate_education_match(
        profile.education_requirement,
        resume_text,
        profile.full_text,
    )
    result.matched_education = edu_result.matched
    result.missing_education = edu_result.missing
    if not FAST_SCORING:
        result.scoring_trace.extend(edu_result.traces)

    for kw in profile.keywords[:30]:
        if kw in [canonicalize_skill(s) for s in profile.skills]:
            continue
        ok, _ = match_skill_to_resume(kw, resume_text, resume_skills, resume_canon, embedding_model)
        (result.matched_keywords if ok else result.missing_keywords).append(kw)

    matched_canon = {canonicalize_skill(s) for s in result.matched_skills}
    jd_canon = {canonicalize_skill(s) for s in profile.skills}
    result.extra_skills = sort_alpha([
        s for s in resume_skills
        if canonicalize_skill(s) not in matched_canon
        and canonicalize_skill(s) not in jd_canon
    ][:25])

    result.matched_skills = sort_alpha(result.matched_skills)
    result.partial_skills = sort_alpha(result.partial_skills)
    result.missing_skills = sort_alpha(result.missing_skills)
    result.matched_responsibilities = sort_alpha(result.matched_responsibilities)
    result.missing_responsibilities = sort_alpha(result.missing_responsibilities)
    result.matched_education = sort_alpha(result.matched_education)
    result.missing_education = sort_alpha(result.missing_education)
    result.matched_keywords = sort_alpha(result.matched_keywords)
    result.missing_keywords = sort_alpha(result.missing_keywords)

    n_resp = max(len(profile.responsibilities), 1)
    n_kw = max(len(profile.keywords[:30]), 1)

    result.resp_pct = round(len(result.matched_responsibilities) / n_resp * 100, 1) if profile.responsibilities else result.skill_pct
    result.keyword_pct = round(len(result.matched_keywords) / n_kw * 100, 1) if profile.keywords else result.skill_pct

    result.resume_domain = detect_domain(resume_text)
    result.jd_domain = detect_domain(profile.full_text)
    penalty, penalty_note = compute_domain_penalty(result.resume_domain, result.jd_domain)
    result.domain_penalty = penalty
    result.trace(penalty_note)

    exp_score, exp_present, exp_missing = score_experience_with_tech(
        profile.experience_years, resume_text, sections, profile.skills,
        [] if FAST_SCORING else result.scoring_trace,
    )
    result.experience_raw = exp_score
    result.experience_present = exp_present
    result.experience_missing = exp_missing
    result.tech_experience_notes = [
        p for p in exp_present if ":" in p and "years" in p.lower()
    ]

    return result


def build_jd_text(jd: JobRole) -> str:
    profile = get_jd_profile(jd)
    return profile.full_text or jd.job_role or ""


def calculate_semantic_score(similarity: float) -> Tuple[float, str]:
    score = round(max(0, min(100, similarity * 100)), 1)
    return score, f"Overall JD-resume semantic similarity: {score}% (embedding cosine {similarity:.3f})"


def score_experience(profile: JDProfile, resume_text: str) -> Tuple[float, List[str], List[str]]:
    resume_years = extract_years_experience(resume_text)
    jd_years = profile.experience_years
    present, missing = [], []

    if jd_years <= 0:
        if resume_years > 0:
            present.append(f"{resume_years:g} years experience found in resume")
            return min(100.0, 70 + resume_years * 4), sort_alpha(present), missing
        norm = normalize_text(resume_text)
        if re.search(r"\b(?:experience|worked|employed|developer|engineer|analyst|consultant)\b", norm):
            present.append("Relevant work experience described in resume")
            return 80.0, sort_alpha(present), ["Explicit experience years not stated"]
        return 65.0, [], ["Experience years not stated in resume"]

    present.append(f"JD requires: {jd_years:g}+ years")
    if resume_years > 0:
        present.append(f"Resume shows: {resume_years:g} years")
    else:
        missing.append(f"No explicit experience years in resume (JD needs {jd_years:g}+)")

    if resume_years >= jd_years:
        return 100.0, sort_alpha(present), sort_alpha(missing)
    if resume_years >= jd_years * 0.75:
        missing.append(f"~{jd_years - resume_years:g} year gap vs JD minimum")
        return 70.0, sort_alpha(present), sort_alpha(missing)
    missing.append(f"{jd_years - resume_years:g} years below JD minimum")
    return max(30, 50 + (resume_years / jd_years) * 40), sort_alpha(present), sort_alpha(missing)


def score_education(profile: JDProfile, resume_text: str, match: ResumeMatch) -> Tuple[float, List[str], List[str]]:
    from education_matching import evaluate_education_match, detect_resume_education_level

    present = list(match.matched_education)
    missing = list(match.missing_education)

    req = profile.education_requirement
    has_req = req and (req.requires_ug or req.requires_pg)

    if not has_req and not profile.education:
        level, label = detect_resume_education_level(resume_text)
        if level >= 3:
            present.append(f"{label} detected in resume")
            return 100.0, sort_alpha(present), sort_alpha(missing)
        if level >= 2:
            present.append(f"{label} detected in resume")
            return 85.0, sort_alpha(present), sort_alpha(missing)
        return 70.0, sort_alpha(present or ["Education mentioned in resume"]), sort_alpha(missing)

    if has_req:
        edu_result = evaluate_education_match(req, resume_text, profile.full_text)
        present = edu_result.matched
        missing = edu_result.missing
        return edu_result.score_pct, sort_alpha(present), sort_alpha(missing)

    if not missing:
        return 100.0, sort_alpha(present), []
    if present:
        return 65.0, sort_alpha(present), sort_alpha(missing)
    return 35.0, sort_alpha(present), sort_alpha(missing)


def _detect_education_level(text: str) -> Tuple[int, str]:
    from education_matching import detect_resume_education_level
    return detect_resume_education_level(text)


def pct_to_points(pct: float, max_pts: int) -> int:
    """Convert a 0-100 match percentage into rubric points for a dimension."""
    return min(max_pts, max(0, round(pct * max_pts / 100)))


def score_supplementary(resume_text: str, profile: JDProfile) -> Dict[str, Tuple[float, str, List[str], List[str]]]:
    """Return 0-100 raw percentages for supplementary rubric dimensions."""
    norm = normalize_text(resume_text)

    growth_words = ["promoted", "lead", "senior", "head", "manager", "architect", "principal", "team lead"]
    growth_found = sort_alpha([w.title() for w in growth_words if w in norm])
    jd_senior = any(w in normalize_text(profile.full_text) for w in ["senior", "lead", "manager", "architect"])
    cg_pct = min(100.0, max(0.0, 38 + len(growth_found) * 18 + (15 if jd_senior and growth_found else 0)))
    cg_missing = [] if cg_pct >= 70 else (
        ["Senior/Lead role evidence"] if jd_senior else ["Career progression markers"]
    )

    metrics = len(re.findall(r"\d+%", resume_text)) + len(re.findall(r"\$\d+", resume_text))
    verbs = ["increased", "reduced", "saved", "optimized", "implemented", "delivered", "achieved", "improved"]
    verbs_found = sort_alpha([v.title() for v in verbs if v in norm])
    ach_pct = min(100.0, max(0.0, 38 + metrics * 18 + len(verbs_found) * 10))
    ach_present = sort_alpha(([f"{metrics} quantified metrics"] if metrics else []) + verbs_found[:6])
    ach_missing = [] if ach_pct >= 60 else ["Quantified achievements / KPIs"]

    wc = len(resume_text.split())
    comm_present = []
    if wc > 80:
        comm_present.append(f"Detailed resume ({wc} words)")
    if re.search(r"email|phone|contact|linkedin|@\w+\.\w+", norm):
        comm_present.append("Contact details present")
    if re.search(r"\b(?:summary|objective|profile)\b", norm):
        comm_present.append("Professional summary present")
    comm_pct = min(100.0, max(0.0, 50 + len(comm_present) * 25))
    comm_missing = [] if comm_pct >= 85 else ["Complete contact info", "Professional summary"]

    culture_found = sort_alpha([c for c in profile.culture_keywords if c.lower() in norm])
    if not profile.culture_keywords:
        cf_pct = 90.0
        cf_missing = []
    else:
        n_culture = len(profile.culture_keywords)
        cf_pct = min(100.0, max(0.0, (len(culture_found) / n_culture) * 80 + 20))
        cf_missing = sort_alpha([c for c in profile.culture_keywords if c not in culture_found][:4])

    return {
        "career_growth": (cg_pct, f"{len(growth_found)} growth markers.", growth_found, cg_missing),
        "achievements_impact": (ach_pct, f"{metrics} metrics, {len(verbs_found)} impact verbs.", ach_present, ach_missing),
        "communication_quality": (comm_pct, "Resume completeness.", sort_alpha(comm_present), comm_missing),
        "cultural_fit": (cf_pct, f"{len(culture_found)}/{len(profile.culture_keywords)} JD culture traits.", culture_found, cf_missing),
    }


def rubric_total(rubric: RubricScores) -> int:
    return min(100, max(0, sum([
        rubric.technical_skills.score, rubric.domain_expertise.score,
        rubric.experience_relevance.score, rubric.career_growth.score,
        rubric.education_learning.score, rubric.achievements_impact.score,
        rubric.communication_quality.score, rubric.cultural_fit.score,
    ])))


def build_rubric(
    profile: JDProfile,
    match: ResumeMatch,
    semantic_score: float,
    semantic_note: str,
    resume_text: str,
    weights: RubricWeights = DEFAULT_RUBRIC_WEIGHTS,
) -> Tuple[RubricScores, int]:
    supp = score_supplementary(resume_text, profile)
    exp_score = match.experience_raw if match.experience_raw else score_experience(profile, resume_text)[0]
    exp_present = match.experience_present or []
    exp_missing = match.experience_missing or []
    edu_score, edu_present, edu_missing = score_education(profile, resume_text, match)

    skill_pct = match.skill_pct
    ts = pct_to_points(skill_pct, weights.technical_skills)
    ts_present = sort_alpha(
        match.matched_skills
        + [f"Partial: {s}" for s in match.partial_skills]
        or (["Partial skill overlap"] if skill_pct > 30 else [])
    )
    ts_missing = sort_alpha(match.missing_skills or (["No JD skills extracted — re-upload detailed JD"] if not profile.skills else []))

    resp_pct = match.resp_pct
    if profile.responsibilities:
        combined_domain = min(100, resp_pct * 0.7 + semantic_score * 0.3)
    else:
        combined_domain = min(100, max(resp_pct, semantic_score))
    de = pct_to_points(combined_domain, weights.domain_expertise)
    de_present = sort_alpha(match.matched_responsibilities[:15] or (
        [f"Semantic JD alignment: {semantic_score}%"] if semantic_score >= 55 else []
    ))
    de_missing = sort_alpha(match.missing_responsibilities[:15] or (
        ["JD responsibilities not evidenced in resume"] if profile.responsibilities else []
    ))

    es = pct_to_points(exp_score, weights.experience_relevance)
    edu = pct_to_points(edu_score, weights.education_learning)
    cg_pct, cg_note, cg_p, cg_m = supp["career_growth"]
    ach_pct, ach_note, ach_p, ach_m = supp["achievements_impact"]
    comm_pct, comm_note, comm_p, comm_m = supp["communication_quality"]
    cf_pct, cf_note, cf_p, cf_m = supp["cultural_fit"]
    cg = pct_to_points(cg_pct, weights.career_growth)
    ach = pct_to_points(ach_pct, weights.achievements_impact)
    comm = pct_to_points(comm_pct, weights.communication_quality)
    cf = pct_to_points(cf_pct, weights.cultural_fit)

    rubric = RubricScores(
        technical_skills=RubricDimension(
            score=ts,
            justification=(
                f"JD skills weighted match {skill_pct}% "
                f"({len(match.matched_skills)} matched, {len(match.partial_skills)} partial, "
                f"{len(match.missing_skills)} missing). Rule: pct_to_points(skill_pct, {weights.technical_skills})."
            ),
            present=ts_present, missing=ts_missing,
        ),
        domain_expertise=RubricDimension(
            score=de,
            justification=f"JD responsibilities: {len(match.matched_responsibilities)}/{len(profile.responsibilities)} matched ({resp_pct}%). {semantic_note}",
            present=de_present, missing=de_missing,
        ),
        experience_relevance=RubricDimension(
            score=es,
            justification=f"Experience: resume vs JD ({profile.experience_text or 'not specified'}).",
            present=exp_present, missing=exp_missing,
        ),
        career_growth=RubricDimension(score=cg, justification=cg_note, present=cg_p, missing=cg_m),
        education_learning=RubricDimension(
            score=edu,
            justification=(
                f"Education: {', '.join(match.matched_education) or 'none matched'} "
                f"vs JD ({profile.education_requirement.summary if profile.education_requirement else 'any'})."
            ),
            present=edu_present, missing=edu_missing,
        ),
        achievements_impact=RubricDimension(score=ach, justification=ach_note, present=ach_p, missing=ach_m),
        communication_quality=RubricDimension(score=comm, justification=comm_note, present=comm_p, missing=comm_m),
        cultural_fit=RubricDimension(score=cf, justification=cf_note, present=cf_p, missing=cf_m),
    )
    total = rubric_total(rubric)
    if hasattr(match, "scoring_trace") and not FAST_SCORING:
        match.scoring_trace.extend([
            f"Rubric technical_skills: {ts}/{weights.technical_skills} pts (weighted skill_pct {skill_pct}%).",
            f"Rubric domain_expertise: {de}/{weights.domain_expertise} pts (combined {combined_domain:.1f}%).",
            f"Rubric experience_relevance: {es}/{weights.experience_relevance} pts (raw {exp_score}%).",
            f"Rubric education_learning: {edu}/{weights.education_learning} pts (raw {edu_score}%).",
            f"Rubric career_growth: {cg}/{weights.career_growth} pts (raw {cg_pct}%).",
            f"Rubric achievements_impact: {ach}/{weights.achievements_impact} pts (raw {ach_pct}%).",
            f"Rubric communication_quality: {comm}/{weights.communication_quality} pts (raw {comm_pct}%).",
            f"Rubric cultural_fit: {cf}/{weights.cultural_fit} pts (raw {cf_pct}%).",
            f"Rubric total before domain adj: {total}/100.",
        ])
    return rubric, total


def run_ats_pipeline(
    resume_text: str,
    jd: JobRole,
    similarity: float,
    embedding_model: Any = None,
    weights: RubricWeights = DEFAULT_RUBRIC_WEIGHTS,
) -> Dict:
    from models import SkillMatchDetail as SkillMatchDetailModel

    profile = get_jd_profile(jd)
    match = match_resume_to_jd(profile, resume_text, embedding_model)
    semantic_score, semantic_note = calculate_semantic_score(similarity)
    exp_score = match.experience_raw if match.experience_raw else score_experience(profile, resume_text)[0]
    edu_score, _, _ = score_education(profile, resume_text, match)

    ats_score_raw = round(
        match.skill_pct * 0.35 + match.resp_pct * 0.25 + semantic_score * 0.20
        + exp_score * 0.12 + edu_score * 0.08,
        1,
    )
    ats_score = round(max(0.0, ats_score_raw - match.domain_penalty * 0.5), 1)
    match.trace(
        f"ATS composite: ({match.skill_pct}×0.35 + {match.resp_pct}×0.25 + {semantic_score}×0.20 "
        f"+ {exp_score}×0.12 + {edu_score}×0.08) = {ats_score_raw}; "
        f"domain penalty -{match.domain_penalty * 0.5:.1f} -> {ats_score}."
    )

    rubric, total_score = build_rubric(profile, match, semantic_score, semantic_note, resume_text, weights)
    if match.domain_penalty > 0 and semantic_score >= 62:
        waived = match.domain_penalty
        match.domain_penalty = 0.0
        match.trace(
            f"Domain penalty waived ({waived:.0f} pts): overall semantic alignment {semantic_score}% ≥ 62%."
        )
    elif match.domain_penalty > 0:
        total_score = max(0, min(100, total_score - int(round(match.domain_penalty * 0.35))))
        match.trace(
            f"Rubric total adjusted for domain mismatch: -{int(round(match.domain_penalty * 0.35))} pts."
        )

    skill_detail_models = [
        SkillMatchDetailModel(
            skill_name=d.skill_name,
            status=d.status,
            match_type=d.match_type,
            confidence=d.confidence,
            evidence=d.evidence,
            section=d.section,
            reason=d.reason,
            priority=d.priority,
            credit=d.credit,
        )
        for d in match.skill_details
    ]

    return {
        "jd_skills": profile.skills,
        "jd_responsibilities": profile.responsibilities,
        "resume_skills": match.resume_skills,
        "matched_skills": match.matched_skills,
        "missing_skills": match.missing_skills,
        "partial_skills": match.partial_skills,
        "skill_details": skill_detail_models,
        "matched_responsibilities": match.matched_responsibilities,
        "missing_responsibilities": match.missing_responsibilities,
        "matched_education": match.matched_education,
        "missing_education": match.missing_education,
        "extra_skills": match.extra_skills,
        "skill_score": match.skill_pct,
        "semantic_score": semantic_score,
        "experience_score": exp_score,
        "education_score": edu_score,
        "responsibility_score": match.resp_pct,
        "ats_score": ats_score,
        "resume_domain": match.resume_domain,
        "jd_domain": match.jd_domain,
        "domain_penalty": match.domain_penalty,
        "scoring_trace": match.scoring_trace,
        "tech_experience_notes": match.tech_experience_notes,
        "rubric": rubric,
        "total_score": total_score,
        "rubric_weights": weights,
    }


def enrich_jd_from_text(jd: JobRole, jd_text: str) -> JobRole:
    profile = parse_jd_full(jd.model_copy(update={"responsibilities": jd_text}))
    _jd_cache[(jd.job_role or "") + "|" + jd_text[:500]] = profile

    updates: Dict[str, str] = {"responsibilities": jd_text}
    if profile.skills:
        updates["skills"] = ", ".join(profile.skills)
    if profile.experience_years > 0:
        updates["experience"] = f"Minimum {profile.experience_years:g} years experience"
    elif not jd.experience:
        updates["experience"] = jd.experience or "Relevant experience required"

    return jd.model_copy(update=updates)


def clear_jd_cache():
    _jd_cache.clear()

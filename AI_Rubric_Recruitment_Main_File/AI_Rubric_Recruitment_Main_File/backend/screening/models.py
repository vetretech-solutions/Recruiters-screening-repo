
# ============================================================
# models.py
# Pydantic models matching the REAL Neon DB schema exactly.
#
# resume_candidates columns:
#   resume_id, name, email, mobile_no, summary,
#   technical_skills, work_experience, project,
#   education, internship_experience, certification,
#   soft_skills, linkedin_url, github_url, created_at
#
# job_roles columns:
#   job_role, experience, project_duration,
#   project_initiative, skills, responsibilities,
#   bonus_skills, created_at
# ============================================================

from pydantic import BaseModel, Field
from typing import List, Optional, Any
from datetime import datetime


# ── Database Row Models ─────────────────────────────────────

class Candidate(BaseModel):
    """Maps 1-to-1 with the resume_candidates table."""
    resume_id: Any
    name: str
    emailid: Optional[str] = None
    mobile_no: Optional[str] = None
    summary: Optional[str] = None
    technical_skills: Optional[str] = None
    work_experience: Optional[str] = None
    project: Optional[str] = None
    education: Optional[str] = None
    internship_experience: Optional[str] = None
    certification: Optional[str] = None
    soft_skills: Optional[str] = None
    links: Optional[str] = None
    rtr_status: Optional[str] = "not_sent"
    agreement_id: Optional[str] = None

    class Config:
        from_attributes = True


class JobRole(BaseModel):
    """Maps 1-to-1 with the job_roles table."""
    job_role: str
    experience: Optional[str] = None
    project_duration: Optional[str] = None
    project: Optional[str] = None
    skills: Optional[str] = None
    responsibilities: Optional[str] = None
    bonus: Optional[str] = None

    class Config:
        from_attributes = True


# ── Rubric Score Models ─────────────────────────────────────

class RubricDimension(BaseModel):
    """A single rubric evaluation dimension."""
    score: int = Field(..., ge=0)
    justification: str
    present: List[str] = Field(default_factory=list, description="What the candidate has for this dimension")
    missing: List[str] = Field(default_factory=list, description="What the candidate lacks for this dimension")


class RubricWeights(BaseModel):
    """User-adjustable max points per rubric dimension (must sum to 100)."""
    technical_skills: int = Field(22, ge=0, le=100)
    domain_expertise: int = Field(8, ge=0, le=100)
    experience_relevance: int = Field(20, ge=0, le=100)
    career_growth: int = Field(10, ge=0, le=100)
    education_learning: int = Field(10, ge=0, le=100)
    achievements_impact: int = Field(15, ge=0, le=100)
    communication_quality: int = Field(5, ge=0, le=100)
    cultural_fit: int = Field(10, ge=0, le=100)

    def total(self) -> int:
        return (
            self.technical_skills + self.domain_expertise + self.experience_relevance
            + self.career_growth + self.education_learning + self.achievements_impact
            + self.communication_quality + self.cultural_fit
        )


DEFAULT_RUBRIC_WEIGHTS = RubricWeights()


class RubricScores(BaseModel):
    """Enhanced 8-dimension rubric scoring model (total = 100 points)."""
    technical_skills: RubricDimension      # skill matching
    domain_expertise: RubricDimension      # semantic/embedding similarity
    experience_relevance: RubricDimension  # experience matching
    career_growth: RubricDimension
    education_learning: RubricDimension    # education matching
    achievements_impact: RubricDimension
    communication_quality: RubricDimension
    cultural_fit: RubricDimension


class SkillMatchDetail(BaseModel):
    """Per-skill match report with evidence and explainability."""
    skill_name: str
    status: str = Field(..., description="Matched | Partial | Missing")
    match_type: str = Field(..., description="Exact | Alias | Fuzzy | Semantic | None")
    confidence: float = Field(..., ge=0, le=100)
    evidence: str = ""
    section: str = ""
    reason: str = ""
    priority: str = "medium"
    credit: float = Field(0.0, ge=0, le=1.0)


class ATSBreakdown(BaseModel):
    """ATS pipeline component scores and skill match details."""
    skill_score: float = Field(..., description="Weighted skill match % with partial credit")
    semantic_score: float = Field(..., description="Embedding cosine similarity * 100")
    experience_score: float = Field(..., description="Experience match score 0-100")
    education_score: float = Field(..., description="Education match score 0-100")
    ats_score: float = Field(..., description="Weighted ATS score (may include domain penalty)")
    jd_skills: List[str] = Field(default_factory=list)
    resume_skills: List[str] = Field(default_factory=list)
    matched_skills: List[str] = Field(default_factory=list)
    missing_skills: List[str] = Field(default_factory=list)
    partial_skills: List[str] = Field(default_factory=list)
    skill_details: List[SkillMatchDetail] = Field(default_factory=list)
    extra_skills: List[str] = Field(default_factory=list)
    jd_responsibilities: List[str] = Field(default_factory=list)
    matched_responsibilities: List[str] = Field(default_factory=list)
    missing_responsibilities: List[str] = Field(default_factory=list)
    matched_education: List[str] = Field(default_factory=list)
    missing_education: List[str] = Field(default_factory=list)
    responsibility_score: float = 0.0
    resume_domain: Optional[str] = None
    jd_domain: Optional[str] = None
    domain_penalty: float = 0.0
    scoring_trace: List[str] = Field(default_factory=list)
    tech_experience_notes: List[str] = Field(default_factory=list)


class CandidateEvaluation(BaseModel):
    """Full Rubric evaluation result for one candidate × one job role."""
    resume_id: Any
    candidate_name: str
    job_title: str
    dimension_scores: RubricScores
    total_score: int = Field(..., ge=0, le=100)
    ats_breakdown: Optional[ATSBreakdown] = None
    overall_summary: str
    strengths: List[str]
    areas_for_improvement: List[str]
    red_flags: Optional[List[str]] = None
    recommendation: str
    rtr_status: Optional[str] = "not_sent" # not_sent, pending, accepted
    agreement_id: Optional[str] = None


# ── Top 5 Selection Models ──────────────────────────────────

class TopCandidateEntry(BaseModel):
    rank: int
    candidate_name: str
    total_score: int
    reason: str


class TopCandidatesResult(BaseModel):
    job_title: str
    top_candidates: List[TopCandidateEntry]


# ── API Request / Response Models ──────────────────────────

class AnalyseJobRequest(BaseModel):
    """
    Request body for /analyse.
    Pass the job_role name, batch index, and Top N preference.
    """
    job_role: str = Field(..., description="The job_role value from the job_roles table.")
    batch_index: int = Field(0, description="The batch index to process (0-based).")
    batch_size: int = Field(5, description="Number of candidates per batch.")
    top_n: int = Field(5, description="Number of top candidates to return from this batch.")


class FullAnalysisResult(BaseModel):
    """Complete response returned from /analyse."""
    job_role: JobRole
    all_evaluations: List[CandidateEvaluation]
    top_5: TopCandidatesResult
    rubric_weights: Optional[RubricWeights] = None


# ── RTR Agreement Models ──────────────────────────────────

class RTRRequest(BaseModel):
    resume_id: str
    job_role: str
    candidate_name: Optional[str] = None
    candidate_email: Optional[str] = None

class RTRVerificationRequest(BaseModel):
    agreement_id: str
    candidate_email: Optional[str] = None
    otp: str

class RTRAcceptance(BaseModel):
    agreement_id: str
    candidate_name: str
    candidate_email: str
    signed_at: str
    ip_address: str
    status: str



class FinalSelectedCandidate(BaseModel):
    """Result saved to the database."""
    candidate_name: str
    job_title: str
    total_score: int
    overall_summary: str
    recommendation: str
    strengths: List[str]
    areas_for_improvement: List[str]
    created_at: Optional[datetime] = None

class HealthResponse(BaseModel):
    status: str
    db_connected: bool
    candidate_count: int
    job_role_count: int

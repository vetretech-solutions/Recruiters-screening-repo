import { getStoredToken } from "./session";
import { getScreeningApiBase } from "./backend-url";

function parseApiError(status: number, body: string): string {
  try {
    const err = JSON.parse(body) as { detail?: string | Array<{ msg?: string }> };
    if (typeof err.detail === "string" && err.detail) return err.detail;
    if (Array.isArray(err.detail)) {
      return err.detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
    }
  } catch {
    /* not JSON */
  }
  if (body.trim()) return body.slice(0, 300);
  return `Request failed (HTTP ${status})`;
}

function authHeaders(): Record<string, string> {
  const token = getStoredToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export interface JobRole {
  job_role: string;
  experience: string | null;
  project_duration?: string | null;
  project_initiative?: string | null;
  project?: string | null;
  skills: string | null;
  responsibilities: string | null;
  bonus_skills?: string | null;
  bonus?: string | null;
}

export interface RubricDimension {
  score: number;
  justification: string;
  present?: string[];
  missing?: string[];
}

export interface RubricScores {
  technical_skills: RubricDimension;
  domain_expertise: RubricDimension;
  experience_relevance: RubricDimension;
  career_growth: RubricDimension;
  education_learning: RubricDimension;
  achievements_impact: RubricDimension;
  communication_quality: RubricDimension;
  cultural_fit: RubricDimension;
}

export interface ATSBreakdown {
  skill_score: number;
  semantic_score: number;
  experience_score: number;
  education_score: number;
  ats_score: number;
  jd_skills: string[];
  resume_skills: string[];
  matched_skills: string[];
  missing_skills: string[];
  extra_skills: string[];
  jd_responsibilities?: string[];
  matched_responsibilities?: string[];
  missing_responsibilities?: string[];
  matched_education?: string[];
  missing_education?: string[];
  responsibility_score?: number;
}

export interface CandidateEvaluation {
  resume_id: string;
  candidate_name: string;
  job_title: string;
  dimension_scores: RubricScores;
  total_score: number;
  ats_breakdown?: ATSBreakdown;
  overall_summary: string;
  strengths: string[];
  areas_for_improvement: string[];
  red_flags?: string[];
  recommendation: string;
  rtr_status?: "not_sent" | "pending" | "accepted";
  agreement_id?: string;
}

export interface RubricWeights {
  technical_skills: number;
  domain_expertise: number;
  experience_relevance: number;
  career_growth: number;
  education_learning: number;
  achievements_impact: number;
  communication_quality: number;
  cultural_fit: number;
}

export const DEFAULT_RUBRIC_WEIGHTS: RubricWeights = {
  technical_skills: 22,
  domain_expertise: 8,
  experience_relevance: 20,
  career_growth: 10,
  education_learning: 10,
  achievements_impact: 15,
  communication_quality: 5,
  cultural_fit: 10,
};

export const RUBRIC_DIMENSION_KEYS = [
  "technical_skills",
  "domain_expertise",
  "experience_relevance",
  "career_growth",
  "education_learning",
  "achievements_impact",
  "communication_quality",
  "cultural_fit",
] as const;

export type RubricDimensionKey = (typeof RUBRIC_DIMENSION_KEYS)[number];

export function rubricWeightsTotal(weights: RubricWeights): number {
  return RUBRIC_DIMENSION_KEYS.reduce((sum, key) => sum + weights[key], 0);
}

export interface TopCandidateEntry {
  rank: number;
  candidate_name: string;
  total_score: number;
  reason: string;
}

export interface TopCandidatesResult {
  job_title: string;
  top_candidates: TopCandidateEntry[];
}

export interface FullAnalysisResult {
  job_role: JobRole;
  all_evaluations: CandidateEvaluation[];
  top_result?: TopCandidatesResult;
  top_5?: TopCandidatesResult;
  rubric_weights?: RubricWeights;
}

export interface RTRRequest {
  resume_id: string;
  job_role: string;
  candidate_name?: string;
  candidate_email?: string;
}

export interface RTRVerificationRequest {
  agreement_id: string;
  candidate_email?: string;
  otp: string;
}

export interface HealthResponse {
  status: string;
  module?: string;
}

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${getScreeningApiBase()}/health`, { headers: authHeaders() });
  if (!res.ok) throw new Error("Health check failed");
  return res.json();
}

export async function fetchJobRoles(): Promise<JobRole[]> {
  return [];
}

export async function parseJobRoles(file: File): Promise<JobRole[]> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${getScreeningApiBase()}/parse-job-roles`, {
    method: "POST",
    headers: authHeaders(),
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Failed to parse job roles");
  }
  return res.json();
}

export function getScreeningBatchLimit(): number {
  const base = getScreeningApiBase();
  return base.startsWith("http") ? 20 : 100;
}

export async function uploadAndAnalyseResumes(
  jobRole: JobRole,
  files: File[],
  offset: number,
  batchLimit: number,
  rubricWeights: RubricWeights,
  onUpdate: (data: Record<string, unknown>) => void,
  uploadSessionId?: string
): Promise<void> {
  const formData = new FormData();
  formData.append("job_role_json", JSON.stringify(jobRole));
  formData.append("rubric_weights_json", JSON.stringify(rubricWeights));
  formData.append("offset", offset.toString());
  formData.append("batch_limit", batchLimit.toString());
  if (uploadSessionId) {
    formData.append("upload_session_id", uploadSessionId);
  }
  if (offset > 0 && uploadSessionId) {
    formData.append("use_cached_files", "true");
  } else {
    files.forEach((file) => formData.append("files", file));
  }

  let res: Response;
  try {
    res = await fetch(`${getScreeningApiBase()}/upload-and-analyse`, {
      method: "POST",
      headers: authHeaders(),
      body: formData,
    });
  } catch (err) {
    const base = getScreeningApiBase();
    const hint =
      base.startsWith("http")
        ? "Check Railway is online and CORS allows your Vercel domain."
        : "BACKEND_URL is missing on Vercel — set it and redeploy.";
    throw new Error(
      err instanceof Error
        ? `Cannot reach backend (${base || "/api/screening"}). ${hint}`
        : "Cannot reach backend"
    );
  }

  if (!res.ok) {
    const body = await res.text();
    throw new Error(parseApiError(res.status, body));
  }

  const reader = res.body?.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let streamError: string | null = null;
  let sawDone = false;
  let scoredCount = 0;

  if (!reader) throw new Error("Could not read stream");

  const processLine = (line: string) => {
    if (!line.startsWith("data: ")) return;
    const jsonStr = line.replace("data: ", "").trim();
    if (!jsonStr) return;
    const data = JSON.parse(jsonStr);
    if (data.error) {
      streamError = data.error;
      return;
    }
    if (data.done) sawDone = true;
    if (data.batch && Array.isArray(data.batch)) scoredCount += data.batch.length;
    onUpdate(data);
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      if (buffer.trim()) buffer.split("\n").forEach(processLine);
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    lines.forEach(processLine);
  }
  if (streamError) throw new Error(streamError);
  if (!sawDone && scoredCount === 0) {
    throw new Error(
      "Analysis stopped before any resume was scored. On Railway, large ZIPs (200+ resumes) often run out of memory — try 5–10 resumes first."
    );
  }
}

export function recommendationColor(rec: string): string {
  switch (rec) {
    case "Highly Recommended": return "#22c55e";
    case "Recommended": return "#2563eb";
    case "Borderline": return "#eab308";
    case "Not Recommended": return "#ef4444";
    default: return "#64748b";
  }
}

export const SCORE_BUCKET_STYLES = {
  highly: { label: "Highly Recommended", range: "85+", color: "#16a34a", bg: "rgba(34, 197, 94, 0.1)", border: "rgba(34, 197, 94, 0.35)" },
  recommended: { label: "Recommended", range: "70–84", color: "#2563eb", bg: "rgba(37, 99, 235, 0.1)", border: "rgba(37, 99, 235, 0.35)" },
  borderline: { label: "Borderline", range: "50–69", color: "#ca8a04", bg: "rgba(234, 179, 8, 0.12)", border: "rgba(202, 138, 4, 0.35)" },
  below: { label: "Below 50", range: "< 50", color: "#dc2626", bg: "rgba(239, 68, 68, 0.1)", border: "rgba(220, 38, 38, 0.35)" },
} as const;

export function computeScoreDistribution(evaluations: { total_score: number }[]) {
  const total = evaluations.length;
  const highly = evaluations.filter((e) => e.total_score >= 85).length;
  const recommended = evaluations.filter((e) => e.total_score >= 70 && e.total_score < 85).length;
  const borderline = evaluations.filter((e) => e.total_score >= 50 && e.total_score < 70).length;
  const below = evaluations.filter((e) => e.total_score < 50).length;
  const pct = (n: number) => (total > 0 ? Math.round((n / total) * 100) : 0);
  return {
    total,
    highly,
    recommended,
    borderline,
    below,
    highlyPct: pct(highly),
    recommendedPct: pct(recommended),
    borderlinePct: pct(borderline),
    belowPct: pct(below),
  };
}

export function scoreGrade(score: number): string {
  if (score >= 85) return "Excellent";
  if (score >= 70) return "Good";
  if (score >= 50) return "Average";
  return "Below Average";
}

export function maxScoreForDimension(
  key: keyof RubricScores,
  weights: RubricWeights = DEFAULT_RUBRIC_WEIGHTS
): number {
  return weights[key as RubricDimensionKey];
}

export function dimensionLabel(key: keyof RubricScores): string {
  const labels: Record<keyof RubricScores, string> = {
    technical_skills: "Tech Skills",
    domain_expertise: "Domain",
    experience_relevance: "Experience",
    career_growth: "Growth",
    education_learning: "Education",
    achievements_impact: "Impact",
    communication_quality: "Comm.",
    cultural_fit: "Culture",
  };
  return labels[key];
}

export async function sendRTR(_req: RTRRequest): Promise<{ status: string; agreement_id: string }> {
  throw new Error("RTR email is not available yet. Contact your administrator.");
}

export async function verifyRTR(_req: RTRVerificationRequest): Promise<{ status: string; candidate_name: string }> {
  throw new Error("RTR verification is not available yet.");
}

export async function getRTRStatus(_agreementId: string): Promise<{ status: string }> {
  return { status: "not_sent" };
}

export async function analyseJobRole(): Promise<void> {
  throw new Error("Use upload-based analysis instead.");
}

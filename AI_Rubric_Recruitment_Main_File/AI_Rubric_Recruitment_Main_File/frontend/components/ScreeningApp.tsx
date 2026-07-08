// @ts-nocheck
"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { createPortal } from "react-dom";
import {
  fetchJobRoles,
  fetchHealth,
  analyseJobRole,
  uploadAndAnalyseResumes,
  getScreeningBatchLimit,
  parseJobRoles,
  recommendationColor,
  scoreGrade,
  maxScoreForDimension,
  dimensionLabel,
  sendRTR,
  verifyRTR,
  getRTRStatus,
  DEFAULT_RUBRIC_WEIGHTS,
  RUBRIC_DIMENSION_KEYS,
  rubricWeightsTotal,
  SCORE_BUCKET_STYLES,
  computeScoreDistribution,
  type JobRole,
  type FullAnalysisResult,
  type CandidateEvaluation,
  type HealthResponse,
  type RubricScores,
  type ATSBreakdown,
  type RubricWeights,
  type RubricDimensionKey,
} from "@/lib/screening-api";

function fileKey(f: File): string {
  return `${f.name}::${f.size}::${f.lastModified}`;
}

const ANALYSIS_PHASES = [
  { id: "prepare", label: "Preparing files and rubric" },
  { id: "extract", label: "Extracting resume text" },
  { id: "score", label: "Scoring candidates against JD" },
  { id: "finalize", label: "Building ranked results" },
] as const;

function phaseFromMessage(message: string): (typeof ANALYSIS_PHASES)[number]["id"] {
  const lower = message.toLowerCase();
  if (lower.includes("complete") || lower.includes("scored")) return "finalize";
  if (/scoring resumes?\s+\d+/i.test(message) || lower.includes("scoring")) return "score";
  if (lower.includes("found") || lower.includes("extract")) return "extract";
  return "prepare";
}

function isScoringStartSignal(data: Record<string, unknown>, message?: string): boolean {
  if (data.batch && Array.isArray(data.batch) && data.batch.length > 0) return true;
  const progress = typeof data.progress === "number" ? data.progress : 0;
  const total = typeof data.total === "number" ? data.total : 0;
  if (total > 0 && progress > 0) return true;
  if (message && /scoring resumes?\s+\d+/i.test(message)) return true;
  if (message && /^scored\s+\d+/i.test(message)) return true;
  return false;
}

function PreScoringLoader({ message }: { message: string }) {
  return (
    <div className="pre-scoring-loader fade-in-up">
      <div className="pre-scoring-loader-row">
        <span className="spinner" style={{ width: 24, height: 24, borderWidth: 2, flexShrink: 0 }} />
        <span>{message || "Uploading resumes and extracting text..."}</span>
      </div>
      <p className="pre-scoring-loader-hint">
        Preparing your files before scoring begins. Large ZIP uploads may take a few minutes.
      </p>
      <div className="pre-scoring-steps">
        <div className="pre-scoring-step pre-scoring-step--active">
          <span className="analysis-step-dot" />
          <span>Uploading files and rubric</span>
        </div>
        <div className="pre-scoring-step">
          <span className="analysis-step-dot" />
          <span>Extracting resume text</span>
        </div>
      </div>
    </div>
  );
}

function ScoringProgressBanner({
  current,
  total,
}: {
  current: number;
  total: number;
}) {
  const pct = total > 0 ? Math.min(100, Math.round((current / total) * 100)) : 0;
  return (
    <div className="scoring-progress-banner fade-in-up">
      <div className="scoring-progress-banner-row">
        <span className="spinner" style={{ width: 18, height: 18, borderWidth: 2, flexShrink: 0 }} />
        <span>
          {total > 0
            ? `Scoring resume ${current} of ${total} — results appear below as each candidate is processed`
            : "Scoring resumes — results appear below as each candidate is processed"}
        </span>
        {total > 0 && <span className="scoring-progress-pct">{pct}%</span>}
      </div>
      <div className="analysis-progress-track" style={{ marginTop: 10 }}>
        <div className="analysis-progress-fill" style={{ width: `${total > 0 ? Math.max(pct, 4) : 4}%` }} />
      </div>
    </div>
  );
}

function mergeUploadedFiles(existing: File[], incoming: File[]): File[] {
  const map = new Map(existing.map((f) => [fileKey(f), f]));
  incoming.forEach((f) => map.set(fileKey(f), f));
  return Array.from(map.values());
}

// ─────────────────────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────────────────────

function ScoreRing({ score }: { score: number }) {
  const radius = 40;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;
  const color =
    score >= 85 ? "#22c55e" :
    score >= 70 ? "#2563eb" :
    score >= 50 ? "#eab308" : "#ef4444";

  return (
    <div className="score-ring" style={{ width: 96, height: 96 }}>
      <svg width={96} height={96} viewBox="0 0 96 96" style={{ transform: "rotate(-90deg)" }}>
        <circle cx={48} cy={48} r={radius} fill="none"
          stroke="rgba(59,130,246,0.15)" strokeWidth={8} />
        <circle
          cx={48} cy={48} r={radius} fill="none"
          stroke={color} strokeWidth={8}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ transition: "stroke-dashoffset 1s cubic-bezier(0.34,1.2,0.64,1), stroke 0.3s" }}
        />
      </svg>
      <div style={{ position: "absolute", textAlign: "center" }}>
        <div style={{ fontSize: "1.4rem", fontWeight: 800, color, lineHeight: 1 }}>{score}</div>
        <div style={{ fontSize: "0.62rem", color: "#64748b", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>/100</div>
      </div>
    </div>
  );
}

function RubricBar({ label, score, max }: { label: string; score: number; max: number }) {
  const pct   = Math.round((score / max) * 100);
  const color = pct >= 85 ? "#22c55e" : pct >= 60 ? "#2563eb" : pct >= 40 ? "#eab308" : "#ef4444";
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
        <span style={{ fontSize: "0.8rem", color: "#6b7280", fontWeight: 500 }}>{label}</span>
        <span style={{ fontSize: "0.8rem", fontWeight: 700, color }}>
          {score}<span style={{ color: "#6b7280", fontWeight: 400 }}>/{max}</span>
        </span>
      </div>
      <div className="progress-bar-track">
        <div className="progress-bar-fill"
          style={{ width: `${pct}%`, background: `linear-gradient(90deg, ${color}99, ${color})` }} />
      </div>
    </div>
  );
}

function RecommendationBadge({ rec }: { rec: string }) {
  const color = recommendationColor(rec);
  return (
    <span className="badge" style={{
      background: `${color}22`, color,
      border: `1px solid ${color}66`,
      fontWeight: 700,
    }}>
      {rec}
    </span>
  );
}

function ScoreDistribution({ evaluations }: { evaluations: CandidateEvaluation[] }) {
  const dist = computeScoreDistribution(evaluations);
  if (dist.total === 0) return null;

  const buckets = [
    { key: "highly" as const, count: dist.highly, pct: dist.highlyPct },
    { key: "recommended" as const, count: dist.recommended, pct: dist.recommendedPct },
    { key: "borderline" as const, count: dist.borderline, pct: dist.borderlinePct },
    { key: "below" as const, count: dist.below, pct: dist.belowPct },
  ];

  return (
    <div className="score-distribution-panel fade-in-up">
      <div className="score-distribution-title">Score Distribution</div>
      <div className="score-distribution-grid">
        {buckets.map(({ key, count, pct }) => {
          const style = SCORE_BUCKET_STYLES[key];
          return (
            <div
              key={key}
              className="score-distribution-card"
              style={{ background: style.bg, borderColor: style.border }}
            >
              <div className="score-distribution-count" style={{ color: style.color }}>
                {count}
              </div>
              <div className="score-distribution-label">
                {style.label} ({style.range})
              </div>
              <div className="score-distribution-pct">{pct}% of screened</div>
            </div>
          );
        })}
      </div>
      <p className="score-distribution-note">
        Scores are strict and evidence-based: skills listed only in a skills section earn partial credit.
        In a bulk ZIP with mixed roles, only 10–20% scoring 70+ is normal — the engine is filtering
        for genuine fit, not inflating matches.
      </p>
    </div>
  );
}

function RubricWeightsEditor({
  weights,
  onChange,
}: {
  weights: RubricWeights;
  onChange: (weights: RubricWeights) => void;
}) {
  const total = rubricWeightsTotal(weights);
  const isValid = total === 100;

  const updateWeight = (key: RubricDimensionKey, value: number) => {
    onChange({ ...weights, [key]: Math.max(0, Math.min(100, value)) });
  };

  return (
    <div style={{
      textAlign: "left", maxWidth: 720, margin: "0 auto 28px",
      background: "#f8f9fb", borderRadius: 16,
      border: `1px solid ${isValid ? "rgba(59,130,246,0.3)" : "rgba(239,68,68,0.4)"}`,
      padding: "24px 28px",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16, flexWrap: "wrap", gap: 10 }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: "1rem", color: "#1a1a2e" }}>Rubric Dimension Weights</div>
          <div style={{ fontSize: "0.8rem", color: "#6b7280", marginTop: 4 }}>
            Adjust how much each dimension contributes to the total score (must sum to 100)
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{
            fontSize: "0.85rem", fontWeight: 800,
            color: isValid ? "#10b981" : "#ef4444",
            background: isValid ? "rgba(16,185,129,0.12)" : "rgba(239,68,68,0.12)",
            padding: "6px 14px", borderRadius: 8,
          }}>
            Total: {total}/100
          </span>
          <button
            type="button"
            onClick={() => onChange({ ...DEFAULT_RUBRIC_WEIGHTS })}
            style={{
              padding: "6px 14px", borderRadius: 8, fontSize: "0.78rem", fontWeight: 700,
              background: "rgba(59,130,246,0.1)", border: "1px solid rgba(59,130,246,0.3)",
              color: "#1d4ed8", cursor: "pointer",
            }}
          >
            Reset Default
          </button>
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        {RUBRIC_DIMENSION_KEYS.map((key) => (
          <div key={key} style={{ display: "grid", gridTemplateColumns: "140px 1fr 56px", gap: 12, alignItems: "center" }}>
            <span style={{ fontSize: "0.82rem", color: "#475569", fontWeight: 600 }}>
              {dimensionLabel(key)}
            </span>
            <input
              type="range"
              min={0}
              max={50}
              value={weights[key]}
              onChange={(e) => updateWeight(key, Number(e.target.value))}
              style={{ width: "100%", accentColor: "#3b82f6" }}
            />
            <input
              type="number"
              min={0}
              max={100}
              value={weights[key]}
              onChange={(e) => updateWeight(key, Number(e.target.value) || 0)}
              className="select-dropdown"
              style={{ width: 56, padding: "6px 8px", fontSize: "0.82rem", textAlign: "center", borderRadius: 8 }}
            />
          </div>
        ))}
      </div>
      {!isValid && (
        <div style={{ marginTop: 12, fontSize: "0.78rem", color: "#b91c1c", fontWeight: 600 }}>
          Weights must total exactly 100 before you can start analysis.
        </div>
      )}
    </div>
  );
}

function RubricDetailModal({
  ev,
  onClose,
  rubricWeights,
}: {
  ev: CandidateEvaluation;
  onClose: () => void;
  rubricWeights: RubricWeights;
}) {
  const [mounted, setMounted] = useState(false);
  const rubricKeys = Object.keys(ev.dimension_scores) as (keyof RubricScores)[];

  useEffect(() => {
    setMounted(true);
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [onClose]);

  if (!mounted) return null;

  const modal = (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, zIndex: 99999,
        background: "rgba(0,0,0,0.72)", backdropFilter: "blur(8px)",
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: "24px 16px",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "100%", maxWidth: 820, maxHeight: "90vh",
          background: "#ffffff",
          border: "1px solid #e0e4ea",
          borderRadius: 16, boxShadow: "0 12px 40px rgba(0,0,0,0.15)",
          display: "flex", flexDirection: "column", overflow: "hidden",
        }}
      >
        {/* Header */}
        <div style={{
          padding: "18px 22px", borderBottom: "1px solid rgba(59,130,246,0.15)",
          display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12,
        }}>
          <div>
            <div style={{ fontSize: "0.72rem", color: "#64748b", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>
              Full Rubric Breakdown — Present vs Missing
            </div>
            <div style={{ fontWeight: 800, fontSize: "1.1rem", color: "#1a1a2e" }}>{ev.candidate_name}</div>
            <div style={{ fontSize: "0.82rem", color: "#6b7280", marginTop: 4 }}>
              Rubric Score: <strong style={{ color: "#1d4ed8" }}>{ev.total_score}/100</strong>
              {ev.ats_breakdown && (
                <> · JD Skills {ev.ats_breakdown.matched_skills.length}/{ev.ats_breakdown.jd_skills.length}
                · Responsibilities {ev.ats_breakdown.matched_responsibilities?.length ?? 0}/{ev.ats_breakdown.jd_responsibilities?.length ?? 0}</>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              background: "rgba(239,68,68,0.15)", border: "1px solid rgba(239,68,68,0.35)",
              borderRadius: 8, padding: "8px 16px", color: "#b91c1c",
              fontSize: "0.82rem", fontWeight: 700, cursor: "pointer", flexShrink: 0,
            }}
          >
            Close
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: "20px 22px", overflowY: "auto", flex: 1 }}>

          {/* 8 Rubric Dimensions */}
          <div style={{ marginBottom: 24 }}>
            <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "#1e40af", marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.08em" }}>
              8-Dimension Rubric Analysis
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {rubricKeys.map((key) => {
                const dim = ev.dimension_scores[key];
                const max = maxScoreForDimension(key, rubricWeights);
                const pct = Math.round((dim.score / max) * 100);
                const color = pct >= 75 ? "#10b981" : pct >= 50 ? "#3b82f6" : pct >= 30 ? "#f59e0b" : "#ef4444";

                const present = [...(dim.present?.length ? dim.present : (
                  key === "technical_skills" ? (ev.ats_breakdown?.matched_skills ?? []) :
                  key === "domain_expertise" ? (ev.ats_breakdown?.matched_responsibilities ?? []) :
                  key === "education_learning" ? (ev.ats_breakdown?.matched_education ?? []) :
                  []
                ))].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
                const missing = [...(dim.missing?.length ? dim.missing : (
                  key === "technical_skills" ? (ev.ats_breakdown?.missing_skills ?? []) :
                  key === "domain_expertise" ? (ev.ats_breakdown?.missing_responsibilities ?? []) :
                  key === "education_learning" ? (ev.ats_breakdown?.missing_education ?? []) :
                  []
                ))].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));

                return (
                  <div key={key} style={{
                    background: "#f8f9fb", borderRadius: 12,
                    border: `1px solid ${color}33`, padding: "14px 16px",
                  }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                      <span style={{ fontWeight: 700, fontSize: "0.88rem", color: "#1a1a2e" }}>
                        {dimensionLabel(key)}
                      </span>
                      <span style={{ fontWeight: 800, fontSize: "0.95rem", color }}>
                        {dim.score}/{max} pts
                      </span>
                    </div>
                    <div style={{ height: 4, background: "#e5e7eb", borderRadius: 4, marginBottom: 10 }}>
                      <div style={{ height: "100%", width: `${pct}%`, background: color, borderRadius: 4 }} />
                    </div>
                    <div style={{ fontSize: "0.78rem", color: "#64748b", marginBottom: 10 }}>{dim.justification}</div>

                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                      <div style={{ background: "rgba(16,185,129,0.07)", borderRadius: 8, padding: "10px 12px", border: "1px solid rgba(16,185,129,0.2)" }}>
                        <div style={{ fontSize: "0.68rem", fontWeight: 700, color: "#10b981", marginBottom: 6, textTransform: "uppercase" }}>
                          Present ({present.length})
                        </div>
                        {present.length > 0 ? present.map((item, i) => (
                          <div key={i} style={{ fontSize: "0.78rem", color: "#047857", marginBottom: 3, display: "flex", gap: 6 }}>
                            <span>•</span><span>{item}</span>
                          </div>
                        )) : (
                          <span style={{ fontSize: "0.76rem", color: "#64748b" }}>Nothing significant detected</span>
                        )}
                      </div>
                      <div style={{ background: "rgba(239,68,68,0.07)", borderRadius: 8, padding: "10px 12px", border: "1px solid rgba(239,68,68,0.2)" }}>
                        <div style={{ fontSize: "0.68rem", fontWeight: 700, color: "#ef4444", marginBottom: 6, textTransform: "uppercase" }}>
                          Missing ({missing.length})
                        </div>
                        {missing.length > 0 ? missing.map((item, i) => (
                          <div key={i} style={{ fontSize: "0.78rem", color: "#b91c1c", marginBottom: 3, display: "flex", gap: 6 }}>
                            <span>•</span><span>{item}</span>
                          </div>
                        )) : (
                          <span style={{ fontSize: "0.76rem", color: "#64748b" }}>No significant gaps</span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* JD → Resume mapping details */}
          {ev.ats_breakdown && (
            <>
              <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "#1e40af", marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.08em" }}>
                JD → Resume Mapping (from uploaded JD)
              </div>

              {/* JD Skills */}
              {ev.ats_breakdown.jd_skills.length > 0 && (
                <div style={{ marginBottom: 16 }}>
                  <div style={{ fontSize: "0.72rem", color: "#6b7280", marginBottom: 8, fontWeight: 600 }}>
                    JD Skills — {ev.ats_breakdown.matched_skills.length} matched / {ev.ats_breakdown.missing_skills.length} missing
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    {[...ev.ats_breakdown.jd_skills].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" })).map((skill) => {
                      const isMatched = ev.ats_breakdown!.matched_skills.includes(skill);
                      return (
                        <div key={skill} style={{
                          display: "flex", alignItems: "center", gap: 10, padding: "7px 12px",
                          borderRadius: 8, fontSize: "0.82rem",
                          background: isMatched ? "rgba(16,185,129,0.1)" : "rgba(239,68,68,0.1)",
                          border: `1px solid ${isMatched ? "rgba(16,185,129,0.25)" : "rgba(239,68,68,0.25)"}`,
                        }}>
                          <span style={{ color: isMatched ? "#10b981" : "#ef4444", fontWeight: 700, fontSize: "0.75rem" }}>{isMatched ? "MATCH" : "GAP"}</span>
                          <span style={{ flex: 1, color: isMatched ? "#047857" : "#b91c1c", fontWeight: 600 }}>{skill}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* JD Responsibilities */}
              {(ev.ats_breakdown.jd_responsibilities?.length ?? 0) > 0 && (
                <div style={{ marginBottom: 16 }}>
                  <div style={{ fontSize: "0.72rem", color: "#6b7280", marginBottom: 8, fontWeight: 600 }}>
                    JD Responsibilities — {ev.ats_breakdown.matched_responsibilities?.length ?? 0} matched / {ev.ats_breakdown.missing_responsibilities?.length ?? 0} missing
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    {[...(ev.ats_breakdown.jd_responsibilities ?? [])].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" })).map((resp) => {
                      const isMatched = ev.ats_breakdown!.matched_responsibilities?.includes(resp);
                      return (
                        <div key={resp} style={{
                          display: "flex", alignItems: "flex-start", gap: 10, padding: "7px 12px",
                          borderRadius: 8, fontSize: "0.8rem",
                          background: isMatched ? "rgba(16,185,129,0.1)" : "rgba(239,68,68,0.1)",
                          border: `1px solid ${isMatched ? "rgba(16,185,129,0.25)" : "rgba(239,68,68,0.25)"}`,
                        }}>
                          <span style={{ color: isMatched ? "#10b981" : "#ef4444", fontWeight: 700, fontSize: "0.75rem", flexShrink: 0 }}>{isMatched ? "MATCH" : "GAP"}</span>
                          <span style={{ color: isMatched ? "#047857" : "#b91c1c" }}>{resp}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* JD Education */}
              {((ev.ats_breakdown.matched_education?.length ?? 0) + (ev.ats_breakdown.missing_education?.length ?? 0)) > 0 && (
                <div style={{ marginBottom: 16 }}>
                  <div style={{ fontSize: "0.72rem", color: "#6b7280", marginBottom: 8, fontWeight: 600 }}>JD Education Requirements</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {ev.ats_breakdown.matched_education?.map((e) => (
                      <span key={e} style={{ fontSize: "0.72rem", padding: "3px 10px", borderRadius: 4, background: "rgba(16,185,129,0.15)", color: "#047857", fontWeight: 600 }}>Met: {e}</span>
                    ))}
                    {ev.ats_breakdown.missing_education?.map((e) => (
                      <span key={e} style={{ fontSize: "0.72rem", padding: "3px 10px", borderRadius: 4, background: "rgba(239,68,68,0.15)", color: "#b91c1c", fontWeight: 600 }}>Missing: {e}</span>
                    ))}
                  </div>
                </div>
              )}

              {ev.ats_breakdown.extra_skills && ev.ats_breakdown.extra_skills.length > 0 && (
                <div style={{ background: "rgba(59,130,246,0.06)", border: "1px solid rgba(59,130,246,0.25)", borderRadius: 10, padding: "12px 14px" }}>
                  <div style={{ fontSize: "0.72rem", fontWeight: 700, color: "#3b82f6", marginBottom: 8 }}>+ Extra Resume Skills ({ev.ats_breakdown.extra_skills.length})</div>
                  {ev.ats_breakdown.extra_skills.map((s, i) => (
                    <div key={s} style={{ fontSize: "0.8rem", color: "#2563eb", marginBottom: 3 }}>{i + 1}. {s}</div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div style={{ padding: "14px 22px", borderTop: "1px solid rgba(59,130,246,0.15)", display: "flex", justifyContent: "flex-end" }}>
          <button onClick={onClose} className="btn-glow" style={{ padding: "10px 28px", borderRadius: 10, fontSize: "0.85rem" }}>
            Close
          </button>
        </div>
      </div>
    </div>
  );

  return createPortal(modal, document.body);
}

function ATSBreakdownPanel({ ats }: { ats: ATSBreakdown }) {
  const components = [
    { label: "Skill Match", score: ats.skill_score, weight: "40%", color: "#3b82f6", rubricMax: 22 },
    { label: "Semantic Similarity", score: ats.semantic_score, weight: "30%", color: "#8b5cf6", rubricMax: 8 },
    { label: "Experience", score: ats.experience_score, weight: "20%", color: "#3b82f6", rubricMax: 20 },
    { label: "Education", score: ats.education_score, weight: "10%", color: "#10b981", rubricMax: 10 },
  ];

  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        marginBottom: 12, flexWrap: "wrap", gap: 8,
      }}>
        <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "#1e40af", textTransform: "uppercase", letterSpacing: "0.08em" }}>
          ATS + Rubric Breakdown
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <div style={{
            fontSize: "0.85rem", fontWeight: 700, color: "#1d4ed8",
            background: "rgba(59,130,246,0.12)", border: "1px solid rgba(59,130,246,0.3)",
            borderRadius: 8, padding: "4px 12px",
          }}>
            ATS {ats.ats_score}%
          </div>
        </div>
      </div>

      {/* Score summary only — full skill lists in modal */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: 8 }}>
        {components.map((c) => (
          <div key={c.label} style={{
            background: "rgba(59,130,246,0.06)", borderRadius: 8, padding: "10px 12px",
            border: "1px solid rgba(59,130,246,0.12)",
          }}>
            <div style={{ fontSize: "0.68rem", color: "#64748b", fontWeight: 600, marginBottom: 4 }}>
              {c.label} ({c.weight} → {c.rubricMax}pts)
            </div>
            <div style={{ fontSize: "1.1rem", fontWeight: 800, color: c.color }}>{c.score}%</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function CandidateDetailCard({
  ev,
  rank,
  scoreRank,
  rubricWeights,
}: {
  ev: CandidateEvaluation;
  rank?: number;
  scoreRank?: number;
  rubricWeights: RubricWeights;
}) {
  const [expanded, setExpanded] = useState(false);
  const [showSkillModal, setShowSkillModal] = useState(false);
  const [rtrLoading, setRtrLoading] = useState(false);
  const [localRtrStatus, setLocalRtrStatus] = useState(ev.rtr_status || "not_sent");
  const [currentAgreementId, setCurrentAgreementId] = useState<string | undefined>(ev.agreement_id);
  
  const rubricKeys = Object.keys(ev.dimension_scores) as (keyof RubricScores)[];

  // 🔄 Poll backend for RTR status if it's currently pending
  useEffect(() => {
    let interval: any;
    if (localRtrStatus === "pending" && currentAgreementId) {
      interval = setInterval(async () => {
        try {
          const res = await getRTRStatus(currentAgreementId);
          if (res.status === "accepted") {
            setLocalRtrStatus("accepted");
            clearInterval(interval);
          }
        } catch (e) { console.error("Polling error:", e); }
      }, 5000); // Check every 5 seconds
    }
    return () => clearInterval(interval);
  }, [localRtrStatus, currentAgreementId]);

  const handleSendRTR = async () => {
    if (!ev.resume_id) {
      alert("Error: Resume ID is missing for this candidate.");
      return;
    }
    setRtrLoading(true);
    try {
      const res = await sendRTR({ 
        resume_id: ev.resume_id, 
        job_role: ev.job_title,
        candidate_name: ev.candidate_name 
      });
      if (res.status === "success") {
        setLocalRtrStatus("pending");
        setCurrentAgreementId(res.agreement_id);
      } else {
        alert("RTR Email failed to send. Check backend logs.");
      }
    } catch (err) {
      alert("Error sending RTR: " + (err as Error).message);
    } finally {
      setRtrLoading(false);
    }
  };

  return (
    <>
    {showSkillModal && (
      <RubricDetailModal ev={ev} onClose={() => setShowSkillModal(false)} rubricWeights={rubricWeights} />
    )}
    <div className="candidate-card fade-in-up" style={{ padding: "20px 24px", marginBottom: 14 }}>

      {/* ── Header ── */}
      <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
        {rank && (
          <div className={`medal-${rank}`} style={{
            width: 36, height: 36, borderRadius: "50%",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontWeight: 800, fontSize: "0.95rem", color: "white", flexShrink: 0,
          }}>{rank}</div>
        )}

        <div style={{ flex: 1, minWidth: 160 }}>
          <div style={{ fontWeight: 700, fontSize: "1rem", color: "#1a1a2e" }}>
            {ev.candidate_name}
          </div>
          <div style={{ fontSize: "0.8rem", color: "#64748b", marginTop: 2 }}>
            {scoreGrade(ev.total_score)} Candidate
            {!rank && scoreRank != null && (
              <span style={{ marginLeft: 8, color: "#2563eb", fontWeight: 600 }}>· #{scoreRank} by score</span>
            )}
          </div>
        </div>

        <ScoreRing score={ev.total_score} />

        <div style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "flex-end" }}>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {localRtrStatus === "accepted" ? (
            <span style={{ fontSize: "0.7rem", padding: "4px 8px", background: "rgba(34,197,94,0.15)", color: "#15803d", borderRadius: 4, fontWeight: 700 }}>CONFIRMED</span>
          ) : localRtrStatus === "pending" ? (
            <span style={{ fontSize: "0.7rem", padding: "4px 8px", background: "rgba(234,179,8,0.15)", color: "#a16207", borderRadius: 4, fontWeight: 700 }}>PENDING</span>
          ) : (
            <button 
              onClick={(e) => { e.stopPropagation(); handleSendRTR(); }} 
              disabled={rtrLoading}
              style={{ padding: "4px 10px", background: "rgba(37,99,235,0.1)", border: "1px solid rgba(37,99,235,0.35)", borderRadius: 4, color: "#2563eb", fontSize: "0.7rem", cursor: "pointer", fontWeight: 700 }}
            >
              {rtrLoading ? "SENDING..." : "SEND RTR"}
            </button>
          )}
          <RecommendationBadge rec={ev.recommendation} />
        </div>
          <button
            onClick={() => setExpanded(!expanded)}
            style={{
              background: "rgba(59,130,246,0.1)", border: "1px solid rgba(59,130,246,0.25)",
              borderRadius: 8, padding: "4px 14px",
              color: "#2563eb", fontSize: "0.78rem", fontWeight: 600,
              cursor: "pointer", transition: "all 0.2s",
            }}
          >
            {expanded ? "▲ Collapse" : "▼ Details"}
          </button>
        </div>
      </div>

      <div style={{ marginTop: 10, display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <span style={{ fontSize: "0.72rem", padding: "3px 10px", borderRadius: 6, background: "rgba(37,99,235,0.12)", color: "#2563eb", fontWeight: 700 }}>
            Rubric {ev.total_score}/100
          </span>
          {ev.ats_breakdown && (
            <>
              <span style={{ fontSize: "0.72rem", padding: "3px 10px", borderRadius: 6, background: "rgba(16,185,129,0.12)", color: "#047857", fontWeight: 600 }}>
                {ev.ats_breakdown.matched_skills.length} matched
              </span>
              {ev.ats_breakdown.missing_skills.length > 0 && (
                <span style={{ fontSize: "0.72rem", padding: "3px 10px", borderRadius: 6, background: "rgba(239,68,68,0.12)", color: "#b91c1c", fontWeight: 600 }}>
                  {ev.ats_breakdown.missing_skills.length} missing
                </span>
              )}
            </>
          )}
          <button
            onClick={(e) => { e.stopPropagation(); setShowSkillModal(true); }}
            style={{
              fontSize: "0.72rem", padding: "5px 14px", borderRadius: 6, cursor: "pointer",
              background: "rgba(37,99,235,0.14)", border: "1px solid rgba(37,99,235,0.45)",
              color: "#1d4ed8", fontWeight: 700, transition: "all 0.2s",
            }}
          >
            View Rubric Details
          </button>
        </div>

      {/* ── Rubric mini-bars ── */}
      <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px,1fr))", gap: "0 24px" }}>
        {(Object.keys(ev.dimension_scores) as (keyof RubricScores)[]).map((k) => (
          <RubricBar key={k} label={dimensionLabel(k)} score={ev.dimension_scores[k].score} max={maxScoreForDimension(k, rubricWeights)} />
        ))}
      </div>

      {/* ── Expanded details ── */}
      {expanded && (
        <div style={{ marginTop: 18, borderTop: "1px solid rgba(59,130,246,0.15)", paddingTop: 18 }}>

          {ev.ats_breakdown && <ATSBreakdownPanel ats={ev.ats_breakdown} />}

          <p style={{ fontSize: "0.875rem", color: "#6b7280", lineHeight: 1.7, marginBottom: 16 }}>
            {ev.overall_summary}
          </p>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
            <div>
              <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "#10b981", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>
                ✦ Strengths
              </div>
              {ev.strengths.map((s, i) => (
                <div key={i} style={{ display: "flex", gap: 8, marginBottom: 5, fontSize: "0.82rem", color: "#6b7280" }}>
                  <span style={{ color: "#10b981", flexShrink: 0 }}>▸</span>{s}
                </div>
              ))}
            </div>
            <div>
              <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "#f59e0b", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>
                ⚑ Areas to Improve
              </div>
              {ev.areas_for_improvement.map((a, i) => (
                <div key={i} style={{ display: "flex", gap: 8, marginBottom: 5, fontSize: "0.82rem", color: "#6b7280" }}>
                  <span style={{ color: "#f59e0b", flexShrink: 0 }}>▸</span>{a}
                </div>
              ))}
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {rubricKeys.map((k) => (
              <div key={k} style={{ background: "rgba(59,130,246,0.06)", borderRadius: 8, padding: "8px 12px" }}>
                <span style={{ fontSize: "0.75rem", fontWeight: 700, color: "#1e40af" }}>
                  {dimensionLabel(k)} ({ev.dimension_scores[k].score}/{maxScoreForDimension(k, rubricWeights)}):{" "}
                </span>
                <span style={{ fontSize: "0.79rem", color: "#6b7280" }}>
                  {ev.dimension_scores[k].justification}
                </span>
              </div>
            ))}
          </div>

          {ev.red_flags && ev.red_flags.length > 0 && (
            <div style={{ marginTop: 16, background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)", borderRadius: 8, padding: "12px 16px" }}>
              <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "#ef4444", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>
                Red Flags
              </div>
              {ev.red_flags.map((r, i) => (
                <div key={i} style={{ display: "flex", gap: 8, marginBottom: 4, fontSize: "0.82rem", color: "#b91c1c" }}>
                  <span style={{ color: "#ef4444", flexShrink: 0 }}>•</span>{r}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
    </>
  );
}

function TopPodium({
  result,
  allEvals,
  rubricWeights,
}: {
  result: FullAnalysisResult["top_result"];
  allEvals: CandidateEvaluation[];
  rubricWeights: RubricWeights;
}) {
  const evalMap: Record<string, CandidateEvaluation> = {};
  allEvals.forEach((e) => { evalMap[e.candidate_name] = e; });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {result.top_candidates.map((c) => {
        const ev = evalMap[c.candidate_name];
        return ev ? (
          <CandidateDetailCard key={c.rank} ev={ev} rank={c.rank} rubricWeights={rubricWeights} />
        ) : (
          <div key={c.rank} className="candidate-card" style={{ padding: "16px 20px" }}>
            <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
              <div className={`medal-${c.rank <= 3 ? c.rank : "other"}`} style={{
                width: 32, height: 32, borderRadius: "50%",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontWeight: 800, color: "white",
                background: c.rank === 1 ? "#fbbf24" : c.rank === 2 ? "#9ca3af" : c.rank === 3 ? "#b45309" : "#3b82f6"
              }}>{c.rank}</div>
              <div>
                <div style={{ fontWeight: 700, color: "#1a1a2e" }}>{c.candidate_name}</div>
                <div style={{ fontSize: "0.8rem", color: "#64748b" }}>{c.reason}</div>
              </div>
              <div style={{ marginLeft: "auto", fontWeight: 800, fontSize: "1.2rem", color: "#3b82f6" }}>
                {c.total_score}<span style={{ fontSize: "0.75rem", color: "#6b7280" }}>/100</span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main Page
// ─────────────────────────────────────────────────────────────────────────────

export default function HomePage() {
  const [health, setHealth]               = useState<HealthResponse | null>(null);
  const [jobRoles, setJobRoles]           = useState<JobRole[]>([]);
  const [selectedJobRole, setSelectedJobRole] = useState<string>("");
  const [topN, setTopN]                   = useState<number>(5);
  const [sortBy, setSortBy]               = useState<"score-desc" | "alpha">("score-desc");
  const [loading, setLoading]             = useState(false);
  const [result, setResult]               = useState<FullAnalysisResult | null>(null);
  const [error, setError]                 = useState<string | null>(null);
  const [currentStep, setCurrentStep] = useState<number>(1);
  const [selectedBatch, setSelectedBatch] = useState<number>(1);
  const [activeTab, setActiveTab] = useState<"results" | "overview">("overview");
  const [healthLoading, setHealthLoading] = useState(true);
  const [progress, setProgress] = useState<{ current: number; total: number }>({ current: 0, total: 0 });
  const [uploadedFiles, setUploadedFiles] = useState<File[]>([]);
  const [jdFile, setJdFile]               = useState<File | null>(null);
  const [processingMessage, setProcessingMessage] = useState<string>("");
  const [loadingLog, setLoadingLog] = useState<string[]>([]);
  const [analysisPhase, setAnalysisPhase] = useState<(typeof ANALYSIS_PHASES)[number]["id"]>("prepare");
  const [jdUploading, setJdUploading] = useState(false);
  const [scoringStarted, setScoringStarted] = useState(false);
  const [prepMessage, setPrepMessage] = useState("");
  const scoringStartedRef = useRef(false);
  const uploadSessionRef = useRef("");
  const [offset, setOffset] = useState<number>(0);
  const batchLimit = getScreeningBatchLimit();
  const [totalExtracted, setTotalExtracted] = useState<number>(0);
  const [rubricWeights, setRubricWeights] = useState<RubricWeights>({ ...DEFAULT_RUBRIC_WEIGHTS });
  const [lastScreenedFileCount, setLastScreenedFileCount] = useState(0);

  const alreadyScreenedCount = result?.all_evaluations.length ?? 0;
  const hasNewUploads = uploadedFiles.length > lastScreenedFileCount;
  const canRunAnalysis = uploadedFiles.length > 0
    && rubricWeightsTotal(rubricWeights) === 100
    && (alreadyScreenedCount === 0 || hasNewUploads);

  const loadInitialData = useCallback(async () => {
    setHealthLoading(true);
    try {
      const data = await fetchHealth();
      setHealth(data);
    } catch (err: unknown) {
      console.error("Health check failed", err);
    } finally {
      setHealthLoading(false);
    }
  }, []);

  useEffect(() => { loadInitialData(); }, [loadInitialData]);

  const appendLoadingMessage = (message: string) => {
    if (!message.trim()) return;
    setProcessingMessage(message);
    setAnalysisPhase(phaseFromMessage(message));
    setLoadingLog((prev) => (prev[prev.length - 1] === message ? prev : [...prev, message]));
  };

  const beginScoring = useCallback(() => {
    if (scoringStartedRef.current) return;
    scoringStartedRef.current = true;
    setScoringStarted(true);
    setAnalysisPhase("score");
    setCurrentStep(4);
    setActiveTab("overview");
  }, []);

  const handleJobRolesUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.[0]) {
      setJdUploading(true);
      setLoading(true);
      setProcessingMessage("Reading job description file...");
      setError(null);
      try {
        appendLoadingMessage("Parsing job roles from uploaded file...");
        const roles = await parseJobRoles(e.target.files[0]);
        setJobRoles(roles);
        if (roles.length > 0) setSelectedJobRole(roles[0].job_role);
        setJdFile(e.target.files[0]);
        appendLoadingMessage(`Found ${roles.length} job role(s).`);
        setCurrentStep(2);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "Failed to parse job roles");
      } finally {
        setLoading(false);
        setJdUploading(false);
        setProcessingMessage("");
      }
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const newFiles = Array.from(e.target.files);
      setUploadedFiles((prev) => mergeUploadedFiles(prev, newFiles));
      uploadSessionRef.current = "";
      e.target.value = "";
    }
  };

  const handleAnalyse = async () => {
    const activeJob = jobRoles.find((j) => j.job_role === selectedJobRole);
    if (!selectedJobRole || !activeJob) return;

    if (rubricWeightsTotal(rubricWeights) !== 100) {
      setError("Rubric weights must sum to exactly 100 before starting analysis.");
      return;
    }
    
    setLoading(true);
    setError(null);
    setLoadingLog([]);
    setAnalysisPhase("prepare");
    setScoringStarted(false);
    scoringStartedRef.current = false;
    setPrepMessage("");
    setProgress({ current: 0, total: 0 });

    const alreadyScreened = result?.all_evaluations.length ?? 0;
    const isContinuation = alreadyScreened > 0 && !hasNewUploads;

    if (!isContinuation || !uploadSessionRef.current) {
      uploadSessionRef.current = crypto.randomUUID();
    }

    const prepText = isContinuation
      ? `Preparing to continue from resume ${alreadyScreened + 1}...`
      : "Uploading resumes and extracting text...";
    setPrepMessage(prepText);
    setProcessingMessage(prepText);
    
    if (!isContinuation) {
      setResult({
        job_role: activeJob,
        all_evaluations: [],
        top_result: { job_title: activeJob.job_role, top_candidates: [] },
        rubric_weights: rubricWeights,
      });
      setTotalExtracted(0);
    }

    try {
      if (uploadedFiles.length === 0) {
        setError("Please upload resumes (ZIP/PDF/Word) first.");
        setLoading(false);
        return;
      }

      let currentOffset = isContinuation ? alreadyScreened : 0;
      let processedCount = isContinuation ? alreadyScreened : 0;

      while (true) {
        let nextOffset: number | null = null;

        await uploadAndAnalyseResumes(
          activeJob,
          uploadedFiles,
          currentOffset,
          batchLimit,
          rubricWeights,
          (data) => {
          const streamMessage = data.message ? String(data.message) : undefined;

          if (isScoringStartSignal(data, streamMessage)) {
            beginScoring();
          }

          if (data.total_extracted) {
            setTotalExtracted(data.total_extracted);
            if (!scoringStartedRef.current) {
              setPrepMessage(`Found ${data.total_extracted} resume(s). Starting scoring...`);
            }
          }
          if (data.extract_progress != null && data.extract_total) {
            setProgress({
              current: Number(data.extract_progress),
              total: Number(data.extract_total),
            });
          }
          if (data.progress != null && data.total) {
            setProgress({ current: Number(data.progress), total: Number(data.total) });
          }
          if (streamMessage && !scoringStartedRef.current) {
            setPrepMessage(streamMessage);
            setProcessingMessage(streamMessage);
          }
          if (data.batch) {
            processedCount += data.batch.length;
            setResult((prev) => {
              if (!prev) return prev;
              const existingNames = new Set(prev.all_evaluations.map((e) => e.candidate_name));
              const newEvals = data.batch!.filter((e) => !existingNames.has(e.candidate_name));
              return {
                ...prev,
                all_evaluations: [...prev.all_evaluations, ...newEvals],
                rubric_weights: data.rubric_weights ?? prev.rubric_weights ?? rubricWeights,
              };
            });
          }
          if (data.done) {
            if (data.rubric_weights) {
              setResult((prev) => prev ? { ...prev, rubric_weights: data.rubric_weights } : prev);
            }
            if (data.nextOffset != null) {
              nextOffset = data.nextOffset;
              setPrepMessage(`Scored ${processedCount} so far — loading next batch...`);
            }
          }
        },
          uploadSessionRef.current
        );

        if (nextOffset != null) {
          currentOffset = nextOffset;
          setOffset(currentOffset);
        } else {
          setOffset(0);
          setLastScreenedFileCount(uploadedFiles.length);
          setActiveTab("overview");
          setAnalysisPhase("finalize");
          break;
        }
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "An error occurred during analysis.");
    } finally {
      setLoading(false);
      setScoringStarted(false);
      scoringStartedRef.current = false;
      setPrepMessage("");
    }
  };

  const avgScore = result && result.all_evaluations.length > 0
    ? Math.round(result.all_evaluations.reduce((s, e) => s + e.total_score, 0) / result.all_evaluations.length)
    : 0;

  const roleEvaluations = result?.all_evaluations?.filter((ev) => ev.job_title === selectedJobRole) ?? [];

  return (
    <div className="screening-app">
      <div className="mesh-bg" />
      <div className="screening-app-inner">
        {(loading || !healthLoading) && (
          <div className="screening-status-bar">
            {loading && (
              <div className="screening-status-pill screening-status-pill--loading">
                {scoringStarted && progress.total > 0
                  ? `Scoring ${progress.current}/${progress.total}`
                  : prepMessage || processingMessage}
              </div>
            )}
            {!healthLoading && (
              <div className={`screening-status-pill screening-status-pill--${health?.status === "ok" ? "ok" : "error"}`}>
                <span className="status-dot" style={{ background: health?.status === "ok" ? "#3b82f6" : "#ef4444" }} />
                {health?.status === "ok" ? "API Ready" : "API Offline"}
              </div>
            )}
          </div>
        )}

        <main style={{ maxWidth: 1200, margin: "0 auto", padding: "1.75rem 1.5rem 80px" }}>
          <div style={{ marginBottom: 32 }} className="fade-in-up">
            <h2 style={{ fontSize: "1.5rem", fontWeight: 700, marginBottom: "0.25rem", color: "#1a1a2e" }}>
              Rubric Screening
            </h2>
            <p style={{ fontSize: "0.95rem", color: "#6b7280", lineHeight: 1.6 }}>
              Upload job requirements and candidate resumes for automated skill matching, rubric scoring, and ranked results.
            </p>
          </div>

          {/* STEP INDICATOR */}
          <div style={{ display: "flex", justifyContent: "center", gap: 12, marginBottom: 32 }}>
            {[1, 2, 3, 4].map(s => (
              <div key={s} style={{
                width: 40, height: 40, borderRadius: "50%",
                background: currentStep >= s ? "rgba(59,130,246,0.15)" : "#e5e7eb",
                border: currentStep >= s ? "2px solid #3b82f6" : "1px solid #d1d5db",
                color: currentStep >= s ? "#1d4ed8" : "#64748b",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontWeight: 800, fontSize: "0.9rem", transition: "all 0.3s ease"
              }}>
                {s}
              </div>
            ))}
          </div>

          {/* STEP 1: UPLOAD JOB ROLES */}
          {currentStep === 1 && (
            <div className="glass-card fade-in-up" style={{ padding: "40px", textAlign: "center" }}>
              <h2 style={{ fontSize: "1.25rem", fontWeight: 700, marginBottom: 8, color: "#1a1a2e" }}>Upload Job Description</h2>
              <p style={{ color: "#6b7280", marginBottom: 28, fontSize: "0.9rem" }}>Upload a ZIP, PDF, Word, CSV, or JSON file containing job requirements.</p>
              
              <div style={{
                maxWidth: 400, margin: "0 auto",
                border: "1px dashed #2563eb",
                background: "rgba(59,130,246,0.04)",
                borderRadius: 12, padding: "28px",
                cursor: "pointer", transition: "all 0.2s"
              }} onClick={() => document.getElementById('jd-upload')?.click()}>
                <span style={{ fontSize: "0.9rem", color: jdFile ? "#1a1a2e" : "#64748b", fontWeight: 600 }}>
                  {jdFile ? jdFile.name : "Select job description file"}
                </span>
                <input
                  id="jd-upload"
                  type="file"
                  accept=".zip,.pdf,.docx,.doc,.txt,.csv,.json"
                  style={{ display: "none" }}
                  onChange={handleJobRolesUpload}
                  disabled={jdUploading}
                />
              </div>
              {jdUploading && (
                <div className="upload-loading-inline">
                  <span className="spinner" style={{ width: 20, height: 20, borderWidth: 2 }} />
                  {processingMessage || "Parsing job description..."}
                </div>
              )}
            </div>
          )}

          {/* STEP 2: SELECT ROLE */}
          {currentStep === 2 && (
            <div className="glass-card fade-in-up" style={{ padding: "40px", textAlign: "center" }}>
              <h2 style={{ fontSize: "1.25rem", fontWeight: 700, marginBottom: 8, color: "#1a1a2e" }}>Select Target Role</h2>
              <p style={{ color: "#6b7280", marginBottom: 28, fontSize: "0.9rem" }}>Choose the job role to screen candidates against.</p>
              
              <select
                className="select-dropdown"
                value={selectedJobRole}
                onChange={(e) => setSelectedJobRole(e.target.value)}
                style={{ width: "100%", maxWidth: 400, padding: "14px 20px", marginBottom: 32, fontSize: "1.05rem" }}
              >
                {[...jobRoles].sort((a, b) => a.job_role.localeCompare(b.job_role, undefined, { sensitivity: "base" })).map((role) => (
                  <option key={role.job_role} value={role.job_role}>
                    {role.job_role}
                  </option>
                ))}
              </select>

              <button className="btn-glow" onClick={() => setCurrentStep(3)} style={{ padding: "12px 40px", borderRadius: 10, fontSize: "0.9rem" }}>
                Continue
              </button>
            </div>
          )}

          {/* STEP 3: CONFIGURE RUBRIC & UPLOAD RESUMES */}
          {currentStep === 3 && (
            <div className="glass-card fade-in-up" style={{ padding: "40px", textAlign: "center" }}>
              <h2 style={{ fontSize: "1.25rem", fontWeight: 700, marginBottom: 8, color: "#1a1a2e" }}>Configure Rubric & Upload Resumes</h2>
              <p style={{ color: "#6b7280", marginBottom: 20, fontSize: "0.9rem" }}>
                Set scoring weights, then upload resumes. Additional uploads are combined with previous batches.
              </p>

              {(result?.all_evaluations.length ?? 0) > 0 && (
                <div style={{
                  maxWidth: 520, margin: "0 auto 20px", padding: "12px 16px", borderRadius: 10,
                  background: "rgba(59,130,246,0.08)", border: "1px solid rgba(59,130,246,0.25)",
                  fontSize: "0.82rem", color: "#1d4ed8", textAlign: "left",
                }}>
                  <strong>{result!.all_evaluations.length}</strong> resume(s) already screened.
                  {hasNewUploads
                    ? " New files detected — run analysis to screen the combined batch."
                    : " Add more files to screen additional candidates."}
                </div>
              )}

              <RubricWeightsEditor weights={rubricWeights} onChange={setRubricWeights} />
              
              <div style={{
                maxWidth: 400, margin: "0 auto 20px",
                border: "1px dashed #2563eb",
                background: "rgba(59,130,246,0.04)",
                borderRadius: 12, padding: "28px",
                cursor: "pointer", transition: "all 0.2s"
              }} onClick={() => document.getElementById('file-upload')?.click()}>
                <span style={{ fontSize: "0.9rem", color: uploadedFiles.length > 0 ? "#1a1a2e" : "#64748b", fontWeight: 600 }}>
                  {uploadedFiles.length > 0
                    ? `${uploadedFiles.length} file(s) in queue`
                    : "Select resume files or ZIP"}
                </span>
                <input
                  id="file-upload"
                  type="file"
                  multiple
                  accept=".zip,.pdf,.docx,.doc"
                  style={{ display: "none" }}
                  onChange={handleFileChange}
                />
              </div>

              <div style={{ display: "flex", gap: 12, justifyContent: "center" }}>
                <button 
                  className="btn-glow"
                  onClick={() => handleAnalyse()}
                  disabled={loading || !canRunAnalysis}
                  style={{ padding: "14px 48px", borderRadius: 12, minWidth: 240 }}
                >
                  {(result?.all_evaluations.length ?? 0) > 0 ? "Screen All Resumes" : "Start Analysis"}
                </button>
              </div>
              {loading && !scoringStarted && (
                <PreScoringLoader message={prepMessage || processingMessage} />
              )}
            </div>
          )}

          {/* STEP 4: ANALYTICS */}
          {currentStep === 4 && (
            <div className="fade-in-up">
              <div style={{ display: "flex", gap: 12, marginBottom: 24, justifyContent: "center" }}>
                 <button className="btn-glow" onClick={() => setCurrentStep(3)} style={{ padding: "12px 32px", fontSize: "0.9rem" }}>
                   Back to Upload
                 </button>
                 <button 
                  className="btn-glow"
                  disabled={loading || !canRunAnalysis}
                  onClick={handleAnalyse} 
                  style={{ padding: "12px 32px", minWidth: 220, fontSize: "0.9rem" }}
                >
                  {hasNewUploads ? "Screen Additional Resumes" : alreadyScreenedCount > 0 ? "All Resumes Screened" : "Run Analysis"}
                 </button>
                 {loading && !scoringStarted && (
                   <PreScoringLoader message={prepMessage || processingMessage} />
                 )}
              </div>

              {loading && scoringStarted && (
                <ScoringProgressBanner
                  current={Math.max(progress.current, result?.all_evaluations?.length || 0)}
                  total={progress.total || totalExtracted}
                />
              )}

              <div style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))",
                gap: 14, marginBottom: 28,
              }}>
                {[
                  { label: "Files in Queue", value: `${uploadedFiles.length}` },
                  { label: "Resumes Found", value: `${totalExtracted || 0}` },
                  { label: "Candidates Screened", value: `${result?.all_evaluations?.length || 0}` },
                  { label: "Target Role", value: result?.job_role?.job_role || "", small: true },
                  { label: "Average Score", value: `${avgScore}/100` },
                ].map((s) => (
                  <div key={s.label} className="glass-card" style={{ padding: "16px 18px", textAlign: "center" }}>
                    <div style={{ fontWeight: 700, fontSize: s.small ? "0.82rem" : "1.35rem", color: "#1a1a2e", lineHeight: 1.2 }}>
                      {s.value}
                    </div>
                    <div style={{ fontSize: "0.7rem", color: "#64748b", fontWeight: 600, marginTop: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                      {s.label}
                    </div>
                  </div>
                ))}
              </div>

              {roleEvaluations.length > 0 && (
                <ScoreDistribution evaluations={roleEvaluations} />
              )}

              <div style={{ display: "flex", gap: 10, marginBottom: 20, alignItems: "center", flexWrap: "wrap" }}>
                <button 
                  className={`tab-btn ${activeTab === 'results' ? 'active' : ''}`}
                  onClick={() => setActiveTab("results")}
                >
                  Top Results
                </button>
                <button 
                  className={`tab-btn ${activeTab === 'overview' ? 'active' : ''}`}
                  onClick={() => setActiveTab("overview")}
                >
                  All Candidates ({result?.all_evaluations?.length || 0}{totalExtracted ? ` of ${totalExtracted}` : ""})
                </button>

                {activeTab === "results" && (
                  <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontSize: "0.78rem", color: "#64748b", fontWeight: 600 }}>Sort:</span>
                      <select
                        className="select-dropdown"
                        value={sortBy}
                        onChange={(e) => setSortBy(e.target.value as "score-desc" | "alpha")}
                        style={{ padding: "6px 12px", fontSize: "0.85rem", borderRadius: 8, minWidth: 150 }}
                      >
                        <option value="score-desc">Score: High → Low</option>
                        <option value="alpha">Name: A → Z</option>
                      </select>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontSize: "0.78rem", color: "#64748b", fontWeight: 600 }}>Show top:</span>
                      <select
                        className="select-dropdown"
                        value={topN}
                        onChange={(e) => setTopN(Number(e.target.value))}
                        style={{ padding: "6px 12px", fontSize: "0.85rem", borderRadius: 8, minWidth: 80 }}
                      >
                        <option value={5}>Top 5</option>
                        <option value={10}>Top 10</option>
                        <option value={20}>Top 20</option>
                        <option value={50}>Top 50</option>
                        <option value={9999}>All</option>
                      </select>
                    </div>
                  </div>
                )}

                {activeTab === "overview" && (
                  <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: "0.78rem", color: "#64748b", fontWeight: 600 }}>Sort:</span>
                    <select
                      className="select-dropdown"
                      value={sortBy}
                      onChange={(e) => setSortBy(e.target.value as "score-desc" | "alpha")}
                      style={{ padding: "6px 12px", fontSize: "0.85rem", borderRadius: 8, minWidth: 150 }}
                    >
                      <option value="score-desc">Score: High → Low</option>
                      <option value="alpha">Name: A → Z</option>
                    </select>
                  </div>
                )}
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                {(() => {
                  const filtered = roleEvaluations;
                  const byScore = [...filtered].sort((a, b) => b.total_score - a.total_score);
                  const baseList = activeTab === "results" ? byScore.slice(0, topN) : filtered;
                  const sorted = sortBy === "score-desc"
                    ? [...baseList].sort((a, b) => b.total_score - a.total_score)
                    : [...baseList].sort((a, b) => a.candidate_name.localeCompare(b.candidate_name, undefined, { sensitivity: "base" }));
                  const scoreRankMap = new Map(byScore.map((ev, idx) => [ev.candidate_name, idx + 1]));
                  const activeWeights = result?.rubric_weights ?? rubricWeights;
                  return sorted.map((ev, i) => (
                    <CandidateDetailCard
                      key={ev.candidate_name + i}
                      ev={ev}
                      rank={activeTab === "results" && sortBy === "score-desc" ? i + 1 : undefined}
                      scoreRank={scoreRankMap.get(ev.candidate_name)}
                      rubricWeights={activeWeights}
                    />
                  ));
                })()}
              </div>
            </div>
          )}

          {error && (
            <div className="glass-card fade-in-up" style={{ padding: "16px 20px", marginBottom: 20, border: "1px solid rgba(239,68,68,0.4)", color: "#b91c1c", textAlign: "center" }}>
              {error}
            </div>
          )}

          {!result && !loading && !error && currentStep === 4 && (
            <div className="glass-card fade-in-up" style={{ padding: "48px 32px", textAlign: "center" }}>
              <div style={{ fontFamily: "'Outfit', sans-serif", fontWeight: 700, fontSize: "1.1rem", color: "#1a1a2e", marginBottom: 8 }}>
                No Results Yet
              </div>
              <p style={{ color: "#64748b", fontSize: "0.9rem" }}>Upload resumes and run analysis to see screening results.</p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

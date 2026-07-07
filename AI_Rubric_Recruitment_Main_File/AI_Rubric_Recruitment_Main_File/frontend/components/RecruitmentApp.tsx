"use client";

import { useEffect, useRef, useState } from "react";
import {
  recruitmentApi,
  Applicant,
  ApplicantDetail,
  JobDescription,
  JobPosting,
  Platform,
  PlatformConnection,
  PlatformPost,
} from "@/lib/recruitment-api";
import { PortalUser } from "@/lib/portal-api";
import { getStoredUser } from "@/lib/session";

import JDPreview from "@/components/recruitment/JDPreview";
import JDEditor from "@/components/recruitment/JDEditor";
import ConnectModal from "@/components/recruitment/ConnectModal";

const PENDING_SHARE_JOB_KEY = "pending_share_job_id";

type Step = "create" | "preview" | "edit" | "platforms" | "applicants";

export default function RecruitmentApp() {
  const initialLoadDone = useRef(false);

  const [user, setUser] = useState<PortalUser | null>(null);
  const [ready, setReady] = useState(false);
  const [step, setStep] = useState<Step>("create");
  const [naturalLanguage, setNaturalLanguage] = useState("");
  const [job, setJob] = useState<JobPosting | null>(null);
  const [editedJd, setEditedJd] = useState<JobDescription | null>(null);
  const [jobs, setJobs] = useState<JobPosting[]>([]);
  const [platforms, setPlatforms] = useState<Platform[]>([]);
  const [connections, setConnections] = useState<PlatformConnection[]>([]);
  const [platformPosts, setPlatformPosts] = useState<PlatformPost[]>([]);
  const [applicants, setApplicants] = useState<Applicant[]>([]);
  const [viewApplicant, setViewApplicant] = useState<ApplicantDetail | null>(null);
  const [loadingApplicant, setLoadingApplicant] = useState(false);
  const [exportingApplicants, setExportingApplicants] = useState(false);
  const [loading, setLoading] = useState(false);
  const [posting, setPosting] = useState(false);
  const [selectedPlatform, setSelectedPlatform] = useState("");
  const [connectModalPlatform, setConnectModalPlatform] = useState<Platform | null>(null);
  const [lastPosted, setLastPosted] = useState<PlatformPost | null>(null);
  const [error, setError] = useState("");
  const [successMsg, setSuccessMsg] = useState("");
  useEffect(() => {
    const stored = getStoredUser();
    if (!stored) return;
    setUser(stored);
    setReady(true);

    if (initialLoadDone.current) return;
    initialLoadDone.current = true;

    const params = new URLSearchParams(window.location.search);
    const connected = params.get("connected");
    const via = params.get("via");
    const oauthError = params.get("oauth_error");

    if (connected) {
      setStep("platforms");
      window.history.replaceState({}, "", "/recruitment");
      recruitmentApi.getConnections().then((conns) => {
        setConnections(conns);
        const match = conns.find((c) => c.platform === connected);
        if (match?.is_oauth) {
          const label = match.account_email;
          const looksPlaceholder = label.includes("@connected") || label === "linkedin-user@connected";
          setSuccessMsg(
            via === "google"
              ? `LinkedIn authorized for ${label}`
              : looksPlaceholder
                ? "LinkedIn authorized. You can now click Post Job."
                : `LinkedIn connected as ${match.account_name || label}`
          );
        } else {
          setError("LinkedIn authorization did not complete. Please connect again.");
        }
      }).catch(() => {});
    }
    if (oauthError) {
      setError(decodeURIComponent(oauthError));
      setStep("platforms");
      window.history.replaceState({}, "", "/recruitment");
    }

    recruitmentApi.listJobs().then((list) => {
      setJobs(list);
      const pendingId = sessionStorage.getItem(PENDING_SHARE_JOB_KEY);
      if (pendingId) {
        const pending = list.find((j) => j.id === Number(pendingId));
        if (pending) {
          loadJob(pending, Boolean(connected));
        }
      }
    }).catch(() => {});
    recruitmentApi.getPlatforms().then(setPlatforms).catch(() => {});
    if (!connected) {
      recruitmentApi.getConnections().then(setConnections).catch(() => setConnections([]));
    }
  }, []);

  useEffect(() => {
    if (!user?.id) return;
    recruitmentApi.getConnections().then(setConnections).catch(() => setConnections([]));
  }, [user?.id]);

  useEffect(() => {
    if (job?.id) {
      sessionStorage.setItem(PENDING_SHARE_JOB_KEY, String(job.id));
    }
  }, [job?.id]);

  function getConnection(platformId: string) {
    return connections.find((c) => c.platform === platformId);
  }

  function canPostOnPlatform(platformId: string, conn?: PlatformConnection) {
    if (!conn) return false;
    if (platformId === "linkedin") return conn.can_post ?? conn.is_oauth;
    return true;
  }

  function connectionStatus(platformId: string, conn: PlatformConnection) {
    if (platformId === "linkedin") {
      return conn.is_oauth ? "✓ Authorized" : "⚠ Re-authorize on LinkedIn";
    }
    return "✓ Connected";
  }

  async function handleGenerate(e?: React.FormEvent) {
    e?.preventDefault();
    if (!naturalLanguage.trim() || naturalLanguage.length < 10) {
      setError("Please describe the role in at least 10 characters.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const result = await recruitmentApi.generateJD(naturalLanguage);
      setJob(result);
      setEditedJd(result.jd);
      setStep("preview");
      setJobs((prev) => [result, ...prev.filter((j) => j.id !== result.id)]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate JD");
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleGenerate();
    }
  }

  async function handleSaveEdit() {
    if (!job || !editedJd) return;
    setLoading(true);
    try {
      const updated = await recruitmentApi.updateJob(job.id, editedJd);
      setJob(updated);
      setEditedJd(updated.jd);
      setStep("preview");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setLoading(false);
    }
  }

  async function handleDownload() {
    if (!job) return;
    await recruitmentApi.downloadJob(job.id, job.title);
  }

  async function loadJob(j: JobPosting, openShare = false) {
    setJob(j);
    setEditedJd(j.jd);
    setNaturalLanguage(j.natural_language_input || "");
    sessionStorage.setItem(PENDING_SHARE_JOB_KEY, String(j.id));
    setError("");
    setSuccessMsg("");
    setLastPosted(null);
    setSelectedPlatform("");
    const [posts, apps, conns] = await Promise.all([
      recruitmentApi.getPlatformPosts(j.id).catch(() => []),
      recruitmentApi.getApplicants(j.id).catch(() => []),
      recruitmentApi.getConnections().catch(() => []),
    ]);
    setPlatformPosts(posts);
    setApplicants(apps);
    setConnections(conns);
    if (openShare) {
      await handleSharePost(j, posts, conns);
    } else {
      setStep("preview");
    }
  }

  async function handlePostPlatform(platformId?: string, forceRepost = false) {
    const target = platformId || selectedPlatform;
    if (!job || !target) {
      setError("Please select a platform to post to.");
      return;
    }
    const conn = getConnection(target);
    if (!conn) {
      const p = platforms.find((pl) => pl.id === target);
      if (p) setConnectModalPlatform(p);
      setError(`Connect your ${p?.name || target} account first.`);
      return;
    }
    if (!canPostOnPlatform(target, conn)) {
      const p = platforms.find((pl) => pl.id === target);
      if (p) setConnectModalPlatform(p);
      setError("Connect and authorize LinkedIn before sharing.");
      return;
    }
    const alreadyPosted = platformPosts.some((p) => p.platform === target);
    if (alreadyPosted && !forceRepost) {
      setError("Already shared on this platform. Click Share Again to publish a new post.");
      return;
    }
    setPosting(true);
    setError("");
    setLastPosted(null);
    setSelectedPlatform(target);
    try {
      const post = await recruitmentApi.postToPlatform(job.id, target, forceRepost);
      setPlatformPosts((prev) => {
        const filtered = prev.filter((p) => p.platform !== target);
        return [post, ...filtered];
      });
      const apps = await recruitmentApi.getApplicants(job.id).catch(() => []);
      setApplicants(apps);
      setJob({ ...job, status: "published" });
      setLastPosted(post);
      setSelectedPlatform("");
      setSuccessMsg(post.message || `Shared on ${target} as ${conn.account_email}`);
      setStep("platforms");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to post");
    } finally {
      setPosting(false);
    }
  }

  async function handleSharePost(
    targetJob?: JobPosting,
    knownPosts?: PlatformPost[],
    knownConns?: PlatformConnection[],
  ) {
    const activeJob = targetJob || job;
    if (!activeJob) {
      setError("Select a job first.");
      return;
    }

    setJob(activeJob);
    setEditedJd(activeJob.jd);
    sessionStorage.setItem(PENDING_SHARE_JOB_KEY, String(activeJob.id));
    setStep("platforms");
    setError("");
    setSuccessMsg("");
    setLastPosted(null);

    const [posts, conns] = await Promise.all([
      knownPosts ? Promise.resolve(knownPosts) : recruitmentApi.getPlatformPosts(activeJob.id).catch(() => []),
      knownConns ? Promise.resolve(knownConns) : recruitmentApi.getConnections().catch(() => []),
    ]);
    setPlatformPosts(posts);
    setConnections(conns);

    const platformList =
      platforms.length > 0 ? platforms : await recruitmentApi.getPlatforms().catch(() => []);
    if (!platforms.length && platformList.length) {
      setPlatforms(platformList);
    }

    const ready = platformList.filter((p) => {
      const conn = conns.find((c) => c.platform === p.id);
      return canPostOnPlatform(p.id, conn);
    });
    const toShare = ready.filter((p) => !posts.some((pp) => pp.platform === p.id));

    if (toShare.length === 0) {
      if (ready.length === 0) {
        setError("Connect a platform account first (e.g. LinkedIn), then click Share Post.");
      } else if (posts.length > 0) {
        setError(
          "Already shared on all connected platforms. Use Share Again below to publish a new post."
        );
      }
      return;
    }

    setPosting(true);
    try {
      let last: PlatformPost | null = null;
      for (const p of toShare) {
        setSelectedPlatform(p.id);
        const post = await recruitmentApi.postToPlatform(activeJob.id, p.id);
        last = post;
        setPlatformPosts((prev) => [post, ...prev.filter((x) => x.platform !== p.id)]);
      }
      if (last) {
        setLastPosted(last);
        setSuccessMsg(last.message || `Shared on ${last.platform}`);
      }
      setJob({ ...activeJob, status: "published" });
      setJobs((prev) =>
        prev.map((j) => (j.id === activeJob.id ? { ...j, status: "published" } : j))
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to share");
    } finally {
      setPosting(false);
      setSelectedPlatform("");
    }
  }

  async function handleDisconnect(platformId: string) {
    try {
      await recruitmentApi.disconnectPlatform(platformId);
      const conns = await recruitmentApi.getConnections();
      setConnections(conns);
      setSelectedPlatform("");
      setError("");
      setLastPosted(null);
      const name = platforms.find((p) => p.id === platformId)?.name || platformId;
      setSuccessMsg(
        `Disconnected from ${name}. Click "+ Connect Account" to link a different ${name} account.`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to disconnect");
    }
  }

  function handlePlatformClick(p: Platform) {
    setSelectedPlatform(p.id);
    setError("");
    setLastPosted(null);
    const conn = getConnection(p.id);
    if (!conn) {
      setConnectModalPlatform(p);
    }
  }

  function copyToClipboard(text: string) {
    navigator.clipboard.writeText(text);
    setSuccessMsg("Copied to clipboard!");
  }

  async function goToApplicants() {
    if (!job) return;
    setError("");
    const apps = await recruitmentApi.getApplicants(job.id);
    setApplicants(apps);
    setStep("applicants");
  }

  async function refreshApplicants() {
    if (!job) return;
    const apps = await recruitmentApi.getApplicants(job.id);
    setApplicants(apps);
  }

  async function openApplicant(applicant: Applicant) {
    if (!job) return;
    setLoadingApplicant(true);
    setError("");
    try {
      const detail = await recruitmentApi.getApplicant(job.id, applicant.id);
      setViewApplicant(detail);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load applicant");
    } finally {
      setLoadingApplicant(false);
    }
  }

  async function downloadApplicantResume(applicant: Applicant) {
    if (!job) return;
    setError("");
    try {
      await recruitmentApi.downloadApplicantResume(job.id, applicant.id, applicant.full_name);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not download resume");
    }
  }

  async function downloadApplicantApplication(applicant: Applicant) {
    if (!job) return;
    setError("");
    try {
      await recruitmentApi.downloadApplicantApplication(job.id, applicant.id, applicant.full_name);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not download application");
    }
  }

  async function exportApplicantsCsv() {
    if (!job) return;
    setExportingApplicants(true);
    setError("");
    try {
      await recruitmentApi.exportApplicants(job.id, job.title);
      setSuccessMsg("Applicants exported as CSV");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not export applicants");
    } finally {
      setExportingApplicants(false);
    }
  }

  async function goToPlatforms() {
    if (!job) return;
    setError("");
    setSuccessMsg("");
    setLastPosted(null);
    setSelectedPlatform("");
    try {
      const [posts, conns] = await Promise.all([
        recruitmentApi.getPlatformPosts(job.id),
        recruitmentApi.getConnections(),
      ]);
      setPlatformPosts(posts);
      setConnections(conns);
    } catch {
      setPlatformPosts([]);
    }
    setStep("platforms");
  }

  if (!ready || !user) {
    return (
      <div className="container" style={{ paddingTop: "4rem", color: "var(--muted)" }}>
        Loading...
      </div>
    );
  }

  const steps: { key: Step; label: string; num: string }[] = [
    { key: "create", label: "Describe Role", num: "01" },
    { key: "preview", label: "Review JD", num: "02" },
    { key: "edit", label: "Edit JD", num: "03" },
    { key: "platforms", label: "Share Post", num: "04" },
    { key: "applicants", label: "Applicants", num: "05" },
  ];

  const currentStepIndex = steps.findIndex((s) => s.key === step);

  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "270px 1fr", gap: "1.5rem" }}>
        <aside className="sidebar">
          <div className="sidebar-header">
            <h3>Job Postings</h3>
            <button
              className="btn btn-primary"
              style={{ padding: "0.3rem 0.7rem", fontSize: "0.78rem" }}
              onClick={() => {
                setJob(null);
                setEditedJd(null);
                setNaturalLanguage("");
                setStep("create");
                setPlatformPosts([]);
                setApplicants([]);
                setError("");
                setSuccessMsg("");
              }}
            >
              + New
            </button>
          </div>
          {jobs.length === 0 && (
            <p style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
              No jobs yet. Create your first JD.
            </p>
          )}
          {jobs.map((j) => (
            <div
              key={j.id}
              className={`list-item${job?.id === j.id ? " active" : ""}`}
              onClick={() => loadJob(j)}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600, fontSize: "0.9rem" }}>{j.title}</div>
                <div style={{ fontSize: "0.75rem", color: "var(--muted)" }}>
                  {new Date(j.created_at).toLocaleDateString()}
                </div>
              </div>
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "flex-end",
                  gap: "0.35rem",
                  flexShrink: 0,
                }}
              >
                <span className={`badge badge-${j.status === "published" ? "published" : "draft"}`}>
                  {j.status}
                </span>
                <button
                  type="button"
                  className="btn btn-secondary"
                  style={{ padding: "0.25rem 0.55rem", fontSize: "0.7rem" }}
                  onClick={(e) => {
                    e.stopPropagation();
                    void handleSharePost(j);
                  }}
                >
                  Share Post
                </button>
              </div>
            </div>
          ))}
        </aside>

        <main>
          <div className="step-indicator">
            {steps.map((s, i) => {
              const canJump =
                job &&
                (s.key === "preview" ||
                  s.key === "edit" ||
                  s.key === "platforms" ||
                  s.key === "applicants");
              return (
                <div
                  key={s.key}
                  className={`step ${i === currentStepIndex ? "active" : ""} ${i < currentStepIndex ? "done" : ""}`}
                  style={canJump ? { cursor: "pointer" } : undefined}
                  onClick={() => {
                    if (!job || !canJump) return;
                    if (s.key === "platforms") goToPlatforms();
                    else if (s.key === "applicants") goToApplicants();
                    else setStep(s.key);
                  }}
                >
                  <span className="step-num">{s.num}</span>
                  {s.label}
                </div>
              );
            })}
          </div>

          {error && <p className="error" style={{ marginBottom: "1rem" }}>{error}</p>}
          {successMsg && !error && (
            <div className="success-banner" style={{ marginBottom: "1rem" }}>
              <h4>✓ {successMsg}</h4>
            </div>
          )}

          {step === "create" && (
            <div className="card card-glow">
              <div className="page-header">
                <div>
                  <h2>Describe the Role</h2>
                  <p>
                    Type job details in natural language — title, skills, experience, location.
                    Press <strong>Enter</strong> to generate.
                  </p>
                </div>
              </div>
              <form onSubmit={handleGenerate}>
                <textarea
                  className="textarea"
                  value={naturalLanguage}
                  onChange={(e) => setNaturalLanguage(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="e.g. We need a Senior Python Developer with 5 years experience in FastAPI, AWS, and microservices. Remote position, Bangalore based company, salary 15-20 LPA..."
                  rows={7}
                  autoFocus
                />
                <div style={{ marginTop: "1.25rem", display: "flex", gap: "0.75rem", alignItems: "center" }}>
                  <button className="btn btn-primary" type="submit" disabled={loading}>
                    {loading ? (
                      <>
                        <span className="spinner" /> Generating...
                      </>
                    ) : (
                      "✨ Generate Job Description"
                    )}
                  </button>
                  <span style={{ color: "var(--muted)", fontSize: "0.8rem" }}>or press Enter</span>
                </div>
              </form>
            </div>
          )}

          {step === "preview" && job && editedJd && (
            <div className="card">
              <div className="page-header">
                <div>
                  <h2>{job.title}</h2>
                  <p>Review the job description, then share it to LinkedIn and other platforms.</p>
                </div>
                <div style={{ display: "flex", gap: "0.5rem", flexShrink: 0, flexWrap: "wrap" }}>
                  <button
                    className="btn btn-primary"
                    onClick={() => handleSharePost()}
                    disabled={posting}
                  >
                    {posting ? <><span className="spinner" /> Sharing...</> : "Share Post"}
                  </button>
                  <button className="btn btn-secondary" onClick={handleDownload}>
                    Download
                  </button>
                  <button className="btn btn-secondary" onClick={() => setStep("edit")}>
                    Edit
                  </button>
                </div>
              </div>
              {platformPosts.length > 0 && (
                <div
                  style={{
                    marginBottom: "1rem",
                    padding: "0.75rem 1rem",
                    background: "var(--surface2)",
                    borderRadius: 8,
                    border: "1px solid var(--border)",
                  }}
                >
                  <strong>Already shared on:</strong>{" "}
                  {platformPosts.map((p) => p.platform).join(", ")}
                  <button
                    type="button"
                    className="btn btn-secondary"
                    style={{ marginLeft: "0.75rem", padding: "0.25rem 0.65rem", fontSize: "0.8rem" }}
                    onClick={() => handleSharePost()}
                  >
                    Share to more platforms
                  </button>
                </div>
              )}
              <JDPreview jd={editedJd} />
            </div>
          )}

          {step === "edit" && job && editedJd && (
            <div className="card">
              <div className="page-header">
                <div>
                  <h2>Edit Job Description</h2>
                  <p>Make changes to the generated content.</p>
                </div>
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                  <button
                    className="btn btn-secondary"
                    onClick={() => handleSharePost()}
                    disabled={posting}
                  >
                    Share Post
                  </button>
                  <button className="btn btn-secondary" onClick={() => setStep("preview")}>
                    Cancel
                  </button>
                  <button className="btn btn-primary" onClick={handleSaveEdit} disabled={loading}>
                    {loading ? <span className="spinner" /> : "Save Changes"}
                  </button>
                  <button className="btn btn-secondary" onClick={handleDownload}>
                    Download
                  </button>
                </div>
              </div>
              <JDEditor jd={editedJd} onChange={setEditedJd} />
            </div>
          )}

          {step === "platforms" && job && (
            <div className="card">
              <div className="page-header">
                <div>
                  <h2>Share Post — {job.title}</h2>
                  <p>
                    Each recruiter connects <strong>their own</strong> LinkedIn account — you do
                    <strong> not </strong> need to request LinkedIn access for every person.
                  </p>
                </div>
                <button className="btn btn-primary" onClick={goToApplicants}>
                  View Applicants (
                  {applicants.length ||
                    platformPosts.reduce((s, p) => s + p.applicant_count, 0)}
                  )
                </button>
              </div>

              <div className="platform-grid" style={{ marginBottom: "1.5rem" }}>
                {platforms.map((p) => {
                  const conn = getConnection(p.id);
                  const isPosted = platformPosts.some((pp) => pp.platform === p.id);
                  const isSelected = selectedPlatform === p.id;

                  return (
                    <div
                      key={p.id}
                      className={`platform-card ${p.logo} ${isSelected ? "selected" : ""} ${isPosted ? "posted" : ""}`}
                      onClick={() => !isPosted && handlePlatformClick(p)}
                      style={{ cursor: isPosted ? "default" : "pointer" }}
                    >
                      <div className={`platform-icon ${p.logo}`}>
                        {p.name.slice(0, 2).toUpperCase()}
                      </div>
                      <div className="platform-name">{p.name}</div>

                      {isPosted ? (
                        <>
                          <div className="connected-info">✓ Posted</div>
                          {conn && (
                            <div className="connected-email">{conn.account_email}</div>
                          )}
                          {conn && canPostOnPlatform(p.id, conn) && (
                            <button
                              className="btn btn-primary"
                              style={{ width: "100%", marginTop: "0.5rem", fontSize: "0.85rem" }}
                              onClick={(e) => {
                                e.stopPropagation();
                                handlePostPlatform(p.id, true);
                              }}
                              disabled={posting}
                            >
                              {posting && selectedPlatform === p.id ? (
                                <><span className="spinner" /> Sharing...</>
                              ) : (
                                "Share Again"
                              )}
                            </button>
                          )}
                          {conn ? (
                            <>
                              <button
                                className="btn btn-danger"
                                style={{ width: "100%", marginTop: "0.5rem", fontSize: "0.85rem" }}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleDisconnect(p.id);
                                }}
                              >
                                Disconnect
                              </button>
                              {p.id === "linkedin" && (
                                <button
                                  className="btn btn-secondary"
                                  style={{ width: "100%", marginTop: "0.5rem", fontSize: "0.85rem" }}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setConnectModalPlatform(p);
                                  }}
                                >
                                  Switch LinkedIn Account
                                </button>
                              )}
                            </>
                          ) : (
                            <button
                              className="btn btn-connect"
                              style={{ width: "100%", marginTop: "0.75rem" }}
                              onClick={(e) => {
                                e.stopPropagation();
                                setConnectModalPlatform(p);
                              }}
                            >
                              + Connect Account
                            </button>
                          )}
                        </>
                      ) : conn ? (
                        <>
                          <div className="connected-info">
                            {connectionStatus(p.id, conn)}
                          </div>
                          <div className="connected-email">{conn.account_email}</div>
                          {p.id === "linkedin" && !canPostOnPlatform(p.id, conn) && (
                            <p style={{ fontSize: "0.75rem", color: "var(--danger, #c0392b)", marginTop: "0.35rem" }}>
                              Complete LinkedIn sign-in to post jobs
                            </p>
                          )}
                          <button
                            className="btn btn-primary"
                            style={{ width: "100%", marginTop: "0.75rem", fontSize: "0.85rem" }}
                            onClick={(e) => {
                              e.stopPropagation();
                              handlePostPlatform(p.id);
                            }}
                            disabled={posting || !canPostOnPlatform(p.id, conn)}
                          >
                            {posting && selectedPlatform === p.id ? (
                              <><span className="spinner" /> Posting...</>
                            ) : (
                              "Share Post"
                            )}
                          </button>
                          <button
                            className="btn btn-danger"
                            style={{ marginTop: "0.5rem" }}
                            onClick={(e) => {
                              e.stopPropagation();
                              handleDisconnect(p.id);
                            }}
                          >
                            Disconnect
                          </button>
                          {p.id === "linkedin" && (
                            <button
                              className="btn btn-secondary"
                              style={{ width: "100%", marginTop: "0.5rem", fontSize: "0.85rem" }}
                              onClick={(e) => {
                                e.stopPropagation();
                                setConnectModalPlatform(p);
                              }}
                            >
                              Switch LinkedIn Account
                            </button>
                          )}
                        </>
                      ) : (
                        <button
                          className="btn btn-connect"
                          onClick={(e) => {
                            e.stopPropagation();
                            setConnectModalPlatform(p);
                          }}
                        >
                          + Connect Account
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>

              {lastPosted && (
                <div className="success-banner">
                  <h4>
                    ✓ {lastPosted.message || `Posted to ${lastPosted.platform}`}
                  </h4>
                  {(lastPosted.account_name || lastPosted.account_email) && (
                    <p style={{ fontSize: "0.9rem", marginBottom: "0.5rem" }}>
                      <strong>Posted as:</strong>{" "}
                      {lastPosted.account_name || lastPosted.account_email}
                      {lastPosted.account_email && lastPosted.account_name && (
                        <span style={{ color: "var(--muted)" }}>
                          {" "}({lastPosted.account_email})
                        </span>
                      )}
                    </p>
                  )}
                  {lastPosted.external_url && lastPosted.external_post_id && (
                    <p style={{ fontSize: "0.9rem", marginBottom: "0.75rem" }}>
                      <strong>View on {lastPosted.platform}:</strong>{" "}
                      <a href={lastPosted.external_url} target="_blank" rel="noopener noreferrer">
                        {lastPosted.external_url}
                      </a>
                    </p>
                  )}
                  {lastPosted.account_url && (
                    <p style={{ fontSize: "0.9rem", marginBottom: "0.75rem" }}>
                      <strong>Your page:</strong>{" "}
                      <a href={lastPosted.account_url} target="_blank" rel="noopener noreferrer">
                        {lastPosted.account_url}
                      </a>
                    </p>
                  )}
                  <p style={{ fontSize: "0.9rem", marginBottom: "0.75rem" }}>
                    <strong>Candidate apply link:</strong>
                  </p>
                  <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center" }}>
                    <code
                      style={{
                        flex: 1,
                        padding: "0.5rem 0.75rem",
                        background: "var(--bg)",
                        borderRadius: 8,
                        fontSize: "0.85rem",
                        wordBreak: "break-all",
                      }}
                    >
                      {lastPosted.apply_url}
                    </code>
                    <button
                      className="btn btn-secondary"
                      onClick={() => copyToClipboard(lastPosted.apply_url)}
                    >
                      Copy
                    </button>
                  </div>
                </div>
              )}

              {platformPosts.length > 0 && (
                <div style={{ marginTop: "1.5rem" }}>
                  <h3 style={{ fontSize: "1rem", marginBottom: "0.75rem", fontWeight: 700 }}>
                    Posted Platforms
                  </h3>
                  <table className="applicant-table">
                    <thead>
                      <tr>
                        <th>Platform</th>
                        <th>Posted As</th>
                        <th>Applicants</th>
                        <th>Posted On</th>
                        <th>Job Link</th>
                        <th>Apply Link</th>
                      </tr>
                    </thead>
                    <tbody>
                      {platformPosts.map((pp) => (
                        <tr key={pp.id}>
                          <td style={{ fontWeight: 600, textTransform: "capitalize" }}>
                            {pp.platform}
                          </td>
                          <td>
                            {pp.account_name || pp.account_email || (
                              <span style={{ color: "var(--muted)" }}>—</span>
                            )}
                          </td>
                          <td>{pp.applicant_count}</td>
                          <td style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
                            {new Date(pp.posted_at).toLocaleString()}
                          </td>
                          <td>
                            {pp.external_url && pp.external_post_id ? (
                              <a
                                href={pp.external_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                style={{ fontSize: "0.75rem" }}
                              >
                                View
                              </a>
                            ) : (
                              <span style={{ color: "var(--muted)", fontSize: "0.75rem" }}>—</span>
                            )}
                          </td>
                          <td>
                            <button
                              type="button"
                              className="btn btn-secondary"
                              style={{ padding: "0.2rem 0.6rem", fontSize: "0.75rem" }}
                              onClick={() => copyToClipboard(pp.apply_url)}
                            >
                              Copy link
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <div style={{ marginTop: "1.5rem" }}>
                <button className="btn btn-secondary" onClick={() => setStep("preview")}>
                  ← Back to JD
                </button>
              </div>
            </div>
          )}

          {step === "applicants" && job && (
            <div className="card">
              <div className="page-header">
                <div>
                  <h2>Applicants for {job.title}</h2>
                  <p>Candidates who applied through your posted platforms (including LinkedIn)</p>
                </div>
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                  <button className="btn btn-secondary" onClick={refreshApplicants}>
                    Refresh
                  </button>
                  {applicants.length > 0 && (
                    <button
                      className="btn btn-secondary"
                      onClick={exportApplicantsCsv}
                      disabled={exportingApplicants}
                    >
                      {exportingApplicants ? "Exporting..." : "Download CSV"}
                    </button>
                  )}
                  <button className="btn btn-secondary" onClick={goToPlatforms}>
                    ← Platforms
                  </button>
                </div>
              </div>

              {applicants.length === 0 ? (
                <div className="empty-state">
                  <div className="empty-state-icon">👥</div>
                  <h3>No applicants yet</h3>
                  <p>
                    Share your job on LinkedIn. When candidates click Apply and submit the form,
                    their applications appear here.
                  </p>
                </div>
              ) : (
                <table className="applicant-table">
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Email</th>
                      <th>Phone</th>
                      <th>Platform</th>
                      <th>Applied</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {applicants.map((a) => (
                      <tr key={a.id}>
                        <td style={{ fontWeight: 600 }}>{a.full_name}</td>
                        <td>{a.email}</td>
                        <td>{a.phone || "—"}</td>
                        <td>
                          <span
                            className="badge badge-published"
                            style={{ textTransform: "capitalize" }}
                          >
                            {a.platform}
                          </span>
                        </td>
                        <td style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
                          {new Date(a.applied_at).toLocaleString()}
                        </td>
                        <td>
                          <div style={{ display: "flex", gap: "0.35rem", flexWrap: "wrap" }}>
                            <button
                              type="button"
                              className="btn btn-secondary"
                              style={{ padding: "0.35rem 0.65rem", fontSize: "0.8rem" }}
                              onClick={() => openApplicant(a)}
                              disabled={loadingApplicant}
                            >
                              View
                            </button>
                            <button
                              type="button"
                              className="btn btn-secondary"
                              style={{ padding: "0.35rem 0.65rem", fontSize: "0.8rem" }}
                              onClick={() => downloadApplicantApplication(a)}
                            >
                              Application
                            </button>
                            {a.has_resume && (
                              <button
                                type="button"
                                className="btn btn-secondary"
                                style={{ padding: "0.35rem 0.65rem", fontSize: "0.8rem" }}
                                onClick={() => downloadApplicantResume(a)}
                              >
                                Resume
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </main>
      </div>

      {viewApplicant && job && (
        <div className="modal-overlay" onClick={() => setViewApplicant(null)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 640 }}>
            <button
              className="modal-close"
              onClick={() => setViewApplicant(null)}
              aria-label="Close"
            >
              ×
            </button>
            <h2 className="modal-title">{viewApplicant.full_name}</h2>
            <p className="modal-subtitle">Application for {job.title}</p>

            <div style={{ display: "grid", gap: "0.75rem", marginBottom: "1rem" }}>
              <div>
                <strong>Email:</strong> {viewApplicant.email}
              </div>
              <div>
                <strong>Phone:</strong> {viewApplicant.phone || "—"}
              </div>
              {viewApplicant.location && (
                <div>
                  <strong>Location:</strong> {viewApplicant.location}
                </div>
              )}
              {(viewApplicant.current_title || viewApplicant.current_company) && (
                <div>
                  <strong>Current role:</strong>{" "}
                  {[viewApplicant.current_title, viewApplicant.current_company].filter(Boolean).join(" at ")}
                </div>
              )}
              {viewApplicant.years_experience && (
                <div>
                  <strong>Experience:</strong> {viewApplicant.years_experience} years
                </div>
              )}
              <div>
                <strong>Platform:</strong>{" "}
                <span style={{ textTransform: "capitalize" }}>{viewApplicant.platform}</span>
              </div>
              <div>
                <strong>Applied:</strong> {new Date(viewApplicant.applied_at).toLocaleString()}
              </div>
              {viewApplicant.resume_filename && (
                <div>
                  <strong>CV file:</strong> {viewApplicant.resume_filename}
                </div>
              )}
            </div>

            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "1rem" }}>
              <button
                type="button"
                className="btn btn-secondary"
                style={{ padding: "0.35rem 0.65rem", fontSize: "0.8rem" }}
                onClick={() => downloadApplicantApplication(viewApplicant)}
              >
                Download Application (.docx)
              </button>
              {viewApplicant.has_resume && (
                <button
                  type="button"
                  className="btn btn-secondary"
                  style={{ padding: "0.35rem 0.65rem", fontSize: "0.8rem" }}
                  onClick={() => downloadApplicantResume(viewApplicant)}
                >
                  Download Resume (.docx)
                </button>
              )}
            </div>

            {viewApplicant.cover_letter && (
              <div style={{ marginBottom: "1rem" }}>
                <strong>Cover letter</strong>
                <pre
                  style={{
                    whiteSpace: "pre-wrap",
                    background: "var(--surface2)",
                    border: "1px solid var(--border)",
                    borderRadius: 8,
                    padding: "1rem",
                    maxHeight: 200,
                    overflow: "auto",
                    fontSize: "0.88rem",
                    lineHeight: 1.5,
                    marginTop: "0.5rem",
                  }}
                >
                  {viewApplicant.cover_letter}
                </pre>
              </div>
            )}

            {viewApplicant.resume_text ? (
              <div>
                <strong>Resume</strong>
                <pre
                  style={{
                    whiteSpace: "pre-wrap",
                    background: "var(--surface2)",
                    border: "1px solid var(--border)",
                    borderRadius: 8,
                    padding: "1rem",
                    maxHeight: 320,
                    overflow: "auto",
                    fontSize: "0.88rem",
                    lineHeight: 1.5,
                  }}
                >
                  {viewApplicant.resume_text}
                </pre>
              </div>
            ) : viewApplicant.has_resume ? null : (
              <p className="modal-note">No resume was submitted.</p>
            )}
          </div>
        </div>
      )}

      {connectModalPlatform && user && (
        <ConnectModal
          key={`${connectModalPlatform.id}-${user.id}-${connections.length}`}
          platform={connectModalPlatform}
          userEmail={user.email}
          userName={user.full_name}
          onClose={() => setConnectModalPlatform(null)}
          onConnected={(conn) => {
            setConnections((prev) => {
              const filtered = prev.filter((c) => c.platform !== conn.platform);
              return [conn, ...filtered];
            });
            setSelectedPlatform(conn.platform);
            setStep("platforms");
            if (conn.is_oauth) {
              setSuccessMsg(
                `LinkedIn connected as ${conn.account_name || conn.account_email}. You can now click Post Job.`
              );
              setError("");
            } else {
              setError("LinkedIn connection failed — not authorized for posting. Try again.");
              setSuccessMsg("");
            }
          }}
          connectFn={recruitmentApi.connectPlatform}
          quickConnectFn={recruitmentApi.connectPlatformQuick}
          googleConnectFn={recruitmentApi.startGoogleConnect}
        />
      )}
    </div>
  );
}

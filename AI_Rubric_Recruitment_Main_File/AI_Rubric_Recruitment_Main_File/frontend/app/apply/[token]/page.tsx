"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import JDPreview from "@/components/recruitment/JDPreview";
import { applyApi } from "@/lib/apply-api";
import { JobDescription } from "@/lib/recruitment-api";

const EMPTY_JD: JobDescription = {
  title: "",
  company: "",
  location: "",
  employment_type: "",
  experience_level: "",
  salary_range: "",
  summary: "",
  responsibilities: [],
  required_skills: [],
  preferred_skills: [],
  qualifications: [],
  benefits: [],
  about_company: "",
};

const EXPERIENCE_OPTIONS = [
  { value: "", label: "Select experience" },
  { value: "0-1", label: "0–1 years" },
  { value: "1-3", label: "1–3 years" },
  { value: "3-5", label: "3–5 years" },
  { value: "5-8", label: "5–8 years" },
  { value: "8+", label: "8+ years" },
];

function normalizeJd(job: Partial<JobDescription>, title: string): JobDescription {
  return {
    ...EMPTY_JD,
    ...job,
    title: job.title || title,
    responsibilities: job.responsibilities ?? [],
    required_skills: job.required_skills ?? [],
    preferred_skills: job.preferred_skills ?? [],
    qualifications: job.qualifications ?? [],
    benefits: job.benefits ?? [],
  };
}

export default function ApplyPage() {
  const params = useParams();
  const token = params.token as string;

  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [platform, setPlatform] = useState("");
  const [jd, setJd] = useState<JobDescription | null>(null);

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [currentTitle, setCurrentTitle] = useState("");
  const [currentCompany, setCurrentCompany] = useState("");
  const [yearsExperience, setYearsExperience] = useState("");
  const [location, setLocation] = useState("");
  const [coverLetter, setCoverLetter] = useState("");
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [resumeFileName, setResumeFileName] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    let cancelled = false;

    applyApi
      .getJob(token)
      .then((data) => {
        if (cancelled) return;
        setPlatform(data.platform);
        setJd(normalizeJd(data.job, data.title));
      })
      .catch(() => {
        if (cancelled) return;
        setNotFound(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  function handleResumeChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] || null;
    setResumeFile(file);
    setResumeFileName(file?.name || "");
    setError("");
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");

    if (!resumeFile && !coverLetter.trim()) {
      setError("Please upload your CV or write a short cover letter.");
      return;
    }

    setSubmitting(true);
    try {
      await applyApi.submit(token, {
        full_name: fullName.trim(),
        email: email.trim(),
        phone: phone.trim(),
        current_title: currentTitle.trim() || undefined,
        current_company: currentCompany.trim() || undefined,
        years_experience: yearsExperience || undefined,
        location: location.trim() || undefined,
        cover_letter: coverLetter.trim() || undefined,
        resume_file: resumeFile,
      });
      setSubmitted(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not submit application");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <div className="apply-page">
        <div className="apply-container">
          <p className="apply-muted">Loading job details...</p>
        </div>
      </div>
    );
  }

  if (notFound || !jd) {
    return (
      <div className="apply-page">
        <div className="apply-container apply-not-found">
          <h1>Job not found</h1>
          <p className="apply-muted">
            This application link is invalid or the job posting is no longer available.
          </p>
        </div>
      </div>
    );
  }

  if (submitted) {
    return (
      <div className="apply-page">
        <div className="apply-container apply-success">
          <h1>Application submitted</h1>
          <p className="apply-muted">
            Thank you, {fullName}. We received your application for <strong>{jd.title}</strong>.
          </p>
        </div>
      </div>
    );
  }

  const isLinkedIn = platform.toLowerCase() === "linkedin";

  return (
    <div className="apply-page">
      <header className="apply-header">
        <div className="apply-container apply-header-inner">
          <div className="apply-brand">AI Recruiter Portal</div>
          {platform && <span className="apply-platform-badge">via {platform}</span>}
        </div>
      </header>

      <div className="apply-container apply-layout">
        <section className="apply-jd-card">
          <JDPreview jd={jd} />
        </section>

        <section className="apply-form-card">
          <h2>Apply for this role</h2>
          <p className="apply-muted">
            {isLinkedIn
              ? "Complete your details and upload your CV to apply from LinkedIn."
              : "Fill in your details below to submit your application."}
          </p>

          <form onSubmit={handleSubmit}>
            <div className="apply-form-section">
              <h3 className="apply-section-title">Personal details</h3>
              <div className="form-group">
                <label className="label">Full name *</label>
                <input
                  className="input"
                  required
                  minLength={2}
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="Jane Smith"
                />
              </div>
              <div className="form-group">
                <label className="label">Email *</label>
                <input
                  className="input"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@email.com"
                />
              </div>
              <div className="form-group">
                <label className="label">Phone *</label>
                <input
                  className="input"
                  type="tel"
                  required
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="+1 555 000 0000"
                />
              </div>
              <div className="form-group">
                <label className="label">Location</label>
                <input
                  className="input"
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                  placeholder="City, Country"
                />
              </div>
            </div>

            <div className="apply-form-section">
              <h3 className="apply-section-title">Professional background</h3>
              <div className="form-group">
                <label className="label">Current job title</label>
                <input
                  className="input"
                  value={currentTitle}
                  onChange={(e) => setCurrentTitle(e.target.value)}
                  placeholder="Software Engineer"
                />
              </div>
              <div className="form-group">
                <label className="label">Current company</label>
                <input
                  className="input"
                  value={currentCompany}
                  onChange={(e) => setCurrentCompany(e.target.value)}
                  placeholder="Acme Corp"
                />
              </div>
              <div className="form-group">
                <label className="label">Years of experience</label>
                <select
                  className="input"
                  value={yearsExperience}
                  onChange={(e) => setYearsExperience(e.target.value)}
                >
                  {EXPERIENCE_OPTIONS.map((opt) => (
                    <option key={opt.value || "empty"} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="apply-form-section">
              <h3 className="apply-section-title">Resume & cover letter</h3>
              <div className="form-group">
                <label className="label">Upload CV *</label>
                <input
                  className="input apply-file-input"
                  type="file"
                  accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
                  onChange={handleResumeChange}
                />
                <p className="apply-muted apply-file-hint">
                  PDF, DOCX, or TXT — max 5 MB. {resumeFileName && `Selected: ${resumeFileName}`}
                </p>
              </div>
              <div className="form-group">
                <label className="label">Cover letter</label>
                <textarea
                  className="input apply-textarea"
                  rows={5}
                  value={coverLetter}
                  onChange={(e) => setCoverLetter(e.target.value)}
                  placeholder="Tell us why you are a great fit for this role..."
                />
                <p className="apply-muted apply-file-hint">
                  Required if you do not upload a CV.
                </p>
              </div>
            </div>

            {error && <div className="alert alert-error">{error}</div>}

            <button className="btn btn-primary btn-full" disabled={submitting}>
              {submitting ? "Submitting..." : "Submit application"}
            </button>
          </form>
        </section>
      </div>
    </div>
  );
}

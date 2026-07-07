"use client";

import { JobDescription } from "@/lib/recruitment-api";

interface Props {
  jd: JobDescription;
  onChange: (jd: JobDescription) => void;
}

function ListEditor({
  label,
  items,
  onChange,
}: {
  label: string;
  items: string[];
  onChange: (items: string[]) => void;
}) {
  return (
    <div className="edit-field">
      <label className="label">{label}</label>
      {items.map((item, i) => (
        <div key={i} style={{ display: "flex", gap: "0.5rem", marginBottom: "0.4rem" }}>
          <input
            className="input"
            value={item}
            onChange={(e) => {
              const next = [...items];
              next[i] = e.target.value;
              onChange(next);
            }}
          />
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => onChange(items.filter((_, idx) => idx !== i))}
            style={{ padding: "0.4rem 0.6rem" }}
          >
            ✕
          </button>
        </div>
      ))}
      <button
        type="button"
        className="btn btn-secondary"
        onClick={() => onChange([...items, ""])}
        style={{ marginTop: "0.25rem", fontSize: "0.85rem" }}
      >
        + Add
      </button>
    </div>
  );
}

export default function JDEditor({ jd, onChange }: Props) {
  function update(field: keyof JobDescription, value: string | string[]) {
    onChange({ ...jd, [field]: value });
  }

  return (
    <div>
      <div className="edit-field">
        <label className="label">Job Title</label>
        <input className="input" value={jd.title} onChange={(e) => update("title", e.target.value)} />
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
        <div className="edit-field">
          <label className="label">Company</label>
          <input className="input" value={jd.company} onChange={(e) => update("company", e.target.value)} />
        </div>
        <div className="edit-field">
          <label className="label">Location</label>
          <input className="input" value={jd.location} onChange={(e) => update("location", e.target.value)} />
        </div>
        <div className="edit-field">
          <label className="label">Employment Type</label>
          <input className="input" value={jd.employment_type} onChange={(e) => update("employment_type", e.target.value)} />
        </div>
        <div className="edit-field">
          <label className="label">Experience Level</label>
          <input className="input" value={jd.experience_level} onChange={(e) => update("experience_level", e.target.value)} />
        </div>
      </div>
      <div className="edit-field">
        <label className="label" style={{ display: "flex", alignItems: "center", gap: "0.5rem", cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={Boolean(jd.salary_range?.trim())}
            onChange={(e) => update("salary_range", e.target.checked ? (jd.salary_range || "Competitive") : "")}
            style={{ width: "auto", cursor: "pointer" }}
          />
          Include salary range in job description
        </label>
        {jd.salary_range?.trim() ? (
          <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.5rem" }}>
            <input
              className="input"
              value={jd.salary_range}
              onChange={(e) => update("salary_range", e.target.value)}
              placeholder="e.g. $80,000 - $120,000 or 15-20 LPA"
            />
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => update("salary_range", "")}
              style={{ padding: "0.4rem 0.75rem", flexShrink: 0 }}
              title="Remove salary"
            >
              Remove
            </button>
          </div>
        ) : null}
      </div>
      <div className="edit-field">
        <label className="label">Summary</label>
        <textarea className="textarea" value={jd.summary} onChange={(e) => update("summary", e.target.value)} rows={3} />
      </div>
      <ListEditor label="Responsibilities" items={jd.responsibilities || []} onChange={(v) => update("responsibilities", v)} />
      <ListEditor label="Required Skills" items={jd.required_skills || []} onChange={(v) => update("required_skills", v)} />
      <ListEditor label="Preferred Skills" items={jd.preferred_skills || []} onChange={(v) => update("preferred_skills", v)} />
      <ListEditor label="Qualifications" items={jd.qualifications || []} onChange={(v) => update("qualifications", v)} />
      <ListEditor label="Benefits" items={jd.benefits || []} onChange={(v) => update("benefits", v)} />
      <div className="edit-field">
        <label className="label">About Company</label>
        <textarea className="textarea" value={jd.about_company} onChange={(e) => update("about_company", e.target.value)} rows={3} />
      </div>
    </div>
  );
}

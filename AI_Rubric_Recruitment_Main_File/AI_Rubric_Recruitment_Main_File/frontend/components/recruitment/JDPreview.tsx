import { JobDescription } from "@/lib/recruitment-api";

export default function JDPreview({ jd }: { jd: JobDescription }) {
  return (
    <div className="jd-preview">
      <h2>{jd.title}</h2>
      <div className="meta">
        {jd.company} · {jd.location} · {jd.employment_type} · {jd.experience_level}
        {jd.salary_range && ` · ${jd.salary_range}`}
      </div>

      <h3>Summary</h3>
      <p>{jd.summary}</p>

      <h3>Responsibilities</h3>
      <ul>
        {jd.responsibilities?.map((r, i) => <li key={i}>{r}</li>)}
      </ul>

      <h3>Required Skills</h3>
      <ul>
        {jd.required_skills?.map((s, i) => <li key={i}>{s}</li>)}
      </ul>

      {jd.preferred_skills?.length > 0 && (
        <>
          <h3>Preferred Skills</h3>
          <ul>
            {jd.preferred_skills.map((s, i) => <li key={i}>{s}</li>)}
          </ul>
        </>
      )}

      <h3>Qualifications</h3>
      <ul>
        {jd.qualifications?.map((q, i) => <li key={i}>{q}</li>)}
      </ul>

      {jd.benefits?.length > 0 && (
        <>
          <h3>Benefits</h3>
          <ul>
            {jd.benefits.map((b, i) => <li key={i}>{b}</li>)}
          </ul>
        </>
      )}

      {jd.about_company && (
        <>
          <h3>About the Company</h3>
          <p>{jd.about_company}</p>
        </>
      )}
    </div>
  );
}

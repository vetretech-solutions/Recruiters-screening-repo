GENERATE_JD_PROMPT = """You are an expert HR recruiter and job description writer.

The recruiter described a role in natural language. Generate a complete, professional job description.

Recruiter input:
{user_input}

Return ONLY valid JSON with this exact structure:
{{
  "title": "Job title",
  "company": "Company name (use 'Our Company' if not specified)",
  "location": "City, Country or Remote",
  "employment_type": "Full-time | Part-time | Contract | Internship",
  "experience_level": "e.g. 3-5 years",
  "salary_range": "e.g. $80,000 - $120,000, Competitive, or empty string \"\" if salary should not be shown",
  "summary": "2-3 sentence overview of the role",
  "responsibilities": ["bullet 1", "bullet 2", ...],
  "required_skills": ["skill 1", "skill 2", ...],
  "preferred_skills": ["skill 1", ...],
  "qualifications": ["degree or certification requirements"],
  "benefits": ["benefit 1", "benefit 2", ...],
  "about_company": "Brief company description"
}}

Make it realistic, detailed, and ready to publish on job boards. Use 5-8 responsibilities.

SKILLS RULES (critical):
- Read the recruiter input carefully and extract EVERY skill, technology, tool, framework, language, platform, and competency mentioned.
- Put each mentioned skill in required_skills (core/must-have) or preferred_skills (nice-to-have). Do NOT drop or skip any skill from the input.
- If the input lists skills separated by commas, "and", slashes, or bullets, include ALL of them in the JD.
- Add related skills only when reasonable; never remove skills the recruiter explicitly mentioned.
- required_skills should include all must-have skills from the input (minimum every technology named).

If the recruiter did not mention salary or compensation, set salary_range to an empty string."""

EDIT_JD_PROMPT = """You are an expert HR recruiter. The recruiter edited a job description. 
Polish and improve the edited content while preserving their intent.

Current JD (JSON):
{jd_json}

Recruiter edits:
{edits}

Return ONLY valid JSON with the same structure as the input, incorporating the edits naturally."""

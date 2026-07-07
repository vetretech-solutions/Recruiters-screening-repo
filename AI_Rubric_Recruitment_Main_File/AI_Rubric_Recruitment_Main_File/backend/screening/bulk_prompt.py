def get_bulk_analysis_prompt(job_title: str, job_description: str, candidates_data: str, candidate_count: int = 20) -> str:
    """
    Advanced bulk prompt based on Enhanced Resume Rubric v2.1.
    Dynamically adjusted for the number of candidates in the current batch.
    """
    return f"""
You are a Lead AI Technical Recruiter. Your task is to perform an INITIAL SCREENING of {candidate_count} candidates against a specific Job Description.

### MISSION:
Analyze the provided resume data for {candidate_count} candidates. For each candidate, provide a total score (0-100) based on the rubric, a brief justification, and key strengths/gaps.

### RUBRIC (Total 100):
1. Technical Skills (22)
2. Domain Expertise (8)
3. Experience Scope (20)
4. Career Growth (10)
5. Education (10)
6. Achievements (15)
7. Communication (5)
8. Cultural Fit (10)

### JOB SPECIFICATIONS:
Title: {job_title}
Requirements: {job_description}

### CANDIDATES DATA:
{candidates_data}

### OUTPUT FORMAT (STRICT JSON ARRAY ONLY):
Return a JSON array of {candidate_count} objects. Each object MUST follow this schema:
{{
  "candidate_name": "Full Name",
  "total_score": 0-100,
  "overall_summary": "3-4 sentence evaluation highlighting why this score was given.",
  "strengths": ["...", "..."],
  "areas_for_improvement": ["...", "..."],
  "recommendation": "Highly Recommended | Recommended | Borderline | Not Recommended",
  "dimension_scores": {{
    "technical_skills": {{ "score": 0-22, "justification": "..." }},
    "domain_expertise": {{ "score": 0-8, "justification": "..." }},
    "experience_relevance": {{ "score": 0-20, "justification": "..." }},
    "career_growth": {{ "score": 0-10, "justification": "..." }},
    "education_learning": {{ "score": 0-10, "justification": "..." }},
    "achievements_impact": {{ "score": 0-15, "justification": "..." }},
    "communication_quality": {{ "score": 0-5, "justification": "..." }},
    "cultural_fit": {{ "score": 0-10, "justification": "..." }}
  }}
}}

Return ONLY the JSON array. Accuracy and consistency across all {candidate_count} candidates is required.
"""

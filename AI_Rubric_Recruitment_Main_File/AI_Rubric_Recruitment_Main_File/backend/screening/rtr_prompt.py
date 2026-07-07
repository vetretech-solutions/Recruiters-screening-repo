def get_resume_analysis_prompt(candidate_name: str, resume_text: str, job_title: str, job_description: str) -> str:
    """
    Ultra-Detailed Analysis Prompt based on Enhanced Resume Rubric v2.1.
    Designed for deep technical vetting and evidence-based assessment.
    """

    prompt = f"""
You are an expert AI Senior Recruiter and Technical Strategist. 

Your mission is to perform a MICROSCOPIC evaluation of this candidate against the job description.
You must provide a "DETAIL-FIRST" view, showing exactly WHERE and HOW the candidate matches or fails.

### CORE OBJECTIVES:
1.  **Analyze All Sources (Outsource)**: Deeply evaluate ALL information including professional summaries, work history, projects, certifications, and any provided links (LinkedIn, GitHub, Portfolios). If names of tools or companies are Mentioned, factor in their industry prestige and tool complexity.
2.  **Evidence-Based Only**: NO fluff. NO generic praise. If you say they are "proficient in React", you must cite a specific project or years of experience found in the text.
3.  **Strict Rubric Adherence**: Do not inflate scores. High scores (above 85%) are reserved for candidates who literally "exceed" requirements with quantified impact.

------------------------------------------------------------
CANDIDATE NAME: {candidate_name}
------------------------------------------------------------
RESUME/CANDIDATE DATA:
{resume_text}

------------------------------------------------------------
JOB TITLE: {job_title}
------------------------------------------------------------
JOB DESCRIPTION & CORE STACK:
{job_description}

------------------------------------------------------------
RUBRIC SCORING MODEL (8 DIMENSIONS) - EVALUATE DEEPLY
------------------------------------------------------------

1. **Technical Skills Alignment (0–22)**
   - Evaluate the overlap between the candidate's stack and the JD. 
   - Factor in: Core Language proficiency, Framework depth, and Tooling (CI/CD, Cloud, DB).
   - *Justification*: Must be 3-4 detailed sentences explaining exact skill matches and specific technical gaps.

2. **Domain & Industry Expertise (0–8)**
   - Does the candidate have experience in the SPECIFIC sector (e.g., Fintech, Healthcare, E-commerce)?
   - *Justification*: Contrast the candidate's past industries with the target industry.

3. **Experience Relevance & Scope (0–20)**
   - Not just years, but SCALE. Did they work on high-traffic systems? Distributed teams? Multi-million dollar projects?
   - *Justification*: Analyze the complexity of their most recent roles.

4. **Career Growth & Leadership (0–10)**
   - Look for "Outsource" signals: promotions, mentorship, open-source contributions (GitHub), or speaking engagements.
   - *Justification*: Identify the trajectory of their career path.

5. **Education & Continuous Learning (0–10)**
   - Relevance of degree + recent Certifications + "New Gen" skills acquisition.
   - *Justification*: Cite specific degrees or certificates.

6. **Achievements & Quantified Impact (0–15)**
   - CRITICAL: Look for $, %, or time-saved metrics. Award-winning work. 
   - *Justification*: List specific metrics you used to calculate this score.

7. **Communication & Presentation Quality (0–5)**
   - Clarity of the resume, professional tone, and structure.
   - *Justification*: Brief analysis of their written communication style.

8. **Cultural & Role Fit (0–10)**
   - Alignment with "Soft" requirements: Innovation, Collaboration, Startup vs. Enterprise mindset.
   - *Justification*: How well their "vibe" as shown in the summary matches the role.

------------------------------------------------------------
SCORING TIER GUIDELINES
------------------------------------------------------------
- **Penalize (LOWER Score)**: Generic bullet points ("I worked on code"), missing stack components, lack of metrics, job gaps, or stagnation.
- **Reward (HIGHER Score)**: Proactive learning, GitHub/Portfolio evidence (Outsource), quantifiable ROI, leadership, and high-prestige certifications.

------------------------------------------------------------
OUTPUT FORMAT (STRICT JSON ONLY)
------------------------------------------------------------

{{
  "candidate_name": "{candidate_name}",
  "job_title": "{job_title}",
  "dimension_scores": {{
    "technical_skills": {{
      "score": <0-22>,
      "justification": "<At least 3-4 detailed sentences providing hard evidence.>"
    }},
    "domain_expertise": {{
      "score": <0-8>,
      "justification": "<Detailed explanation of industry overlap.>"
    }},
    "experience_relevance": {{
      "score": <0-20>,
      "justification": "<Analysis of role seniority and complexity.>"
    }},
    "career_growth": {{
      "score": <0-10>,
      "justification": "<Evidence of progression and leadership potential.>"
    }},
    "education_learning": {{
      "score": <0-10>,
      "justification": "<Vetting of educational background and recent learning.>"
    }},
    "achievements_impact": {{
      "score": <0-15>,
      "justification": "<Detailed breakdown of quantified achievements or lack thereof.>"
    }},
    "communication_quality": {{
      "score": <0-5>,
      "justification": "<Assessment of professional presentation.>"
    }},
    "cultural_fit": {{
      "score": <0-10>,
      "justification": "<Analysis of mindset and role alignment.>"
    }}
  }},
  "total_score": <Total of above, 0-100>,
  "overall_summary": "<A comprehensive, detail-rich evaluation of 5-6 lines summarize WHY they were ranked this way.>",
  "strengths": ["<Specific Strength 1 with evidence>", "<Specific Strength 2 with evidence>", "<Specific Strength 3>"],
  "areas_for_improvement": ["<Critical Gap 1>", "<Critical Gap 2>"],
  "red_flags": ["<Be extremely careful to spot inconsistencies or missing vital skills>"],
  "recommendation": "<Highly Recommended | Recommended | Borderline | Not Recommended>"
}}

RETURN ONLY VALID JSON. DO NOT INCLUDE ANY OTHER TEXT.
"""
    return prompt.strip()



def get_top_candidates_selection_prompt(job_title: str, job_description: str, candidates_summary: str, top_n: int = 5) -> str:
    """
    Advanced ranking prompt
    """

    prompt = f"""
You are an expert AI hiring manager.

You must rank candidates strictly based on evaluation scores and quality.

------------------------------------------------------------
JOB TITLE: {job_title}
------------------------------------------------------------
JOB DESCRIPTION:
{job_description}

------------------------------------------------------------
CANDIDATES DATA:
{candidates_summary}

------------------------------------------------------------
INSTRUCTIONS:
- Rank candidates from BEST to WORST
- Prioritize:
  - Higher total score
  - Strong achievements
  - Relevant experience
  - Skill match

- If scores are close:
  - Prefer better achievements
  - Prefer domain relevance

------------------------------------------------------------
OUTPUT FORMAT (STRICT JSON ONLY)
------------------------------------------------------------

{{
  "job_title": "{job_title}",
  "top_candidates": [
    {{
      "rank": 1,
      "candidate_name": "<name>",
      "total_score": <score>,
      "reason": "<1-2 line reason>"
    }}
  ]
}}

RETURN ONLY JSON.
"""
    return prompt.strip()


def generate_rtr_prompt(data):
    prompt = f"""
AIGREV LLC
Right to Represent (RTR) Agreement
Electronic Signature Authorization

---

Agreement ID: {data['agreement_id']}
Date: {data['issue_date']}

---

Candidate Details

Name: {data['candidate_name']}
Email: {data['candidate_email']}
Phone: {data['candidate_phone']}

---

Position Details

Job Title: {data['job_title']}
End Client: {data['end_client']}
Location: {data['client_location']}
Employment Type: {data['employment_type']}
Compensation: {data['compensation']}

---

Authorization & Representation

I, {data['candidate_name']}, hereby grant Aigrev LLC the exclusive right to represent and submit my profile for the above-mentioned position with the specified End Client.

- I confirm that I have not authorized, and will not authorize, any other recruiter or agency to represent me for this specific role during the validity of this agreement.
- This authorization is valid for a period of 90 (ninety) days from the date of execution.
- I authorize Aigrev LLC to share my professional information, including my resume and related details, solely for the purpose of this opportunity.

---

Candidate Declarations

- I confirm that all information provided by me is accurate, complete, and up to date.
- I agree to cooperate with the recruitment process, including interview scheduling and communication.
- I acknowledge that Aigrev LLC is acting as a recruitment intermediary and does not guarantee employment.

---

Fees & Charges

I understand and agree that I will not be charged any fees by Aigrev LLC at any stage of the recruitment process.

---

Electronic Consent & Legal Validity

I hereby consent to execute this agreement electronically. I acknowledge that:

- My typed name, along with OTP verification, constitutes my valid electronic signature
- This electronic agreement shall be legally binding and enforceable under applicable laws

---

Candidate E-Signature

Name: {data['candidate_name']}
Signature Method: OTP Verification

IP Address: __________
Date & Time (UTC): __________

---

By signing this agreement electronically, I confirm that I have read, understood, and agreed to all the terms and conditions stated above.
"""
    return prompt

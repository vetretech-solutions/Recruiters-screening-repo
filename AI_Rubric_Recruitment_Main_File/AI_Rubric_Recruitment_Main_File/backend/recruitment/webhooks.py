"""Inbound application webhooks from job platforms."""

from sqlalchemy.orm import Session

from database import Applicant, PlatformPost
from platform_service import submit_application


def _find_platform_post(db: Session, external_id: str) -> PlatformPost | None:
    post = (
        db.query(PlatformPost)
        .filter(PlatformPost.apply_token == external_id)
        .first()
    )
    if post:
        return post
    post = (
        db.query(PlatformPost)
        .filter(PlatformPost.external_post_id == external_id)
        .first()
    )
    if post:
        return post
    if external_id.isdigit():
        return db.query(PlatformPost).filter(PlatformPost.id == int(external_id)).first()
    # LinkedIn job listing webhooks may use job-{id}-linkedin-{token_prefix}
    if external_id.startswith("job-"):
        prefix = external_id.rsplit("-", 1)[-1]
        if prefix:
            post = (
                db.query(PlatformPost)
                .filter(PlatformPost.apply_token.like(f"{prefix}%"))
                .first()
            )
            if post:
                return post
    return None


def handle_linkedin_apply_webhook(
    db: Session,
    external_id: str,
    payload: dict,
) -> Applicant:
    platform_post = _find_platform_post(db, external_id)
    if not platform_post:
        raise ValueError("Job posting not found for webhook")

    applicant_data = payload.get("applicant") or payload
    full_name = (
        applicant_data.get("fullName")
        or applicant_data.get("full_name")
        or f"{applicant_data.get('firstName', '')} {applicant_data.get('lastName', '')}".strip()
        or "LinkedIn Applicant"
    )
    email = applicant_data.get("email") or applicant_data.get("contactEmail", "")
    phone = applicant_data.get("phone") or applicant_data.get("phoneNumber")
    resume = applicant_data.get("resume") or applicant_data.get("resumeText")
    if isinstance(resume, dict):
        resume = (
            resume.get("text")
            or resume.get("content")
            or resume.get("resumeText")
            or resume.get("body")
        )
    if not email:
        linkedin_id = str(
            applicant_data.get("linkedinId")
            or applicant_data.get("memberId")
            or applicant_data.get("id")
            or ""
        ).strip()
        if linkedin_id:
            email = f"linkedin-{linkedin_id}@applicant.local"
        else:
            raise ValueError("Applicant email is required")

    return submit_application(
        db,
        platform_post.apply_token,
        full_name=full_name,
        email=email,
        phone=phone,
        linkedin_url=applicant_data.get("linkedinUrl") or applicant_data.get("linkedin_url"),
        current_title=applicant_data.get("currentTitle") or applicant_data.get("current_title"),
        current_company=applicant_data.get("currentCompany") or applicant_data.get("current_company"),
        years_experience=str(applicant_data.get("yearsExperience") or applicant_data.get("years_experience") or "") or None,
        location=applicant_data.get("location"),
        cover_letter=applicant_data.get("coverLetter") or applicant_data.get("cover_letter"),
        resume_text=str(resume) if resume else None,
    )


def handle_ziprecruiter_apply_webhook(
    db: Session,
    payload: dict,
) -> Applicant:
    job_id = str(payload.get("job_id") or payload.get("zr_application_id", ""))
    platform_post = (
        db.query(PlatformPost)
        .filter(PlatformPost.external_post_id == job_id)
        .first()
    )
    if not platform_post:
        raise ValueError("Job posting not found for ZipRecruiter webhook")

    profile = payload.get("profile") or payload
    full_name = profile.get("name") or profile.get("full_name") or "ZipRecruiter Applicant"
    email = profile.get("email", "")
    if not email:
        raise ValueError("Applicant email is required")

    phone = profile.get("phone")
    resume = profile.get("resume") or profile.get("resume_text")

    return submit_application(
        db,
        platform_post.apply_token,
        full_name=full_name,
        email=email,
        phone=phone,
        resume_text=str(resume) if resume else None,
    )


def handle_indeed_apply_webhook(
    db: Session,
    payload: dict,
) -> Applicant:
    job_id = str(payload.get("jobId") or payload.get("job_id") or "")
    platform_post = (
        db.query(PlatformPost)
        .filter(PlatformPost.external_post_id == job_id)
        .first()
    )
    if not platform_post:
        raise ValueError("Job posting not found for Indeed webhook")

    applicant = payload.get("applicant") or payload
    full_name = applicant.get("fullName") or applicant.get("full_name") or "Indeed Applicant"
    email = applicant.get("email", "")
    if not email:
        raise ValueError("Applicant email is required")

    phone = applicant.get("phone")
    resume = applicant.get("resume") or applicant.get("resumeText")

    return submit_application(
        db,
        platform_post.apply_token,
        full_name=full_name,
        email=email,
        phone=phone,
        resume_text=str(resume) if resume else None,
    )

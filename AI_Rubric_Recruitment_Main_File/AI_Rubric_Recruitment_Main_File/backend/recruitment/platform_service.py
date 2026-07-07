import secrets

from sqlalchemy.orm import Session

from app_urls import public_app_url
from database import Applicant, JobPosting, PlatformPost, User
from platform_apis import post_to_platform as api_post_to_platform
from platform_connect import get_user_connection

PLATFORM_MANUAL_POST_URLS = {
    "linkedin": "https://www.linkedin.com/talent/job-posting/",
    "indeed": "https://employers.indeed.com/p/post-job",
    "dice": "https://www.dice.com/hiring/post-job",
    "ziprecruiter": "https://www.ziprecruiter.com/post-a-job",
}

PLATFORMS = [
    {
        "id": "linkedin",
        "name": "LinkedIn",
        "logo": "linkedin",
        "description": "Connect your LinkedIn account to post jobs directly to your profile or company page.",
        "supports_oauth": True,
    },
    {
        "id": "indeed",
        "name": "Indeed",
        "logo": "indeed",
        "description": "Connect your Indeed employer account to publish job listings automatically.",
        "supports_oauth": False,
    },
    {
        "id": "dice",
        "name": "Dice",
        "logo": "dice",
        "description": "Connect your Dice employer account to reach tech talent.",
        "supports_oauth": False,
    },
    {
        "id": "ziprecruiter",
        "name": "ZipRecruiter",
        "logo": "ziprecruiter",
        "description": "Connect your ZipRecruiter account to distribute jobs across networks.",
        "supports_oauth": False,
    },
]


def get_platforms() -> list[dict]:
    return PLATFORMS


def _verify_linkedin_connection(connection) -> None:
    """Ensure we have a real OAuth token and verified email before posting."""
    if not connection.access_token:
        raise ValueError(
            "LinkedIn is not authorized for posting. Disconnect and connect again on linkedin.com."
        )
    email = (connection.account_email or "").strip().lower()
    if not email or email.endswith("@connected") or email == "linkedin-user@connected":
        raise ValueError(
            "LinkedIn email could not be verified. Update backend/.env: "
            "LINKEDIN_OAUTH_SCOPES=openid profile email w_member_social, restart backend, "
            "disconnect LinkedIn, and connect again."
        )


def post_to_platform(
    db: Session,
    user: User,
    posting: JobPosting,
    platform: str,
    base_url: str = "http://localhost:3000",
    force: bool = False,
) -> tuple[PlatformPost, str]:
    platform = platform.lower()
    valid_ids = {p["id"] for p in PLATFORMS}
    if platform not in valid_ids:
        raise ValueError(f"Unsupported platform: {platform}")

    connection = get_user_connection(db, user.id, platform)
    if not connection:
        platform_name = next((p["name"] for p in PLATFORMS if p["id"] == platform), platform)
        raise ValueError(
            f"Please connect your {platform_name} account first before posting."
        )

    if platform == "linkedin":
        _verify_linkedin_connection(connection)

    existing = (
        db.query(PlatformPost)
        .filter(
            PlatformPost.job_posting_id == posting.id,
            PlatformPost.platform == platform,
        )
        .first()
    )
    if existing and not force:
        apply_url = get_apply_url(existing, base_url)
        message = _build_post_message(platform, connection, apply_url, existing)
        return existing, message

    if existing and force:
        db.query(Applicant).filter(Applicant.platform_post_id == existing.id).update(
            {Applicant.platform_post_id: None}
        )
        db.delete(existing)
        db.flush()

    token = secrets.token_urlsafe(16)
    jd = posting.get_jd()
    apply_url = f"{public_app_url()}/apply/{token}"
    external_id = f"job-{posting.id}-{platform}-{token[:8]}"

    result = api_post_to_platform(
        platform,
        connection,
        jd,
        apply_url,
        external_id,
    )

    if not result.success:
        raise ValueError(result.message)

    external_url = result.external_url or PLATFORM_MANUAL_POST_URLS.get(
        platform, PLATFORM_MANUAL_POST_URLS["indeed"]
    )

    platform_post = PlatformPost(
        job_posting_id=posting.id,
        platform=platform,
        external_url=external_url,
        account_url=connection.account_url,
        external_post_id=result.external_post_id,
        apply_token=token,
        status=result.status,
    )
    db.add(platform_post)
    posting.status = "published"
    db.commit()
    db.refresh(platform_post)

    message = _build_post_message(platform, connection, apply_url, platform_post, result.message)
    return platform_post, message


def _build_post_message(
    platform: str,
    connection,
    apply_url: str,
    platform_post: PlatformPost,
    api_message: str | None = None,
) -> str:
    if api_message:
        return api_message
    name = next((p["name"] for p in PLATFORMS if p["id"] == platform), platform)
    account = connection.account_name or connection.account_email
    if platform_post.external_post_id:
        return f"Successfully posted to {name} as {account}!"
    return f"Could not confirm post on {name}. Please try again."


def get_apply_url(platform_post: PlatformPost, base_url: str | None = None) -> str:
    _ = base_url  # kept for API compatibility; always use public frontend URL
    return f"{public_app_url()}/apply/{platform_post.apply_token}"


def submit_application(
    db: Session,
    apply_token: str,
    full_name: str,
    email: str,
    *,
    phone: str | None = None,
    linkedin_url: str | None = None,
    current_title: str | None = None,
    current_company: str | None = None,
    years_experience: str | None = None,
    location: str | None = None,
    cover_letter: str | None = None,
    resume_text: str | None = None,
    resume_filename: str | None = None,
    resume_file_path: str | None = None,
) -> Applicant:
    platform_post = (
        db.query(PlatformPost).filter(PlatformPost.apply_token == apply_token).first()
    )
    if not platform_post:
        raise ValueError("Invalid apply link")

    applicant = Applicant(
        job_posting_id=platform_post.job_posting_id,
        platform_post_id=platform_post.id,
        full_name=full_name,
        email=email,
        phone=phone,
        linkedin_url=linkedin_url,
        current_title=current_title,
        current_company=current_company,
        years_experience=years_experience,
        location=location,
        cover_letter=cover_letter,
        resume_text=resume_text,
        resume_filename=resume_filename,
        resume_file_path=resume_file_path,
        platform=platform_post.platform,
    )
    db.add(applicant)
    db.commit()
    db.refresh(applicant)
    return applicant

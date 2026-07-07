"""Real job posting integrations for LinkedIn, Indeed, Dice, and ZipRecruiter."""

import os
import smtplib
import time
from dataclasses import dataclass
from email.mime.text import MIMEText
from typing import Any

import httpx

from database import PlatformConnection
from job_feed import html_job_description
from jd_service import jd_to_text

LINKEDIN_SIMPLE_JOBS_URL = "https://api.linkedin.com/rest/simpleJobPostings"
LINKEDIN_UGC_URL = "https://api.linkedin.com/v2/ugcPosts"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"

INDEED_TOKEN_URL = "https://apis.indeed.com/oauth/v2/tokens"
INDEED_GRAPHQL_URL = "https://apis.indeed.com/graphql"

ZIPRECRUITER_JOBS_URL = "https://api.ziprecruiter.com/partner/v0/job"

DICE_BATCH_EMAIL = "dicejobs@dice.com"


@dataclass
class PostResult:
    external_post_id: str | None
    external_url: str | None
    message: str
    success: bool
    status: str = "published"  # published | syndicated | pending


def _linkedin_org_id() -> str | None:
    return os.getenv("LINKEDIN_ORGANIZATION_ID", "").strip() or None


def _indeed_configured() -> bool:
    return bool(
        os.getenv("INDEED_CLIENT_ID")
        and os.getenv("INDEED_CLIENT_SECRET")
        and os.getenv("INDEED_EMPLOYER_ID")
    )


def _ziprecruiter_configured() -> bool:
    return bool(os.getenv("ZIPRECRUITER_API_KEY"))


def _dice_batch_configured() -> bool:
    return bool(os.getenv("DICE_BATCH_USERNAME") and os.getenv("DICE_BATCH_PASSWORD"))


def _smtp_configured() -> bool:
    return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_FROM"))


def _get_linkedin_person_urn(
    access_token: str,
    refresh_token: str | None = None,
) -> str | None:
    from linkedin_browser import is_browser_session
    from linkedin_profile import (
        person_id_to_urn,
        resolve_linkedin_person_id,
        unpack_linkedin_person_id,
    )

    if is_browser_session(access_token):
        return None

    person_id = unpack_linkedin_person_id(refresh_token)
    if person_id:
        return person_id_to_urn(person_id)

    person_id, _ = resolve_linkedin_person_id(access_token)
    if person_id:
        return person_id_to_urn(person_id)
    return None


def _post_linkedin_rest(
    access_token: str,
    author_urn: str,
    text: str,
) -> tuple[int, str, str | None]:
    """Post using LinkedIn REST Posts API. Returns (status, detail, post_id)."""
    linkedin_version = os.getenv("LINKEDIN_API_VERSION", "202503")
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
        "LinkedIn-Version": linkedin_version,
    }
    payload = {
        "author": author_urn,
        "commentary": text,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    with httpx.Client(timeout=25) as client:
        res = client.post("https://api.linkedin.com/rest/posts", json=payload, headers=headers)
        post_id = res.headers.get("x-restli-id") or res.headers.get("x-linkedin-id")
        detail = ""
        try:
            body = res.json()
            detail = body.get("message") or str(body)[:300]
        except Exception:
            detail = res.text[:300]
        return res.status_code, detail, post_id


def _get_linkedin_client_token() -> str | None:
    """Client-credentials token for Job Posting API (partner apps)."""
    client_id = os.getenv("LINKEDIN_CLIENT_ID")
    client_secret = os.getenv("LINKEDIN_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None
    with httpx.Client(timeout=20) as client:
        res = client.post(
            LINKEDIN_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if res.status_code == 200:
            return res.json().get("access_token")
    return None


def post_linkedin_job_listing(
    connection: PlatformConnection,
    jd: dict[str, Any],
    apply_url: str,
    external_id: str,
) -> PostResult | None:
    """Create a LinkedIn Job Listing via Simple Job Postings API (requires partner access)."""
    org_id = _linkedin_org_id()
    if not org_id:
        return None

    token = connection.access_token or _get_linkedin_client_token()
    if not token:
        return None

    webhook_url = os.getenv("BACKEND_URL", "http://127.0.0.1:8001").rstrip("/")
    apply_token = apply_url.rstrip("/").split("/")[-1]
    webhook_url += f"/api/webhooks/linkedin/apply/{apply_token}"

    payload = {
        "elements": [
            {
                "externalJobPostingId": external_id,
                "title": jd.get("title", "Job Opening"),
                "description": html_job_description(jd),
                "integrationContext": f"urn:li:organization:{org_id}",
                "listedAt": int(time.time() * 1000),
                "jobPostingOperationType": "CREATE",
                "location": jd.get("location", "Remote"),
                "availability": "PUBLIC",
                "companyApplyUrl": apply_url,
                "listingType": "BASIC",
                "posterEmail": connection.account_email,
                "onsiteApplyConfiguration": {
                    "applyWebhookUrl": webhook_url,
                },
            }
        ]
    }

    linkedin_version = os.getenv("LINKEDIN_API_VERSION", "202503")
    with httpx.Client(timeout=30) as client:
        res = client.post(
            LINKEDIN_SIMPLE_JOBS_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0",
                "LinkedIn-Version": linkedin_version,
            },
        )
        if res.status_code in (200, 201, 202):
            data = res.json() if res.content else {}
            elements = data.get("elements", [])
            post_id = None
            if elements:
                post_id = elements[0].get("id") or elements[0].get("externalJobPostingId")
            job_url = f"https://www.linkedin.com/jobs/view/{post_id}" if post_id else None
            return PostResult(
                external_post_id=post_id or external_id,
                external_url=job_url,
                message=(
                    f"Job listing published on LinkedIn as {connection.account_name or connection.account_email}."
                ),
                success=True,
                status="published",
            )
    return None


def post_linkedin_social(
    connection: PlatformConnection,
    jd: dict[str, Any],
    apply_url: str,
) -> PostResult:
    """Post hiring announcement with apply link on the member's LinkedIn feed."""
    from app_urls import is_local_app_url
    from linkedin_browser import is_browser_session, post_to_linkedin_feed

    title = jd.get("title", "We're Hiring")
    company = jd.get("company", "")
    location = jd.get("location", "")
    summary = jd.get("summary", "")
    post_text = (
        f"🚀 We're hiring: {title}"
        + (f" at {company}" if company else "")
        + (f" ({location})" if location else "")
        + f"\n\n{summary}\n\nApply here: {apply_url}"
    )

    if connection.access_token and is_browser_session(connection.access_token):
        post_url, message = post_to_linkedin_feed(connection.access_token, post_text)
        if post_url:
            return PostResult(
                external_post_id=post_url,
                external_url=post_url,
                message=(
                    f"Hiring post published on LinkedIn as "
                    f"{connection.account_name or connection.account_email}."
                ),
                success=True,
                status="published",
            )
        return PostResult(
            external_post_id=None,
            external_url=None,
            message=message,
            success=False,
            status="pending",
        )

    if not connection.access_token:
        return PostResult(
            external_post_id=None,
            external_url=None,
            message=(
                "LinkedIn OAuth required. Connect via LinkedIn OAuth to enable auto-posting."
            ),
            success=False,
            status="pending",
        )

    author_urn = _get_linkedin_person_urn(
        connection.access_token,
        connection.refresh_token,
    )
    if not author_urn:
        return PostResult(
            external_post_id=None,
            external_url=None,
            message=(
                "Could not resolve your LinkedIn profile for posting. "
                "Disconnect LinkedIn, then reconnect. In LinkedIn Developer Portal → Products, "
                "enable 'Sign In with LinkedIn using OpenID Connect', set "
                "LINKEDIN_OAUTH_SCOPES=openid profile w_member_social in backend .env, "
                "restart the backend, and connect again."
            ),
            success=False,
            status="pending",
        )

    plain_payload = {
        "author": author_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": post_text},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }

    # Article cards with localhost/private URLs break on LinkedIn — use plain text link instead.
    article_payload = {
        "author": author_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": post_text},
                "shareMediaCategory": "ARTICLE",
                "media": [
                    {
                        "status": "READY",
                        "originalUrl": apply_url,
                        "title": {"text": f"{title} — Apply Now"},
                        "description": {"text": summary[:200] if summary else post_text[:200]},
                    }
                ],
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }

    headers = {
        "Authorization": f"Bearer {connection.access_token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }

    with httpx.Client(timeout=20) as client:
        if is_local_app_url(apply_url):
            res = client.post(LINKEDIN_UGC_URL, json=plain_payload, headers=headers)
        else:
            res = client.post(LINKEDIN_UGC_URL, json=article_payload, headers=headers)
            if res.status_code not in (200, 201):
                res = client.post(LINKEDIN_UGC_URL, json=plain_payload, headers=headers)

        if res.status_code not in (200, 201):
            rest_status, rest_detail, rest_post_id = _post_linkedin_rest(
                connection.access_token, author_urn, post_text
            )
            if rest_status in (200, 201):
                return PostResult(
                    external_post_id=rest_post_id,
                    external_url=(
                        f"https://www.linkedin.com/feed/update/{rest_post_id}"
                        if rest_post_id else None
                    ),
                    message=(
                        f"Hiring post published on LinkedIn as "
                        f"{connection.account_name or connection.account_email}."
                    ),
                    success=True,
                    status="published",
                )
            if rest_detail:
                error_detail = f"UGC: {res.status_code}; REST: {rest_status} — {rest_detail}"
            else:
                error_detail = ""
        else:
            error_detail = ""

        if res.status_code in (200, 201):
            post_id = res.headers.get("x-restli-id") or ""
            if not post_id and res.content:
                post_id = res.json().get("id", "")
            return PostResult(
                external_post_id=post_id or None,
                external_url=f"https://www.linkedin.com/feed/update/{post_id}" if post_id else None,
                message=(
                    f"Hiring post published on LinkedIn as "
                    f"{connection.account_name or connection.account_email}."
                ),
                success=True,
                status="published",
            )

        if not error_detail:
            try:
                body = res.json()
                error_detail = body.get("message") or body.get("error_description") or str(body)[:300]
            except Exception:
                error_detail = res.text[:300]

        return PostResult(
            external_post_id=None,
            external_url="https://www.linkedin.com/talent/job-posting/",
            message=(
                f"LinkedIn post failed: {error_detail or res.status_code}. "
                f"Enable 'Sign In with LinkedIn using OpenID Connect' in Developer Portal "
                f"and set LINKEDIN_OAUTH_SCOPES=openid profile w_member_social in .env."
            ),
            success=False,
            status="pending",
        )


def post_to_linkedin(
    connection: PlatformConnection,
    jd: dict[str, Any],
    apply_url: str,
    external_id: str,
) -> PostResult:
    """Try LinkedIn Job Listing API first, then social share."""
    job_result = post_linkedin_job_listing(connection, jd, apply_url, external_id)
    if job_result and job_result.success:
        return job_result
    return post_linkedin_social(connection, jd, apply_url)


def _get_indeed_token() -> str | None:
    client_id = os.getenv("INDEED_CLIENT_ID")
    client_secret = os.getenv("INDEED_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None

    with httpx.Client(timeout=20) as client:
        res = client.post(
            INDEED_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "employer_access",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if res.status_code == 200:
            return res.json().get("access_token")
    return None


def post_to_indeed(
    connection: PlatformConnection,
    jd: dict[str, Any],
    apply_url: str,
    external_id: str,
) -> PostResult:
    if not _indeed_configured():
        return PostResult(
            external_post_id=None,
            external_url="https://employers.indeed.com/p/post-job",
            message=(
                "Indeed API not configured. Add INDEED_CLIENT_ID, INDEED_CLIENT_SECRET, "
                "and INDEED_EMPLOYER_ID to your .env file."
            ),
            success=False,
            status="pending",
        )

    token = _get_indeed_token()
    if not token:
        return PostResult(
            external_post_id=None,
            external_url="https://employers.indeed.com/p/post-job",
            message="Indeed authentication failed. Check your INDEED_CLIENT_ID and INDEED_CLIENT_SECRET.",
            success=False,
            status="pending",
        )

    employer_id = os.getenv("INDEED_EMPLOYER_ID", "")
    description = jd_to_text(jd)
    location = jd.get("location", "Remote")
    city = location.split(",")[0].strip() if location else "Remote"
    state = location.split(",")[1].strip() if "," in location else ""

    mutation = """
    mutation CreateJob($input: CreateSourcedJobPostingsInput!) {
      jobsIngest {
        createSourcedJobPostings(input: $input) {
          results {
            jobPosting {
              sourcedPostingId
            }
          }
        }
      }
    }
    """

    variables = {
        "input": {
            "jobPostings": [
                {
                    "body": {
                        "title": jd.get("title", "Job Opening"),
                        "description": description,
                        "location": {
                            "city": city,
                            "state": state or None,
                            "country": "US",
                        },
                    },
                    "metadata": {
                        "jobPostingId": external_id,
                        "url": apply_url,
                        "jobSource": {
                            "companyName": jd.get("company", "Company"),
                            "sourceName": employer_id,
                            "sourceType": "Employer",
                        },
                        "contacts": [
                            {"contactType": ["contact"], "contactInfo": {"contactEmail": connection.account_email}}
                        ],
                    },
                }
            ]
        }
    }

    with httpx.Client(timeout=30) as client:
        res = client.post(
            INDEED_GRAPHQL_URL,
            json={"query": mutation, "variables": variables},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )

        if res.status_code == 200:
            data = res.json()
            if "errors" in data:
                errors = "; ".join(e.get("message", str(e)) for e in data["errors"])
                return PostResult(
                    external_post_id=None,
                    external_url="https://employers.indeed.com/p/post-job",
                    message=f"Indeed API error: {errors}",
                    success=False,
                    status="pending",
                )

            results = (
                data.get("data", {})
                .get("jobsIngest", {})
                .get("createSourcedJobPostings", {})
                .get("results", [])
            )
            if results:
                post_id = results[0].get("jobPosting", {}).get("sourcedPostingId")
                if post_id:
                    return PostResult(
                        external_post_id=post_id,
                        external_url=f"https://www.indeed.com/viewjob?jk={post_id}",
                        message=(
                            f"Job published on Indeed as {connection.account_name or connection.account_email}."
                        ),
                        success=True,
                        status="published",
                    )

        return PostResult(
            external_post_id=None,
            external_url="https://employers.indeed.com/p/post-job",
            message=f"Indeed posting failed (HTTP {res.status_code}). Verify your Indeed API credentials.",
            success=False,
            status="pending",
        )


def _build_dice_batch_sgml(
    jd: dict[str, Any],
    apply_url: str,
    external_id: str,
    contact_email: str,
    group_id: str,
) -> str:
    title = jd.get("title", "Job Opening")
    location = jd.get("location", "Remote")
    description = jd_to_text(jd).replace("\n", " ")
    employment = (jd.get("employment_type") or "FULLTIME").upper().replace("-", "").replace(" ", "")
    if employment not in ("FULLTIME", "PARTTIME", "CONTRACT", "INTERN"):
        employment = "FULLTIME"

    return f"""<doc>
<position>
<title>{title}</title>
<jobid>{external_id}</jobid>
<groupid>{group_id}</groupid>
<email>{contact_email}</email>
<applylink>{apply_url}</applylink>
<location>{location}</location>
<jobtype>{employment}</jobtype>
<description>{description}</description>
</position>
</doc>"""


def post_to_dice(
    connection: PlatformConnection,
    jd: dict[str, Any],
    apply_url: str,
    external_id: str,
) -> PostResult:
    if not _dice_batch_configured():
        return PostResult(
            external_post_id=None,
            external_url="https://www.dice.com/hiring/post-job",
            message=(
                "Dice API not configured. Add DICE_BATCH_USERNAME and DICE_BATCH_PASSWORD "
                "(from Dice support) plus SMTP_HOST and SMTP_FROM to your .env file."
            ),
            success=False,
            status="pending",
        )

    if not _smtp_configured():
        return PostResult(
            external_post_id=None,
            external_url="https://www.dice.com/hiring/post-job",
            message="SMTP not configured. Add SMTP_HOST and SMTP_FROM to send jobs to Dice.",
            success=False,
            status="pending",
        )

    batch_user = os.getenv("DICE_BATCH_USERNAME", "")
    batch_pass = os.getenv("DICE_BATCH_PASSWORD", "")
    group_id = os.getenv("DICE_GROUP_ID", batch_user)
    sgml = _build_dice_batch_sgml(
        jd, apply_url, external_id, connection.account_email, group_id
    )

    body_text = f"{batch_user}\n{batch_pass}"

    try:
        from email.mime.multipart import MIMEMultipart
        from email.mime.base import MIMEBase
        from email import encoders

        host = os.getenv("SMTP_HOST", "")
        port = int(os.getenv("SMTP_PORT", "587"))
        multipart = MIMEMultipart()
        multipart["Subject"] = f"Dice Batch Posting - {jd.get('title', 'Job')}"
        multipart["From"] = os.getenv("SMTP_FROM", "")
        multipart["To"] = DICE_BATCH_EMAIL
        multipart.attach(MIMEText(body_text, "plain"))

        attachment = MIMEBase("text", "plain")
        attachment.set_payload(sgml)
        encoders.encode_base64(attachment)
        attachment.add_header("Content-Disposition", "attachment", filename="batch.sgml")
        multipart.attach(attachment)

        with smtplib.SMTP(host, port, timeout=30) as server:
            if os.getenv("SMTP_TLS", "true").lower() == "true":
                server.starttls()
            smtp_user = os.getenv("SMTP_USER", "")
            smtp_pass = os.getenv("SMTP_PASSWORD", "")
            if smtp_user and smtp_pass:
                server.login(smtp_user, smtp_pass)
            server.sendmail(
                os.getenv("SMTP_FROM", ""),
                DICE_BATCH_EMAIL,
                multipart.as_string(),
            )
        return PostResult(
            external_post_id=external_id,
            external_url="https://www.dice.com/hiring",
            message=(
                f"Job submitted to Dice via batch posting as "
                f"{connection.account_name or connection.account_email}."
            ),
            success=True,
            status="published",
        )
    except Exception as exc:
        return PostResult(
            external_post_id=None,
            external_url="https://www.dice.com/hiring/post-job",
            message=f"Dice batch posting failed: {exc}",
            success=False,
            status="pending",
        )


def post_to_ziprecruiter(
    connection: PlatformConnection,
    jd: dict[str, Any],
    apply_url: str,
    external_id: str,
) -> PostResult:
    api_key = os.getenv("ZIPRECRUITER_API_KEY", "")
    if not api_key:
        return PostResult(
            external_post_id=None,
            external_url="https://www.ziprecruiter.com/post-a-job",
            message=(
                "ZipRecruiter API not configured. Add ZIPRECRUITER_API_KEY "
                "(from ZipRecruiter partner program) to your .env file."
            ),
            success=False,
            status="pending",
        )

    location = jd.get("location", "Remote")
    city = location.split(",")[0].strip() if location else "Remote"
    state = location.split(",")[1].strip() if "," in location else ""

    payload = {
        "name": jd.get("title", "Job Opening"),
        "job_id": external_id,
        "employer": jd.get("company", "Company"),
        "description": html_job_description(jd),
        "city": city,
        "state": state or None,
        "country": "US",
        "job_type": jd.get("employment_type", "Full-Time"),
        "url": apply_url,
        "contact_email": connection.account_email,
    }

    with httpx.Client(timeout=30) as client:
        res = client.post(
            ZIPRECRUITER_JOBS_URL,
            json=payload,
            auth=(api_key, ""),
            headers={"Content-Type": "application/json"},
        )

        if res.status_code in (200, 201):
            data = res.json() if res.content else {}
            job_id = data.get("job_id") or data.get("id") or external_id
            job_url = data.get("url") or f"https://www.ziprecruiter.com/c/Jobs/{job_id}"
            return PostResult(
                external_post_id=str(job_id),
                external_url=job_url,
                message=(
                    f"Job published on ZipRecruiter as "
                    f"{connection.account_name or connection.account_email}."
                ),
                success=True,
                status="published",
            )

        error_detail = ""
        try:
            error_detail = res.json().get("message", res.text[:200])
        except Exception:
            error_detail = res.text[:200]

        return PostResult(
            external_post_id=None,
            external_url="https://www.ziprecruiter.com/post-a-job",
            message=f"ZipRecruiter posting failed ({res.status_code}): {error_detail}",
            success=False,
            status="pending",
        )


def post_to_platform(
    platform: str,
    connection: PlatformConnection,
    jd: dict[str, Any],
    apply_url: str,
    external_id: str,
) -> PostResult:
    """Route job posting to the correct platform API."""
    platform = platform.lower()
    if platform == "linkedin":
        return post_to_linkedin(connection, jd, apply_url, external_id)
    if platform == "indeed":
        return post_to_indeed(connection, jd, apply_url, external_id)
    if platform == "dice":
        return post_to_dice(connection, jd, apply_url, external_id)
    if platform == "ziprecruiter":
        return post_to_ziprecruiter(connection, jd, apply_url, external_id)
    return PostResult(
        external_post_id=None,
        external_url=None,
        message=f"Unsupported platform: {platform}",
        success=False,
        status="pending",
    )

import json
import os
import secrets
import urllib.parse
from csv import writer as csv_writer
from io import StringIO
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse, Response
from sqlalchemy import or_
from sqlalchemy.orm import Session

from auth import (
    TEAM_ROLES,
    create_access_token,
    get_current_user,
    hash_password,
    require_roles,
    resolve_registration_role,
    verify_password,
)
from database import Applicant, ContactSubmission, JobPosting, PlatformPost, User, get_db, init_db
from applicant_files import resolve_applicant_resume_path, save_applicant_resume
from application_export import build_applicant_docx, build_resume_docx
from resume_extract import extract_resume_text
from jd_service import (
    create_job_posting,
    generate_jd_from_natural_language,
    jd_to_text,
    update_job_posting,
)
from platform_connect import (
    begin_linkedin_oauth,
    build_linkedin_authorize_url,
    connect_platform,
    connect_platform_google_fallback,
    connect_platform_quick,
    connection_to_dict,
    disconnect_platform,
    get_google_oauth_start_url,
    get_oauth_start_url,
    get_user_connection,
    handle_google_oauth_callback,
    handle_oauth_callback,
    list_user_connections,
    prepare_linkedin_reconnect,
    validate_linkedin_oauth_state,
    linkedin_full_login_url,
    linkedin_setup_status,
    linkedin_logout_redirect_url,
    linkedin_post_logout_return_url,
    peek_oauth_state,
    _linkedin_configured,
)
from job_feed import build_job_xml, build_multi_job_feed
from app_urls import public_app_url
from platform_service import (
    get_apply_url,
    get_platforms,
    post_to_platform,
    submit_application,
)
from webhooks import (
    handle_indeed_apply_webhook,
    handle_linkedin_apply_webhook,
    handle_ziprecruiter_apply_webhook,
)
from schemas import (
    ApplicantDetailOut,
    ApplicantOut,
    ChangePasswordRequest,
    ConnectPlatformRequest,
    ContactRequest,
    ContactSubmissionOut,
    CreateUserRequest,
    GenerateJDRequest,
    JobPostingOut,
    PaginatedContactSubmissions,
    PaginatedUsers,
    PlatformConnectionOut,
    PlatformInfo,
    PlatformPostOut,
    PostToPlatformRequest,
    SetPasswordRequest,
    TokenResponse,
    UpdateJDRequest,
    UpdateUserRequest,
    UserLogin,
    UserOut,
    UserRegister,
)


portal_router = APIRouter(tags=["Portal"])
recruitment_router = APIRouter(tags=["Recruitment"])
oauth_router = APIRouter(tags=["OAuth"])


def init_recruitment_db() -> None:
    init_db()


def _base_url(request: Request) -> str:
    origin = request.headers.get("origin") or request.headers.get("referer", "").rstrip("/")
    if origin:
        parsed = urlparse(origin if "://" in origin else f"http://{origin}")
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
    return os.getenv("FRONTEND_URL", "http://localhost:3000")


def _oauth_redirect_uri(request: Request, platform_id: str, *, google: bool = False) -> str:
    """Stable OAuth callback URL — must match LinkedIn/Google app settings exactly."""
    if google:
        explicit = os.getenv("GOOGLE_REDIRECT_URI", "").strip()
        path = "/api/platforms/google/oauth/callback"
    else:
        explicit = os.getenv("LINKEDIN_REDIRECT_URI", "").strip()
        if not explicit:
            explicit = os.getenv(f"{platform_id.upper()}_REDIRECT_URI", "").strip()
        path = f"/api/platforms/{platform_id}/oauth/callback"

    if explicit:
        return explicit.rstrip("/")

    # Browser callback goes through the Next.js proxy on the frontend origin.
    frontend = os.getenv("FRONTEND_URL", "").strip().rstrip("/")
    if frontend:
        return f"{frontend}{path}"

    backend = os.getenv("BACKEND_URL", "").strip().rstrip("/")
    if backend:
        return f"{backend}{path}"

    return f"{str(request.base_url).rstrip('/')}{path}"


def _posting_out(posting: JobPosting) -> JobPostingOut:
    return JobPostingOut(
        id=posting.id,
        title=posting.title,
        jd=posting.get_jd(),
        natural_language_input=posting.natural_language_input,
        status=posting.status,
        created_at=posting.created_at,
        updated_at=posting.updated_at,
    )


@portal_router.get("/health")
def health():
    return {"status": "ok"}


# ── Auth ──────────────────────────────────────────────────────────────────────

@portal_router.post("/auth/register", response_model=TokenResponse)
def register(body: UserRegister, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    role = resolve_registration_role(body.email)
    tenant_id = f"tenant-{secrets.token_urlsafe(8)}"
    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role=role,
        status="active",
        tenant_id=tenant_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id, user.email)
    return TokenResponse(access_token=token, user=_user_out(user))


@portal_router.post("/auth/login", response_model=TokenResponse)
def login(body: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if user.status != "active":
        raise HTTPException(status_code=403, detail="Account is inactive")
    token = create_access_token(user.id, user.email)
    return TokenResponse(access_token=token, user=_user_out(user))


@portal_router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return _user_out(user)


@portal_router.patch("/auth/change-password")
def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.hashed_password = hash_password(body.new_password)
    db.commit()
    return {"message": "Password updated"}


# ── User management ───────────────────────────────────────────────────────────

def _user_out(user: User, tenant_name: str | None = None) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role or "admin",
        status=user.status or "active",
        tenant_id=user.tenant_id,
        tenant_name=tenant_name,
        created_at=user.created_at,
    )


def _search_users(query, q: str):
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(or_(User.full_name.ilike(like), User.email.ilike(like)))
    return query


def _paginate_users(query, page: int, page_size: int, q: str) -> PaginatedUsers:
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    query = _search_users(query, q)
    total = query.count()
    rows = (
        query.order_by(User.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PaginatedUsers(
        items=[_user_out(u) for u in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def _get_tenant_user(db: Session, admin: User, user_id: int) -> User:
    user = (
        db.query(User)
        .filter(
            User.id == user_id,
            User.tenant_id == admin.tenant_id,
            User.role.in_(tuple(TEAM_ROLES)),
        )
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@portal_router.get("/users", response_model=PaginatedUsers)
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    q: str = "",
    admin: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    query = db.query(User).filter(
        User.tenant_id == admin.tenant_id,
        User.role.in_(tuple(TEAM_ROLES)),
    )
    return _paginate_users(query, page, page_size, q)


@portal_router.post("/users", response_model=UserOut)
def create_user(
    body: CreateUserRequest,
    admin: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    if body.role not in TEAM_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role for team user")
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role=body.role,
        status=body.status or "active",
        tenant_id=admin.tenant_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_out(user)


@portal_router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: UpdateUserRequest,
    admin: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    user = _get_tenant_user(db, admin, user_id)
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.status is not None:
        user.status = body.status
    db.commit()
    db.refresh(user)
    return _user_out(user)


@portal_router.patch("/users/{user_id}/password")
def set_user_password(
    user_id: int,
    body: SetPasswordRequest,
    admin: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    user = _get_tenant_user(db, admin, user_id)
    user.hashed_password = hash_password(body.new_password)
    db.commit()
    return {"message": "Password updated"}


@portal_router.get("/super-admin/tenant-admins", response_model=PaginatedUsers)
def list_tenant_admins(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    q: str = "",
    _: User = Depends(require_roles("super_admin")),
    db: Session = Depends(get_db),
):
    query = db.query(User).filter(User.role == "admin")
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    query = _search_users(query, q)
    total = query.count()
    rows = (
        query.order_by(User.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PaginatedUsers(
        items=[_user_out(u, tenant_name=u.full_name) for u in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@portal_router.patch("/super-admin/tenant-admins/{user_id}", response_model=UserOut)
def update_tenant_admin(
    user_id: int,
    body: UpdateUserRequest,
    _: User = Depends(require_roles("super_admin")),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id, User.role == "admin").first()
    if not user:
        raise HTTPException(status_code=404, detail="Administrator not found")
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.status is not None:
        user.status = body.status
    db.commit()
    db.refresh(user)
    return _user_out(user, tenant_name=user.full_name)


@portal_router.patch("/super-admin/tenant-admins/{user_id}/password")
def set_tenant_admin_password(
    user_id: int,
    body: SetPasswordRequest,
    _: User = Depends(require_roles("super_admin")),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id, User.role == "admin").first()
    if not user:
        raise HTTPException(status_code=404, detail="Administrator not found")
    user.hashed_password = hash_password(body.new_password)
    db.commit()
    return {"message": "Password updated"}


# ── Contact form ──────────────────────────────────────────────────────────────

@portal_router.post("/contact")
def submit_contact(body: ContactRequest, db: Session = Depends(get_db)):
    row = ContactSubmission(
        full_name=body.full_name,
        email=body.email,
        company=body.company,
        message=body.message,
    )
    db.add(row)
    db.commit()
    return {"message": "Thank you for contacting us"}


@portal_router.get("/super-admin/contacts", response_model=PaginatedContactSubmissions)
def list_contact_submissions(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    q: str = "",
    _: User = Depends(require_roles("super_admin")),
    db: Session = Depends(get_db),
):
    query = db.query(ContactSubmission)
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                ContactSubmission.full_name.ilike(like),
                ContactSubmission.email.ilike(like),
                ContactSubmission.company.ilike(like),
                ContactSubmission.message.ilike(like),
            )
        )
    total = query.count()
    rows = (
        query.order_by(ContactSubmission.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PaginatedContactSubmissions(
        items=[ContactSubmissionOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


# ── JD Generation ─────────────────────────────────────────────────────────────

@recruitment_router.post("/jd/generate", response_model=JobPostingOut)
def generate_jd(
    body: GenerateJDRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    jd = generate_jd_from_natural_language(body.natural_language)
    posting = create_job_posting(db, user, body.natural_language, jd)
    return _posting_out(posting)


@recruitment_router.get("/jd", response_model=list[JobPostingOut])
def list_jds(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    postings = (
        db.query(JobPosting)
        .filter(JobPosting.recruiter_id == user.id)
        .order_by(JobPosting.created_at.desc())
        .all()
    )
    return [_posting_out(p) for p in postings]


@recruitment_router.get("/jd/{job_id}", response_model=JobPostingOut)
def get_jd(
    job_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    posting = _get_owned_posting(db, user, job_id)
    return _posting_out(posting)


@recruitment_router.put("/jd/{job_id}", response_model=JobPostingOut)
def update_jd(
    job_id: int,
    body: UpdateJDRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    posting = _get_owned_posting(db, user, job_id)
    posting = update_job_posting(db, posting, body.jd)
    return _posting_out(posting)


@recruitment_router.get("/jd/{job_id}/download")
def download_jd(
    job_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    posting = _get_owned_posting(db, user, job_id)
    text = jd_to_text(posting.get_jd())
    filename = posting.title.replace(" ", "_") + "_JD.txt"
    return PlainTextResponse(
        content=text,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Platforms ─────────────────────────────────────────────────────────────────

@recruitment_router.get("/platforms", response_model=list[PlatformInfo])
def platforms():
    return [PlatformInfo(**p) for p in get_platforms()]


@recruitment_router.get("/platforms/connections", response_model=list[PlatformConnectionOut])
def get_connections(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conns = list_user_connections(db, user.id)
    return [PlatformConnectionOut(**connection_to_dict(c)) for c in conns]


@recruitment_router.post("/platforms/{platform_id}/connect")
def connect_platform_account(
    platform_id: str,
    body: ConnectPlatformRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    valid = {p["id"] for p in get_platforms()}
    if platform_id.lower() not in valid:
        raise HTTPException(status_code=404, detail="Platform not found")

    if platform_id.lower() == "linkedin":
        if not _linkedin_configured():
            raise HTTPException(status_code=400, detail="LinkedIn OAuth is not configured.")

        previous = prepare_linkedin_reconnect(db, user)
        redirect_uri = _oauth_redirect_uri(request, platform_id)
        state, _ = begin_linkedin_oauth(db, user.id, redirect_uri)

        from platform_connect import LINKEDIN_LOGOUT_URL

        frontend = _base_url(request)
        launch = f"{frontend}/connect/linkedin?state={urllib.parse.quote(state)}"

        message = (
            "Sign in on linkedin.com (step 1), then authorize this app (step 2). "
            "Use the same browser where you signed in to LinkedIn."
        )

        return {
            "oauth_redirect": launch,
            "oauth_state": state,
            "sign_out_url": LINKEDIN_LOGOUT_URL,
            "sign_out_first": True,
            "replaced_previous": bool(previous),
            "mode": "oauth",
            "message": message,
        }

    try:
        conn = connect_platform(db, user, platform_id, body.email, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return PlatformConnectionOut(**connection_to_dict(conn))


@recruitment_router.delete("/platforms/{platform_id}/connect")
def disconnect_platform_account(
    platform_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        disconnect_platform(db, user, platform_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"message": f"Disconnected from {platform_id}"}


@recruitment_router.post("/platforms/{platform_id}/connect/quick", response_model=PlatformConnectionOut)
def connect_platform_with_portal_email(
    platform_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    valid = {p["id"] for p in get_platforms()}
    if platform_id.lower() not in valid:
        raise HTTPException(status_code=404, detail="Platform not found")
    conn = connect_platform_quick(db, user, platform_id)
    return PlatformConnectionOut(**connection_to_dict(conn))


@recruitment_router.get("/platforms/{platform_id}/google/start")
def start_google_connect(
    platform_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    valid = {p["id"] for p in get_platforms()}
    if platform_id.lower() not in valid:
        raise HTTPException(status_code=404, detail="Platform not found")

    redirect_uri = _oauth_redirect_uri(request, platform_id, google=True)
    url = get_google_oauth_start_url(db, user.id, platform_id, redirect_uri)
    if url:
        return {"auth_url": url, "mode": "oauth"}

    conn = connect_platform_google_fallback(db, user, platform_id)
    return {
        "auth_url": None,
        "mode": "quick",
        "connection": PlatformConnectionOut(**connection_to_dict(conn)),
    }


@oauth_router.get("/platforms/google/oauth/callback")
def google_oauth_callback(
    code: str,
    state: str,
    request: Request,
    db: Session = Depends(get_db),
):
    redirect_uri = _oauth_redirect_uri(request, "google", google=True)
    frontend = _base_url(request)
    try:
        _, platform = handle_google_oauth_callback(db, code, state, redirect_uri)
    except ValueError as exc:
        return RedirectResponse(
            f"{frontend}/dashboard?oauth_error={urllib.parse.quote(str(exc))}"
        )
    return RedirectResponse(f"{frontend}/dashboard?connected={platform}&via=google")


@oauth_router.get("/platforms/{platform_id}/oauth/start")
def start_oauth(
    platform_id: str,
    request: Request,
    force_login: bool = False,
    email: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if platform_id.lower() == "linkedin":
        prepare_linkedin_reconnect(db, user)
    redirect_uri = _oauth_redirect_uri(request, platform_id)
    url = get_oauth_start_url(
        db,
        user.id,
        platform_id,
        redirect_uri,
        force_login=force_login,
        login_hint=email,
        pending_email=email,
    )
    if not url:
        raise HTTPException(
            status_code=400,
            detail="OAuth not available. Use email/password to connect.",
        )
    return {"auth_url": url, "redirect_uri": redirect_uri}


@oauth_router.get("/platforms/linkedin/oauth/go")
def linkedin_oauth_go(
    state: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return LinkedIn authorize URL for a pending connect session (safe redirect hop)."""
    try:
        validate_linkedin_oauth_state(db, state, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    redirect_uri = _oauth_redirect_uri(request, "linkedin")
    auth_url = build_linkedin_authorize_url(state, redirect_uri)
    return {"auth_url": auth_url}


@oauth_router.get("/platforms/linkedin/oauth/begin")
def linkedin_oauth_begin(
    state: str,
    request: Request,
    step: str = "authorize",
    db: Session = Depends(get_db),
):
    """
    authorize: user already signed in on linkedin.com — go straight to OAuth consent.
    logout: clear stale LinkedIn session (optional troubleshooting).
    go: after logout — send to full login page, then OAuth.
    """
    row = peek_oauth_state(db, state)
    if not row:
        frontend = _base_url(request)
        msg = (
            "Connect session expired. Go back to the dashboard and click "
            "Connect LinkedIn again."
        )
        return RedirectResponse(f"{frontend}/dashboard?oauth_error={urllib.parse.quote(msg)}")

    frontend = os.getenv("FRONTEND_URL", _base_url(request)).rstrip("/")

    if step == "logout":
        return_url = linkedin_post_logout_return_url(frontend, state)
        return RedirectResponse(linkedin_logout_redirect_url(return_url))

    redirect_uri = _oauth_redirect_uri(request, "linkedin")
    auth_url = build_linkedin_authorize_url(state, redirect_uri)

    if step == "go":
        return RedirectResponse(linkedin_full_login_url(auth_url))

    return RedirectResponse(auth_url)


@oauth_router.get("/platforms/linkedin/setup")
def linkedin_setup(
    request: Request,
    user: User = Depends(get_current_user),
):
    """One-time LinkedIn Developer Portal checklist (not per-recruiter)."""
    _ = user
    redirect_uri = _oauth_redirect_uri(request, "linkedin")
    return linkedin_setup_status(redirect_uri)


def _oauth_error_message(error: str, description: str | None, platform_id: str) -> str:
    if error == "user_cancelled_login":
        return (
            "LinkedIn login was not completed. If you saw 'Please enter a password' with dots "
            "already filled, that is a LinkedIn page bug — not your password in our app. "
            "Try again: the app now signs you out of LinkedIn first automatically. "
            "On the full login page, type your password manually (no autofill). "
            "Or use a Private/Incognito browser window."
        )
    if error == "unauthorized_client" or error == "invalid_client":
        return (
            "LinkedIn rejected this app. Check LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET "
            "in backend/.env and ensure the Redirect URL in LinkedIn Developer Portal matches "
            "http://localhost:3000/api/platforms/linkedin/oauth/callback exactly."
        )
    if error == "unauthorized_scope_error":
        scopes = os.getenv("LINKEDIN_OAUTH_SCOPES", "w_member_social")
        if description and "openid" in description.lower():
            return (
                "LinkedIn rejected scope 'openid'. Your app only has Share on LinkedIn enabled. "
                "Set LINKEDIN_OAUTH_SCOPES=w_member_social in backend/.env and restart the server. "
                "Or request 'Sign In with LinkedIn using OpenID Connect' in LinkedIn Developer Portal."
            )
        return (
            f"LinkedIn rejected permissions: {description or error}. "
            f"Enable 'Share on LinkedIn' in LinkedIn Developer Portal → Products. "
            f"Scopes requested: {scopes}"
        )
    if error == "access_denied":
        return "LinkedIn authorization was cancelled. Click Connect with LinkedIn and approve all permissions."
    if description:
        return description
    return f"LinkedIn authorization failed: {error}"


@oauth_router.get("/platforms/{platform_id}/oauth/callback")
def oauth_callback(
    platform_id: str,
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    db: Session = Depends(get_db),
):
    frontend = _base_url(request)

    if error:
        msg = _oauth_error_message(error, error_description, platform_id)
        return RedirectResponse(
            f"{frontend}/dashboard?oauth_error={urllib.parse.quote(msg)}"
        )

    if not code or not state:
        return RedirectResponse(
            f"{frontend}/dashboard?oauth_error={urllib.parse.quote('LinkedIn authorization was cancelled or incomplete. Please try again.')}"
        )

    redirect_uri = _oauth_redirect_uri(request, platform_id)
    try:
        handle_oauth_callback(db, platform_id, code, state, redirect_uri)
    except ValueError as exc:
        return RedirectResponse(
            f"{frontend}/dashboard?oauth_error={urllib.parse.quote(str(exc))}"
        )
    return RedirectResponse(f"{frontend}/dashboard?connected={platform_id}")


@recruitment_router.post("/jd/{job_id}/post", response_model=PlatformPostOut)
def post_jd_to_platform(
    job_id: int,
    body: PostToPlatformRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    posting = _get_owned_posting(db, user, job_id)
    try:
        platform_post, message = post_to_platform(
            db,
            user,
            posting,
            body.platform,
            _base_url(request),
            force=body.force,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    conn = get_user_connection(db, user.id, body.platform)
    count = (
        db.query(Applicant)
        .filter(Applicant.platform_post_id == platform_post.id)
        .count()
    )
    return PlatformPostOut(
        id=platform_post.id,
        platform=platform_post.platform,
        external_url=platform_post.external_url,
        external_post_id=platform_post.external_post_id,
        account_url=platform_post.account_url,
        account_email=conn.account_email if conn else None,
        account_name=conn.account_name if conn else None,
        apply_url=get_apply_url(platform_post, _base_url(request)),
        status=platform_post.status,
        posted_at=platform_post.posted_at,
        applicant_count=count,
        message=message,
    )


@recruitment_router.get("/jd/{job_id}/posts", response_model=list[PlatformPostOut])
def list_platform_posts(
    job_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    posting = _get_owned_posting(db, user, job_id)
    posts = (
        db.query(PlatformPost)
        .filter(PlatformPost.job_posting_id == posting.id)
        .order_by(PlatformPost.posted_at.desc())
        .all()
    )
    result = []
    for pp in posts:
        count = db.query(Applicant).filter(Applicant.platform_post_id == pp.id).count()
        apply_url = get_apply_url(pp, _base_url(request))
        result.append(
            PlatformPostOut(
                id=pp.id,
                platform=pp.platform,
                external_url=pp.external_url,
                external_post_id=pp.external_post_id,
                account_url=pp.account_url,
                apply_url=apply_url,
                status=pp.status,
                posted_at=pp.posted_at,
                applicant_count=count,
                message=None,
                account_email=None,
                account_name=None,
            )
        )
    return result


# ── Applicants ────────────────────────────────────────────────────────────────

def _applicant_out(applicant: Applicant) -> ApplicantOut:
    resume = (applicant.resume_text or "").strip()
    has_file = bool(applicant.resume_file_path)
    return ApplicantOut(
        id=applicant.id,
        full_name=applicant.full_name,
        email=applicant.email,
        phone=applicant.phone,
        platform=applicant.platform,
        applied_at=applicant.applied_at,
        has_resume=bool(resume) or has_file,
        linkedin_url=applicant.linkedin_url,
        current_title=applicant.current_title,
        current_company=applicant.current_company,
        years_experience=applicant.years_experience,
        location=applicant.location,
        resume_filename=applicant.resume_filename,
    )


def _applicant_detail_out(applicant: Applicant) -> ApplicantDetailOut:
    base = _applicant_out(applicant)
    return ApplicantDetailOut(
        **base.model_dump(),
        resume_text=applicant.resume_text,
        cover_letter=applicant.cover_letter,
    )


def _get_owned_applicant(db: Session, user: User, job_id: int, applicant_id: int) -> Applicant:
    posting = _get_owned_posting(db, user, job_id)
    applicant = (
        db.query(Applicant)
        .filter(Applicant.id == applicant_id, Applicant.job_posting_id == posting.id)
        .first()
    )
    if not applicant:
        raise HTTPException(status_code=404, detail="Applicant not found")
    return applicant


@recruitment_router.get("/jd/{job_id}/applicants", response_model=list[ApplicantOut])
def list_applicants(
    job_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    posting = _get_owned_posting(db, user, job_id)
    applicants = (
        db.query(Applicant)
        .filter(Applicant.job_posting_id == posting.id)
        .order_by(Applicant.applied_at.desc())
        .all()
    )
    return [_applicant_out(a) for a in applicants]


@recruitment_router.get("/jd/{job_id}/applicants/export")
def export_applicants(
    job_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    posting = _get_owned_posting(db, user, job_id)
    applicants = (
        db.query(Applicant)
        .filter(Applicant.job_posting_id == posting.id)
        .order_by(Applicant.applied_at.desc())
        .all()
    )
    buffer = StringIO()
    csv_out = csv_writer(buffer)
    csv_out.writerow([
        "Name", "Email", "Phone", "LinkedIn", "Current Title", "Current Company",
        "Experience", "Location", "Platform", "Applied At", "Has Resume", "Resume File",
    ])
    for a in applicants:
        csv_out.writerow([
            a.full_name,
            a.email,
            a.phone or "",
            a.linkedin_url or "",
            a.current_title or "",
            a.current_company or "",
            a.years_experience or "",
            a.location or "",
            a.platform,
            a.applied_at.isoformat() if a.applied_at else "",
            "Yes" if ((a.resume_text or "").strip() or a.resume_file_path) else "No",
            a.resume_filename or "",
        ])
    safe_title = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in posting.title)
    filename = f"{safe_title}_applicants.csv"
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@recruitment_router.get("/jd/{job_id}/applicants/{applicant_id}", response_model=ApplicantDetailOut)
def get_applicant(
    job_id: int,
    applicant_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    applicant = _get_owned_applicant(db, user, job_id, applicant_id)
    return _applicant_detail_out(applicant)


@recruitment_router.get("/jd/{job_id}/applicants/{applicant_id}/resume")
def download_applicant_resume(
    job_id: int,
    applicant_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    applicant = _get_owned_applicant(db, user, job_id, applicant_id)
    resume = (applicant.resume_text or "").strip()
    if resume:
        docx_bytes = build_resume_docx(applicant)
        safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in applicant.full_name)
        filename = f"{safe_name}_resume.docx"
        return Response(
            content=docx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    file_path = resolve_applicant_resume_path(applicant.resume_file_path)
    if file_path:
        filename = applicant.resume_filename or file_path.name
        return FileResponse(
            file_path,
            filename=filename,
            media_type="application/octet-stream",
        )

    raise HTTPException(status_code=404, detail="No resume on file for this applicant")


@recruitment_router.get("/jd/{job_id}/applicants/{applicant_id}/application")
def download_applicant_application(
    job_id: int,
    applicant_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    applicant = _get_owned_applicant(db, user, job_id, applicant_id)
    posting = _get_owned_posting(db, user, job_id)
    docx_bytes = build_applicant_docx(applicant, posting.title)
    safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in applicant.full_name)
    filename = f"{safe_name}_application.docx"
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Public apply (candidates) ───────────────────────────────────────────────

@recruitment_router.get("/apply/{token}")
def get_apply_page(token: str, db: Session = Depends(get_db)):
    platform_post = db.query(PlatformPost).filter(PlatformPost.apply_token == token).first()
    if not platform_post:
        raise HTTPException(status_code=404, detail="Job not found")
    posting = db.query(JobPosting).filter(JobPosting.id == platform_post.job_posting_id).first()
    return {
        "platform": platform_post.platform,
        "job": posting.get_jd() if posting else {},
        "title": posting.title if posting else "Job",
    }


@recruitment_router.post("/apply/{token}")
async def apply_to_job(
    token: str,
    full_name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    current_title: str = Form(""),
    current_company: str = Form(""),
    years_experience: str = Form(""),
    location: str = Form(""),
    cover_letter: str = Form(""),
    resume_text: str = Form(""),
    resume_file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    name = full_name.strip()
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="Full name is required")

    extracted_text = resume_text.strip()
    resume_filename: str | None = None
    file_bytes: bytes | None = None

    if resume_file and resume_file.filename:
        file_bytes = await resume_file.read()
        resume_filename = resume_file.filename
        try:
            extracted_text = extract_resume_text(resume_file.filename, file_bytes) or extracted_text
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not extracted_text and not cover_letter.strip():
        raise HTTPException(
            status_code=400,
            detail="Upload your CV or add a cover letter to complete your application",
        )

    try:
        applicant = submit_application(
            db,
            token,
            name,
            email.strip(),
            phone=phone.strip() or None,
            current_title=current_title.strip() or None,
            current_company=current_company.strip() or None,
            years_experience=years_experience.strip() or None,
            location=location.strip() or None,
            cover_letter=cover_letter.strip() or None,
            resume_text=extracted_text or None,
            resume_filename=resume_filename,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if file_bytes and resume_filename:
        relative = save_applicant_resume(applicant.id, resume_filename, file_bytes)
        applicant.resume_file_path = relative
        db.commit()

    return {"message": "Application submitted successfully", "id": applicant.id}


# ── Platform webhooks (inbound applications) ─────────────────────────────────

@portal_router.post("/webhooks/linkedin/apply/{external_id}")
async def linkedin_apply_webhook(
    external_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        payload = await request.json()
        applicant = handle_linkedin_apply_webhook(db, external_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"message": "Application received", "id": applicant.id}


@portal_router.post("/webhooks/ziprecruiter/apply")
async def ziprecruiter_apply_webhook(request: Request, db: Session = Depends(get_db)):
    try:
        payload = await request.json()
        applicant = handle_ziprecruiter_apply_webhook(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"message": "Application received", "id": applicant.id}


@portal_router.post("/webhooks/indeed/apply")
async def indeed_apply_webhook(request: Request, db: Session = Depends(get_db)):
    try:
        payload = await request.json()
        applicant = handle_indeed_apply_webhook(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"message": "Application received", "id": applicant.id}


# ── XML job feeds (for platform syndication) ─────────────────────────────────

@portal_router.get("/feeds/jobs/{feed_token}.xml")
def get_job_feed(feed_token: str, request: Request, db: Session = Depends(get_db)):
    posts = (
        db.query(PlatformPost)
        .filter(PlatformPost.apply_token == feed_token)
        .all()
    )
    if not posts:
        post = db.query(PlatformPost).filter(PlatformPost.id == int(feed_token)).first() if feed_token.isdigit() else None
        if post:
            posts = [post]
    if not posts:
        raise HTTPException(status_code=404, detail="Feed not found")

    if len(posts) == 1:
        pp = posts[0]
        posting = db.query(JobPosting).filter(JobPosting.id == pp.job_posting_id).first()
        recruiter = db.query(User).filter(User.id == posting.recruiter_id).first() if posting else None
        xml = build_job_xml(
            posting,
            pp,
            get_apply_url(pp),
            recruiter.email if recruiter else "",
        )
    else:
        xml = build_multi_job_feed(posts, public_app_url())

    return Response(content=xml, media_type="application/xml")


def _get_owned_posting(db: Session, user: User, job_id: int) -> JobPosting:
    posting = (
        db.query(JobPosting)
        .filter(JobPosting.id == job_id, JobPosting.recruiter_id == user.id)
        .first()
    )
    if not posting:
        raise HTTPException(status_code=404, detail="Job posting not found")
    return posting


def _print_links(host: str, port: int) -> None:
    base = f"http://{host}:{port}"
    print("\n" + "=" * 52, flush=True)
    print("  AI Recruitment & Screening - Backend STARTED", flush=True)
    print("=" * 52, flush=True)
    print(f"  Uvicorn:  {base}", flush=True)
    print(f"  Swagger:  {base}/docs   <-- open this in browser", flush=True)
    print(f"  ReDoc:    {base}/redoc", flush=True)
    print(f"  API:      {base}/api/health", flush=True)
    print("=" * 52, flush=True)
    print("  Press CTRL+C to stop the server\n", flush=True)


def _free_port(port: int) -> None:
    """Stop any process already listening on this port (Windows)."""
    import subprocess
    import sys
    import time

    if sys.platform != "win32":
        return

    current_pid = os.getpid()
    pids: set[int] = set()

    ps_cmd = (
        f"Get-NetTCPConnection -LocalPort {port} -State Listen "
        f"-ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            errors="ignore",
            check=False,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.isdigit():
                pids.add(int(line))
    except Exception:
        pass

    if not pids:
        try:
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                errors="ignore",
                check=False,
            )
            for line in result.stdout.splitlines():
                if "LISTENING" not in line.upper() or f":{port}" not in line:
                    continue
                parts = line.split()
                if parts and parts[-1].isdigit():
                    pids.add(int(parts[-1]))
        except Exception:
            return

    killed = False
    for pid in pids:
        if pid == current_pid:
            continue
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
            check=False,
        )
        killed = True

    if killed:
        time.sleep(1.5)

    # Last resort on Windows: stop orphaned python processes still holding the port
    if sys.platform == "win32" and pids:
        try:
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                errors="ignore",
                check=False,
            )
            still_blocked = any(
                f":{port}" in line and "LISTENING" in line.upper()
                for line in result.stdout.splitlines()
            )
            if still_blocked:
                subprocess.run(
                    [
                        "powershell",
                        "-NoProfile",
                        "-Command",
                        f"Get-NetTCPConnection -LocalPort {port} -State Listen "
                        f"-ErrorAction SilentlyContinue | "
                        f"ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }}",
                    ],
                    capture_output=True,
                    check=False,
                )
                time.sleep(1)
        except Exception:
            pass


def _can_bind(host: str, port: int) -> bool:
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as test_sock:
            test_sock.bind((host, port))
        return True
    except OSError:
        return False


def _acquire_port(host: str, port: int) -> int:
    """Free port and return a port we can bind to."""
    import sys

    for attempt in range(3):
        _free_port(port)
        if _can_bind(host, port):
            return port
        import time
        time.sleep(1)

    for alt in range(port + 1, port + 10):
        if _can_bind(host, alt):
            print(f"\nNOTE: Port {port} was busy. Using port {alt} instead.", flush=True)
            print(f"Update frontend/.env.local: NEXT_PUBLIC_API_URL=http://{host}:{alt}/api\n", flush=True)
            return alt

    print(f"\nERROR: Could not bind port {port}. Close other python/uvicorn terminals and retry.\n")
    sys.exit(1)

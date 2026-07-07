import os
import secrets
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from database import OAuthState, PlatformConnection, User

LINKEDIN_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_PROFILE_URL = "https://api.linkedin.com/v2/userinfo"
LINKEDIN_LOGOUT_URL = "https://www.linkedin.com/m/logout"
LINKEDIN_UAS_LOGOUT_URL = "https://www.linkedin.com/uas/logout"
DEFAULT_LINKEDIN_SCOPES = "openid profile email w_member_social"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

GOOGLE_EMAIL_DOMAINS = ("gmail.com", "googlemail.com", "google.com")

DEFAULT_OAUTH_STATE_TTL = 3600  # 1 hour — users may need time on linkedin.com login


def _oauth_state_ttl() -> int:
    return int(os.getenv("OAUTH_STATE_TTL", str(DEFAULT_OAUTH_STATE_TTL)))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _cleanup_expired_oauth_states(db: Session) -> None:
    now = _utcnow()
    stale = db.query(OAuthState).filter(OAuthState.expires_at < now).all()
    for row in stale:
        db.delete(row)
    if stale:
        db.commit()


def _save_oauth_state(
    db: Session,
    state: str,
    user_id: int,
    platform: str,
    email: str | None = None,
    provider: str = "linkedin",
) -> None:
    _cleanup_expired_oauth_states(db)
    db.query(OAuthState).filter(
        OAuthState.user_id == user_id,
        OAuthState.platform == platform.lower(),
    ).delete()
    db.add(
        OAuthState(
            state=state,
            user_id=user_id,
            platform=platform.lower(),
            email=email,
            provider=provider,
            expires_at=_utcnow() + timedelta(seconds=_oauth_state_ttl()),
        )
    )
    db.commit()


def _consume_oauth_state(db: Session, state: str) -> dict[str, Any] | None:
    row = db.query(OAuthState).filter(OAuthState.state == state).first()
    if not row:
        return None
    if row.expires_at < _utcnow():
        db.delete(row)
        db.commit()
        return None
    data = {
        "user_id": row.user_id,
        "platform": row.platform,
        "email": row.email,
        "provider": row.provider,
    }
    db.delete(row)
    db.commit()
    return data


def _clear_oauth_states(db: Session, user_id: int, platform: str | None = None) -> None:
    query = db.query(OAuthState).filter(OAuthState.user_id == user_id)
    if platform:
        query = query.filter(OAuthState.platform == platform.lower())
    query.delete()
    db.commit()


def _linkedin_configured() -> bool:
    return bool(os.getenv("LINKEDIN_CLIENT_ID") and os.getenv("LINKEDIN_CLIENT_SECRET"))


def _google_configured() -> bool:
    return bool(os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET"))


def get_user_connection(db: Session, user_id: int, platform: str) -> PlatformConnection | None:
    return (
        db.query(PlatformConnection)
        .filter(
            PlatformConnection.user_id == user_id,
            PlatformConnection.platform == platform.lower(),
        )
        .first()
    )


def list_user_connections(db: Session, user_id: int) -> list[PlatformConnection]:
    return (
        db.query(PlatformConnection)
        .filter(PlatformConnection.user_id == user_id)
        .order_by(PlatformConnection.connected_at.desc())
        .all()
    )


def connection_to_dict(conn: PlatformConnection) -> dict[str, Any]:
    has_token = bool(conn.access_token)
    can_post = has_token if conn.platform == "linkedin" else True
    return {
        "platform": conn.platform,
        "account_email": conn.account_email,
        "account_name": conn.account_name,
        "account_url": conn.account_url,
        "connected_at": conn.connected_at,
        "is_oauth": has_token,
        "can_post": can_post,
    }


def prepare_linkedin_reconnect(db: Session, user: User) -> str | None:
    """
    Drop any stored LinkedIn connection and pending OAuth states before a new sign-in.
    Returns the previously connected email, if any.
    """
    existing = get_user_connection(db, user.id, "linkedin")
    previous_email = existing.account_email if existing else None
    if existing:
        db.delete(existing)
        db.commit()
    _clear_oauth_states(db, user.id, "linkedin")
    return previous_email


def _upsert_connection(
    db: Session,
    user_id: int,
    platform: str,
    email: str,
    account_name: str | None = None,
    account_url: str | None = None,
    access_token: str | None = None,
    refresh_token: str | None = None,
) -> PlatformConnection:
    platform = platform.lower()
    email = email.strip().lower()
    name = account_name or email.split("@")[0].replace(".", " ").title()
    url = account_url or _default_account_url(platform, email)

    existing = get_user_connection(db, user_id, platform)
    if existing:
        existing.account_email = email
        existing.account_name = name
        existing.account_url = url
        if access_token:
            existing.access_token = access_token
        if refresh_token:
            existing.refresh_token = refresh_token
        conn = existing
    else:
        conn = PlatformConnection(
            user_id=user_id,
            platform=platform,
            account_email=email,
            account_name=name,
            account_url=url,
            access_token=access_token,
            refresh_token=refresh_token,
        )
        db.add(conn)

    db.commit()
    db.refresh(conn)
    return conn


def connect_platform(
    db: Session,
    user: User,
    platform: str,
    email: str,
    password: str,
) -> PlatformConnection:
    """Connect via platform credentials. Password is verified, never stored."""
    platform = platform.lower()
    email = email.strip().lower()
    if not email or "@" not in email:
        raise ValueError("Please enter a valid email address.")
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters.")

    if platform == "linkedin":
        raise ValueError(
            "LINKEDIN_OAUTH_REDIRECT:"
            "Use the LinkedIn sign-in button — you will enter your password on linkedin.com."
        )

    return _upsert_connection(db, user.id, platform, email)


def connect_platform_quick(db: Session, user: User, platform: str) -> PlatformConnection:
    """Connect using the recruiter's logged-in portal email (no password needed)."""
    platform = platform.lower()
    if platform == "linkedin":
        raise ValueError(
            "LinkedIn requires your LinkedIn email and password, or use 'Sign in with LinkedIn'."
        )
    return _upsert_connection(
        db,
        user.id,
        platform,
        user.email,
        account_name=user.full_name,
    )


def connect_platform_google_fallback(db: Session, user: User, platform: str) -> PlatformConnection:
    """Use portal email when Google OAuth is not configured."""
    return _upsert_connection(
        db,
        user.id,
        platform,
        user.email,
        account_name=user.full_name,
    )


def disconnect_platform(db: Session, user: User, platform: str) -> None:
    conn = get_user_connection(db, user.id, platform.lower())
    if not conn:
        raise ValueError("No connection found for this platform.")
    db.delete(conn)
    db.commit()
    _clear_oauth_states(db, user.id, platform.lower())


def _default_account_url(platform: str, email: str) -> str:
    slug = email.split("@")[0]
    urls = {
        "linkedin": f"https://www.linkedin.com/in/{slug}",
        "indeed": "https://employers.indeed.com/",
        "dice": "https://www.dice.com/hiring",
        "ziprecruiter": "https://www.ziprecruiter.com/",
    }
    return urls.get(platform, f"https://{platform}.com/{slug}")


def get_google_oauth_start_url(
    db: Session,
    user_id: int,
    platform: str,
    redirect_uri: str,
) -> str | None:
    platform = platform.lower()
    if not _google_configured():
        return None

    state = secrets.token_urlsafe(24)
    _save_oauth_state(db, state, user_id, platform, provider="google")

    params = {
        "response_type": "code",
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account",
    }
    return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"


def handle_google_oauth_callback(
    db: Session,
    code: str,
    state: str,
    redirect_uri: str,
) -> tuple[PlatformConnection, str]:
    state_data = _consume_oauth_state(db, state)
    if not state_data or state_data.get("provider") != "google":
        raise ValueError(
            "LinkedIn sign-in session expired or was interrupted. "
            "Please click Connect LinkedIn again — your session is saved for 30 minutes."
        )

    user_id = state_data["user_id"]
    platform = state_data["platform"]
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

    with httpx.Client(timeout=20) as client:
        token_res = client.post(
            GOOGLE_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
        if token_res.status_code != 200:
            raise ValueError("Google authorization failed. Please try again.")
        token_data = token_res.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise ValueError("Google did not return an access token.")

        profile_res = client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        profile = profile_res.json() if profile_res.status_code == 200 else {}

    email = profile.get("email", "")
    if not email:
        raise ValueError("Could not retrieve email from Google account.")

    name = profile.get("name", email.split("@")[0])
    conn = _upsert_connection(
        db,
        user_id,
        platform,
        email,
        account_name=name,
        access_token=access_token,
        refresh_token=token_data.get("refresh_token"),
    )
    return conn, platform


def _fetch_linkedin_profile(
    client: httpx.Client,
    access_token: str,
    id_token: str | None = None,
) -> dict[str, Any]:
    from linkedin_profile import _decode_jwt_claims, resolve_linkedin_person_id

    profile: dict[str, Any] = {}
    if id_token:
        claims = _decode_jwt_claims(id_token)
        if claims.get("email"):
            profile["email"] = claims.get("email", "")
        if claims.get("name"):
            profile["name"] = claims.get("name", "")

    person_id, hints = resolve_linkedin_person_id(access_token, id_token, client=client)
    if person_id:
        profile.setdefault("email", hints.get("email", ""))
        profile.setdefault("name", hints.get("name", ""))
        profile["sub"] = person_id
        if hints.get("profile_url"):
            profile["profile_url"] = hints.get("profile_url")
        return profile

    profile_res = client.get(
        LINKEDIN_PROFILE_URL,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if profile_res.status_code == 200:
        data = profile_res.json()
        return {
            "email": data.get("email", "") or profile.get("email", ""),
            "name": data.get("name", "") or profile.get("name", ""),
            "sub": data.get("sub", "") or profile.get("sub", ""),
        }
    return profile


def peek_oauth_state(db: Session, state: str) -> OAuthState | None:
    """Return pending OAuth row if valid; does not delete it."""
    row = db.query(OAuthState).filter(OAuthState.state == state).first()
    if not row:
        return None
    if row.expires_at < _utcnow():
        db.delete(row)
        db.commit()
        return None
    return row


def linkedin_post_logout_return_url(frontend_base: str, state: str) -> str:
    base = frontend_base.rstrip("/")
    return f"{base}/connect/linkedin?state={urllib.parse.quote(state)}&step=go"


def linkedin_logout_redirect_url(return_url: str) -> str:
    """LinkedIn logout that returns the user to our app (clears stale Welcome Back sessions)."""
    return (
        f"{LINKEDIN_UAS_LOGOUT_URL}?session_full=true&session_redirect="
        f"{urllib.parse.quote(return_url, safe='')}"
    )


def begin_linkedin_oauth(
    db: Session,
    user_id: int,
    redirect_uri: str,
) -> tuple[str, str]:
    """Create OAuth state and return (state_token, linkedin_authorize_url)."""
    state = secrets.token_urlsafe(24)
    _save_oauth_state(db, state, user_id, "linkedin")
    return state, build_linkedin_authorize_url(state, redirect_uri)


def build_linkedin_authorize_url(state: str, redirect_uri: str) -> str:
    """
    Build LinkedIn OAuth URL for any LinkedIn member.
    No login_hint or prompt=login — those break LinkedIn's password form.
    """
    scopes = os.getenv("LINKEDIN_OAUTH_SCOPES", DEFAULT_LINKEDIN_SCOPES).strip()
    prompt = os.getenv("LINKEDIN_OAUTH_PROMPT", "").strip()
    if "login" in prompt.lower():
        prompt = ""

    params = {
        "response_type": "code",
        "client_id": os.getenv("LINKEDIN_CLIENT_ID"),
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": scopes,
    }
    if prompt:
        params["prompt"] = prompt

    return f"{LINKEDIN_AUTH_URL}?{urllib.parse.urlencode(params)}"


def linkedin_full_login_url(oauth_authorize_url: str) -> str:
    """
    Send users to linkedin.com/login (full form) instead of the broken
    OAuth 'Welcome Back' interstitial that rejects autofilled passwords.
    After login, LinkedIn redirects to the OAuth authorize URL.
    """
    return "https://www.linkedin.com/login?" + urllib.parse.urlencode(
        {"session_redirect": oauth_authorize_url}
    )


def linkedin_setup_status(redirect_uri: str) -> dict[str, Any]:
    """One-time app checklist — recruiters do NOT need individual LinkedIn approval."""
    configured = _linkedin_configured()
    return {
        "configured": configured,
        "redirect_uri": redirect_uri,
        "scopes": os.getenv("LINKEDIN_OAUTH_SCOPES", DEFAULT_LINKEDIN_SCOPES).strip(),
        "developer_portal_url": "https://www.linkedin.com/developers/apps",
        "one_time_setup": True,
        "recruiter_access": "Any recruiter can connect their own LinkedIn once these products are enabled on YOUR app (one time).",
        "required_products": [
            {
                "name": "Sign In with LinkedIn using OpenID Connect",
                "why": "Lets any member sign in (openid profile email scopes)",
            },
            {
                "name": "Share on LinkedIn",
                "why": "Lets members authorize posting (w_member_social scope)",
            },
        ],
        "redirect_uri_must_match": redirect_uri,
        "steps": [
            "Open LinkedIn Developer Portal → your app → Products tab",
            "Add BOTH products above (usually instant approval — not per-user)",
            "Auth tab → add Redirect URL exactly: " + redirect_uri,
            "Copy Client ID + Secret into backend/.env and restart backend",
            "Each recruiter clicks Sign in with LinkedIn in this app — no extra LinkedIn request per person",
        ],
    }


def validate_linkedin_oauth_state(db: Session, state: str, user_id: int) -> None:
    row = db.query(OAuthState).filter(OAuthState.state == state).first()
    if not row:
        raise ValueError(
            "LinkedIn sign-in session expired. Please go back and click Connect LinkedIn again."
        )
    if row.user_id != user_id:
        raise ValueError("Invalid LinkedIn sign-in session.")
    if row.expires_at < _utcnow():
        db.delete(row)
        db.commit()
        raise ValueError(
            "LinkedIn sign-in session expired. Please go back and click Connect LinkedIn again."
        )


def get_oauth_start_url(
    db: Session,
    user_id: int,
    platform: str,
    redirect_uri: str,
    force_login: bool = False,
    login_hint: str | None = None,
    pending_email: str | None = None,
) -> str | None:
    _ = force_login, login_hint, pending_email  # kept for API compatibility
    platform = platform.lower()
    if platform != "linkedin" or not _linkedin_configured():
        return None
    _, url = begin_linkedin_oauth(db, user_id, redirect_uri)
    return url


def handle_oauth_callback(
    db: Session,
    platform: str,
    code: str,
    state: str,
    redirect_uri: str,
) -> PlatformConnection:
    platform = platform.lower()
    state_data = _consume_oauth_state(db, state)
    if not state_data:
        raise ValueError(
            "LinkedIn sign-in session expired or was interrupted. "
            "Please click Connect LinkedIn again — each recruiter can connect their own account."
        )

    user_id = state_data["user_id"]
    if platform == "linkedin":
        return _linkedin_oauth_exchange(db, user_id, code, redirect_uri)
    raise ValueError(f"OAuth not supported for {platform}")


def _linkedin_oauth_exchange(
    db: Session,
    user_id: int,
    code: str,
    redirect_uri: str,
) -> PlatformConnection:
    client_id = os.getenv("LINKEDIN_CLIENT_ID")
    client_secret = os.getenv("LINKEDIN_CLIENT_SECRET")

    with httpx.Client(timeout=20) as client:
        token_res = client.post(
            LINKEDIN_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if token_res.status_code != 200:
            detail = ""
            try:
                detail = token_res.json().get("error_description", "")
            except Exception:
                detail = token_res.text[:200]
            raise ValueError(
                detail
                or "LinkedIn authorization failed. If your app is in Development mode, "
                "add this LinkedIn account as a tester in LinkedIn Developer Portal."
            )
        token_data = token_res.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise ValueError("LinkedIn did not return an access token.")

        id_token = token_data.get("id_token")
        profile = _fetch_linkedin_profile(client, access_token, id_token=id_token)

    from linkedin_profile import _decode_jwt_sub, pack_linkedin_refresh

    person_id = ""
    if id_token:
        person_id = _decode_jwt_sub(id_token) or ""
    if not person_id:
        person_id = profile.get("sub", "") or ""

    profile_email = (profile.get("email") or "").strip().lower()

    if not profile_email:
        raise ValueError(
            "LinkedIn did not return your email. Enable 'Sign In with LinkedIn using OpenID Connect' "
            "in LinkedIn Developer Portal and set LINKEDIN_OAUTH_SCOPES=openid profile email w_member_social "
            "in backend/.env, then restart the backend and connect again."
        )

    email = profile_email
    name = profile.get("name") or email.split("@")[0].replace(".", " ").title()
    account_url = profile.get("profile_url") or (
        f"https://www.linkedin.com/in/{person_id}" if person_id else _default_account_url("linkedin", email)
    )

    if not person_id:
        raise ValueError(
            "LinkedIn authorized but your profile ID could not be loaded. "
            "Enable BOTH 'Share on LinkedIn' and 'Sign In with LinkedIn using OpenID Connect' "
            "in LinkedIn Developer Portal, restart the backend, and connect again."
        )

    refresh = pack_linkedin_refresh(person_id, token_data.get("refresh_token"))

    # Replace any previous LinkedIn connection for this recruiter with the newly signed-in account.
    existing = get_user_connection(db, user_id, "linkedin")
    if existing:
        db.delete(existing)
        db.flush()

    conn = PlatformConnection(
        user_id=user_id,
        platform="linkedin",
        account_email=email,
        account_name=name,
        account_url=account_url,
        access_token=access_token,
        refresh_token=refresh,
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return conn

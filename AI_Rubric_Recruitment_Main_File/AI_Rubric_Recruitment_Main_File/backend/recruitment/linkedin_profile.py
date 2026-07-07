"""Resolve LinkedIn member ID / URN for OAuth posting."""

import base64
import json
import os
from typing import Any

import httpx


def _decode_jwt_claims(id_token: str) -> dict[str, Any]:
    try:
        parts = id_token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1]
        padded = payload + "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _decode_jwt_sub(id_token: str) -> str | None:
    sub = _decode_jwt_claims(id_token).get("sub", "")
    if not sub:
        return None
    if str(sub).startswith("urn:li:person:"):
        return str(sub).split(":")[-1]
    return str(sub)


def _person_id_from_data(data: dict[str, Any]) -> str | None:
    raw_id = data.get("id") or data.get("sub")
    if not raw_id:
        return None
    raw_id = str(raw_id)
    if raw_id.startswith("urn:li:person:"):
        return raw_id.split(":")[-1]
    return raw_id


def resolve_linkedin_person_id(
    access_token: str,
    id_token: str | None = None,
    client: httpx.Client | None = None,
) -> tuple[str | None, dict[str, Any]]:
    """
    Return (person_id, profile_hints).
    Tries id_token, /v2/me, /rest/me, /v2/userinfo.
    """
    profile: dict[str, Any] = {}

    if id_token:
        person_id = _decode_jwt_sub(id_token)
        if person_id:
            return person_id, {"sub": person_id, "source": "id_token"}

    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=20)

    try:
        auth = {"Authorization": f"Bearer {access_token}"}

        # v2/me — do NOT send LinkedIn-Version (REST-only header breaks v2)
        me_res = client.get(
            "https://api.linkedin.com/v2/me?projection=(id,localizedFirstName,localizedLastName,vanityName)",
            headers={**auth, "X-Restli-Protocol-Version": "2.0.0"},
        )
        if me_res.status_code == 200:
            me = me_res.json()
            person_id = _person_id_from_data(me)
            if person_id:
                first = me.get("localizedFirstName", "")
                last = me.get("localizedLastName", "")
                vanity = me.get("vanityName", "")
                profile = {
                    "sub": person_id,
                    "name": f"{first} {last}".strip(),
                    "profile_url": f"https://www.linkedin.com/in/{vanity}" if vanity else None,
                    "source": "v2/me",
                }
                return person_id, profile

        # REST me endpoint
        linkedin_version = os.getenv("LINKEDIN_API_VERSION", "202503")
        rest_res = client.get(
            "https://api.linkedin.com/rest/me",
            headers={**auth, "LinkedIn-Version": linkedin_version},
        )
        if rest_res.status_code == 200:
            rest = rest_res.json()
            person_id = _person_id_from_data(rest)
            if person_id:
                profile = {"sub": person_id, "source": "rest/me"}
                return person_id, profile

        # OpenID userinfo (needs openid scope)
        info_res = client.get("https://api.linkedin.com/v2/userinfo", headers=auth)
        if info_res.status_code == 200:
            info = info_res.json()
            person_id = _person_id_from_data(info)
            if person_id:
                profile = {
                    "sub": person_id,
                    "email": info.get("email"),
                    "name": info.get("name"),
                    "source": "userinfo",
                }
                return person_id, profile

        return None, profile
    finally:
        if owns_client and client:
            client.close()


def person_id_to_urn(person_id: str) -> str:
    if person_id.startswith("urn:li:person:"):
        return person_id
    return f"urn:li:person:{person_id}"


PERSON_ID_PREFIX = "person_id:"
OAUTH_REFRESH_MARKER = "|oauth_refresh:"


def pack_linkedin_refresh(person_id: str, oauth_refresh: str | None = None) -> str:
    """Persist member ID for posting; optionally keep LinkedIn OAuth refresh token."""
    if not person_id:
        raise ValueError("LinkedIn person_id is required")
    packed = f"{PERSON_ID_PREFIX}{person_id}"
    if oauth_refresh:
        packed += f"{OAUTH_REFRESH_MARKER}{oauth_refresh}"
    return packed


def unpack_linkedin_person_id(refresh_token: str | None) -> str | None:
    if not refresh_token or not refresh_token.startswith(PERSON_ID_PREFIX):
        return None
    rest = refresh_token[len(PERSON_ID_PREFIX) :]
    if OAUTH_REFRESH_MARKER in rest:
        return rest.split(OAUTH_REFRESH_MARKER, 1)[0].strip() or None
    return rest.strip() or None


def unpack_linkedin_oauth_refresh(refresh_token: str | None) -> str | None:
    if not refresh_token or OAUTH_REFRESH_MARKER not in refresh_token:
        return None
    return refresh_token.split(OAUTH_REFRESH_MARKER, 1)[1].strip() or None

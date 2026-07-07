"""Public-facing app URLs for candidate apply links (never backend API URLs)."""

import os
from urllib.parse import urlparse


def public_app_url() -> str:
    """Base URL candidates use to open /apply/{token} in the browser."""
    for key in ("PUBLIC_APP_URL", "FRONTEND_URL"):
        url = os.getenv(key, "").strip().rstrip("/")
        if url:
            return url
    return "http://localhost:3000"


def is_local_app_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "::1") or host.endswith(".local")

"""Persist uploaded applicant resume files on disk."""

from __future__ import annotations

import re
from pathlib import Path

UPLOAD_ROOT = Path(__file__).resolve().parent / "uploads" / "applicants"


def _safe_filename(name: str) -> str:
    base = Path(name).name
    cleaned = re.sub(r"[^\w.\-]+", "_", base).strip("._")
    return cleaned or "resume.pdf"


def save_applicant_resume(applicant_id: int, filename: str, content: bytes) -> str:
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    safe = _safe_filename(filename)
    path = UPLOAD_ROOT / f"{applicant_id}_{safe}"
    path.write_bytes(content)
    return str(path.relative_to(Path(__file__).resolve().parent))


def resolve_applicant_resume_path(relative_path: str | None) -> Path | None:
    if not relative_path:
        return None
    base = Path(__file__).resolve().parent
    path = (base / relative_path).resolve()
    if not str(path).startswith(str(base.resolve())):
        return None
    return path if path.is_file() else None

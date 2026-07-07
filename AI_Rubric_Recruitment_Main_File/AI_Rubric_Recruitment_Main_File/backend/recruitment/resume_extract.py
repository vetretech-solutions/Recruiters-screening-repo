"""Extract plain text from uploaded resume files."""

from __future__ import annotations

from io import BytesIO

MAX_RESUME_BYTES = 5 * 1024 * 1024
ALLOWED_RESUME_EXTENSIONS = {".pdf", ".docx", ".txt"}


def _extension(filename: str) -> str:
    dot = filename.rfind(".")
    return filename[dot:].lower() if dot >= 0 else ""


def extract_resume_text(filename: str, content: bytes) -> str:
    if len(content) > MAX_RESUME_BYTES:
        raise ValueError("Resume file must be 5 MB or smaller")

    ext = _extension(filename)
    if ext not in ALLOWED_RESUME_EXTENSIONS:
        raise ValueError("Upload a PDF, DOCX, or TXT resume")

    if ext == ".txt":
        return content.decode("utf-8", errors="ignore").strip()

    if ext == ".pdf":
        import fitz

        doc = fitz.open(stream=content, filetype="pdf")
        try:
            parts = [page.get_text("text") for page in doc]
        finally:
            doc.close()
        return "\n".join(parts).strip()

    if ext == ".docx":
        from docx import Document

        doc = Document(BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs if p.text).strip()

    raise ValueError("Unsupported resume file type")

import json
import os
import re
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY", "")
PRIMARY_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
FALLBACK_MODELS = [
    m.strip()
    for m in os.getenv("GEMINI_FALLBACK_MODELS", "gemini-2.0-flash,gemini-1.5-flash").split(",")
    if m.strip()
]


class GeminiError(Exception):
    pass


def _get_client() -> genai.Client:
    if not API_KEY:
        raise GeminiError("GEMINI_API_KEY is not set in .env")
    return genai.Client(api_key=API_KEY)


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            return json.loads(text[start : end + 1])
        raise GeminiError("Failed to parse JSON from AI response")


def generate_json(prompt: str, system: str = "") -> dict[str, Any]:
    client = _get_client()
    models = [PRIMARY_MODEL] + [m for m in FALLBACK_MODELS if m != PRIMARY_MODEL]
    last_error: Exception | None = None

    for model in models:
        try:
            config = types.GenerateContentConfig(
                temperature=0.4,
                response_mime_type="application/json",
            )
            contents = prompt
            if system:
                contents = f"{system}\n\n{prompt}"

            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
            text = response.text or ""
            return _extract_json(text)
        except Exception as exc:
            last_error = exc
            continue

    raise GeminiError(f"All models failed: {last_error}")

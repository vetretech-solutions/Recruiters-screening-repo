"""
Unified backend entry point — recruitment portal + rubric screening.

Run:
    cd backend
    python main.py
"""

#yes changes made here
from __future__ import annotations

import importlib.util
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

def _load_module(name: str, folder: str, filename: str = "routes.py"):
    folder_path = ROOT / folder
    filepath = folder_path / filename
    if str(folder_path) not in sys.path:
        sys.path.insert(0, str(folder_path))
    spec = importlib.util.spec_from_file_location(name, filepath)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {filepath}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


recruitment = _load_module("recruitment_routes", "recruitment")
screening = _load_module("screening_routes", "screening")


def _cors_origins() -> list[str]:
    origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    for key in ("FRONTEND_URL", "PUBLIC_APP_URL"):
        url = os.getenv(key, "").strip().rstrip("/")
        if url and url not in origins:
            origins.append(url)
    extra = os.getenv("CORS_ORIGINS", "")
    for url in extra.split(","):
        url = url.strip().rstrip("/")
        if url and url not in origins:
            origins.append(url)
    return origins


@asynccontextmanager
async def lifespan(_app: FastAPI):
    recruitment.init_recruitment_db()
    screening.init_screening_db()
    yield


app = FastAPI(
    title="AI Recruitment & Screening API",
    description="Unified backend for job posting, platforms, and resume rubric screening",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(recruitment.portal_router, prefix="/api")
app.include_router(recruitment.oauth_router, prefix="/api")
app.include_router(recruitment.recruitment_router, prefix="/api/recruitment")
app.include_router(screening.router, prefix="/api/screening")


@app.get("/")
def root():
    return {
        "message": "AI Recruitment & Screening API",
        "docs": "/docs",
        "health": "/api/health",
        "recruitment": "/api/recruitment",
        "screening": "/api/screening/health",
    }


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("RELOAD", "false").lower() in ("1", "true", "yes")

    port = recruitment._acquire_port(host, port)
    recruitment._print_links(host, port)

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )

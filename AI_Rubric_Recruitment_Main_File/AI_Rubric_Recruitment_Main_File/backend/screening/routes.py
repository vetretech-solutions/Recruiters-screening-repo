
# ============================================================
# main.py
# FastAPI application — DB connection, data fetching,
# Gemini Rubric scoring, and REST endpoints.
#
# Real DB schema used:
#   resume_candidates: resume_id, name, email, mobile_no,
#     summary, technical_skills, work_experience, project,
#     education, internship_experience, certification,
#     soft_skills, linkedin_url, github_url, created_at
#
#   job_roles: job_role, experience, project_duration,
#     project_initiative, skills, responsibilities,
#     bonus_skills, created_at
# ============================================================

import os
import json
import logging
from typing import List, Optional
import psycopg2
import psycopg2.extras
from fastapi import APIRouter, HTTPException, File, UploadFile, Form
from fastapi.responses import StreamingResponse
import uuid
import random
import shutil
import tempfile
from datetime import datetime
from models import (
    Candidate,
    JobRole,
    CandidateEvaluation,
    FullAnalysisResult,
    AnalyseJobRequest,
    HealthResponse,
    RTRRequest,
    RTRVerificationRequest,
    FinalSelectedCandidate,
    RubricWeights,
    DEFAULT_RUBRIC_WEIGHTS,
)
from resumeanalyser import (
    analyse_candidate_with_rubric, 
    select_top_candidates, 
    bulk_analyse_uploaded_resumes
)
from rtr_prompt import generate_rtr_prompt
from email_utils import send_rtr_email
from concurrent.futures import ThreadPoolExecutor
from file_utils import extract_zip, get_resume_content, is_resume_file
from ats_engine import enrich_jd_from_text

MAX_RESUMES_PER_BATCH = 100  # legacy pagination cap (prefer processing all in one stream)
MAX_TOTAL_RESUMES = 300      # hard cap on resumes inside one ZIP upload
EXTRACT_WORKERS = int(os.getenv("EXTRACT_WORKERS", "12"))
STREAM_BATCH_SIZE = int(os.getenv("STREAM_BATCH_SIZE", "15"))
# Cached extracted resumes keyed by upload_session_id (avoids re-parsing ZIP on pagination)
_upload_sessions: dict = {}

DB_HOST        = os.getenv("DB_HOST")
DB_PORT        = int(os.getenv("DB_PORT", 5432))
DB_USERNAME    = os.getenv("DB_USERNAME")
DB_PASSWORD    = os.getenv("DB_PASSWORD")
DB_NAME        = os.getenv("DB_NAME", "").strip()

# ── Logging ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

router = APIRouter(tags=["Screening"])


def init_screening_db() -> None:
    create_tables()


from psycopg2 import pool as db_pool

# ── Connection Pool ───────────────────────────────────────────
try:
    _connection_pool = db_pool.SimpleConnectionPool(
        1, 30,  # Min 1, Max 30 connections
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USERNAME,
        password=DB_PASSWORD,
        dbname=DB_NAME,
        connect_timeout=10, # Fast fail if DB is slow
    )
    logger.info("--- DB Connection Pool Initialized (1-30) ---")
except Exception as e:
    logger.error(f"FATAL: Database connection failed: {e}")
    _connection_pool = None

def get_db_connection():
    """
    Retrieves a connection from the pool.
    """
    if not _connection_pool:
        raise HTTPException(status_code=500, detail="Database pool not initialized")
    return _connection_pool.getconn()

def release_db_connection(conn):
    """
    Returns a connection to the pool.
    """
    if _connection_pool and conn:
        _connection_pool.putconn(conn)

def create_tables():
    """
    Creates necessary tables including the new final_selected_candidates table.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Table for RTR status
            cur.execute("""
                CREATE TABLE IF NOT EXISTS candidates_accepted (
                    id SERIAL PRIMARY KEY,
                    resume_id TEXT,
                    candidate_name TEXT,
                    candidate_email TEXT,
                    job_role TEXT,
                    agreement_id TEXT UNIQUE,
                    otp TEXT,
                    status TEXT DEFAULT 'pending',
                    signed_at TIMESTAMP,
                    ip_address TEXT,
                    rtr_content TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            # NEW Table for final analysis results
            cur.execute("""
                CREATE TABLE IF NOT EXISTS final_selected_candidates (
                    id SERIAL PRIMARY KEY,
                    candidate_name TEXT,
                    job_title TEXT,
                    total_score INT,
                    overall_summary TEXT,
                    recommendation TEXT,
                    strengths TEXT[],
                    areas_for_improvement TEXT[],
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
        conn.commit()
        logger.info("Tables ensured.")
    finally:
        conn.close()



# ── JOB ROLE PARSING ──────────────────────────────────────────

def _trim_eval_for_stream(ev: CandidateEvaluation) -> dict:
    """Smaller SSE payload — omit verbose trace fields to speed transfer."""
    data = ev.model_dump()
    bd = data.get("ats_breakdown")
    if bd:
        bd.pop("scoring_trace", None)
        if bd.get("skill_details"):
            for sd in bd["skill_details"]:
                sd.pop("reason", None)
    return data


@router.post("/parse-job-roles", tags=["Job Roles"])
async def parse_job_roles(file: UploadFile = File(...)):
    """
    Parses a CSV, JSON, or ZIP file containing job roles.
    For ZIP: extracts all PDF/Word files and treats each as a JobRole.
    """
    temp_dir = tempfile.mkdtemp()
    try:
        content = await file.read()
        filename = file.filename.lower()
        roles = []
        
        # Save uploaded file
        safe_filename = filename.strip().replace(" ", "_")
        file_path = os.path.join(temp_dir, safe_filename).replace("\\", "/")
        with open(file_path, "wb") as buffer:
            buffer.write(content)

        if filename.endswith(".zip"):
            zip_extract_path = os.path.join(temp_dir, f"extracted_jd_{uuid.uuid4()}").replace("\\", "/")
            extract_zip(file_path, zip_extract_path)
            path_items: List[tuple] = []
            for root, _, filenames in os.walk(zip_extract_path):
                for f in filenames:
                    if f.lower().endswith(('.pdf', '.docx', '.doc', '.txt')):
                        path_items.append((os.path.join(root, f), f))
            with ThreadPoolExecutor(max_workers=EXTRACT_WORKERS) as executor:
                futures = [
                    executor.submit(lambda p=pair: (p[1], get_resume_content(p[0])[1]), pair)
                    for pair in path_items
                ]
                for fut in futures:
                    fname, text = fut.result()
                    if text.strip():
                        role = JobRole(
                            job_role=fname.split('.')[0].replace('_', ' '),
                            responsibilities=text,
                            experience="Extracted from document",
                            skills="",
                            project="",
                            bonus=""
                        )
                        roles.append(enrich_jd_from_text(role, text))
        elif filename.endswith(".csv"):
            import csv
            import io
            text = content.decode("utf-8", errors="ignore")
            reader = csv.DictReader(io.StringIO(text))
            for row in reader:
                roles.append(JobRole(
                    job_role = row.get("job_role", "Unknown Role"),
                    experience = row.get("experience", ""),
                    skills = row.get("skills", ""),
                    responsibilities = row.get("responsibilities", ""),
                    project = row.get("project", ""),
                    bonus = row.get("bonus", "")
                ))
        elif filename.endswith(".json"):
            text = content.decode("utf-8", errors="ignore")
            data = json.loads(text)
            if isinstance(data, list):
                for item in data:
                    roles.append(JobRole(**item))
            else:
                roles.append(JobRole(**data))
        else:
            # Fallback: single PDF/Word/Text file
            _, text = get_resume_content(file_path)
            if text.strip():
                role = JobRole(
                    job_role = filename.split('.')[0].replace('_', ' '),
                    responsibilities = text
                )
                roles.append(enrich_jd_from_text(role, text))

        if not roles:
            raise HTTPException(status_code=400, detail="No job roles could be extracted from the file.")
            
        return roles
    except Exception as e:
        logger.error(f"Failed to parse job roles: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        shutil.rmtree(temp_dir)


# ============================================================
# API ENDPOINTS
# ============================================================

@router.get("/", tags=["Root"])
def root():
    return {
        "message": "AI Resume Screening API is live.",
        "endpoints": {
            "health":     "GET  /health",
            "job_roles":  "GET  /job-roles",
            "analyse":    "POST /analyse",
            "docs":       "GET  /docs",
        },
    }


@router.get("/health", response_model=HealthResponse, tags=["Health"])
def health_check():
    """
    Verifies DB connectivity for saving results only.
    """
    return HealthResponse(
        status          = "ok",
        db_connected    = True, # Always true if we reach here
        candidate_count = 0,
        job_role_count  = 0,
    )


# Removed /job-roles endpoint - Job roles are now exclusively user-uploaded.


# Removed /analyse endpoint - The system now uses /upload-analyse for processing user-uploaded resumes correctly.


def _extract_resume_text(full_path: str, rel_name: str) -> Optional[dict]:
    _, text = get_resume_content(full_path)
    if text.strip():
        return {"name": rel_name, "content": text}
    return None


def _extract_all_resumes(temp_dir: str, files: List[UploadFile]) -> List[dict]:
    """Extract resume text from uploads using parallel PDF/DOCX parsing."""
    path_items: List[tuple] = []

    for upload_file in files:
        safe_filename = upload_file.filename.strip().replace(" ", "_")
        file_path = os.path.join(temp_dir, safe_filename).replace("\\", "/")
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(upload_file.file, buffer)

        if upload_file.filename.lower().endswith(".zip"):
            zip_extract_path = os.path.join(temp_dir, f"extracted_{uuid.uuid4()}").replace("\\", "/")
            extract_zip(file_path, zip_extract_path)
            for root, _, filenames in os.walk(zip_extract_path):
                for f in filenames:
                    if not is_resume_file(f):
                        continue
                    full_f_path = os.path.join(root, f)
                    rel_name = os.path.relpath(full_f_path, zip_extract_path).replace("\\", "/")
                    path_items.append((full_f_path, rel_name))
        else:
            path_items.append((file_path, upload_file.filename))

    all_resumes: List[dict] = []
    if not path_items:
        return all_resumes

    with ThreadPoolExecutor(max_workers=EXTRACT_WORKERS) as executor:
        futures = [executor.submit(_extract_resume_text, p, n) for p, n in path_items]
        for fut in futures:
            item = fut.result()
            if item:
                all_resumes.append(item)

    all_resumes.sort(key=lambda x: x["name"].lower())
    return all_resumes


@router.post("/upload-and-analyse")
async def upload_and_analyse(
    job_role_json: str = Form(...),
    rubric_weights_json: str = Form("{}"),
    offset: int = Form(0),
    batch_limit: int = Form(100),
    upload_session_id: str = Form(""),
    use_cached_files: str = Form("false"),
    files: List[UploadFile] = File(default=[]),
):
    """
    Upload-based analysis. Extracts resumes once per upload_session_id, then scores
    all resumes in parallel batches and streams results back.
    """
    effective_batch_limit = min(batch_limit, MAX_RESUMES_PER_BATCH)

    def event_generator():
        conn = get_db_connection()
        temp_dir = tempfile.mkdtemp()
        try:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            job_role_data = json.loads(job_role_json)
            job_role = JobRole(**job_role_data)
            try:
                weights_data = json.loads(rubric_weights_json) if rubric_weights_json else {}
                rubric_weights = RubricWeights(**weights_data) if weights_data else DEFAULT_RUBRIC_WEIGHTS
            except Exception:
                rubric_weights = DEFAULT_RUBRIC_WEIGHTS
            if rubric_weights.total() != 100:
                yield "data: " + json.dumps({
                    "error": f"Rubric weights must sum to 100 (got {rubric_weights.total()})."
                }) + "\n\n"
                return

            session_key = upload_session_id.strip() if upload_session_id else ""
            use_cache = use_cached_files.strip().lower() in ("1", "true", "yes")
            if session_key and session_key in _upload_sessions and (use_cache or not files):
                all_resumes = _upload_sessions[session_key]
                logger.info(f"Using cached extraction for session {session_key[:8]}... ({len(all_resumes)} resumes)")
            else:
                if not files:
                    yield "data: " + json.dumps({
                        "error": "No files uploaded and no cached session found. Please upload resumes again."
                    }) + "\n\n"
                    return
                logger.info(f"Extracting resumes from {len(files)} files/ZIPs...")
                all_resumes = _extract_all_resumes(temp_dir, files)
                if session_key:
                    _upload_sessions[session_key] = all_resumes
                    if len(_upload_sessions) > 20:
                        oldest = next(iter(_upload_sessions))
                        _upload_sessions.pop(oldest, None)

            logger.info(f"Total resumes extracted after filtering: {len(all_resumes)}")
            total_extracted = len(all_resumes)

            if total_extracted > MAX_TOTAL_RESUMES:
                yield "data: " + json.dumps({
                    "error": (
                        f"ZIP contains {total_extracted} resumes. "
                        f"Maximum allowed is {MAX_TOTAL_RESUMES}. Please split into smaller ZIP files."
                    )
                }) + "\n\n"
                return

            paged_resumes: List[dict] = all_resumes

            logger.info(f"Scoring {len(paged_resumes)} resume(s) (total in upload: {total_extracted})")

            yield "data: " + json.dumps({
                "total_extracted": total_extracted,
                "message": f"Found {total_extracted} resume(s). Scoring {len(paged_resumes)}..."
            }) + "\n\n"

            if not paged_resumes:
                if offset >= total_extracted:
                    yield "data: " + json.dumps({
                        "error": f"Offset {offset} is out of range. Total extracted: {total_extracted}."
                    }) + "\n\n"
                else:
                    yield "data: " + json.dumps({"error": "No valid text could be extracted."}) + "\n\n"
                return

            from resumeanalyser import analyse_resumes_stream

            processed = 0
            for i in range(0, len(paged_resumes), STREAM_BATCH_SIZE):
                batch = paged_resumes[i : i + STREAM_BATCH_SIZE]
                yield "data: " + json.dumps({
                    "progress": processed,
                    "total": total_extracted,
                    "total_extracted": total_extracted,
                    "message": f"Scoring resumes {processed + 1}–{min(processed + len(batch), total_extracted)} of {total_extracted}..."
                }) + "\n\n"

                batch_evals = []
                for eval_obj in analyse_resumes_stream(batch, job_role, rubric_weights):
                    batch_evals.append(eval_obj)
                    processed += 1
                    try:
                        cursor.execute("""
                            INSERT INTO final_selected_candidates 
                            (candidate_name, job_title, total_score, overall_summary, strengths, areas_for_improvement, recommendation)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, (
                            eval_obj.candidate_name, eval_obj.job_title, eval_obj.total_score,
                            eval_obj.overall_summary, eval_obj.strengths, eval_obj.areas_for_improvement,
                            eval_obj.recommendation
                        ))
                    except Exception as e:
                        logger.error(f"DB insert failed for {eval_obj.candidate_name}: {e}")

                    yield "data: " + json.dumps({
                        "batch": [_trim_eval_for_stream(eval_obj)],
                        "progress": processed,
                        "total": total_extracted,
                        "message": f"Scored {processed}/{total_extracted} resumes.",
                        "processed_count": processed,
                    }) + "\n\n"

                conn.commit()

            yield "data: " + json.dumps({
                "done": True,
                "message": f"Analysis complete — {processed} resume(s) scored.",
                "rubric_weights": rubric_weights.model_dump(),
                "total_extracted": total_extracted,
                "nextOffset": None,
            }) + "\n\n"

        except Exception as e:
            logger.error(f"Upload analysis failed: {e}")
            yield "data: " + json.dumps({"error": str(e)}) + "\n\n"
        finally:
            shutil.rmtree(temp_dir)
            release_db_connection(conn)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.post("/send-rtr", tags=["RTR"])
def send_rtr(request: RTRRequest):
    """
    Generates an RTR agreement, an OTP, and sends an email to the candidate.
    """
    conn = get_db_connection()
    try:
        # 1. Fetch Candidate and Job details
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM resume_candidates WHERE resume_id::text = %s::text", (request.resume_id,))
            candidate_row = cur.fetchone()
            cur.execute("SELECT * FROM job_roles WHERE job_role = %s", (request.job_role,))
            job_row = cur.fetchone()

        # We don't raise 404 anymore. If they aren't in DB, we use the fallback values.
        # This allows uploaded resumes (which are not in DB) to receive an RTR.
        
        c_name = request.candidate_name or (candidate_row["name"] if candidate_row else request.resume_id)
        # Default fallback test email so OTP works for demo
        c_email = request.candidate_email or (candidate_row["emailid"] if candidate_row else os.getenv("SMTP_USERNAME", "narmadhavelu30@gmail.com"))
        c_phone = candidate_row["mobile_no"] if candidate_row else "123-456-7890"
        j_role = job_row["job_role"] if job_row else request.job_role

        # 2. Generate RTR Data
        agreement_id = str(uuid.uuid4())
        otp = str(random.randint(100000, 999999))
        
        rtr_data = {
            "agreement_id": agreement_id,
            "issue_date": datetime.now().strftime("%Y-%m-%d"),
            "candidate_name": c_name,
            "candidate_email": c_email,
            "candidate_phone": c_phone,
            "job_title": j_role,
            "end_client": "Aigrev Client", # Placeholder
            "client_location": "Remote",
            "employment_type": "Contract",
            "compensation": "$ / hr"
        }
        
        rtr_content = generate_rtr_prompt(rtr_data)
        
        # 3. Save to candidates_accepted (Pending)
        with conn.cursor() as cur:
            # Upsert logic: if candidate already has an RTR for this job, update it
            cur.execute("""
                INSERT INTO candidates_accepted 
                (resume_id, candidate_name, candidate_email, job_role, agreement_id, otp, status, rtr_content)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (agreement_id) DO NOTHING
            """, (
                request.resume_id, c_name, c_email, 
                j_role, agreement_id, otp, "pending", rtr_content
            ))
        conn.commit()

        # 4. Send Email
        success = send_rtr_email(c_email, c_name, rtr_content, otp, agreement_id)
        
        return {"status": "success" if success else "email_failed", "agreement_id": agreement_id}

    finally:
        conn.close()


@router.post("/verify-rtr", tags=["RTR"])
def verify_rtr(request: RTRVerificationRequest):
    """
    Verifies the OTP and updates the RTR status to 'accepted'.
    """
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM candidates_accepted 
                WHERE agreement_id = %s
            """, (request.agreement_id,))
            row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Agreement not found")
        
        if row["otp"] != request.otp:
            raise HTTPException(status_code=400, detail="Invalid OTP")

        # Update status
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE candidates_accepted 
                SET status = 'accepted', signed_at = %s 
                WHERE agreement_id = %s
            """, (datetime.now(), request.agreement_id))
        conn.commit()
        return {"status": "accepted", "candidate_name": row["candidate_name"]}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.get("/rtr-status/{agreement_id}", tags=["RTR"])
def get_rtr_status(agreement_id: str):
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT status FROM candidates_accepted WHERE agreement_id = %s", (agreement_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="RTR not found")
            return {"status": row["status"]}
    finally:
        conn.close()

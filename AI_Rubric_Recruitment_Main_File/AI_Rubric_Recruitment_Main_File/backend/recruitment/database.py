import json
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    text,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

import pathlib

_DB_FILE = pathlib.Path(__file__).resolve().parent / "recruitment.db"
SQLALCHEMY_DATABASE_URL = f"sqlite:///{_DB_FILE.as_posix()}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    role = Column(String, default="admin", nullable=False)
    status = Column(String, default="active", nullable=False)
    tenant_id = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, default=utcnow)

    job_postings = relationship("JobPosting", back_populates="recruiter")
    platform_connections = relationship("PlatformConnection", back_populates="user")


class JobPosting(Base):
    __tablename__ = "job_postings"

    id = Column(Integer, primary_key=True, index=True)
    recruiter_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    jd_json = Column(Text, nullable=False)
    natural_language_input = Column(Text, nullable=True)
    status = Column(String, default="draft")
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    recruiter = relationship("User", back_populates="job_postings")
    platform_posts = relationship("PlatformPost", back_populates="job_posting")
    applicants = relationship("Applicant", back_populates="job_posting")

    def get_jd(self) -> dict:
        return json.loads(self.jd_json)


class PlatformConnection(Base):
    __tablename__ = "platform_connections"
    __table_args__ = (UniqueConstraint("user_id", "platform", name="uq_user_platform"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    platform = Column(String, nullable=False)
    account_email = Column(String, nullable=False)
    account_name = Column(String, nullable=True)
    account_url = Column(String, nullable=True)
    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    connected_at = Column(DateTime, default=utcnow)

    user = relationship("User", back_populates="platform_connections")


class PlatformPost(Base):
    __tablename__ = "platform_posts"

    id = Column(Integer, primary_key=True, index=True)
    job_posting_id = Column(Integer, ForeignKey("job_postings.id"), nullable=False)
    platform = Column(String, nullable=False)
    external_url = Column(String, nullable=True)
    account_url = Column(String, nullable=True)
    external_post_id = Column(String, nullable=True)
    apply_token = Column(String, unique=True, index=True, nullable=False)
    status = Column(String, default="posted")
    posted_at = Column(DateTime, default=utcnow)

    job_posting = relationship("JobPosting", back_populates="platform_posts")
    applicants = relationship("Applicant", back_populates="platform_post")


class OAuthState(Base):
    """Persist OAuth CSRF state so callbacks survive server restarts."""

    __tablename__ = "oauth_states"

    state = Column(String, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    platform = Column(String, nullable=False)
    email = Column(String, nullable=True)
    provider = Column(String, default="linkedin", nullable=False)
    created_at = Column(DateTime, default=utcnow)
    expires_at = Column(DateTime, nullable=False)


class Applicant(Base):
    __tablename__ = "applicants"

    id = Column(Integer, primary_key=True, index=True)
    job_posting_id = Column(Integer, ForeignKey("job_postings.id"), nullable=False)
    platform_post_id = Column(Integer, ForeignKey("platform_posts.id"), nullable=True)
    full_name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    linkedin_url = Column(String, nullable=True)
    current_title = Column(String, nullable=True)
    current_company = Column(String, nullable=True)
    years_experience = Column(String, nullable=True)
    location = Column(String, nullable=True)
    cover_letter = Column(Text, nullable=True)
    resume_text = Column(Text, nullable=True)
    resume_filename = Column(String, nullable=True)
    resume_file_path = Column(String, nullable=True)
    platform = Column(String, nullable=False)
    applied_at = Column(DateTime, default=utcnow)

    job_posting = relationship("JobPosting", back_populates="applicants")
    platform_post = relationship("PlatformPost", back_populates="applicants")


class ContactSubmission(Base):
    __tablename__ = "contact_submissions"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    company = Column(String, nullable=True)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utcnow)


def _migrate_db() -> None:
    """Add columns/tables for existing SQLite databases."""
    with engine.connect() as conn:
        cols = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(platform_posts)")).fetchall()
        }
        if "account_url" not in cols:
            conn.execute(text("ALTER TABLE platform_posts ADD COLUMN account_url VARCHAR"))
        if "external_post_id" not in cols:
            conn.execute(text("ALTER TABLE platform_posts ADD COLUMN external_post_id VARCHAR"))

        user_cols = {
            row[1] for row in conn.execute(text("PRAGMA table_info(users)")).fetchall()
        }
        if "role" not in user_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR DEFAULT 'admin'"))
        if "status" not in user_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN status VARCHAR DEFAULT 'active'"))
        if "tenant_id" not in user_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN tenant_id VARCHAR"))
        conn.execute(
            text("UPDATE users SET tenant_id = 'tenant-' || id WHERE tenant_id IS NULL OR tenant_id = ''")
        )
        conn.execute(text("UPDATE users SET role = 'admin' WHERE role IS NULL OR role = ''"))
        conn.execute(text("UPDATE users SET status = 'active' WHERE status IS NULL OR status = ''"))

        applicant_cols = {
            row[1] for row in conn.execute(text("PRAGMA table_info(applicants)")).fetchall()
        }
        for col, ddl in (
            ("linkedin_url", "ALTER TABLE applicants ADD COLUMN linkedin_url VARCHAR"),
            ("current_title", "ALTER TABLE applicants ADD COLUMN current_title VARCHAR"),
            ("current_company", "ALTER TABLE applicants ADD COLUMN current_company VARCHAR"),
            ("years_experience", "ALTER TABLE applicants ADD COLUMN years_experience VARCHAR"),
            ("location", "ALTER TABLE applicants ADD COLUMN location VARCHAR"),
            ("cover_letter", "ALTER TABLE applicants ADD COLUMN cover_letter TEXT"),
            ("resume_filename", "ALTER TABLE applicants ADD COLUMN resume_filename VARCHAR"),
            ("resume_file_path", "ALTER TABLE applicants ADD COLUMN resume_file_path VARCHAR"),
        ):
            if col not in applicant_cols:
                conn.execute(text(ddl))

        oauth_exists = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='oauth_states'")
        ).fetchone()
        if oauth_exists:
            oauth_cols = {
                row[1]
                for row in conn.execute(text("PRAGMA table_info(oauth_states)")).fetchall()
            }
            if "expires_at" not in oauth_cols:
                conn.execute(text("DROP TABLE oauth_states"))
        conn.commit()


def init_db() -> None:
    _migrate_db()
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

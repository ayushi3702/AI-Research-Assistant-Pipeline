from __future__ import annotations
import uuid
import datetime
from sqlalchemy import Column, String, Float, DateTime, Text, ForeignKey, Boolean, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

Base = declarative_base()

# IST timezone (UTC+5:30)
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

def _now_ist():
    return datetime.datetime.now(IST).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id            = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email         = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=True)  # null for OAuth-only users
    name          = Column(String, nullable=True)
    provider      = Column(String, default="email")  # email|google
    is_verified   = Column(Boolean, default=False)
    created_at    = Column(DateTime, default=_now_ist)


class ResearchJob(Base):
    __tablename__ = "research_jobs"

    id          = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id     = Column(String, ForeignKey("users.id"), nullable=True)
    query       = Column(Text, nullable=False)
    status      = Column(String, default="pending")   # pending|running|done|failed
    report      = Column(Text)
    created_at  = Column(DateTime, default=_now_ist)
    finished_at = Column(DateTime)


class AgentTask(Base):
    __tablename__ = "agent_tasks"

    id          = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id      = Column(String, ForeignKey("research_jobs.id"))
    agent_name  = Column(String)                       # search|extractor|validator|writer
    status      = Column(String, default="pending")    # pending|running|done|failed
    input_data  = Column(Text)                         # JSON
    output_data = Column(Text)                         # JSON
    started_at  = Column(DateTime)
    finished_at = Column(DateTime)
    duration_ms = Column(Float)


class Source(Base):
    __tablename__ = "sources"

    id              = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id          = Column(String, ForeignKey("research_jobs.id"))
    url             = Column(Text)
    relevance_score = Column(Float)
    content_chunk   = Column(Text)
    source_type     = Column(String)                   # web|pdf|arxiv
    created_at      = Column(DateTime, default=_now_ist)


class Document(Base):
    __tablename__ = "documents"

    id           = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id      = Column(String, ForeignKey("users.id"), nullable=True)
    filename     = Column(String, nullable=False)
    chunks_count = Column(Float, default=0)
    text_length  = Column(Float, default=0)
    created_at   = Column(DateTime, default=_now_ist)


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id         = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id    = Column(String, ForeignKey("users.id"), nullable=False)
    type       = Column(String, nullable=False)  # "Research" | "Q&A"
    title      = Column(String, nullable=False)
    ref_id     = Column(String, nullable=False)  # points to research_jobs.id or qa_interactions.id
    pinned     = Column(Boolean, default=False)
    created_at = Column(DateTime, default=_now_ist)


class ClaimVerification(Base):
    __tablename__ = "claim_verifications"

    id              = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id          = Column(String, ForeignKey("research_jobs.id"), nullable=False, index=True)
    claim           = Column(Text, nullable=False)
    status          = Column(String, default="unverified")  # verified|disputed|unverified
    confidence      = Column(Float, default=0.5)
    supported_by    = Column(Text)   # JSON array of URLs
    contradicted_by = Column(Text)   # JSON array of URLs
    sentence_match  = Column(Text)   # sentence in the report this maps to
    created_at      = Column(DateTime, default=_now_ist)


class ReasoningTrace(Base):
    __tablename__ = "reasoning_traces"

    id         = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id     = Column(String, ForeignKey("research_jobs.id"), nullable=False, index=True)
    agent      = Column(String, nullable=False)
    step       = Column(String, nullable=False)
    reasoning  = Column(Text, nullable=False)
    decision   = Column(Text)
    trace_metadata = Column("trace_metadata", Text)  # JSON
    created_at = Column(DateTime, default=_now_ist)


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id         = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id    = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    type       = Column(String, nullable=False)  # report_ready|verification|system
    subject    = Column(String, nullable=False)
    preview    = Column(Text)       # short content preview
    ref_id     = Column(String)     # e.g. job_id for report notifications
    status     = Column(String, default="sent")  # sent|failed
    is_read    = Column(Boolean, default=False)
    created_at = Column(DateTime, default=_now_ist)


class OAuthConnection(Base):
    __tablename__ = "oauth_connections"

    id            = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id       = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    provider      = Column(String, nullable=False)  # google_docs|notion
    access_token  = Column(Text, nullable=False)
    refresh_token = Column(Text)
    token_expires = Column(DateTime)
    workspace_id  = Column(String)  # Notion workspace ID
    extra         = Column(Text)    # JSON — any provider-specific data
    created_at    = Column(DateTime, default=_now_ist)
    updated_at    = Column(DateTime, default=_now_ist, onupdate=_now_ist)


class QAInteraction(Base):
    __tablename__ = "qa_interactions"

    id              = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id         = Column(String, ForeignKey("users.id"), nullable=True)
    chat_session_id = Column(String, nullable=True, index=True)  # groups multi-turn messages
    document_id     = Column(String, ForeignKey("documents.id"), nullable=True)
    question        = Column(Text, nullable=False)
    answer          = Column(Text, nullable=False)
    sources         = Column(Text)  # JSON-serialized sources
    created_at      = Column(DateTime, default=_now_ist)


# ── Engine + session factory ──────────────────────────────────────────────────

import os
from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./research_pipeline.db")

# Configure engine based on database type
_connect_args = {}
_engine_kwargs = {"echo": False, "pool_pre_ping": True}

if DATABASE_URL.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}
else:
    # Use NullPool for pgbouncer compatibility (pooler handles connections)
    _engine_kwargs["poolclass"] = NullPool

engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    **_engine_kwargs,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db() -> None:
    """Create all tables if they don't exist, and migrate missing columns."""
    Base.metadata.create_all(engine)
    _migrate_missing_columns()
    _drop_removed_columns()


def _migrate_missing_columns():
    """Add any columns defined in models but missing from existing tables."""
    from sqlalchemy import inspect, text
    inspector = inspect(engine)

    for table_class in Base.__subclasses__():
        table_name = table_class.__tablename__
        if not inspector.has_table(table_name):
            continue
        existing = {col["name"] for col in inspector.get_columns(table_name)}
        for col in table_class.__table__.columns:
            if col.name not in existing:
                col_type = col.type.compile(engine.dialect)
                with engine.begin() as conn:
                    conn.execute(text(
                        f'ALTER TABLE {table_name} ADD COLUMN {col.name} {col_type}'
                    ))


def _drop_removed_columns():
    """Drop columns that exist in the database but are no longer defined in models."""
    from sqlalchemy import inspect, text
    inspector = inspect(engine)

    for table_class in Base.__subclasses__():
        table_name = table_class.__tablename__
        if not inspector.has_table(table_name):
            continue
        model_cols = {col.name for col in table_class.__table__.columns}
        existing = {col["name"] for col in inspector.get_columns(table_name)}
        for col_name in existing - model_cols:
            with engine.begin() as conn:
                conn.execute(text(
                    f'ALTER TABLE {table_name} DROP COLUMN {col_name}'
                ))


def get_db():
    """FastAPI dependency — yields a session and closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

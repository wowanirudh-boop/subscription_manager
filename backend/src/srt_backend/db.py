"""Persistence. Stores extracted fields and evidence snippets only - never raw e-mail (R9, PRD 6.1).

PostgreSQL (Cloud SQL, asia-south1) in production; SQLite for development and tests.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import (JSON, Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint,
                        create_engine)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)  # primary Google identity; alert e-mails go here (D13)
    tz: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    templates_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # stage-5 sender templates


class Consent(Base):
    """R1 disclosure acceptance and R9 support-access consents, append-only."""
    __tablename__ = "consents"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(64))  # gmail_disclosure | support_access
    version: Mapped[str] = mapped_column(String(64))
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    granted_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class GmailAccount(Base):
    __tablename__ = "gmail_accounts"
    __table_args__ = (UniqueConstraint("user_id", "email"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    token_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)  # R10: encrypted at rest
    history_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    watch_expires_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_synced_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_status: Mapped[str] = mapped_column(String(32), default="pending")  # pending|running|done|error
    sync_matched: Mapped[int] = mapped_column(Integer, default=0)
    sync_processed: Mapped[int] = mapped_column(Integer, default=0)
    first_result_seconds: Mapped[Optional[float]] = mapped_column(nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExtractionRow(Base):
    """One processed e-mail: extracted fields + per-field evidence sentences. No body."""
    __tablename__ = "extractions"
    __table_args__ = (UniqueConstraint("user_id", "message_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("gmail_accounts.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[str] = mapped_column(String(128))
    email_date: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    related: Mapped[bool] = mapped_column(Boolean)
    data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # Extraction.model_dump (fields+snippets)
    processed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ManualRecord(Base):
    """R5 manual add: all fields user-entered (confirmed)."""
    __tablename__ = "manual_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RecordStateRow(Base):
    __tablename__ = "record_states"
    __table_args__ = (UniqueConstraint("user_id", "record_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    record_key: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict] = mapped_column(JSON)


class SuppressedMerchant(Base):
    """'Not a subscription' suppresses that merchant for that user (R4)."""
    __tablename__ = "suppressed_merchants"
    __table_args__ = (UniqueConstraint("user_id", "merchant_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    merchant_key: Mapped[str] = mapped_column(String(128))


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (UniqueConstraint("user_id", "record_key", "target_date", "days_before", "channel"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    record_key: Mapped[str] = mapped_column(String(64), index=True)
    target_date: Mapped[dt.date] = mapped_column()
    days_before: Mapped[int] = mapped_column(Integer)
    channel: Mapped[str] = mapped_column(String(16))
    send_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(16), default="scheduled")  # scheduled|sent|delivered|failed|cancelled
    sent_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class PushToken(Base):
    __tablename__ = "push_tokens"
    __table_args__ = (UniqueConstraint("user_id", "token"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token: Mapped[str] = mapped_column(String(256))
    platform: Mapped[str] = mapped_column(String(16))


class Event(Base):
    """Aggregated metrics source (M1-M8). Extracted-field level only (Limited Use)."""
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(64), index=True)
    record_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class SupportAccessLog(Base):
    """R9: support tooling may show extracted content only with explicit, logged consent per request."""
    __tablename__ = "support_access_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    operator: Mapped[str] = mapped_column(String(128))
    reason: Mapped[str] = mapped_column(Text)
    consent_id: Mapped[int] = mapped_column(ForeignKey("consents.id", ondelete="CASCADE"))
    at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


_engine = None
_Session: Optional[sessionmaker] = None


def init(url: str) -> None:
    global _engine, _Session
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {"pool_pre_ping": True}
    _engine = create_engine(url, **kwargs)
    Base.metadata.create_all(_engine)
    _Session = sessionmaker(bind=_engine, expire_on_commit=False)


def session() -> Session:
    assert _Session is not None, "db.init() not called"
    return _Session()

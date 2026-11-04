"""Data model. Mirrors PRD v1.1 section 6 (subscription record, field states)."""

from __future__ import annotations

import datetime as dt
from enum import Enum
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field


class FieldState(str, Enum):
    """D5-D7: the product never asserts a value it did not read or derive."""

    CONFIRMED = "confirmed"  # read directly from an email (evidence verified)
    ESTIMATED = "estimated"  # deterministically derived from stated facts
    UNKNOWN = "unknown"  # neither read nor derivable


class EmailType(str, Enum):
    TRIAL_SIGNUP = "trial_signup"
    RECEIPT = "receipt"
    RENEWAL_REMINDER = "renewal_reminder"
    CANCELLATION_CONFIRMATION = "cancellation_confirmation"
    PRICE_CHANGE = "price_change"
    WINBACK_OFFER = "winback_offer"  # Q7: must not be mistaken for a cancellation
    OTHER = "other"


class Kind(str, Enum):
    TRIAL = "trial"
    SUBSCRIPTION = "subscription"
    RENEWAL = "renewal"  # non-subscription recurring: domains, insurance, annual fees


class BillingPeriod(str, Enum):
    MONTHLY = "monthly"
    ANNUAL = "annual"
    OTHER = "other"
    UNKNOWN = "unknown"


class Lifecycle(str, Enum):
    """Subset of PRD 6.3 that Phase 0 can determine from email alone.

    likely_cancelled / cancellation_pending depend on wall-clock time and user
    actions (and flow sign-off decision #2), so they are out of Phase 0 scope.
    """

    ACTIVE = "active"
    CANCELLED_CONFIRMED = "cancelled_confirmed"
    UNKNOWN_DATE = "unknown_date"


class EmailMessage(BaseModel):
    """One Gmail message. ``body_text`` is held in memory only (R9)."""

    message_id: str
    account: str
    thread_id: Optional[str] = None
    from_addr: str
    from_name: str = ""
    subject: str = ""
    date: dt.datetime
    snippet: str = ""
    body_text: Optional[str] = None  # None until fetched (stage 4 survivors only)
    attachment_names: list[str] = Field(default_factory=list)

    @property
    def sender_domain(self) -> str:
        return self.from_addr.rsplit("@", 1)[-1].lower().strip(">")


class Evidence(BaseModel):
    """PRD 6.1: (message_id, account, field, snippet)."""

    message_id: str
    account: str
    snippet: str  # the sentence containing the value


T = TypeVar("T")


class FieldValue(BaseModel, Generic[T]):
    value: Optional[T] = None
    state: FieldState = FieldState.UNKNOWN
    evidence: Optional[Evidence] = None
    derived_from: Optional[str] = None  # human-readable derivation, for estimated values

    @classmethod
    def unknown(cls) -> "FieldValue[T]":
        return cls()

    @property
    def known(self) -> bool:
        return self.state != FieldState.UNKNOWN and self.value is not None


class Extraction(BaseModel):
    """Stage 4/5 output for a single email: fields, states, evidence (R4)."""

    message_id: str
    account: str
    email_date: dt.datetime
    sender: str
    source_stage: str  # "stage4" or "stage5"
    is_subscription_related: bool
    email_type: EmailType = EmailType.OTHER
    merchant: FieldValue[str] = Field(default_factory=FieldValue)
    kind: FieldValue[Kind] = Field(default_factory=FieldValue)
    billing_period: FieldValue[BillingPeriod] = Field(default_factory=FieldValue)
    period_months: Optional[int] = None  # only when billing_period == other and stated (e.g. quarterly = 3)
    amount: FieldValue[float] = Field(default_factory=FieldValue)
    currency: FieldValue[str] = Field(default_factory=FieldValue)
    charge_date: FieldValue[dt.date] = Field(default_factory=FieldValue)
    next_charge_date: FieldValue[dt.date] = Field(default_factory=FieldValue)
    trial_end_date: FieldValue[dt.date] = Field(default_factory=FieldValue)
    cancel_path: FieldValue[str] = Field(default_factory=FieldValue)
    rejected_values: list[str] = Field(default_factory=list)  # model values dropped by evidence checks
    attachment_skipped: bool = False  # body had no amount but attachments exist (flow decision #6 open)


class SubscriptionRecord(BaseModel):
    """PRD 6.1 merged record (D16: one list across accounts)."""

    record_id: str
    merchant: FieldValue[str]
    source_accounts: list[str]
    kind: FieldValue[Kind]
    billing_period: FieldValue[BillingPeriod]
    amount: FieldValue[float]
    currency: FieldValue[str]
    last_charge_date: FieldValue[dt.date]
    next_charge_date: FieldValue[dt.date]
    trial_end_date: FieldValue[dt.date]
    cancel_path: FieldValue[str]
    lifecycle_state: Lifecycle
    message_ids: list[str]
    flags: list[str] = Field(default_factory=list)  # e.g. confirmed value contradicted by a newer email


# ---- Judge labels -------------------------------------------------------------------


class JudgeLabel(BaseModel):
    """Reference label for one email, written blind (without seeing pipeline output)."""

    message_id: str
    is_subscription_related: bool
    email_type: EmailType = EmailType.OTHER
    merchant: Optional[str] = None
    kind: Optional[Kind] = None
    billing_period: Optional[BillingPeriod] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    charge_date: Optional[dt.date] = None
    next_charge_date: Optional[dt.date] = None  # only if stated in the email, not derived
    trial_end_date: Optional[dt.date] = None  # only if stated in the email, not derived
    notes: str = ""
    judge: str = "claude"

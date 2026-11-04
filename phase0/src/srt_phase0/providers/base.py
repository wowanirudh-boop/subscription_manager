"""Provider interface: the swappable model boundary (R4, D23).

A provider proposes values and quotes. It never decides field states: the
pipeline verifies every quote against the email and derives states itself, so
swapping providers (OpenRouter today, on-device later per P2) cannot weaken D5.
"""

from __future__ import annotations

from typing import Optional, Protocol

from pydantic import BaseModel, Field

from ..models import BillingPeriod, EmailType, Kind


class Quoted(BaseModel):
    value: Optional[str] = None
    quote: Optional[str] = None


class QuotedKind(BaseModel):
    value: Optional[Kind] = None
    quote: Optional[str] = None


class QuotedPeriod(BaseModel):
    value: Optional[BillingPeriod] = None
    period_months: Optional[int] = None
    quote: Optional[str] = None


class QuotedAmount(BaseModel):
    value: Optional[float] = None
    currency: Optional[str] = None
    quote: Optional[str] = None


class QuotedInt(BaseModel):
    value: Optional[int] = None
    quote: Optional[str] = None


class RawExtraction(BaseModel):
    """What a model returns for stage 4. Dates are ISO strings (YYYY-MM-DD)."""

    is_subscription_related: bool
    email_type: EmailType = EmailType.OTHER
    merchant: Quoted = Field(default_factory=Quoted)
    kind: QuotedKind = Field(default_factory=QuotedKind)
    billing_period: QuotedPeriod = Field(default_factory=QuotedPeriod)
    amount: QuotedAmount = Field(default_factory=QuotedAmount)
    charge_date: Quoted = Field(default_factory=Quoted)
    next_charge_date: Quoted = Field(default_factory=Quoted)
    trial_end_date: Quoted = Field(default_factory=Quoted)
    trial_length_days: QuotedInt = Field(default_factory=QuotedInt)
    cancel_path: Quoted = Field(default_factory=Quoted)


class TriageInput(BaseModel):
    message_id: Optional[str] = None  # not sent to models; used by the replay provider
    sender: str
    subject: str
    preview: str  # first ~200 characters (R4 stage 3)


class ExtractInput(BaseModel):
    message_id: Optional[str] = None  # not sent to models; used by the replay provider
    sender: str
    sender_name: str
    subject: str
    sent_date: str  # ISO date the email was sent
    body: str  # already truncated to ~1,500 tokens


class UsageStats(BaseModel):
    triage_calls: int = 0
    extract_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: Optional[float] = None  # filled only if the provider reports it


class Provider(Protocol):
    name: str
    usage: UsageStats

    def triage(self, item: TriageInput) -> bool:
        """Stage 3: is this email subscription-related?"""

    def extract(self, item: ExtractInput) -> RawExtraction:
        """Stage 4: propose field values, each with a verbatim quote."""

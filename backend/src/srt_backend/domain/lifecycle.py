"""Lifecycle engine: PRD v1.1 section 6.3, D9-D11, D26, and flow sign-offs #2, #3, #5, #7.

State is *derived*, never stored: the inputs are the merged e-mail facts for a
record (from the Phase 0 pipeline), the user's own actions on it, and today's
date. Re-running with the same inputs always gives the same answer, so a late
e-mail, a disconnect, or a correction can never leave a record in a stale state.

Adopted decisions encoded here (flow review, 5 Nov 2026):
  #2  Active record passes its expected date with no receipt -> stays active,
      next date rolls forward as *estimated*, flagged "no receipt seen".
      (Phase 0 found a real merchant that charges monthly but never e-mails.)
  #3  Charge while cancellation is pending -> active, user notified; not an M1
      surprise if an alert was delivered for that charge.
  #5  "No receipt" is judged at expected date + 3 days (late receipts).
  #7  Unanswered re-subscribe question -> tracking resumes, question stays on
      the record, M1 not counted until answered.
"""

from __future__ import annotations

import datetime as dt
from enum import Enum
from typing import Any, Optional

from dateutil.relativedelta import relativedelta
from pydantic import BaseModel, Field

from srt_phase0.models import BillingPeriod, FieldState, FieldValue, Kind, SubscriptionRecord

LOOKBACK_DAYS = 3  # decision #5


class State(str, Enum):
    ACTIVE = "active"
    CANCELLATION_PENDING = "cancellation_pending"
    CANCELLED_CONFIRMED = "cancelled_confirmed"
    LIKELY_CANCELLED = "likely_cancelled"
    CANCELLED_USER_CONFIRMED = "cancelled_user_confirmed"
    UNKNOWN_DATE = "unknown_date"


ALERTING = {State.ACTIVE, State.CANCELLATION_PENDING}  # R7


class UserRecordState(BaseModel):
    """What the user has done to a record. Persisted per (user, record_key)."""

    cancel_requested_at: Optional[dt.datetime] = None  # "I cancelled" (D9)
    user_confirmed_cancel_at: Optional[dt.datetime] = None  # force-confirm / confirm likely (D10, D26)
    resubscribe_answers: dict[str, bool] = Field(default_factory=dict)  # receipt ISO timestamp -> answer
    overrides: dict[str, Any] = Field(default_factory=dict)  # field -> user-entered value (confirmed)
    muted: bool = False  # R7 per-subscription mute
    suppressed: bool = False  # "Not a subscription" (R4, M3)
    skipped_session: Optional[str] = None  # unknowns queue: skipped in this app session (R6)


class Notice(str, Enum):
    RESUBSCRIBE_QUESTION = "resubscribe_question"  # D26
    CHARGED_WHILE_PENDING = "charged_while_pending"  # decision #3
    NO_RECEIPT_SEEN = "no_receipt_seen"  # decision #2
    NO_MERCHANT_CONFIRMATION = "no_merchant_confirmation"  # shown before force-confirm (R8)


class RecordView(BaseModel):
    record_key: str
    merchant: FieldValue[str]
    kind: FieldValue[Kind]
    billing_period: FieldValue[BillingPeriod]
    period_months: Optional[int] = None
    amount: FieldValue[float]
    currency: FieldValue[str]
    last_charge_date: FieldValue[dt.date]
    next_charge_date: FieldValue[dt.date]
    trial_end_date: FieldValue[dt.date]
    cancel_path: FieldValue[str]
    state: State
    alerts_enabled: bool
    notices: list[Notice] = Field(default_factory=list)
    missed_date: Optional[dt.date] = None
    pending_receipt_at: Optional[dt.datetime] = None  # receipt the re-subscribe question is about
    source_accounts: list[str]
    message_ids: list[str]
    flags: list[str]
    muted: bool = False


_USER = lambda v: FieldValue(value=v, state=FieldState.CONFIRMED, derived_from="user-entered")  # noqa: E731


def _apply_overrides(rec: SubscriptionRecord, us: UserRecordState) -> dict[str, FieldValue]:
    fields = {
        n: getattr(rec, n)
        for n in ("merchant", "kind", "billing_period", "amount", "currency", "last_charge_date",
                  "next_charge_date", "trial_end_date", "cancel_path")
    }
    for name, value in us.overrides.items():
        if name not in fields:
            continue
        if name.endswith("_date") and isinstance(value, str):
            value = dt.date.fromisoformat(value)
        if name == "billing_period":
            value = BillingPeriod(value)
        if name == "next_charge_date" and rec.last_charge_date.known and value <= rec.last_charge_date.value:
            continue  # superseded by a later charge
        fields[name] = _USER(value)
    est = us.overrides.get("_estimated_next")
    if est and "next_charge_date" not in us.overrides:
        est_d = dt.date.fromisoformat(est)
        rec_next = rec.next_charge_date
        if not (rec_next.known and rec_next.state == FieldState.CONFIRMED) and not (
            rec.last_charge_date.known and est_d <= rec.last_charge_date.value
        ):
            fields["next_charge_date"] = FieldValue(
                value=est_d, state=FieldState.ESTIMATED, derived_from="user-stated billing period + last charge date")
    return fields


def add_period(d: dt.date, period: Optional[BillingPeriod], months: Optional[int]) -> Optional[dt.date]:
    if period == BillingPeriod.MONTHLY:
        return d + relativedelta(months=1)
    if period == BillingPeriod.ANNUAL:
        return d + relativedelta(years=1)
    if period == BillingPeriod.OTHER and months:
        return d + relativedelta(months=months)
    return None


def roll_forward(d: dt.date, period: Optional[BillingPeriod], months: Optional[int], today: dt.date) -> Optional[dt.date]:
    """First period boundary on or after (today - lookback)."""
    cur = d
    for _ in range(600):
        if cur + dt.timedelta(days=LOOKBACK_DAYS) >= today:
            return cur
        nxt = add_period(cur, period, months)
        if nxt is None:
            return None
        cur = nxt
    return None


def compute(rec: SubscriptionRecord, us: UserRecordState, today: dt.date) -> RecordView:
    f = _apply_overrides(rec, us)
    period = f["billing_period"].value if f["billing_period"].known else None
    months = us.overrides.get("period_months") or rec.period_months
    nxt: FieldValue = f["next_charge_date"]
    notices: list[Notice] = []
    missed: Optional[dt.date] = None
    pending_receipt: Optional[dt.datetime] = None

    receipt = rec.last_receipt_at
    merchant_cancel = rec.last_cancel_at
    markers = [m for m in (merchant_cancel, us.user_confirmed_cancel_at, us.cancel_requested_at) if m]
    latest_marker = max(markers) if markers else None

    if receipt and latest_marker and receipt > latest_marker:
        # A charge after a cancellation of any kind.
        only_pending = latest_marker == us.cancel_requested_at and not (
            (merchant_cancel and merchant_cancel >= latest_marker) or us.user_confirmed_cancel_at
        )
        if only_pending:
            notices.append(Notice.CHARGED_WHILE_PENDING)  # decision #3
        elif receipt.isoformat() not in us.resubscribe_answers:
            notices.append(Notice.RESUBSCRIBE_QUESTION)  # D26; decision #7: tracking resumes meanwhile
            pending_receipt = receipt
        state = State.ACTIVE
    elif merchant_cancel and (not receipt or merchant_cancel >= receipt):
        state = State.CANCELLED_CONFIRMED
    elif us.user_confirmed_cancel_at:
        state = State.CANCELLED_USER_CONFIRMED
    elif us.cancel_requested_at:
        if nxt.known and today > nxt.value + dt.timedelta(days=LOOKBACK_DAYS):
            state = State.LIKELY_CANCELLED  # D11: expected date passed, no receipt
        else:
            state = State.CANCELLATION_PENDING
            notices.append(Notice.NO_MERCHANT_CONFIRMATION)
    else:
        state = State.ACTIVE

    if state == State.ACTIVE:
        if not nxt.known:
            state = State.UNKNOWN_DATE
        elif today > nxt.value + dt.timedelta(days=LOOKBACK_DAYS):
            # Decision #2: keep active, advance an estimated date, flag the missing receipt.
            missed = nxt.value
            rolled = roll_forward(nxt.value, period, months, today)
            if rolled:
                nxt = FieldValue(value=rolled, state=FieldState.ESTIMATED,
                                 derived_from=f"no receipt seen for {missed.isoformat()}; advanced by billing period",
                                 evidence=nxt.evidence)
                notices.append(Notice.NO_RECEIPT_SEEN)
            else:
                state = State.UNKNOWN_DATE  # cannot advance without a period: ask the user (R6)
                notices.append(Notice.NO_RECEIPT_SEEN)

    return RecordView(
        record_key=rec.record_id, merchant=f["merchant"], kind=f["kind"], billing_period=f["billing_period"],
        period_months=months, amount=f["amount"], currency=f["currency"], last_charge_date=f["last_charge_date"],
        next_charge_date=nxt, trial_end_date=f["trial_end_date"], cancel_path=f["cancel_path"], state=state,
        alerts_enabled=state in ALERTING and nxt.known and not us.muted, notices=notices, missed_date=missed,
        pending_receipt_at=pending_receipt, source_accounts=rec.source_accounts, message_ids=rec.message_ids,
        flags=rec.flags, muted=us.muted,
    )

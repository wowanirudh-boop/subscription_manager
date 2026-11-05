"""Unknowns resolution: R6, D22.

Queue = records whose next charge date is unknown, ordered by expected damage:
annual/trial first, then amount descending, then monthly, then period-unknown.
Different currencies compare by stated amount (no conversion; known limitation, D30).
The home screen shows exactly one card; a skipped card returns no sooner than
the next app session.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

from srt_phase0.models import BillingPeriod, FieldState, Kind

from .lifecycle import LOOKBACK_DAYS, RecordView, State, UserRecordState, add_period, roll_forward


def _rank(v: RecordView) -> tuple:
    period = v.billing_period.value if v.billing_period.known else None
    kind = v.kind.value if v.kind.known else None
    if kind == Kind.TRIAL or period == BillingPeriod.ANNUAL:
        bucket = 0
    elif period == BillingPeriod.MONTHLY:
        bucket = 2
    elif period is None:
        bucket = 3
    else:
        bucket = 1  # other known periods (quarterly, half-yearly) behave like annual-ish
    amount = v.amount.value if v.amount.known else 0.0
    return (bucket, -amount, (v.merchant.value or "").lower())


def queue(views: list[RecordView]) -> list[RecordView]:
    return sorted([v for v in views if v.state == State.UNKNOWN_DATE], key=_rank)


def next_card(views: list[RecordView], states: dict[str, UserRecordState], session_id: str) -> Optional[RecordView]:
    for v in queue(views):
        st = states.get(v.record_key)
        if st and st.skipped_session == session_id:
            continue
        return v
    return None


class Answer:
    MONTHLY = "monthly"
    ANNUAL = "annual"
    NOT_SUBSCRIPTION = "not_subscription"
    SKIP = "skip"
    DATE = "date"


def apply_answer(view: RecordView, st: UserRecordState, answer: str, session_id: str,
                 date: Optional[dt.date], today: dt.date) -> dict:
    """Mutates ``st``. Returns {"needs_date": bool, "event": name-or-None}."""
    if answer == Answer.SKIP:
        st.skipped_session = session_id
        return {"needs_date": False, "event": "unknown_skipped"}
    if answer == Answer.NOT_SUBSCRIPTION:
        st.suppressed = True
        return {"needs_date": False, "event": "false_positive"}  # M3
    if answer == Answer.DATE:
        if date is None:
            raise ValueError("date required")
        st.overrides["next_charge_date"] = date.isoformat()  # direct entry -> confirmed
        return {"needs_date": False, "event": "unknown_resolved"}
    if answer in (Answer.MONTHLY, Answer.ANNUAL):
        period = BillingPeriod.MONTHLY if answer == Answer.MONTHLY else BillingPeriod.ANNUAL
        st.overrides["billing_period"] = period.value  # user-stated -> confirmed
        anchor = view.last_charge_date
        if anchor.known and anchor.state == FieldState.CONFIRMED:
            first = add_period(anchor.value, period, None)
            rolled = roll_forward(first, period, None, today) if first else None
            if rolled:
                # Next date stays *estimated*: derived from a stated period + a confirmed anchor.
                st.overrides.pop("next_charge_date", None)
                st.overrides["_estimated_next"] = rolled.isoformat()
                return {"needs_date": False, "event": "unknown_resolved"}
        return {"needs_date": True, "event": None}  # follow-up asks for the date; period is kept
    raise ValueError(f"unknown answer {answer!r}")


def tapped_date_in_snippet(st: UserRecordState, date: dt.date) -> dict:
    """User tapped a date visible in the evidence that the parser missed -> confirmed + parser-miss log."""
    st.overrides["next_charge_date"] = date.isoformat()
    return {"needs_date": False, "event": "parser_miss"}


__all__ = ["Answer", "apply_answer", "next_card", "queue", "tapped_date_in_snippet", "LOOKBACK_DAYS"]

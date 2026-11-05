"""Build the user's subscription list: e-mail facts (merged) + manual adds + user actions -> views."""

from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from srt_phase0.merge import merchant_key, merge
from srt_phase0.models import (BillingPeriod, Extraction, FieldState, FieldValue, Kind, Lifecycle, SubscriptionRecord)

from ..db import Event, ExtractionRow, ManualRecord, RecordStateRow, SuppressedMerchant, User
from ..domain.lifecycle import RecordView, UserRecordState, compute


def log_event(s: Session, user_id: Optional[int], type_: str, record_key: Optional[str] = None, **data) -> None:
    s.add(Event(user_id=user_id, type=type_, record_key=record_key, data=data or None))


def _user_fv(v) -> FieldValue:
    return FieldValue(value=v, state=FieldState.CONFIRMED, derived_from="user-entered") if v is not None else FieldValue()


def manual_record(row: ManualRecord) -> SubscriptionRecord:
    d = row.data
    nxt = dt.date.fromisoformat(d["next_charge_date"]) if d.get("next_charge_date") else None
    return SubscriptionRecord(
        record_id=f"manual-{row.id}", merchant=_user_fv(d["merchant"]), source_accounts=["manual"],
        kind=_user_fv(Kind(d.get("kind", "subscription"))), billing_period=_user_fv(BillingPeriod(d["billing_period"])),
        amount=_user_fv(d.get("amount")), currency=_user_fv(d.get("currency")), last_charge_date=FieldValue(),
        next_charge_date=_user_fv(nxt), trial_end_date=FieldValue(), cancel_path=FieldValue(),
        lifecycle_state=Lifecycle.ACTIVE if nxt else Lifecycle.UNKNOWN_DATE, message_ids=[],
        first_seen_at=row.created_at,
    )


def load_states(s: Session, user_id: int) -> dict[str, UserRecordState]:
    rows = s.scalars(select(RecordStateRow).where(RecordStateRow.user_id == user_id))
    return {r.record_key: UserRecordState.model_validate(r.data) for r in rows}


def save_state(s: Session, user_id: int, key: str, st: UserRecordState) -> None:
    row = s.scalar(select(RecordStateRow).where(RecordStateRow.user_id == user_id, RecordStateRow.record_key == key))
    data = st.model_dump(mode="json")
    if row:
        row.data = data
    else:
        s.add(RecordStateRow(user_id=user_id, record_key=key, data=data))


def load_records(s: Session, user_id: int) -> list[SubscriptionRecord]:
    suppressed = set(s.scalars(select(SuppressedMerchant.merchant_key).where(SuppressedMerchant.user_id == user_id)))
    exs = []
    for row in s.scalars(select(ExtractionRow).where(ExtractionRow.user_id == user_id, ExtractionRow.related.is_(True))):
        ex = Extraction.model_validate(row.data)
        if ex.merchant.known and merchant_key(ex.merchant.value) in suppressed:
            continue
        exs.append(ex)
    recs = merge(exs)
    recs += [manual_record(m) for m in s.scalars(select(ManualRecord).where(ManualRecord.user_id == user_id))]
    return recs


def build_views(s: Session, user: User, today: dt.date) -> tuple[list[RecordView], dict[str, UserRecordState]]:
    states = load_states(s, user.id)
    views = []
    for r in load_records(s, user.id):
        st = states.get(r.record_id, UserRecordState())
        if st.suppressed:
            continue
        views.append(compute(r, st, today))
    # R5: sorted by next charge date, unknowns last.
    views.sort(key=lambda v: (not v.next_charge_date.known, v.next_charge_date.value or dt.date.max))
    return views, states


def find_view(s: Session, user: User, key: str, today: dt.date) -> tuple[Optional[RecordView], UserRecordState]:
    views, states = build_views(s, user, today)
    view = next((v for v in views if v.record_key == key), None)
    return view, states.get(key, UserRecordState())

"""Sync: first sync (R2) and continuous detection (R3) through the Phase 0 funnel (R4)."""

from __future__ import annotations

import datetime as dt
from typing import Callable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from srt_phase0.pipeline import Pipeline
from srt_phase0.providers.base import Provider
from srt_phase0.queries import build_app_queries
from srt_phase0.sources import EmailSource
from srt_phase0.templates import TemplateStore

from ..db import ExtractionRow, GmailAccount, PushToken, User
from ..domain.lifecycle import Notice
from .alerts_service import alert_delivered_before, reschedule
from .delivery import Delivery
from .records import build_views, log_event


def sync_account(
    s: Session,
    user: User,
    account: GmailAccount,
    source: EmailSource,
    provider: Provider,
    now: dt.datetime,
    delivery: Optional[Delivery] = None,
    first_sync: bool = False,
    on_progress: Optional[Callable[[], None]] = None,
) -> dict:
    """Process new matching mail for one account. Re-runnable: already-processed ids are skipped."""
    today = now.date()
    before = {v.record_key: v for v in build_views(s, user, today)[0]}
    before_receipts = {k: _receipt_at(s, user, k) for k in before}
    skip = set(s.scalars(select(ExtractionRow.message_id).where(ExtractionRow.user_id == user.id)))
    after_epoch = None
    if not first_sync and account.last_synced_at:
        last = account.last_synced_at if account.last_synced_at.tzinfo else account.last_synced_at.replace(tzinfo=dt.timezone.utc)
        after_epoch = int((last - dt.timedelta(days=1)).timestamp())  # overlap; duplicates are skipped by id

    store = TemplateStore.from_json(user.templates_json)
    account.sync_status = "running"
    s.commit()
    res = Pipeline(provider, store, concurrency=4).run([source], today, build_app_queries(today, after_epoch=after_epoch), skip)

    exs = {e.message_id: e for e in res.extractions}
    for t in res.traces:
        if t.error:
            continue  # retried on the next sync
        ex = exs.get(t.message_id)
        s.add(ExtractionRow(user_id=user.id, account_id=account.id, message_id=t.message_id, email_date=t.date,
                            related=bool(ex and ex.is_subscription_related),
                            data=ex.model_dump(mode="json") if ex and ex.is_subscription_related else None))
    user.templates_json = store.to_json()
    account.sync_matched += res.stats.stage1_matches
    account.sync_processed += len([t for t in res.traces if not t.error])
    if first_sync and account.first_result_seconds is None:
        account.first_result_seconds = res.stats.first_result_seconds
    account.last_synced_at = now
    account.sync_status = "done" if not res.stats.errors else "partial"
    s.flush()

    views, _ = build_views(s, user, today)
    if not first_sync:
        _after_new_mail(s, user, views, before_receipts, delivery)
    reschedule(s, user, views, now)
    log_event(s, user.id, "sync", None, first=first_sync, matched=res.stats.stage1_matches,
              stage4=res.stats.stage4_calls, stage5=res.stats.stage5_hits, errors=res.stats.errors,
              usage=res.stats.usage)  # M8
    s.commit()
    return {"matched": res.stats.stage1_matches, "related": res.stats.related_emails, "errors": res.stats.errors}


def _receipt_at(s: Session, user: User, key: str):
    from .records import load_records

    for r in load_records(s, user.id):
        if r.record_id == key:
            return r.last_receipt_at
    return None


def _after_new_mail(s: Session, user: User, views, before_receipts: dict, delivery: Optional[Delivery]) -> None:
    """M1 surprise detection and immediate notices for charges after a cancellation (D26, #3)."""
    from .records import load_records

    receipts = {r.record_id: r.last_receipt_at for r in load_records(s, user.id)}
    tokens = [t.token for t in s.scalars(select(PushToken).where(PushToken.user_id == user.id))]
    for v in views:
        new_receipt = receipts.get(v.record_key)
        if not new_receipt or new_receipt == before_receipts.get(v.record_key):
            continue
        alerted = alert_delivered_before(s, user.id, v.record_key, new_receipt)
        if Notice.RESUBSCRIBE_QUESTION in v.notices:
            msg = f"{v.merchant.value} charged you again. Did you re-subscribe?"
            # decision #7: M1 decided when the question is answered ("No" = surprise)
        elif Notice.CHARGED_WHILE_PENDING in v.notices:
            msg = f"{v.merchant.value} charged you although you said you cancelled."
            if not alerted:
                log_event(s, user.id, "surprise_charge", v.record_key, reason="charged_while_pending_no_alert")
        else:
            msg = None
            if not alerted and v.record_key in before_receipts:
                log_event(s, user.id, "surprise_charge", v.record_key, reason="no_alert_delivered")  # M1
        if msg and delivery and tokens:
            try:
                delivery.push(tokens, v.merchant.value or "Subscription", msg, {"record_key": v.record_key})
            except Exception:  # noqa: BLE001
                log_event(s, user.id, "notice_failed", v.record_key)

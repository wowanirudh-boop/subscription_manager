"""Keeps the alerts table in step with record state; sends due alerts (R7, M5)."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import Alert, PushToken, User
from ..domain import alerts as ladder
from ..domain.lifecycle import RecordView
from .delivery import Delivery
from .records import build_views, log_event


def reschedule(s: Session, user: User, views: list[RecordView], now: dt.datetime) -> None:
    """Idempotent: planned set replaces future scheduled alerts; sent history is kept."""
    planned = {}
    for v in views:
        for p in ladder.plan(v, now, user.tz):
            planned[(p.record_key, p.target_date, p.days_before, p.channel)] = p
    existing = list(s.scalars(select(Alert).where(Alert.user_id == user.id, Alert.status == "scheduled")))
    keep = set()
    for a in existing:
        k = (a.record_key, a.target_date, a.days_before, a.channel)
        if k in planned:
            keep.add(k)
            a.send_at = planned[k].send_at
        else:
            a.status = "cancelled"  # date corrected, record cancelled/muted/resolved (R7: reschedule on change)
    sent = {(a.record_key, a.target_date, a.days_before, a.channel) for a in s.scalars(
        select(Alert).where(Alert.user_id == user.id, Alert.status.in_(("sent", "delivered", "failed"))))}
    for k, p in planned.items():
        if k not in keep and k not in sent:
            s.add(Alert(user_id=user.id, record_key=p.record_key, target_date=p.target_date, days_before=p.days_before,
                        channel=p.channel, send_at=p.send_at))


def tick(s: Session, now: dt.datetime, delivery: Delivery) -> dict:
    due = list(s.scalars(select(Alert).where(Alert.status == "scheduled", Alert.send_at <= now)))
    sent = failed = skipped = 0
    by_user: dict[int, list[Alert]] = {}
    for a in due:
        by_user.setdefault(a.user_id, []).append(a)
    for user_id, alerts in by_user.items():
        user = s.get(User, user_id)
        views = {v.record_key: v for v in build_views(s, user, now.date())[0]}
        tokens = [t.token for t in s.scalars(select(PushToken).where(PushToken.user_id == user_id))]
        for a in alerts:
            v = views.get(a.record_key)
            # Re-check at send time: state may have changed since scheduling.
            if not v or not v.alerts_enabled or v.next_charge_date.value != a.target_date:
                a.status = "cancelled"
                skipped += 1
                continue
            title, body = ladder.render(v, a.days_before)
            try:
                if a.channel == "push":
                    tickets = delivery.push(tokens, title, body, {"record_key": a.record_key, "alert_id": a.id})
                    ok = bool(tickets) and all(t.get("status") == "ok" for t in tickets)
                    if not ok:
                        raise RuntimeError(f"push failed: {tickets or 'no push tokens'}")
                    a.ticket_ids = ",".join(t["id"] for t in tickets if t.get("id"))
                else:
                    delivery.email(user.email, title, body + "\n\n- Subscription Renewal Tracker")
                a.status, a.sent_at = "sent", now
                sent += 1
                log_event(s, user_id, "alert_sent", a.record_key, channel=a.channel, days_before=a.days_before)
            except Exception as e:  # noqa: BLE001 - delivery failures are recorded, never fatal
                a.status, a.error = "failed", str(e)[:500]
                failed += 1
                log_event(s, user_id, "alert_failed", a.record_key, channel=a.channel, days_before=a.days_before)
    return {"due": len(due), "sent": sent, "failed": failed, "skipped": skipped}


def alert_delivered_before(s: Session, user_id: int, record_key: str, charge: dt.datetime) -> bool:
    """M1: was any alert sent for this record in the 8 days before the charge?"""
    return s.scalar(select(Alert.id).where(
        Alert.user_id == user_id, Alert.record_key == record_key, Alert.status.in_(("sent", "delivered")),
        Alert.sent_at <= charge, Alert.sent_at >= charge - dt.timedelta(days=8))) is not None


RECEIPT_DELAY = dt.timedelta(minutes=15)  # Expo recommends checking receipts after ~15 minutes


def poll_receipts(s: Session, now: dt.datetime, delivery: Delivery) -> dict:
    """M5: promote push alerts from 'sent' (Expo accepted) to 'delivered' (Apple/Google accepted)."""
    pending = list(s.scalars(select(Alert).where(Alert.channel == "push", Alert.status == "sent",
                                                 Alert.ticket_ids.is_not(None), Alert.sent_at <= now - RECEIPT_DELAY)))
    ids = [t for a in pending for t in (a.ticket_ids or "").split(",") if t]
    if not ids:
        return {"checked": 0, "delivered": 0, "failed": 0}
    receipts = delivery.receipts(ids)
    delivered = failed = 0
    for a in pending:
        rs = [receipts.get(t) for t in a.ticket_ids.split(",") if t]
        if any(r is None for r in rs):
            continue  # not ready yet
        if any(r.get("status") == "ok" for r in rs):
            a.status = "delivered"
            delivered += 1
            log_event(s, a.user_id, "alert_delivered", a.record_key, channel="push", days_before=a.days_before)
        else:
            a.status, a.error = "failed", str([r.get("message") for r in rs])[:500]
            failed += 1
            log_event(s, a.user_id, "alert_failed", a.record_key, channel="push", days_before=a.days_before)
        for r in rs:
            if (r.get("details") or {}).get("error") == "DeviceNotRegistered":
                bad = (r.get("details") or {}).get("expoPushToken")
                if bad:
                    for t in s.scalars(select(PushToken).where(PushToken.user_id == a.user_id, PushToken.token == bad)):
                        s.delete(t)
    return {"checked": len(pending), "delivered": delivered, "failed": failed}

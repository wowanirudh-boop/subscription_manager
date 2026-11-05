"""Alert ladder: R7, D13, D19, D20, D28 and flow sign-off #1 (send at 09:00 local).

monthly                      -> T-1, T-0
everything else (annual, trial, other, unknown period) -> T-7, T-3, T-1, T-0
Push for every step; e-mail to the user's own address for T-1 and T-0, always.
"""

from __future__ import annotations

import datetime as dt
from typing import Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from srt_phase0.models import BillingPeriod, Kind

from .lifecycle import RecordView

SEND_HOUR = 9  # decision #1
DEFAULT_TZ = "Asia/Kolkata"  # D2: India-only MVP


class PlannedAlert(BaseModel):
    record_key: str
    target_date: dt.date  # the charge / renewal date being warned about
    days_before: int
    send_at: dt.datetime  # UTC
    channel: str  # "push" | "email"


def ladder(period: Optional[BillingPeriod], kind: Optional[Kind]) -> list[int]:
    if kind == Kind.TRIAL:  # D20: all trials use the long ladder
        return [7, 3, 1, 0]
    if period == BillingPeriod.MONTHLY:
        return [1, 0]
    return [7, 3, 1, 0]  # D28: annual, other, unknown


def plan(view: RecordView, now: dt.datetime, tz: str = DEFAULT_TZ) -> list[PlannedAlert]:
    if not view.alerts_enabled or not view.next_charge_date.known:
        return []
    target: dt.date = view.next_charge_date.value
    period = view.billing_period.value if view.billing_period.known else None
    kind = view.kind.value if view.kind.known else None
    zone = ZoneInfo(tz)
    out: list[PlannedAlert] = []
    for k in ladder(period, kind):
        local = dt.datetime.combine(target - dt.timedelta(days=k), dt.time(SEND_HOUR), tzinfo=zone)
        send_at = local.astimezone(dt.timezone.utc)
        if send_at < now - dt.timedelta(hours=12):
            continue  # step already passed; a late T-0 the same morning still goes out
        channels = ["push", "email"] if k <= 1 else ["push"]
        for ch in channels:
            out.append(PlannedAlert(record_key=view.record_key, target_date=target, days_before=k, send_at=send_at, channel=ch))
    return out


def render(view: RecordView, days_before: int) -> tuple[str, str]:
    """Alert content (R7): merchant, amount, currency, date, date state, cancel path."""
    merchant = view.merchant.value or "A subscription"
    when = "today" if days_before == 0 else ("tomorrow" if days_before == 1 else f"in {days_before} days")
    amount = (
        f"{view.currency.value + ' ' if view.currency.known else ''}{view.amount.value:,.2f}"
        if view.amount.known else "an unknown amount"
    )
    date_s = view.next_charge_date.value.strftime("%d %b %Y")
    tag = " (estimated date)" if view.next_charge_date.state.value == "estimated" else ""
    title = f"{merchant} charges {when}"
    body = f"{merchant} will charge {amount} on {date_s}{tag}."
    if view.cancel_path.known:
        body += f" To cancel: {view.cancel_path.value}"
    if view.state.value == "cancellation_pending":
        body = "You said you cancelled, but the merchant hasn't confirmed. " + body
    return title, body

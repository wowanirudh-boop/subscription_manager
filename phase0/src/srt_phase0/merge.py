"""Merge per-email extractions into subscription records (R4, D16, PRD 6.1-6.3).

Rules implemented:
- One record per merchant across all connected accounts.
- Emails are applied oldest -> newest. For each field (PRD 6.2):
    * unknown current value       -> take the new value;
    * estimated current value     -> overwritten by any new known value;
    * confirmed current value     -> overwritten by a newer confirmed value, with a
      flag if they differ ("most recent receipt wins", R4); NOT overwritten by a
      newer estimate unless the confirmed date is already in the past relative to
      the newer email (stale), otherwise flagged.
- Win-back offers never change state (Q7). A cancellation confirmation newer than
  the last receipt -> cancelled_confirmed.
- After merging, an estimated/unknown next date is re-derived from the latest
  charge date + billing period.

Interpretation to review: R4's "most recent receipt wins for amount" and 6.2's
"flags a confirmed one" are combined as overwrite-and-flag.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
from typing import Iterable

from .models import (
    BillingPeriod,
    EmailType,
    Extraction,
    FieldState,
    FieldValue,
    Kind,
    Lifecycle,
    SubscriptionRecord,
)
from .verify import add_period

_SUFFIXES = re.compile(r"\b(india|inc|llc|ltd|limited|pvt|private|technologies|tech|services|co|corp|corporation|gmbh|bv)\b")


def merchant_key(name: str) -> str:
    n = name.lower()
    n = _SUFFIXES.sub(" ", n)
    return re.sub(r"[^a-z0-9]", "", n)


def _key(ex: Extraction) -> str:
    if ex.merchant.known:
        k = merchant_key(ex.merchant.value)
        if k:
            return k
    return "domain:" + ex.sender.rsplit("@", 1)[-1]


def _apply(cur: FieldValue, new: FieldValue, when: dt.datetime, name: str, flags: list[str]) -> FieldValue:
    if not new.known:
        return cur
    if not cur.known or cur.state == FieldState.ESTIMATED:
        return new
    # current is confirmed
    if new.value == cur.value:
        return new if new.state == FieldState.CONFIRMED else cur
    if new.state == FieldState.CONFIRMED:
        flags.append(f"{name} changed from {cur.value} to {new.value} ({when.date().isoformat()})")
        return new
    if isinstance(cur.value, dt.date) and cur.value < when.date():
        return new  # confirmed date already passed: superseded, not a contradiction
    flags.append(f"{name}: newer estimate {new.value} contradicts confirmed {cur.value}; kept confirmed")
    return cur


def merge(extractions: Iterable[Extraction]) -> list[SubscriptionRecord]:
    groups: dict[str, list[Extraction]] = {}
    for ex in extractions:
        if ex.is_subscription_related:
            groups.setdefault(_key(ex), []).append(ex)

    records = []
    for key, exs in groups.items():
        exs.sort(key=lambda e: e.email_date)
        flags: list[str] = []
        f: dict[str, FieldValue] = {
            n: FieldValue()
            for n in ("merchant", "kind", "billing_period", "amount", "currency", "last_charge_date",
                      "next_charge_date", "trial_end_date", "cancel_path")
        }
        period_months = None
        last_receipt: dt.datetime | None = None
        last_cancel: dt.datetime | None = None
        for ex in exs:
            if ex.email_type == EmailType.WINBACK_OFFER:
                # Q7: offers neither cancel nor reactivate; keep only a cancel path if present.
                f["cancel_path"] = _apply(f["cancel_path"], ex.cancel_path, ex.email_date, "cancel_path", flags)
                continue
            if ex.email_type == EmailType.CANCELLATION_CONFIRMATION:
                last_cancel = ex.email_date
            if ex.email_type == EmailType.RECEIPT:
                last_receipt = ex.email_date
                f["last_charge_date"] = _apply(f["last_charge_date"], ex.charge_date, ex.email_date, "last_charge_date", flags)
            f["merchant"] = _apply(f["merchant"], ex.merchant, ex.email_date, "merchant", flags) if not f["merchant"].known else f["merchant"]
            f["kind"] = ex.kind if ex.kind.known else f["kind"]  # latest classification wins (trial -> subscription)
            f["billing_period"] = _apply(f["billing_period"], ex.billing_period, ex.email_date, "billing_period", flags)
            if ex.period_months:
                period_months = ex.period_months
            if ex.email_type == EmailType.PRICE_CHANGE:
                if ex.amount.known:
                    flags.append(f"price change notice: {ex.amount.value} ({ex.email_date.date().isoformat()})")
            elif ex.email_type != EmailType.CANCELLATION_CONFIRMATION:
                f["amount"] = _apply(f["amount"], ex.amount, ex.email_date, "amount", flags)
                f["currency"] = _apply(f["currency"], ex.currency, ex.email_date, "currency", flags)
            if ex.email_type != EmailType.CANCELLATION_CONFIRMATION:
                f["next_charge_date"] = _apply(f["next_charge_date"], ex.next_charge_date, ex.email_date, "next_charge_date", flags)
                f["trial_end_date"] = _apply(f["trial_end_date"], ex.trial_end_date, ex.email_date, "trial_end_date", flags)
            f["cancel_path"] = _apply(f["cancel_path"], ex.cancel_path, ex.email_date, "cancel_path", flags)

        # A receipt after a trial means it converted.
        if f["kind"].known and f["kind"].value == Kind.TRIAL and last_receipt and exs[0].email_date < last_receipt:
            trial_seen = any(e.email_type == EmailType.TRIAL_SIGNUP and e.email_date < last_receipt for e in exs)
            if trial_seen:
                flags.append("trial appears to have converted (receipt after trial sign-up)")

        # Re-derive the next date from the latest charge when it isn't confirmed.
        lc, bp = f["last_charge_date"], f["billing_period"]
        if f["next_charge_date"].state != FieldState.CONFIRMED and lc.known and bp.known:
            nxt = add_period(lc.value, bp.value, period_months)
            if nxt and (not f["next_charge_date"].known or nxt > f["next_charge_date"].value):
                f["next_charge_date"] = FieldValue(
                    value=nxt, state=FieldState.ESTIMATED,
                    derived_from=f"last charge {lc.value.isoformat()} + {bp.value.value}", evidence=lc.evidence,
                )

        if last_cancel and (last_receipt is None or last_cancel > last_receipt):
            state = Lifecycle.CANCELLED_CONFIRMED
        elif not f["next_charge_date"].known:
            state = Lifecycle.UNKNOWN_DATE
        else:
            state = Lifecycle.ACTIVE

        if not f["merchant"].known:
            f["merchant"] = FieldValue(value=key.removeprefix("domain:"), state=FieldState.ESTIMATED, derived_from="sender domain")

        records.append(
            SubscriptionRecord(
                record_id=hashlib.sha1(key.encode()).hexdigest()[:12],
                merchant=f["merchant"],
                source_accounts=sorted({e.account for e in exs}),
                kind=f["kind"],
                billing_period=f["billing_period"],
                amount=f["amount"],
                currency=f["currency"],
                last_charge_date=f["last_charge_date"],
                next_charge_date=f["next_charge_date"],
                trial_end_date=f["trial_end_date"],
                cancel_path=f["cancel_path"],
                lifecycle_state=state,
                message_ids=[e.message_id for e in exs],
                flags=flags,
            )
        )
    # R5: sorted by next_charge_date, unknowns last.
    records.sort(key=lambda r: (not r.next_charge_date.known, r.next_charge_date.value or dt.date.max))
    return records

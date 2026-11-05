"""Merge per-email extractions into subscription records (R4, D16, PRD 6.1-6.3).

Rules implemented:
- One record per merchant across all connected accounts - unless the merchant has
  several plans (see "instances" below).
- Emails are applied oldest -> newest. For each field (PRD 6.2):
    * unknown current value       -> take the new value;
    * estimated current value     -> overwritten by any new known value;
    * confirmed current value     -> overwritten by a newer confirmed value, with a
      flag if they differ ("most recent receipt wins", R4); NOT overwritten by a
      newer estimate unless the confirmed date is already in the past relative to
      the newer email (stale), otherwise flagged. Forward progression of charge
      dates (next month's charge) is not a contradiction and is not flagged.
- Win-back offers never change state (Q7). A cancellation confirmation newer than
  the last charge -> cancelled_confirmed.
- Bank/card alerts (D4 amended 5 Nov 2026) are charges. A merchant seen ONLY in
  bank alerts becomes a record only if its charges repeat at a regular interval
  (or a pre-debit/mandate notice exists); one-off card purchases are dropped.
- Billing period, when no email states it, is inferred from the cadence of >= 2
  charges (~30 / ~91 / ~182 / ~365 days) and marked *estimated*.
- Instances: several plans from one merchant (e.g. several insurance policies paid
  the same day) are split by a stated reference (policy/account number), else by
  amount: charges within 3 days of each other form one billing cycle; a cycle with
  k charges means k plans; charges in other cycles join the plan with the nearest
  amount. Amount-based identity is flagged as estimated.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import math
import re
import statistics
from typing import Iterable, Optional

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

_SUFFIXES = re.compile(r"\b(india|inc|llc|ltd|limited|pvt|private|technologies|tech|services|co|corp|corporation|gmbh|bv|com|www)\b")
CHARGE_TYPES = (EmailType.RECEIPT, EmailType.CARD_TRANSACTION)
_PERIOD_BANDS = [  # (min days, max days, period, months)
    (25, 35, BillingPeriod.MONTHLY, None),
    (84, 98, BillingPeriod.OTHER, 3),
    (175, 190, BillingPeriod.OTHER, 6),
    (350, 380, BillingPeriod.ANNUAL, None),
]
_PROGRESSING_DATES = ("last_charge_date", "next_charge_date", "trial_end_date")


def merchant_key(name: str) -> str:
    n = name.lower()
    # Card descriptors keep the part after the aggregator prefix: "GOOGLE*YOUTUBE" -> "googleyoutube",
    # so YouTube and Google One charges billed through Google are not merged into one record.
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
    if new.value == cur.value:
        return new if new.state == FieldState.CONFIRMED else cur
    if name in _PROGRESSING_DATES and new.value > cur.value:
        return new
    if new.state == FieldState.CONFIRMED:
        flags.append(f"{name} changed from {cur.value} to {new.value} ({when.date().isoformat()})")
        return new
    if isinstance(cur.value, dt.date) and cur.value < when.date():
        return new
    flags.append(f"{name}: newer estimate {new.value} contradicts confirmed {cur.value}; kept confirmed")
    return cur


# ---- cadence --------------------------------------------------------------------------


def charge_dates(exs: Iterable[Extraction]) -> list[dt.date]:
    """Distinct charge dates (charges within 3 days of each other count once)."""
    ds = sorted(e.charge_date.value for e in exs if e.email_type in CHARGE_TYPES and e.charge_date.known)
    out: list[dt.date] = []
    for d in ds:
        if not out or (d - out[-1]).days > 3:
            out.append(d)
    return out


def infer_period(dates: list[dt.date]) -> Optional[tuple[BillingPeriod, Optional[int], int]]:
    """(period, months, n_charges) if the gaps between charges are regular, else None."""
    if len(dates) < 2:
        return None
    gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
    med = statistics.median(gaps)
    for lo, hi, period, months in _PERIOD_BANDS:
        if lo <= med <= hi:
            # every gap must be a whole number of periods within tolerance (missed alerts allowed)
            unit = statistics.median([g for g in gaps if lo <= g <= hi] or [med])
            ok = all(abs(g / unit - round(g / unit)) <= 0.12 and round(g / unit) >= 1 for g in gaps)
            if ok:
                return period, months, len(dates)
    return None


# ---- instances (several plans from one merchant) ---------------------------------------


def _dist(a: float, b: float) -> float:
    return abs(math.log(max(a, 0.01) / max(b, 0.01)))


def split_instances(exs: list[Extraction]) -> list[tuple[str, list[Extraction], Optional[str], list[str]]]:
    """Return [(suffix, extractions, reference, flags)]. One element when there is one plan."""
    refs = {e.reference.value for e in exs if e.reference.known}
    if len(refs) >= 2:
        groups: dict[str, list[Extraction]] = {r: [] for r in refs}
        loose = []
        for e in exs:
            (groups[e.reference.value] if e.reference.known else loose).append(e)
        flags_loose = []
        for e in loose:  # attach to the reference group with the nearest amount, else the first
            if e.amount.known:
                best = min(groups, key=lambda r: min((_dist(e.amount.value, x.amount.value) for x in groups[r] if x.amount.known), default=9))
            else:
                best = sorted(groups)[0]
                flags_loose.append(f"an email without amount or reference was attached to {best}")
            groups[best].append(e)
        return [(f"ref:{r}", g, r, list(flags_loose)) for r, g in sorted(groups.items())]

    charges = sorted((e for e in exs if e.email_type in CHARGE_TYPES and e.charge_date.known and e.amount.known),
                     key=lambda e: e.charge_date.value)
    cycles: list[list[Extraction]] = []
    for e in charges:
        if cycles and (e.charge_date.value - cycles[-1][-1].charge_date.value).days <= 3:
            cycles[-1].append(e)
        else:
            cycles.append([e])
    k = max((len({round(x.amount.value, 2) for x in c}) for c in cycles), default=0)
    if k <= 1:
        return [("", exs, next(iter(refs), None), [])]

    seed = next(c for c in cycles if len({round(x.amount.value, 2) for x in c}) == k)
    slots: list[list[Extraction]] = [[x] for x in sorted({round(x.amount.value, 2): x for x in seed}.values(), key=lambda x: x.amount.value)]
    placed = {id(x) for s in slots for x in s}
    for c in cycles:
        pending = [x for x in c if id(x) not in placed]
        used: set[int] = set()
        pairs = sorted(((_dist(x.amount.value, statistics.median(y.amount.value for y in s)), i, j)
                        for i, x in enumerate(pending) for j, s in enumerate(slots)), key=lambda t: t[0])
        done: set[int] = set()
        for _, i, j in pairs:
            if i in done or j in used:
                continue
            slots[j].append(pending[i])
            done.add(i)
            used.add(j)
        for i, x in enumerate(pending):  # more charges than slots in a cycle: nearest slot
            if i not in done:
                slots[min(range(len(slots)), key=lambda j: _dist(x.amount.value, slots[j][0].amount.value))].append(x)
        placed |= {id(x) for x in c}
    flag = f"one of {len(slots)} plans from this merchant, told apart by amount (estimated)"
    out = [(f"#{i + 1}", list(s), None, [flag]) for i, s in enumerate(slots)]
    for e in exs:
        if id(e) in placed:
            continue
        if e.amount.known:
            j = min(range(len(out)), key=lambda j: _dist(e.amount.value, statistics.median(x.amount.value for x in out[j][1] if x.amount.known)))
            out[j][1].append(e)
        else:
            out[0][1].append(e)
            out[0][3].append("an email without amount was attached to plan #1")
    return out


# ---- building one record --------------------------------------------------------------


def _build(key: str, suffix: str, exs: list[Extraction], reference: Optional[str], extra_flags: list[str]) -> Optional[SubscriptionRecord]:
    exs.sort(key=lambda e: e.email_date)
    flags: list[str] = list(extra_flags)
    f: dict[str, FieldValue] = {
        n: FieldValue()
        for n in ("merchant", "kind", "billing_period", "amount", "currency", "last_charge_date",
                  "next_charge_date", "trial_end_date", "cancel_path")
    }
    period_months = None
    last_receipt: dt.datetime | None = None
    last_cancel: dt.datetime | None = None
    sources = sorted({"bank" if e.email_type in (EmailType.CARD_TRANSACTION, EmailType.PRE_DEBIT_NOTICE) else "merchant" for e in exs})
    for ex in exs:
        if ex.email_type == EmailType.WINBACK_OFFER:
            f["cancel_path"] = _apply(f["cancel_path"], ex.cancel_path, ex.email_date, "cancel_path", flags)
            continue
        if ex.email_type == EmailType.CANCELLATION_CONFIRMATION:
            last_cancel = ex.email_date
        if ex.email_type in CHARGE_TYPES:
            last_receipt = ex.email_date
            f["last_charge_date"] = _apply(f["last_charge_date"], ex.charge_date, ex.email_date, "last_charge_date", flags)
        if not f["merchant"].known:
            f["merchant"] = ex.merchant
        f["kind"] = ex.kind if ex.kind.known else f["kind"]
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

    dates = charge_dates(exs)
    cadence = infer_period(dates)
    bank_only = sources == ["bank"]
    has_mandate = any(e.email_type == EmailType.PRE_DEBIT_NOTICE for e in exs)
    if bank_only and not cadence and not has_mandate:
        return None  # a one-off card purchase, not a subscription

    if not f["billing_period"].known and cadence:
        period, months, n = cadence
        f["billing_period"] = FieldValue(value=period, state=FieldState.ESTIMATED,
                                         derived_from=f"{n} charges at a regular interval ({dates[0]} to {dates[-1]})")
        period_months = period_months or months

    if f["kind"].known and f["kind"].value == Kind.TRIAL and last_receipt:
        if any(e.email_type == EmailType.TRIAL_SIGNUP and e.email_date < last_receipt for e in exs):
            flags.append("trial appears to have converted (charge after trial sign-up)")

    lc, bp = f["last_charge_date"], f["billing_period"]
    if f["next_charge_date"].known and lc.known and f["next_charge_date"].value <= lc.value:
        flags.append(f"next charge {f['next_charge_date'].value} superseded by charge on {lc.value}")
        f["next_charge_date"] = FieldValue()
    if f["next_charge_date"].state != FieldState.CONFIRMED and lc.known and bp.known:
        nxt = add_period(lc.value, bp.value, period_months)
        if nxt and (not f["next_charge_date"].known or nxt > f["next_charge_date"].value):
            f["next_charge_date"] = FieldValue(
                value=nxt, state=FieldState.ESTIMATED,
                derived_from=f"last charge {lc.value.isoformat()} + {bp.value.value}"
                + (" (period inferred from repeats)" if bp.state == FieldState.ESTIMATED else ""),
                evidence=lc.evidence,
            )

    if last_cancel and (last_receipt is None or last_cancel > last_receipt):
        state = Lifecycle.CANCELLED_CONFIRMED
    elif not f["next_charge_date"].known:
        state = Lifecycle.UNKNOWN_DATE
    else:
        state = Lifecycle.ACTIVE

    if not f["merchant"].known:
        f["merchant"] = FieldValue(value=key.removeprefix("domain:"), state=FieldState.ESTIMATED, derived_from="sender domain")

    return SubscriptionRecord(
        record_id=hashlib.sha1((key + suffix).encode()).hexdigest()[:12],
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
        period_months=period_months,
        reference=reference,
        sources=sources,
        last_receipt_at=last_receipt,
        last_cancel_at=last_cancel,
        first_seen_at=exs[0].email_date,
    )


def merge(extractions: Iterable[Extraction]) -> list[SubscriptionRecord]:
    groups: dict[str, list[Extraction]] = {}
    for ex in extractions:
        if ex.is_subscription_related:
            groups.setdefault(_key(ex), []).append(ex)
    records = []
    for key, exs in groups.items():
        for suffix, part, ref, flags in split_instances(exs):
            r = _build(key, suffix, part, ref, flags)
            if r:
                records.append(r)
    records.sort(key=lambda r: (not r.next_charge_date.known, r.next_charge_date.value or dt.date.max))
    return records

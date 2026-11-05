"""Turn a model's RawExtraction into an Extraction with field states (PRD 6.2).

confirmed  - the value is backed by a verbatim quote that occurs in the email
             and that quote contains the value.
estimated  - deterministically derived from confirmed/estimated facts (D6), with
             the derivation recorded.
unknown    - everything else (D7). An unstated trial length is never estimated.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Optional

from dateutil.relativedelta import relativedelta

from .models import (
    BillingPeriod,
    EmailMessage,
    EmailType,
    Evidence,
    Extraction,
    FieldState,
    FieldValue,
    Kind,
)
from .providers.base import RawExtraction
from .textutil import (
    contains_quote,
    find_amounts,
    norm,
    quote_supports_amount,
    quote_supports_currency,
    quote_supports_date,
)

_PERIOD_WORDS = {
    BillingPeriod.MONTHLY: r"month|monthly|/mo\b|30 days",
    BillingPeriod.ANNUAL: r"year|annual|annually|yearly|/yr\b|12 months|365 days",
    BillingPeriod.OTHER: r"quarter|week|\b\d+\s*months?\b|half[- ]year|semi-annual|\b\d+\s*days?\b",
}
_KIND_WORDS = {
    Kind.TRIAL: r"trial",
    Kind.SUBSCRIPTION: r"subscri|membership|plan|premium|pro\b|monthly|annual|renew",
    Kind.RENEWAL: r"renew|domain|insurance|policy|premium|annual fee|membership",
}


def _alnum(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _haystack(msg: EmailMessage) -> str:
    return f"{msg.subject}\n{msg.body_text or ''}"


def _ev(msg: EmailMessage, quote: str) -> Evidence:
    return Evidence(message_id=msg.message_id, account=msg.account, snippet=" ".join(quote.split())[:400])


def _quoted_ok(msg: EmailMessage, quote: Optional[str]) -> bool:
    return bool(quote) and contains_quote(_haystack(msg), quote)


def _parse_iso(s: Optional[str]) -> Optional[dt.date]:
    if not s:
        return None
    try:
        return dt.date.fromisoformat(s.strip()[:10])
    except ValueError:
        return None


def add_period(d: dt.date, period: BillingPeriod, period_months: Optional[int]) -> Optional[dt.date]:
    if period == BillingPeriod.MONTHLY:
        return d + relativedelta(months=1)
    if period == BillingPeriod.ANNUAL:
        return d + relativedelta(years=1)
    if period == BillingPeriod.OTHER and period_months:
        return d + relativedelta(months=period_months)
    return None


def verify(raw: RawExtraction, msg: EmailMessage, stage: str = "stage4") -> Extraction:
    ex = Extraction(
        message_id=msg.message_id,
        account=msg.account,
        email_date=msg.date,
        sender=msg.from_addr.lower(),
        source_stage=stage,
        is_subscription_related=raw.is_subscription_related,
        email_type=raw.email_type,
    )
    if not raw.is_subscription_related:
        return ex
    rejected = ex.rejected_values

    # merchant: must be visible in the email or its sender identity.
    if raw.merchant.value:
        hay = _alnum(f"{_haystack(msg)} {msg.from_name} {msg.sender_domain}")
        if _alnum(raw.merchant.value) and _alnum(raw.merchant.value) in hay:
            quote = raw.merchant.quote if _quoted_ok(msg, raw.merchant.quote) else f"From: {msg.from_name or msg.from_addr}"
            ex.merchant = FieldValue(value=raw.merchant.value.strip(), state=FieldState.CONFIRMED, evidence=_ev(msg, quote))
        else:
            rejected.append(f"merchant={raw.merchant.value!r}")

    # kind: a classification, kept only when a quote in the email supports it.
    if raw.kind.value:
        q = raw.kind.quote
        if _quoted_ok(msg, q) and re.search(_KIND_WORDS[raw.kind.value], q, re.I):
            ex.kind = FieldValue(value=raw.kind.value, state=FieldState.CONFIRMED, evidence=_ev(msg, q))
        else:
            rejected.append(f"kind={raw.kind.value.value}")

    # billing period
    bp = raw.billing_period
    if bp.value and bp.value != BillingPeriod.UNKNOWN:
        if _quoted_ok(msg, bp.quote) and re.search(_PERIOD_WORDS[bp.value], bp.quote, re.I):
            ex.billing_period = FieldValue(value=bp.value, state=FieldState.CONFIRMED, evidence=_ev(msg, bp.quote))
            if bp.value == BillingPeriod.OTHER and bp.period_months and re.search(
                rf"\b{bp.period_months}\b|quarter", bp.quote, re.I
            ):
                ex.period_months = bp.period_months
        else:
            rejected.append(f"billing_period={bp.value.value}")

    # amount + currency
    a = raw.amount
    if a.value is not None:
        if _quoted_ok(msg, a.quote) and quote_supports_amount(a.quote, a.value):
            ex.amount = FieldValue(value=float(a.value), state=FieldState.CONFIRMED, evidence=_ev(msg, a.quote))
            if a.currency and quote_supports_currency(a.quote, a.currency):
                ex.currency = FieldValue(value=a.currency.upper(), state=FieldState.CONFIRMED, evidence=_ev(msg, a.quote))
            elif a.currency:
                rejected.append(f"currency={a.currency}")
        else:
            rejected.append(f"amount={a.value}")

    # stated dates
    for name in ("charge_date", "next_charge_date", "trial_end_date"):
        q = getattr(raw, name)
        d = _parse_iso(q.value)
        if q.value is None:
            continue
        if d and _quoted_ok(msg, q.quote) and quote_supports_date(q.quote, d):
            setattr(ex, name, FieldValue(value=d, state=FieldState.CONFIRMED, evidence=_ev(msg, q.quote)))
        else:
            rejected.append(f"{name}={q.value}")

    # cancel path: the URL/text must literally be in the email.
    cp = raw.cancel_path
    if cp.value:
        if contains_quote(_haystack(msg), cp.value):
            ex.cancel_path = FieldValue(value=cp.value.strip(), state=FieldState.CONFIRMED, evidence=_ev(msg, cp.quote or cp.value))
        else:
            rejected.append("cancel_path")

    ref = raw.reference
    if ref.value:
        if contains_quote(_haystack(msg), ref.value) and len(ref.value.strip()) >= 4:
            ex.reference = FieldValue(value=ref.value.strip(), state=FieldState.CONFIRMED, evidence=_ev(msg, ref.quote or ref.value))
        else:
            rejected.append("reference")

    # attachments: R4 says attachments only if the body has no amount. Phase 0 does
    # not parse attachments (flow sign-off #6 is open); record when it would have.
    if not ex.amount.known and msg.attachment_names and not find_amounts(msg.body_text or ""):
        ex.attachment_skipped = True

    derive(ex, raw, msg)
    return ex


def derive(ex: Extraction, raw: RawExtraction, msg: EmailMessage) -> None:
    """D6 derivations. Only from stated facts; results are 'estimated'."""
    sent = msg.date.date()

    # A receipt with no stated charge date was sent when the charge happened.
    if ex.email_type in (EmailType.RECEIPT, EmailType.CARD_TRANSACTION) and not ex.charge_date.known:
        ex.charge_date = FieldValue(
            value=sent, state=FieldState.ESTIMATED, derived_from="receipt sent date",
            evidence=Evidence(message_id=msg.message_id, account=msg.account, snippet=f"Email sent {sent.isoformat()}"),
        )

    # Trial end from a stated trial length (never from an assumed length).
    tl = raw.trial_length_days
    if (
        not ex.trial_end_date.known
        and ex.email_type == EmailType.TRIAL_SIGNUP
        and tl.value
        and _quoted_ok(msg, tl.quote)
        and re.search(rf"\b{tl.value}\b", tl.quote or "")
    ):
        ex.trial_end_date = FieldValue(
            value=sent + dt.timedelta(days=tl.value), state=FieldState.ESTIMATED,
            derived_from=f"sign-up email date + stated {tl.value}-day trial", evidence=_ev(msg, tl.quote),
        )

    if ex.next_charge_date.known:
        return
    # Trials convert at trial end.
    if ex.trial_end_date.known:
        ex.next_charge_date = FieldValue(
            value=ex.trial_end_date.value, state=FieldState.ESTIMATED,
            derived_from="trial end date", evidence=ex.trial_end_date.evidence,
        )
        return
    # Last charge + billing period.
    if ex.charge_date.known and ex.billing_period.known:
        nxt = add_period(ex.charge_date.value, ex.billing_period.value, ex.period_months)
        if nxt:
            ex.next_charge_date = FieldValue(
                value=nxt, state=FieldState.ESTIMATED,
                derived_from=f"charge date {ex.charge_date.value.isoformat()} + {ex.billing_period.value.value}",
                evidence=ex.charge_date.evidence,
            )

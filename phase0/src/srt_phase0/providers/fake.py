"""Deterministic keyword/regex provider.

Exists so the pipeline, verifier, merge and scorer can be exercised end to end
without a model or network. Its accuracy is NOT representative of an LLM and
must never be reported as a Phase 0 result.
"""

from __future__ import annotations

import re

from ..models import BillingPeriod, EmailType, Kind
from ..textutil import find_amounts, find_dates, sentences
from .base import (
    ExtractInput,
    Quoted,
    QuotedAmount,
    QuotedInt,
    QuotedKind,
    QuotedPeriod,
    RawExtraction,
    TriageInput,
    UsageStats,
)

_RELEVANT = re.compile(
    r"\b(receipt|invoice|trial|renew\w*|subscription|membership|premium|auto-?pay|mandate|"
    r"payment (?:received|successful|confirmation)|charged|billing|plan)\b",
    re.I,
)
_IRRELEVANT = re.compile(r"\b(otp|one[- ]time password|shipped|out for delivery|newsletter|webinar)\b", re.I)
_URL = re.compile(r"https?://\S+")


def _first(sents: list[str], pat: str) -> str | None:
    rx = re.compile(pat, re.I)
    return next((s for s in sents if rx.search(s)), None)


class FakeProvider:
    name = "fake"

    def __init__(self) -> None:
        self.usage = UsageStats()

    def triage(self, item: TriageInput) -> bool:
        self.usage.triage_calls += 1
        text = f"{item.subject} {item.preview}"
        return bool(_RELEVANT.search(text)) and not _IRRELEVANT.search(text)

    def extract(self, item: ExtractInput) -> RawExtraction:
        self.usage.extract_calls += 1
        body = item.body
        text = f"{item.subject}\n{body}"
        sents = list(sentences(body))
        low = text.lower()

        if re.search(r"we miss you|come back|% off|rejoin", low):
            etype = EmailType.WINBACK_OFFER
        elif re.search(r"(subscription|membership|plan) (has been|was) cancel|cancellation (is )?confirmed", low):
            etype = EmailType.CANCELLATION_CONFIRMATION
        elif re.search(r"price (change|increase)|new price", low):
            etype = EmailType.PRICE_CHANGE
        elif "trial" in low and re.search(r"start|welcome|begun|activ", low):
            etype = EmailType.TRIAL_SIGNUP
        elif re.search(r"will (auto-?)?renew|renewal (reminder|notice)|due for renewal|expires on|premium .* is due on", low):
            etype = EmailType.RENEWAL_REMINDER
        elif re.search(r"receipt|invoice|payment (received|successful)|we('ve| have) charged|thank you for your payment", low):
            etype = EmailType.RECEIPT
        else:
            etype = EmailType.OTHER

        related = etype not in (EmailType.OTHER,) and bool(_RELEVANT.search(text))
        out = RawExtraction(is_subscription_related=related, email_type=etype)
        if not related:
            return out

        out.merchant = Quoted(value=item.sender_name or item.sender.split("@")[-1], quote=None)

        if etype == EmailType.TRIAL_SIGNUP:
            out.kind = QuotedKind(value=Kind.TRIAL, quote=_first(sents, r"trial"))
        elif re.search(r"domain|insurance|policy|premium due|annual fee", low):
            out.kind = QuotedKind(value=Kind.RENEWAL, quote=_first(sents, r"domain|insurance|policy|annual fee"))
        else:
            out.kind = QuotedKind(value=Kind.SUBSCRIPTION, quote=_first(sents, r"subscription|membership|plan"))

        ps = _first(sents, r"\b(monthly|per month|/month|every month|a month)\b")
        if ps:
            out.billing_period = QuotedPeriod(value=BillingPeriod.MONTHLY, quote=ps)
        else:
            ps = _first(sents, r"\b(annual|annually|yearly|per year|/year|every year|1 year|one year)\b")
            if ps:
                out.billing_period = QuotedPeriod(value=BillingPeriod.ANNUAL, quote=ps)
            else:
                ps = _first(sents, r"\b(quarterly|every 3 months)\b")
                if ps:
                    out.billing_period = QuotedPeriod(value=BillingPeriod.OTHER, period_months=3, quote=ps)

        for s in sents:
            amts = find_amounts(s)
            if amts:
                a, cur, _ = amts[-1] if etype == EmailType.PRICE_CHANGE else amts[0]
                out.amount = QuotedAmount(value=a, currency=cur, quote=s)
                break

        def date_in(pat: str) -> Quoted:
            s = _first([x for x in sents if find_dates(x)], pat)
            if not s:
                return Quoted()
            return Quoted(value=find_dates(s)[0][0].isoformat(), quote=s)

        out.trial_end_date = date_in(r"trial (ends|will end|expires)|until")
        out.next_charge_date = date_in(r"next (charge|payment|billing)|renew|will be charged|due on|expires on")
        out.charge_date = date_in(r"charged\b.*\bon\b|paid on|payment date|date of payment|billed on")
        if out.next_charge_date.quote and out.next_charge_date.quote == out.trial_end_date.quote:
            out.next_charge_date = Quoted()

        ts = _first(sents, r"\b\d+[- ]day\b.*trial|trial.*\b\d+[- ]days?\b")
        if ts:
            m = re.search(r"(\d+)[- ]days?", ts)
            out.trial_length_days = QuotedInt(value=int(m.group(1)), quote=ts)

        url = next((u.rstrip(").,") for u in _URL.findall(body) if "cancel" in u.lower() or "manage" in u.lower()), None)
        if url:
            out.cancel_path = Quoted(value=url, quote=url)
        return out

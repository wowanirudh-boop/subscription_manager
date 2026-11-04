"""Stage 5: learn once per sender (R4, D24).

After a successful stage-4 extraction, build a deterministic extractor for that
sender's email layout: for each confirmed field, a regex anchored on the text
around the value in its evidence sentence. Later emails from the same sender
with a matching structure are extracted without a model call.

Correctness rule (R4): the template applies only when the new email's structure
matches; if it yields unknown for a field it previously found, the caller falls
back to stage 4. Template output is a RawExtraction that goes through the same
verifier as model output, so it meets the same evidence bar.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from .models import BillingPeriod, EmailMessage, EmailType, Extraction, FieldState, Kind
from .providers.base import (
    Quoted,
    QuotedAmount,
    QuotedInt,
    QuotedKind,
    QuotedPeriod,
    RawExtraction,
)
from .textutil import find_amounts, find_dates, parse_amount_str, quote_supports_amount, quote_supports_date, sentences

SIMILARITY_THRESHOLD = 0.8
CONTEXT_CHARS = 40

_MONTH_WORD = re.compile(
    r"\b(jan(uary)?|feb(ruary)?|mar(ch)?|apr(il)?|may|june?|july?|aug(ust)?|sept?(ember)?|oct(ober)?|nov(ember)?|dec(ember)?)\b",
    re.I,
)
DATE_CAP = (
    r"(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\.?,?\s+\d{4}|[A-Za-z]{3,9}\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}"
    r"|\d{4}-\d{2}-\d{2}|\d{1,2}[/.-]\d{1,2}[/.-]\d{4})"
)
AMT_CAP = (
    r"((?:₹|rs\.?|inr|us\$|\$|€|£|usd|eur|gbp|sgd|aed)?\s?\d[\d,]*(?:\.\d{1,2})?"
    r"(?:\s?(?:inr|usd|eur|gbp|sgd|aed)\b)?)"
)
_PERIOD_ALTS = {
    "monthly": BillingPeriod.MONTHLY, "per month": BillingPeriod.MONTHLY, "a month": BillingPeriod.MONTHLY,
    "every month": BillingPeriod.MONTHLY, "/month": BillingPeriod.MONTHLY, "month": BillingPeriod.MONTHLY,
    "annually": BillingPeriod.ANNUAL, "annual": BillingPeriod.ANNUAL, "yearly": BillingPeriod.ANNUAL,
    "per year": BillingPeriod.ANNUAL, "every year": BillingPeriod.ANNUAL, "/year": BillingPeriod.ANNUAL,
    "year": BillingPeriod.ANNUAL, "quarterly": BillingPeriod.OTHER,
}
PERIOD_CAP = "(" + "|".join(re.escape(k) for k in sorted(_PERIOD_ALTS, key=len, reverse=True)) + ")"
INT_CAP = r"(\d+)"

_DATE_FIELDS = ("charge_date", "next_charge_date", "trial_end_date")


def skeleton(text: str) -> set[str]:
    """Structure fingerprint: lines with variable tokens masked."""
    out = set()
    for ln in text.splitlines():
        ln = ln.strip().lower()
        if not ln:
            continue
        ln = re.sub(r"https?://\S+", "<url>", ln)
        ln = _MONTH_WORD.sub("<mon>", ln)
        ln = re.sub(r"\d+", "#", ln)
        ln = re.sub(r"\s+", " ", ln)
        out.add(ln)
    return out


def similarity(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


_ANY_MONTH = r"[A-Za-z]{3,9}\.?"


def _lit(s: str) -> str:
    """Literal context -> regex, with digits and month names generalised."""
    parts = []
    for tok in re.split(r"(\d+|\s+)", s):
        if not tok:
            continue
        if tok.isdigit():
            parts.append(r"\d+")
        elif tok.isspace():
            parts.append(r"\s+")
        else:
            out, last = [], 0
            for m in _MONTH_WORD.finditer(tok):
                out.append(re.escape(tok[last : m.start()]))
                out.append(_ANY_MONTH)
                last = m.end()
            out.append(re.escape(tok[last:]))
            parts.append("".join(out))
    return "".join(parts)


def _pattern(quote: str, surface: str, cap: str) -> Optional[str]:
    i = quote.find(surface)
    if i < 0:
        return None
    pre = quote[max(0, i - CONTEXT_CHARS) : i]
    post = quote[i + len(surface) : i + len(surface) + CONTEXT_CHARS]
    # cut context at a word boundary so partial words don't over-constrain
    pre = pre.split(" ", 1)[1] if " " in pre and len(pre) == CONTEXT_CHARS else pre
    post = post.rsplit(" ", 1)[0] if " " in post and len(post) == CONTEXT_CHARS else post
    return _lit(pre) + cap + _lit(post)


class SenderTemplate(BaseModel):
    sender: str
    source_message_id: str
    skeleton: list[str]
    email_type: EmailType
    merchant: Optional[str] = None
    kind: Optional[Kind] = None
    kind_word: Optional[str] = None
    period_months: Optional[int] = None
    patterns: dict[str, str] = Field(default_factory=dict)  # field -> regex with one capture group
    date_dayfirst: dict[str, bool] = Field(default_factory=dict)
    found_fields: list[str] = Field(default_factory=list)
    uses: int = 0

    # ---- learning ----------------------------------------------------------------

    @classmethod
    def learn(cls, msg: EmailMessage, ex: Extraction, raw: RawExtraction) -> Optional["SenderTemplate"]:
        if ex.source_stage != "stage4" or not ex.is_subscription_related or msg.body_text is None:
            return None
        t = cls(
            sender=msg.from_addr.lower(),
            source_message_id=msg.message_id,
            skeleton=sorted(skeleton(msg.body_text)),
            email_type=ex.email_type,
            period_months=ex.period_months,
        )
        found: list[str] = []
        if ex.merchant.state == FieldState.CONFIRMED:
            t.merchant = ex.merchant.value
            found.append("merchant")
        if ex.kind.state == FieldState.CONFIRMED:
            t.kind = ex.kind.value
            m = re.search(r"trial|subscri\w*|membership|plan|renew\w*|domain|insurance|policy|premium", ex.kind.evidence.snippet, re.I)
            t.kind_word = m.group(0).lower() if m else None
            found.append("kind")
        if ex.billing_period.state == FieldState.CONFIRMED:
            q = ex.billing_period.evidence.snippet
            m = re.search(PERIOD_CAP, q, re.I)
            p = m and _pattern(q, m.group(0), PERIOD_CAP)
            if not p:
                return None
            t.patterns["billing_period"] = p
            found.append("billing_period")
        if ex.amount.state == FieldState.CONFIRMED:
            q = ex.amount.evidence.snippet
            s = quote_supports_amount(q, ex.amount.value)
            p = s and _pattern(q, s, AMT_CAP)
            if not p:
                return None
            t.patterns["amount"] = p
            found.append("amount")
        for f in _DATE_FIELDS:
            fv = getattr(ex, f)
            if fv.state != FieldState.CONFIRMED:
                continue
            q = fv.evidence.snippet
            s = quote_supports_date(q, fv.value)
            p = s and _pattern(q, s, DATE_CAP)
            if not p:
                return None
            t.patterns[f] = p
            if re.fullmatch(r"\d{1,2}[/.-]\d{1,2}[/.-]\d{4}", s):
                a = int(re.split(r"[/.-]", s)[0])
                t.date_dayfirst[f] = fv.value.day == a
            found.append(f)
        tl = raw.trial_length_days
        if tl.value and tl.quote and f"{tl.value}" in tl.quote:
            p = _pattern(tl.quote, str(tl.value), INT_CAP)
            if p:
                t.patterns["trial_length_days"] = p
        if ex.cancel_path.state == FieldState.CONFIRMED and ex.cancel_path.value.startswith("http"):
            base = ex.cancel_path.value.split("?", 1)[0]
            t.patterns["cancel_path"] = "(" + re.escape(base) + r"[^\s)>\"']*)"
            found.append("cancel_path")
        # A template that recovers no money/date facts saves nothing worth the risk.
        if not any(f in found for f in ("amount", *_DATE_FIELDS)):
            return None
        t.found_fields = found
        return t

    # ---- applying ----------------------------------------------------------------

    def matches(self, msg: EmailMessage) -> bool:
        return (
            msg.from_addr.lower() == self.sender
            and msg.body_text is not None
            and similarity(set(self.skeleton), skeleton(msg.body_text)) >= SIMILARITY_THRESHOLD
        )

    def apply(self, msg: EmailMessage) -> Optional[RawExtraction]:
        """Return a RawExtraction, or None if any previously found field is missing."""
        body = msg.body_text or ""
        sents = list(sentences(body))

        def search(field: str) -> Optional[tuple[str, str]]:
            rx = re.compile(self.patterns[field], re.I)
            for s in sents:
                m = rx.search(" ".join(s.split()))
                if m:
                    return m.group(1), s
            return None

        raw = RawExtraction(is_subscription_related=True, email_type=self.email_type)
        if self.merchant:
            raw.merchant = Quoted(value=self.merchant, quote=None)
        if self.kind:
            q = next((s for s in sents if self.kind_word and self.kind_word in s.lower()), None)
            raw.kind = QuotedKind(value=self.kind, quote=q)
        if "billing_period" in self.patterns:
            hit = search("billing_period")
            if not hit:
                return None
            raw.billing_period = QuotedPeriod(
                value=_PERIOD_ALTS[hit[0].lower()], period_months=self.period_months, quote=hit[1]
            )
        if "amount" in self.patterns:
            hit = search("amount")
            if not hit:
                return None
            amts = find_amounts(hit[0])
            if amts:
                raw.amount = QuotedAmount(value=amts[0][0], currency=amts[0][1], quote=hit[1])
            else:
                raw.amount = QuotedAmount(value=parse_amount_str(re.sub(r"[^\d.,]", "", hit[0])), quote=hit[1])
        for f in _DATE_FIELDS:
            if f not in self.patterns:
                continue
            hit = search(f)
            if not hit:
                return None
            dates = find_dates(hit[0])
            if not dates:
                return None
            if f in self.date_dayfirst and len(dates) > 1:
                d = dates[0][0] if self.date_dayfirst[f] else dates[1][0]
            else:
                d = dates[0][0]
            setattr(raw, f, Quoted(value=d.isoformat(), quote=hit[1]))
        if "trial_length_days" in self.patterns:
            hit = search("trial_length_days")
            if hit:
                raw.trial_length_days = QuotedInt(value=int(hit[0]), quote=hit[1])
        if "cancel_path" in self.patterns:
            hit = search("cancel_path")
            if hit:
                raw.cancel_path = Quoted(value=hit[0], quote=hit[1])
        return raw


class TemplateStore:
    """Per-sender templates, persisted as JSON (contains snippets-derived regexes only)."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path
        self.by_sender: dict[str, list[SenderTemplate]] = {}
        if path and path.exists():
            data = json.loads(path.read_text())
            for sender, items in data.items():
                self.by_sender[sender] = [SenderTemplate.model_validate(i) for i in items]

    def find(self, msg: EmailMessage) -> Optional[SenderTemplate]:
        best, best_sim = None, 0.0
        if msg.body_text is None:
            return None
        sk = skeleton(msg.body_text)
        for t in self.by_sender.get(msg.from_addr.lower(), []):
            sim = similarity(set(t.skeleton), sk)
            if sim >= SIMILARITY_THRESHOLD and sim > best_sim:
                best, best_sim = t, sim
        return best

    def add(self, t: SenderTemplate) -> None:
        items = self.by_sender.setdefault(t.sender, [])
        # replace a template for the same structure rather than accumulating duplicates
        items[:] = [x for x in items if similarity(set(x.skeleton), set(t.skeleton)) < SIMILARITY_THRESHOLD]
        items.append(t)

    def save(self) -> None:
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps({s: [t.model_dump(mode="json") for t in ts] for s, ts in self.by_sender.items()}, indent=1)
            )

    def __len__(self) -> int:
        return sum(len(v) for v in self.by_sender.values())

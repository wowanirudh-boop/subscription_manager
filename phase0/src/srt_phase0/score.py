"""Scoring against reference labels: the A3 gate (PRD 11, 13).

A3: general-purpose extraction reaches > 85% recall and > 90% precision on unseen
merchants. Reported at two levels:
- email level: is this email subscription-related (triage + stage 4 combined);
- merchant level: does the merged list contain the merchants the judge found.

Every proportion carries a Wilson 95% interval. The verdict is "pass" only when
the interval's lower bound clears the threshold, "fail" when the upper bound is
below it, and "inconclusive" otherwise.

Blind spot: emails that stage 1 (Gmail search) never matched are not in the
trace, so neither the pipeline nor the judge saw them. Recall here is recall
*given stage 1*, which overstates true recall by an unknown amount.
"""

from __future__ import annotations

import datetime as dt
import math
from typing import Optional

from pydantic import BaseModel, Field

from .merge import merchant_key
from .models import Extraction, FieldState, JudgeLabel, SubscriptionRecord
from .pipeline import MessageTrace, RunStats

RECALL_TARGET = 0.85
PRECISION_TARGET = 0.90
FIELDS = ("merchant", "kind", "billing_period", "amount", "currency", "charge_date", "next_charge_date", "trial_end_date")


class Proportion(BaseModel):
    k: int
    n: int
    value: Optional[float]
    lo: Optional[float]
    hi: Optional[float]

    def fmt(self) -> str:
        if not self.n:
            return "n/a (n=0)"
        return f"{self.value:.1%} [{self.lo:.1%}–{self.hi:.1%}] ({self.k}/{self.n})"


def wilson(k: int, n: int, z: float = 1.96) -> Proportion:
    if n == 0:
        return Proportion(k=0, n=0, value=None, lo=None, hi=None)
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return Proportion(k=k, n=n, value=p, lo=max(0.0, centre - half), hi=min(1.0, centre + half))


def verdict(p: Proportion, target: float) -> str:
    if not p.n:
        return "no data"
    if p.lo > target:
        return "pass"
    if p.hi < target:
        return "fail"
    return "inconclusive"


class FieldScore(BaseModel):
    correct: int = 0  # pipeline confirmed == judge
    wrong: int = 0  # pipeline confirmed != judge  (asserted a wrong fact: worst case under D5)
    missed: int = 0  # judge has a value, pipeline unknown
    spurious: int = 0  # judge null, pipeline confirmed a value
    estimated: int = 0  # pipeline estimated (not comparable to stated-only labels)
    estimated_matches_judge: int = 0


class Scorecard(BaseModel):
    labelled: int
    labelled_in_trace: int
    email_precision: Proportion
    email_recall: Proportion
    triage_recall: Proportion
    stage4_recall_given_triage: Proportion
    email_type_accuracy: Proportion
    merchant_precision: Proportion
    merchant_recall: Proportion
    missed_merchants: list[str] = Field(default_factory=list)
    spurious_merchants: list[str] = Field(default_factory=list)
    fields: dict[str, FieldScore]
    wrong_examples: list[str] = Field(default_factory=list)
    a3_precision_verdict: str
    a3_recall_verdict: str


def _same_merchant(a: Optional[str], b: Optional[str]) -> bool:
    if not a or not b:
        return False
    ka, kb = merchant_key(a), merchant_key(b)
    return bool(ka and kb) and (ka == kb or ka in kb or kb in ka)


def _eq(field: str, judge_v, pipe_v) -> bool:
    if field == "merchant":
        return _same_merchant(judge_v, pipe_v)
    if field == "amount":
        return abs(float(judge_v) - float(pipe_v)) < 0.01
    if field == "currency":
        return str(judge_v).upper() == str(pipe_v).upper()
    if isinstance(pipe_v, str) and isinstance(judge_v, dt.date):
        return judge_v.isoformat() == pipe_v
    return getattr(judge_v, "value", judge_v) == getattr(pipe_v, "value", pipe_v)


def score(
    traces: list[MessageTrace],
    extractions: list[Extraction],
    records: list[SubscriptionRecord],
    labels: dict[str, JudgeLabel],
) -> Scorecard:
    trace_by_id = {t.message_id: t for t in traces}
    ex_by_id = {e.message_id: e for e in extractions}
    L = [lab for mid, lab in labels.items() if mid in trace_by_id and not trace_by_id[mid].error]

    tp = fp = fn = 0
    triage_pos = triage_hit = 0
    s4_n = s4_hit = 0
    type_n = type_ok = 0
    fields = {f: FieldScore() for f in FIELDS}
    wrong_examples: list[str] = []
    for lab in L:
        t = trace_by_id[lab.message_id]
        ex = ex_by_id.get(lab.message_id)
        pred = bool(t.triage_relevant and ex and ex.is_subscription_related)
        if lab.is_subscription_related:
            triage_pos += 1
            triage_hit += bool(t.triage_relevant)
            if t.triage_relevant:
                s4_n += 1
                s4_hit += bool(ex and ex.is_subscription_related)
        if pred and lab.is_subscription_related:
            tp += 1
            type_n += 1
            type_ok += ex.email_type == lab.email_type
            for f in FIELDS:
                fv = getattr(ex, f)
                jv = getattr(lab, f)
                sc = fields[f]
                if fv.state == FieldState.ESTIMATED:
                    sc.estimated += 1
                    if jv is not None and _eq(f, jv, fv.value):
                        sc.estimated_matches_judge += 1
                elif fv.state == FieldState.CONFIRMED:
                    if jv is None:
                        sc.spurious += 1
                    elif _eq(f, jv, fv.value):
                        sc.correct += 1
                    else:
                        sc.wrong += 1
                        if len(wrong_examples) < 25:
                            wrong_examples.append(f"{lab.message_id} {f}: pipeline={fv.value} judge={jv}")
                elif jv is not None:
                    sc.missed += 1
        elif pred:
            fp += 1
        elif lab.is_subscription_related:
            fn += 1

    # merchant level, restricted to labelled emails
    labelled_ids = {lab.message_id for lab in L}
    judge_merchants: dict[str, set[str]] = {}
    for lab in L:
        if lab.is_subscription_related and lab.merchant:
            judge_merchants.setdefault(merchant_key(lab.merchant) or lab.merchant, set()).add(lab.message_id)
    pipe_records = [r for r in records if labelled_ids & set(r.message_ids)]

    def rec_matches(r: SubscriptionRecord, jkey: str, jids: set[str]) -> bool:
        return _same_merchant(r.merchant.value, jkey) or bool(jids & set(r.message_ids))

    found = [k for k, ids in judge_merchants.items() if any(rec_matches(r, k, ids) for r in pipe_records)]
    good_recs = [r for r in pipe_records if any(rec_matches(r, k, ids) for k, ids in judge_merchants.items())]

    p_email = wilson(tp, tp + fp)
    r_email = wilson(tp, tp + fn)
    p_merch = wilson(len(good_recs), len(pipe_records))
    r_merch = wilson(len(found), len(judge_merchants))
    return Scorecard(
        labelled=len(labels),
        labelled_in_trace=len(L),
        email_precision=p_email,
        email_recall=r_email,
        triage_recall=wilson(triage_hit, triage_pos),
        stage4_recall_given_triage=wilson(s4_hit, s4_n),
        email_type_accuracy=wilson(type_ok, type_n),
        merchant_precision=p_merch,
        merchant_recall=r_merch,
        missed_merchants=sorted(set(judge_merchants) - set(found)),
        spurious_merchants=sorted(r.merchant.value for r in pipe_records if r not in good_recs),
        fields=fields,
        wrong_examples=wrong_examples,
        # A3 is judged at merchant level: that is what a missed alert depends on.
        a3_precision_verdict=verdict(p_merch, PRECISION_TARGET),
        a3_recall_verdict=verdict(r_merch, RECALL_TARGET),
    )


def report(sc: Scorecard, stats: RunStats, judge_name: str) -> str:
    u = stats.usage
    per_k = (lambda x: f"{x / stats.stage1_matches * 1000:.0f}") if stats.stage1_matches else (lambda x: "n/a")
    lines = [
        "# Phase 0 scorecard",
        "",
        f"- Provider: `{stats.provider}`; query set `{stats.query_set_version}`; accounts: {len(stats.accounts)}",
        f"- Reference labels: **{judge_name}** ({sc.labelled_in_trace} labelled emails in this run)",
        "- Recall is measured *given stage 1*: emails Gmail search never matched are invisible to both pipeline and judge.",
        "",
        "## A3 gate (merchant level, Wilson 95% interval)",
        "",
        f"| Metric | Result | Target | Verdict |",
        f"|---|---|---|---|",
        f"| Precision | {sc.merchant_precision.fmt()} | > {PRECISION_TARGET:.0%} | **{sc.a3_precision_verdict}** |",
        f"| Recall | {sc.merchant_recall.fmt()} | > {RECALL_TARGET:.0%} | **{sc.a3_recall_verdict}** |",
        "",
        "## Email level",
        "",
        f"- Precision: {sc.email_precision.fmt()}",
        f"- Recall: {sc.email_recall.fmt()}",
        f"- Triage (stage 3) recall: {sc.triage_recall.fmt()}",
        f"- Stage 4/5 recall given triage pass: {sc.stage4_recall_given_triage.fmt()}",
        f"- Email-type accuracy (true positives): {sc.email_type_accuracy.fmt()}",
        "",
        "## Field accuracy on true positives",
        "",
        "`wrong` = pipeline asserted a confirmed value that differs from the judge (the D5 failure that matters most).",
        "",
        "| Field | correct | wrong | missed | spurious | estimated (matches judge) |",
        "|---|---|---|---|---|---|",
    ]
    for f, s in sc.fields.items():
        lines.append(f"| {f} | {s.correct} | {s.wrong} | {s.missed} | {s.spurious} | {s.estimated} ({s.estimated_matches_judge}) |")
    lines += [
        "",
        "## Funnel and cost (M8) and timing (D29)",
        "",
        f"- Stage 1 matches: {stats.stage1_matches}",
        f"- Triage passed: {stats.triage_passed}",
        f"- Stage 4 model extractions: {stats.stage4_calls} (pre-filter pass rate {stats.prefilter_pass_rate:.1%})" if stats.prefilter_pass_rate is not None else "- Stage 4 model extractions: 0",
        f"- Stage 5 template hits: {stats.stage5_hits}; fallbacks to stage 4: {stats.stage5_fallbacks}; templates learned: {stats.templates_learned}",
        f"- Model calls per 1,000 matches: triage {per_k(u.get('triage_calls', 0))}, extraction {per_k(u.get('extract_calls', 0))}",
        f"- Tokens: {u.get('prompt_tokens', 0)} in / {u.get('completion_tokens', 0)} out; reported cost: {('$%.4f' % u['cost_usd']) if u.get('cost_usd') is not None else 'not reported'}",
        f"- First result: {stats.first_result_seconds}s (target ≤ 30 s); total: {stats.total_seconds}s"
        + (f"; {stats.total_seconds / stats.stage1_matches * 1000:.0f}s per 1,000 matches" if stats.stage1_matches else ""),
        f"- Values dropped by evidence checks: {stats.rejected_values}; attachments skipped (no amount in body): {stats.attachments_skipped}; errors: {stats.errors}",
    ]
    if sc.missed_merchants:
        lines += ["", "## Missed merchants", ""] + [f"- {m}" for m in sc.missed_merchants]
    if sc.spurious_merchants:
        lines += ["", "## Spurious merchants", ""] + [f"- {m}" for m in sc.spurious_merchants]
    if sc.wrong_examples:
        lines += ["", "## Wrong confirmed values (first 25)", ""] + [f"- {w}" for w in sc.wrong_examples]
    return "\n".join(lines) + "\n"

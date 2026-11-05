"""Funnel orchestration: stage 1 -> 3 -> (5 | 4) -> verify -> merge (R4, D24).

Measures what Phase 0 must report (PRD section 13): stage-1 match count, pre-filter
pass rate (M8), first-result time and time to complete (D29), LLM calls/cost.

Bodies live only in memory for the duration of one message (R9).
"""

from __future__ import annotations

import datetime as dt
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Iterable, Optional

from pydantic import BaseModel, Field

from .merge import merge
from .models import EmailMessage, Extraction, FieldState, SubscriptionRecord
from .providers.base import ExtractInput, Provider, TriageInput
from .queries import QUERY_SET_VERSION, build_queries
from .sources import EmailSource
from .templates import SenderTemplate, TemplateStore
from .textutil import truncate_tokens
from .verify import verify


class MessageTrace(BaseModel):
    message_id: str
    account: str
    sender: str
    subject: str
    date: dt.datetime
    triage_relevant: Optional[bool] = None
    stage: Optional[str] = None  # stage4 | stage5 | None (stopped at triage)
    template_fallback: bool = False
    attachment_read: bool = False
    related: Optional[bool] = None
    error: Optional[str] = None
    seconds: float = 0.0


class RunStats(BaseModel):
    query_set_version: str = QUERY_SET_VERSION
    provider: str = ""
    accounts: list[str] = Field(default_factory=list)
    stage1_matches: int = 0
    triage_passed: int = 0
    stage4_calls: int = 0
    stage5_hits: int = 0
    stage5_fallbacks: int = 0
    templates_learned: int = 0
    related_emails: int = 0
    attachments_skipped: int = 0
    rejected_values: int = 0
    errors: int = 0
    first_result_seconds: Optional[float] = None
    total_seconds: float = 0.0
    usage: dict = Field(default_factory=dict)

    @property
    def prefilter_pass_rate(self) -> Optional[float]:
        """M8: fraction of stage-1 matches that reach stage 4 (model extraction)."""
        return self.stage4_calls / self.stage1_matches if self.stage1_matches else None


class RunResult(BaseModel):
    stats: RunStats
    traces: list[MessageTrace]
    extractions: list[Extraction]
    records: list[SubscriptionRecord]


_TEMPLATE_FIELD_ATTR = {
    "merchant": "merchant", "kind": "kind", "billing_period": "billing_period", "amount": "amount",
    "charge_date": "charge_date", "next_charge_date": "next_charge_date", "trial_end_date": "trial_end_date",
    "cancel_path": "cancel_path",
}


def _template_ok(t: SenderTemplate, ex: Extraction) -> bool:
    """R4 correctness rule: every field the template found before must be confirmed now."""
    return all(getattr(ex, _TEMPLATE_FIELD_ATTR[f]).state == FieldState.CONFIRMED for f in t.found_fields)


class Pipeline:
    def __init__(
        self,
        provider: Provider,
        templates: Optional[TemplateStore] = None,
        concurrency: int = 8,
        max_body_tokens: int = 1500,
        on_extraction: Optional[Callable[[Extraction], None]] = None,
    ) -> None:
        self.provider = provider
        self.templates = templates or TemplateStore()
        self.concurrency = concurrency
        self.max_body_tokens = max_body_tokens
        self.on_extraction = on_extraction
        self._lock = threading.Lock()

    def _process(self, src: EmailSource, message_id: str, stats: RunStats, t0: float) -> tuple[MessageTrace, Optional[Extraction]]:
        start = time.monotonic()
        meta = src.metadata(message_id)
        trace = MessageTrace(
            message_id=message_id, account=src.account, sender=meta.from_addr, subject=meta.subject, date=meta.date
        )
        try:
            relevant = self.provider.triage(
                TriageInput(message_id=message_id, sender=meta.from_addr, subject=meta.subject, preview=meta.snippet[:200])
            )
            trace.triage_relevant = relevant
            if not relevant:
                return trace, None
            full: EmailMessage = src.full(meta)
            ex = None
            with self._lock:
                template = self.templates.find(full)
            if template:
                raw = template.apply(full)
                if raw is not None:
                    cand = verify(raw, full, stage="stage5")
                    if _template_ok(template, cand):
                        ex = cand
                        trace.stage = "stage5"
                        with self._lock:
                            template.uses += 1
                if ex is None:
                    trace.template_fallback = True
            if ex is None:
                body = truncate_tokens(full.body_text or "", self.max_body_tokens)
                raw = self.provider.extract(
                    ExtractInput(
                        message_id=full.message_id, sender=full.from_addr, sender_name=full.from_name, subject=full.subject,
                        sent_date=full.date.date().isoformat(), body=body,
                    )
                )
                ex = verify(raw, full, stage="stage4")
                trace.stage = "stage4"
                if ex.attachment_skipped and hasattr(src, "attachment_text"):
                    att = src.attachment_text(full)
                    if att:  # decision #6: read page 1 of the PDF only when the body has no amount
                        full = full.model_copy(update={"body_text": f"{full.body_text}\n\n[Attachment, page 1]\n{att}"})
                        raw = self.provider.extract(ExtractInput(
                            message_id=full.message_id, sender=full.from_addr, sender_name=full.from_name,
                            subject=full.subject, sent_date=full.date.date().isoformat(),
                            body=truncate_tokens(full.body_text or "", self.max_body_tokens)))
                        ex = verify(raw, full, stage="stage4")
                        trace.attachment_read = True
                learned = SenderTemplate.learn(full, ex, raw)
                if learned:
                    with self._lock:
                        self.templates.add(learned)
                        stats.templates_learned += 1
            trace.related = ex.is_subscription_related
            if ex.is_subscription_related:
                with self._lock:
                    if stats.first_result_seconds is None:
                        stats.first_result_seconds = round(time.monotonic() - t0, 2)
                if self.on_extraction:
                    self.on_extraction(ex)
            return trace, ex
        except Exception as e:  # keep going; errors are reported in stats
            trace.error = f"{type(e).__name__}: {e}"[:300]
            return trace, None
        finally:
            trace.seconds = round(time.monotonic() - start, 3)

    def run(
        self,
        sources: Iterable[EmailSource],
        today: Optional[dt.date] = None,
        queries: Optional[list[str]] = None,
        skip_ids: Optional[set[str]] = None,
    ) -> RunResult:
        """``queries`` overrides the stage-1 query set (incremental sync uses an ``after:`` bound);
        ``skip_ids`` are message ids already processed for this user."""
        today = today or dt.date.today()
        queries = queries or build_queries(today)
        skip_ids = skip_ids or set()
        stats = RunStats(provider=self.provider.name)
        traces: list[MessageTrace] = []
        extractions: list[Extraction] = []
        t0 = time.monotonic()
        # Concurrency=1 keeps template learning deterministic (and is what tests use);
        # higher values trade some stage-5 reuse within one run for wall-clock time.
        with ThreadPoolExecutor(max_workers=max(1, self.concurrency)) as pool:
            for src in sources:
                stats.accounts.append(src.account)
                futures = [pool.submit(self._process, src, mid, stats, t0)
                           for mid in src.search(queries) if mid not in skip_ids]
                for fut in futures:  # submission order = newest first
                    trace, ex = fut.result()
                    traces.append(trace)
                    if ex is not None:
                        extractions.append(ex)

        stats.stage1_matches = len(traces)
        stats.triage_passed = sum(1 for t in traces if t.triage_relevant)
        stats.stage4_calls = sum(1 for t in traces if t.stage == "stage4")
        stats.stage5_hits = sum(1 for t in traces if t.stage == "stage5")
        stats.stage5_fallbacks = sum(1 for t in traces if t.template_fallback)
        stats.related_emails = sum(1 for e in extractions if e.is_subscription_related)
        stats.attachments_skipped = sum(1 for e in extractions if e.attachment_skipped)
        stats.rejected_values = sum(len(e.rejected_values) for e in extractions)
        stats.errors = sum(1 for t in traces if t.error)
        stats.total_seconds = round(time.monotonic() - t0, 2)
        stats.usage = self.provider.usage.model_dump()
        return RunResult(stats=stats, traces=traces, extractions=extractions, records=merge(extractions))


def save_run(result: RunResult, run_dir: Path) -> None:
    """Writes extracted fields, evidence snippets and email metadata only - never bodies."""
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "stats.json").write_text(
        json.dumps({**result.stats.model_dump(mode="json"), "prefilter_pass_rate": result.stats.prefilter_pass_rate}, indent=2)
    )
    with (run_dir / "trace.jsonl").open("w") as f:
        for t in result.traces:
            f.write(t.model_dump_json() + "\n")
    with (run_dir / "extractions.jsonl").open("w") as f:
        for e in result.extractions:
            f.write(e.model_dump_json() + "\n")
    (run_dir / "records.json").write_text(json.dumps([r.model_dump(mode="json") for r in result.records], indent=2))


def load_run(run_dir: Path) -> tuple[RunStats, list[MessageTrace], list[Extraction], list[SubscriptionRecord]]:
    stats = RunStats.model_validate(json.loads((run_dir / "stats.json").read_text()))
    traces = [MessageTrace.model_validate_json(l) for l in (run_dir / "trace.jsonl").read_text().splitlines() if l.strip()]
    exs = [Extraction.model_validate_json(l) for l in (run_dir / "extractions.jsonl").read_text().splitlines() if l.strip()]
    recs = [SubscriptionRecord.model_validate(r) for r in json.loads((run_dir / "records.json").read_text())]
    return stats, traces, exs, recs

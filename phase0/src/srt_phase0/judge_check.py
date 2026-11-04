"""Validate judge labels before scoring: coverage, schema, internal consistency."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from .models import JudgeLabel

_FIELDS = ("merchant", "kind", "billing_period", "amount", "currency", "charge_date", "next_charge_date", "trial_end_date")


def check_labels(judge_dir: Path) -> tuple[list[str], int, int]:
    """Return (problems, exported_count, labelled_count)."""
    exported: dict[str, dict] = {}
    for p in sorted(judge_dir.glob("batch-*.jsonl")):
        for line in p.read_text().splitlines():
            if line.strip():
                d = json.loads(line)
                exported[d["message_id"]] = d
    problems: list[str] = []
    labels: dict[str, JudgeLabel] = {}
    lp = judge_dir / "labels.jsonl"
    if not lp.exists():
        return [f"{lp} does not exist"], len(exported), 0
    for n, line in enumerate(lp.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            lab = JudgeLabel.model_validate_json(line)
        except ValidationError as e:
            problems.append(f"labels.jsonl line {n}: invalid — {e.errors()[0]['loc']}: {e.errors()[0]['msg']}")
            continue
        labels[lab.message_id] = lab

    for mid in exported.keys() - labels.keys():
        problems.append(f"{mid}: exported but not labelled")
    for mid in labels.keys() - exported.keys():
        problems.append(f"{mid}: labelled but not in any exported batch")
    for mid, lab in labels.items():
        email = exported.get(mid)
        if not lab.is_subscription_related:
            filled = [f for f in _FIELDS if getattr(lab, f) is not None]
            if filled:
                problems.append(f"{mid}: not subscription-related but has values for {', '.join(filled)}")
            continue
        if not lab.merchant:
            problems.append(f"{mid}: subscription-related but merchant is empty")
        if lab.amount is not None and lab.amount < 0:
            problems.append(f"{mid}: negative amount")
        if email and lab.amount is not None:
            digits = f"{lab.amount:,.2f}".rstrip("0").rstrip(".").replace(",", "")
            body = (email.get("body", "") + email.get("subject", "")).replace(",", "")
            if digits not in body:
                problems.append(f"{mid}: amount {lab.amount} does not appear in the email text (check for a typo)")
    return problems, len(exported), len(labels)

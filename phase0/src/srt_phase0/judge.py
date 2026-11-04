"""Judge workflow: export blind batches, collect reference labels.

The judge (Claude in the build session, by the founder's decision) labels emails
WITHOUT seeing the pipeline's output, to avoid anchoring. Batches deliberately
mix triage-passed and triage-rejected emails in random order so triage recall
can be measured.

Privacy: batches contain email bodies. This is a Phase 0-only exception to R9
("raw bodies never persisted"); files live under the gitignored data/ directory
and must be removed with ``srt-phase0 purge`` after scoring.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from .models import JudgeLabel
from .pipeline import MessageTrace
from .sources import EmailSource

BATCH_SIZE = 25
MAX_BODY_CHARS = 12000

RUBRIC = """# Judge rubric (blind labelling)

Label each email in batch-*.jsonl. Write one JSON object per line to labels.jsonl:

{"message_id": "...", "is_subscription_related": true|false, "email_type": "...",
 "merchant": "...", "kind": "trial|subscription|renewal", "billing_period": "monthly|annual|other|unknown",
 "amount": 199.0, "currency": "INR", "charge_date": "YYYY-MM-DD",
 "next_charge_date": "YYYY-MM-DD", "trial_end_date": "YYYY-MM-DD", "notes": "..."}

Definitions (same as the extraction prompt, so judge and pipeline answer one question):
- is_subscription_related: evidence of a RECURRING charge or a trial that may convert:
  trial sign-ups, recurring receipts/invoices, renewal reminders, cancellation
  confirmations, price-change notices, non-subscription renewals (domains,
  insurance, annual fees). One-off purchases, newsletters, marketing, OTPs: false.
- email_type: trial_signup | receipt | renewal_reminder | cancellation_confirmation |
  price_change | winback_offer | other. A "come back" discount is winback_offer.
- Field values ONLY if the email states them. Use null otherwise. Do not compute dates.
  next_charge_date and trial_end_date are stated dates only (no derivation).
- charge_date: the payment date the email states (null if only implied by sending).
- currency: ISO code only if a symbol/code is shown.
- merchant: short display name of the company charging the user.
If is_subscription_related is false, leave every field null.
"""


def export(
    traces: list[MessageTrace],
    sources: dict[str, EmailSource],
    out_dir: Path,
    n_passed: int = 300,
    n_rejected: int = 100,
    seed: int = 7,
) -> list[Path]:
    rng = random.Random(seed)
    ok = [t for t in traces if not t.error]
    passed = [t for t in ok if t.triage_relevant]
    rejected = [t for t in ok if t.triage_relevant is False]
    sample = rng.sample(passed, min(n_passed, len(passed))) + rng.sample(rejected, min(n_rejected, len(rejected)))
    rng.shuffle(sample)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "RUBRIC.md").write_text(RUBRIC)
    paths = []
    for i in range(0, len(sample), BATCH_SIZE):
        p = out_dir / f"batch-{i // BATCH_SIZE + 1:03d}.jsonl"
        with p.open("w") as f:
            for t in sample[i : i + BATCH_SIZE]:
                src = sources[t.account]
                full = src.full(src.metadata(t.message_id))
                f.write(
                    json.dumps(
                        {
                            "message_id": t.message_id,
                            "from": f"{full.from_name} <{full.from_addr}>",
                            "subject": full.subject,
                            "date": full.date.isoformat(),
                            "attachments": full.attachment_names,
                            "body": (full.body_text or "")[:MAX_BODY_CHARS],
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        paths.append(p)
    return paths


def load_labels(path: Path) -> dict[str, JudgeLabel]:
    out: dict[str, JudgeLabel] = {}
    for line in path.read_text().splitlines():
        if line.strip():
            lab = JudgeLabel.model_validate_json(line)
            out[lab.message_id] = lab  # later lines override earlier ones (corrections)
    return out


def labels_from_fixtures(fixtures: Path, out: Path) -> int:
    """Synthetic fixtures carry their own truth; write it as a labels file."""
    n = 0
    with out.open("w") as f:
        for line in fixtures.read_text().splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            lab = JudgeLabel(message_id=d["message_id"], judge="fixture-truth", **d["truth"])
            f.write(lab.model_dump_json() + "\n")
            n += 1
    return n

"""Replay provider: answers written in advance by Claude in the build session.

Development mode chosen by the founder: Claude (in the Claude Code session)
reads the emails via the Gmail connector and writes, per message, the answers a
model would give for stage 3 and stage 4 into an answers file. The pipeline
then treats them exactly like model output: same evidence verification,
derivation, templates and merge.

answers.jsonl, one line per email:
  {"message_id": "...", "triage": true, "extraction": { ...RawExtraction... }}
  {"message_id": "...", "triage": false}

A message with no answer raises, so it shows up as an error in the run trace
instead of being silently treated as "not a subscription".
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from .base import ExtractInput, RawExtraction, TriageInput, UsageStats


class MissingAnswer(KeyError):
    pass


class ReplayProvider:
    name = "replay-claude"

    def __init__(self, path: Optional[Path] = None) -> None:
        path = path or (Path(os.environ["SRT_ANSWERS"]) if os.environ.get("SRT_ANSWERS") else None)
        if not path or not Path(path).exists():
            raise FileNotFoundError("Answers file not found: pass --answers or set SRT_ANSWERS")
        self.usage = UsageStats()
        self.triage_answers: dict[str, bool] = {}
        self.extractions: dict[str, RawExtraction] = {}
        for n, line in enumerate(Path(path).read_text().splitlines(), 1):
            if not line.strip():
                continue
            d = json.loads(line)
            mid = d["message_id"]
            self.triage_answers[mid] = bool(d["triage"])
            if d.get("extraction") is not None:
                self.extractions[mid] = RawExtraction.model_validate(d["extraction"])

    def triage(self, item: TriageInput) -> bool:
        self.usage.triage_calls += 1
        if item.message_id not in self.triage_answers:
            raise MissingAnswer(f"no triage answer for {item.message_id}")
        return self.triage_answers[item.message_id]

    def extract(self, item: ExtractInput) -> RawExtraction:
        self.usage.extract_calls += 1
        if item.message_id not in self.extractions:
            raise MissingAnswer(f"no extraction answer for {item.message_id}")
        return self.extractions[item.message_id]

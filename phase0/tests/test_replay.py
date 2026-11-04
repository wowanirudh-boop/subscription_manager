"""Claude-as-the-model dev mode: answers file -> same verification and merge as a real model."""

import datetime as dt
import json
from pathlib import Path

import pytest
from conftest import A, B

from srt_phase0.models import Lifecycle
from srt_phase0.pipeline import Pipeline
from srt_phase0.providers.base import TriageInput
from srt_phase0.providers.replay import MissingAnswer, ReplayProvider
from srt_phase0.sources import FixtureSource

ANSWERS = Path(__file__).resolve().parents[1] / "fixtures" / "claude_answers_synthetic.jsonl"


def test_replay_run_on_synthetic(fixtures_path):
    res = Pipeline(ReplayProvider(ANSWERS), concurrency=1).run(
        [FixtureSource(fixtures_path, A), FixtureSource(fixtures_path, B)], today=dt.date(2026, 11, 4))
    assert res.stats.errors == 0
    by = {r.merchant.value: r for r in res.records}
    assert "Promo Deals" not in by and "TrustedBank" not in by  # injection email rejected at triage
    assert by["GymPass"].lifecycle_state == Lifecycle.CANCELLED_CONFIRMED
    assert by["PixelForge"].lifecycle_state == Lifecycle.UNKNOWN_DATE  # no stated trial length
    assert by["TuneBox"].trial_end_date.value == dt.date(2026, 11, 19)
    assert by["SafeLife Insurance"].next_charge_date.value == dt.date(2026, 11, 28)


def test_missing_answer_is_an_error_not_a_negative(tmp_path):
    p = tmp_path / "a.jsonl"
    p.write_text(json.dumps({"message_id": "x", "triage": False}) + "\n")
    with pytest.raises(MissingAnswer):
        ReplayProvider(p).triage(TriageInput(message_id="y", sender="s", subject="t", preview="p"))

"""End-to-end on synthetic fixtures with the fake provider, plus privacy checks."""

import datetime as dt

from conftest import A, B

from srt_phase0.judge import export, labels_from_fixtures, load_labels
from srt_phase0.models import Lifecycle
from srt_phase0.pipeline import Pipeline, load_run, save_run
from srt_phase0.providers import FakeProvider
from srt_phase0.score import score
from srt_phase0.sources import FixtureSource


def _run(fixtures_path):
    sources = [FixtureSource(fixtures_path, A), FixtureSource(fixtures_path, B)]
    return Pipeline(FakeProvider(), concurrency=1).run(sources, today=dt.date(2026, 11, 4)), sources


def test_funnel_counts_and_stage5_reuse(fixtures_path):
    res, _ = _run(fixtures_path)
    s = res.stats
    assert s.stage1_matches == 22  # mh-1 is a deliberate stage-1 miss
    assert "mh-1" not in {t.message_id for t in res.traces}
    assert s.stage5_hits >= 2  # StreamFlix Sep/Aug reuse the October template
    assert s.stage4_calls + s.stage5_hits == s.triage_passed - s.errors
    assert s.first_result_seconds is not None


def test_newest_first_within_account(fixtures_path):
    res, _ = _run(fixtures_path)
    dates = [t.date for t in res.traces if t.account == A]
    assert dates == sorted(dates, reverse=True)


def test_records(fixtures_path):
    res, _ = _run(fixtures_path)
    by = {r.merchant.value: r for r in res.records}
    assert by["VidMax"].source_accounts == [A, B]
    assert by["GymPass"].lifecycle_state == Lifecycle.CANCELLED_CONFIRMED
    assert by["StreamFlix"].next_charge_date.value == dt.date(2026, 11, 5)


def test_saved_run_contains_no_bodies(tmp_path, fixtures_path):
    res, _ = _run(fixtures_path)
    save_run(res, tmp_path / "run")
    blob = "".join(p.read_text() for p in (tmp_path / "run").iterdir())
    # Lines that are only in bodies and never used as evidence:
    assert "Enjoy all Pro features" not in blob
    assert "Hi Anirudh" not in blob
    assert "one time password" not in blob.lower()
    stats, traces, exs, recs = load_run(tmp_path / "run")
    assert len(traces) == len(res.traces) and len(recs) == len(res.records)


def test_judge_export_is_blind_and_scoring_runs(tmp_path, fixtures_path):
    res, sources = _run(fixtures_path)
    paths = export(res.traces, {s.account: s for s in sources}, tmp_path / "judge", n_passed=100, n_rejected=100)
    rows = [l for p in paths for l in p.read_text().splitlines()]
    assert len(rows) == 22
    assert "triage" not in rows[0] and "stage" not in rows[0]  # no pipeline output leaks to the judge
    labels_path = tmp_path / "labels.jsonl"
    labels_from_fixtures(fixtures_path, labels_path)
    sc = score(res.traces, res.extractions, res.records, load_labels(labels_path))
    assert sc.labelled == 23 and sc.labelled_in_trace == 22
    assert sc.email_precision.n > 0 and sc.merchant_recall.n > 0

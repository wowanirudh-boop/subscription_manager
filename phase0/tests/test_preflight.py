import json

import httpx

from srt_phase0.judge_check import check_labels
from srt_phase0.preflight import check_openrouter_models, run_preflight

MODELS = {"data": [
    {"id": "small/model", "supported_parameters": ["response_format", "structured_outputs"], "pricing": {"prompt": "0.0000001", "completion": "0.0000004"}},
    {"id": "no-schema/model", "supported_parameters": ["temperature"]},
]}


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_network_block_is_reported_with_fix():
    def handler(req):
        raise httpx.ConnectError("connect_rejected")
    checks = check_openrouter_models(_client(handler))
    assert checks[0].status == "FAIL" and "allowed domains" in checks[0].detail


def test_model_capability(monkeypatch):
    monkeypatch.setenv("OPENROUTER_TRIAGE_MODEL", "small/model")
    monkeypatch.setenv("OPENROUTER_EXTRACT_MODEL", "no-schema/model")
    checks = {c.name: c for c in check_openrouter_models(_client(lambda r: httpx.Response(200, json=MODELS)))}
    assert checks["OPENROUTER_TRIAGE_MODEL"].status == "PASS"
    assert checks["OPENROUTER_EXTRACT_MODEL"].status == "FAIL"


def test_missing_config_fails(monkeypatch, tmp_path):
    for k in ("OPENROUTER_API_KEY", "OPENROUTER_TRIAGE_MODEL", "OPENROUTER_EXTRACT_MODEL",
              "GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_OAUTH_CLIENT_SECRETS"):
        monkeypatch.delenv(k, raising=False)
    checks = {c.name: c for c in run_preflight([], tmp_path, _client(lambda r: httpx.Response(200, json=MODELS)))}
    assert checks["OpenRouter config"].status == "FAIL"
    assert checks["Google OAuth client"].status == "FAIL"
    assert checks["OpenRouter key valid"].status == "SKIP"


def _write(d, batch, labels):
    d.mkdir(parents=True, exist_ok=True)
    (d / "batch-001.jsonl").write_text("".join(json.dumps(b) + "\n" for b in batch))
    (d / "labels.jsonl").write_text("".join(json.dumps(l) + "\n" for l in labels))


def test_judge_check_finds_gaps_and_inconsistencies(tmp_path):
    batch = [{"message_id": "a", "subject": "Receipt", "body": "We charged ₹1,299 today."},
             {"message_id": "b", "subject": "Hi", "body": "Newsletter"},
             {"message_id": "c", "subject": "x", "body": "y"}]
    labels = [
        {"message_id": "a", "is_subscription_related": True, "merchant": "X", "amount": 1300},
        {"message_id": "b", "is_subscription_related": False, "amount": 5},
    ]
    _write(tmp_path, batch, labels)
    problems, n_exp, n_lab = check_labels(tmp_path)
    text = "\n".join(problems)
    assert (n_exp, n_lab) == (3, 2)
    assert "c: exported but not labelled" in text
    assert "b: not subscription-related but has values for amount" in text
    assert "a: amount 1300.0 does not appear" in text


def test_judge_check_clean(tmp_path):
    _write(tmp_path, [{"message_id": "a", "subject": "Receipt", "body": "We charged ₹1,299 today."}],
           [{"message_id": "a", "is_subscription_related": True, "merchant": "X", "amount": 1299}])
    problems, _, _ = check_labels(tmp_path)
    assert problems == []

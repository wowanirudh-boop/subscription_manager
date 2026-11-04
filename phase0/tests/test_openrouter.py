"""OpenRouter request shape, data-handling flags, retries - no network."""

import json

import httpx
import pytest

from srt_phase0.providers.base import ExtractInput, TriageInput
from srt_phase0.providers.openrouter import OpenRouterError, OpenRouterProvider


def _provider(handler, **kw):
    return OpenRouterProvider(api_key="k", triage_model="t-model", extract_model="x-model",
                              client=httpx.Client(transport=httpx.MockTransport(handler)), **kw)


def _ok(content: dict, usage=None):
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(content)}}],
                                     "usage": usage or {"prompt_tokens": 10, "completion_tokens": 2, "cost": 0.0001}})


def test_triage_request_shape():
    seen = {}

    def handler(req: httpx.Request):
        seen["body"] = json.loads(req.content)
        seen["auth"] = req.headers["authorization"]
        return _ok({"relevant": True})

    p = _provider(handler)
    assert p.triage(TriageInput(sender="a@b", subject="Receipt", preview="We charged"))
    b = seen["body"]
    assert seen["auth"] == "Bearer k"
    assert b["model"] == "t-model" and b["temperature"] == 0
    assert b["response_format"]["type"] == "json_schema" and b["response_format"]["json_schema"]["strict"] is True
    assert b["provider"]["data_collection"] == "deny" and b["provider"]["zdr"] is True
    assert b["provider"]["require_parameters"] is True
    # untrusted content is fenced, and the system prompt says to ignore instructions in it
    assert "<<<EMAIL-" in b["messages"][1]["content"]
    assert "untrusted" in b["messages"][0]["content"]
    assert p.usage.cost_usd == pytest.approx(0.0001)


def test_extract_parses_schema_output():
    content = {
        "is_subscription_related": True, "email_type": "receipt",
        "merchant": {"value": "X", "quote": None}, "kind": {"value": "subscription", "quote": "q"},
        "billing_period": {"value": "monthly", "quote": "q", "period_months": None},
        "amount": {"value": 5.0, "currency": "USD", "quote": "q"},
        "charge_date": {"value": None, "quote": None}, "next_charge_date": {"value": None, "quote": None},
        "trial_end_date": {"value": None, "quote": None}, "trial_length_days": {"value": None, "quote": None},
        "cancel_path": {"value": None, "quote": None},
    }
    p = _provider(lambda req: _ok(content))
    out = p.extract(ExtractInput(sender="a@b", sender_name="X", subject="s", sent_date="2026-01-01", body="b"))
    assert out.amount.value == 5.0 and out.email_type.value == "receipt"


def test_retries_on_429_then_succeeds(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(429, text="slow down") if calls["n"] < 3 else _ok({"relevant": False})

    assert _provider(handler).triage(TriageInput(sender="a", subject="b", preview="c")) is False
    assert calls["n"] == 3


def test_does_not_retry_400(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(400, text="bad model")

    with pytest.raises(OpenRouterError):
        _provider(handler).triage(TriageInput(sender="a", subject="b", preview="c"))
    assert calls["n"] == 1


def test_missing_config_is_explicit(monkeypatch):
    for k in ("OPENROUTER_API_KEY", "OPENROUTER_TRIAGE_MODEL", "OPENROUTER_EXTRACT_MODEL"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(OpenRouterError, match="OPENROUTER_API_KEY"):
        OpenRouterProvider()

"""OpenRouter provider (OpenAI-compatible chat completions API).

Configuration (environment):
  OPENROUTER_API_KEY        required
  OPENROUTER_TRIAGE_MODEL   required, e.g. a small/cheap model for stage 3
  OPENROUTER_EXTRACT_MODEL  required, model for stage 4 (must support structured output)
  OPENROUTER_ZDR            "1" (default) to request zero-data-retention endpoints only
  OPENROUTER_BASE_URL       optional, default https://openrouter.ai/api/v1

Data-handling routing (R10): every request sets provider.data_collection = "deny"
(route only to upstream providers that do not store/train on prompts) and, by
default, provider.zdr = true. These parameter names are from OpenRouter's
provider-routing docs as I understand them; confirm against the current docs
before relying on them for the R10 requirement. require_parameters = true makes
OpenRouter refuse providers that cannot honour the JSON schema.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Optional

import httpx

from .. import prompts
from .base import ExtractInput, RawExtraction, TriageInput, UsageStats


class OpenRouterError(RuntimeError):
    pass


class OpenRouterProvider:
    name = "openrouter"

    def __init__(
        self,
        api_key: Optional[str] = None,
        triage_model: Optional[str] = None,
        extract_model: Optional[str] = None,
        base_url: Optional[str] = None,
        zdr: Optional[bool] = None,
        timeout: float = 60.0,
        max_retries: int = 4,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        self.triage_model = triage_model or os.environ.get("OPENROUTER_TRIAGE_MODEL")
        self.extract_model = extract_model or os.environ.get("OPENROUTER_EXTRACT_MODEL")
        missing = [
            n
            for n, v in [
                ("OPENROUTER_API_KEY", self.api_key),
                ("OPENROUTER_TRIAGE_MODEL", self.triage_model),
                ("OPENROUTER_EXTRACT_MODEL", self.extract_model),
            ]
            if not v
        ]
        if missing:
            raise OpenRouterError(f"Missing configuration: {', '.join(missing)}")
        self.base_url = (base_url or os.environ.get("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")
        self.zdr = zdr if zdr is not None else os.environ.get("OPENROUTER_ZDR", "1") == "1"
        self.max_retries = max_retries
        self.client = client or httpx.Client(timeout=timeout)
        self.usage = UsageStats()
        self._usage_lock = threading.Lock()  # the pipeline calls providers from several threads

    # -- transport ---------------------------------------------------------------

    def _call(self, model: str, system: str, user: str, schema_name: str, schema: dict) -> dict[str, Any]:
        provider_prefs: dict[str, Any] = {"data_collection": "deny", "require_parameters": True}
        if self.zdr:
            provider_prefs["zdr"] = True
        body = {
            "model": model,
            "temperature": 0,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            },
            "provider": provider_prefs,
            "usage": {"include": True},
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "X-Title": "srt-phase0"}
        delay = 2.0
        last: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                r = self.client.post(f"{self.base_url}/chat/completions", json=body, headers=headers)
                if r.status_code in (429, 500, 502, 503, 504):
                    raise OpenRouterError(f"HTTP {r.status_code}: {r.text[:300]}")
                if r.status_code >= 400:
                    # Not retryable (bad model id, unsupported parameter, auth).
                    raise OpenRouterError(f"HTTP {r.status_code}: {r.text[:500]}")
                data = r.json()
                self._record_usage(data.get("usage") or {})
                content = data["choices"][0]["message"]["content"]
                return json.loads(content)
            except (httpx.TransportError, OpenRouterError, json.JSONDecodeError, KeyError) as e:
                last = e
                retryable = not (isinstance(e, OpenRouterError) and "HTTP 4" in str(e) and "HTTP 429" not in str(e))
                if not retryable or attempt == self.max_retries:
                    break
                time.sleep(delay)
                delay *= 2
        raise OpenRouterError(f"OpenRouter call failed: {last}")

    def _record_usage(self, usage: dict) -> None:
        with self._usage_lock:
            self._add_usage(usage)

    def _add_usage(self, usage: dict) -> None:
        self.usage.prompt_tokens += int(usage.get("prompt_tokens") or 0)
        self.usage.completion_tokens += int(usage.get("completion_tokens") or 0)
        if usage.get("cost") is not None:
            self.usage.cost_usd = (self.usage.cost_usd or 0.0) + float(usage["cost"])

    # -- Provider protocol ----------------------------------------------------------

    def triage(self, item: TriageInput) -> bool:
        with self._usage_lock:
            self.usage.triage_calls += 1
        out = self._call(self.triage_model, prompts.TRIAGE_SYSTEM, prompts.triage_user(item), "triage", prompts.TRIAGE_SCHEMA)
        return bool(out.get("relevant"))

    def extract(self, item: ExtractInput) -> RawExtraction:
        with self._usage_lock:
            self.usage.extract_calls += 1
        out = self._call(
            self.extract_model, prompts.EXTRACT_SYSTEM, prompts.extract_user(item), "extraction", prompts.EXTRACT_SCHEMA
        )
        return RawExtraction.model_validate(out)

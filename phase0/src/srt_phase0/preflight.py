"""Preflight for a real-inbox run: configuration, network, model capability, Gmail tokens.

Every check prints PASS / FAIL / SKIP with the action that fixes a failure, so a
real run is never started against a half-configured environment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import httpx

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"


@dataclass
class Check:
    name: str
    status: str  # PASS | FAIL | SKIP
    detail: str


def _env(name: str) -> Optional[str]:
    v = os.environ.get(name)
    return v.strip() if v and v.strip() else None


def check_env(prefix_names: list[str], label: str, fix: str) -> Check:
    missing = [n for n in prefix_names if not _env(n)]
    if missing:
        return Check(label, "FAIL", f"missing {', '.join(missing)} — {fix}")
    return Check(label, "PASS", "all set")


def check_openrouter_models(client: httpx.Client) -> list[Check]:
    out: list[Check] = []
    try:
        r = client.get(OPENROUTER_MODELS_URL, timeout=20)
        r.raise_for_status()
        models = {m["id"]: m for m in r.json().get("data", [])}
        out.append(Check("openrouter.ai reachable", "PASS", f"{len(models)} models listed"))
    except Exception as e:  # network policy block shows up here
        out.append(Check(
            "openrouter.ai reachable", "FAIL",
            f"{type(e).__name__}: {str(e)[:120]} — add openrouter.ai to the environment's allowed domains "
            "(environment menu in the session title bar → Edit → Network access)",
        ))
        return out
    for var in ("OPENROUTER_TRIAGE_MODEL", "OPENROUTER_EXTRACT_MODEL"):
        mid = _env(var)
        if not mid:
            out.append(Check(var, "SKIP", "not set"))
            continue
        m = models.get(mid)
        if not m:
            out.append(Check(var, "FAIL", f"model id {mid!r} not found on OpenRouter"))
            continue
        params = set(m.get("supported_parameters") or [])
        if params and not ({"structured_outputs", "response_format"} & params):
            out.append(Check(var, "FAIL", f"{mid} does not list structured_outputs/response_format support"))
        else:
            pricing = m.get("pricing") or {}
            out.append(Check(var, "PASS", f"{mid} (prompt ${pricing.get('prompt', '?')}/token, completion ${pricing.get('completion', '?')}/token)"))
    return out


def check_openrouter_key(client: httpx.Client) -> Check:
    key = _env("OPENROUTER_API_KEY")
    if not key:
        return Check("OpenRouter key valid", "SKIP", "OPENROUTER_API_KEY not set")
    try:
        r = client.get("https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {key}"}, timeout=20)
        if r.status_code == 200:
            return Check("OpenRouter key valid", "PASS", "key accepted")
        return Check("OpenRouter key valid", "FAIL", f"HTTP {r.status_code} — check the key")
    except Exception as e:
        return Check("OpenRouter key valid", "FAIL", f"{type(e).__name__}: {str(e)[:120]}")


def check_gmail(accounts: list[str], auth_dir: Path, loader: Optional[Callable] = None) -> list[Check]:
    from . import auth

    loader = loader or auth.load
    out = []
    for a in accounts:
        try:
            creds = loader(a, auth_dir)
            from googleapiclient.discovery import build

            p = build("gmail", "v1", credentials=creds, cache_discovery=False).users().getProfile(userId="me").execute()
            out.append(Check(f"Gmail {a}", "PASS", f"{p.get('messagesTotal', '?')} messages in mailbox"))
        except SystemExit as e:
            out.append(Check(f"Gmail {a}", "FAIL", str(e)))
        except Exception as e:
            out.append(Check(f"Gmail {a}", "FAIL",
                             f"{type(e).__name__}: {str(e)[:120]} — re-run `srt-phase0 auth start/finish` (Testing-mode tokens expire)"))
    return out


def run_preflight(accounts: list[str], auth_dir: Path, client: Optional[httpx.Client] = None) -> list[Check]:
    client = client or httpx.Client()
    checks = [
        check_env(["OPENROUTER_API_KEY", "OPENROUTER_TRIAGE_MODEL", "OPENROUTER_EXTRACT_MODEL"], "OpenRouter config",
                  "add them in the environment settings, then start a new session"),
        check_env(["GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET"], "Google OAuth client",
                  "see phase0/docs/gmail-oauth-setup.md") if not _env("GOOGLE_OAUTH_CLIENT_SECRETS")
        else Check("Google OAuth client", "PASS", "client secrets file configured"),
    ]
    checks += check_openrouter_models(client)
    checks.append(check_openrouter_key(client))
    if accounts:
        checks += check_gmail(accounts, auth_dir)
    else:
        checks.append(Check("Gmail accounts", "SKIP", "pass --accounts to test tokens"))
    return checks

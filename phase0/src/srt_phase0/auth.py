"""Gmail OAuth for a headless container (two-step loopback flow).

1. ``start``: prints a Google consent URL (gmail.readonly only, D8). The user
   opens it on any device and approves. Google redirects to http://localhost:8765/...
   which fails to load (nothing listens there) - that is expected.
2. ``finish``: the user pastes that full localhost URL; we exchange the code
   (PKCE-protected) for tokens.

Partial grants are rejected (flow sign-off #8 proposal: partial grant = no grant).
Tokens are stored under data/auth with 0600 permissions. NOTE: R10 requires
KMS/HSM-backed encryption at rest in production; Phase 0 uses file permissions
only, on a single-user container.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx

from .sources import GMAIL_SCOPE

REDIRECT_URI = "http://localhost:8765/"


def _client_config() -> dict:
    path = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRETS")
    if path:
        return json.loads(Path(path).read_text())
    cid, secret = os.environ.get("GOOGLE_OAUTH_CLIENT_ID"), os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
    if not (cid and secret):
        raise SystemExit(
            "Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET (or GOOGLE_OAUTH_CLIENT_SECRETS=path/to/client_secret.json). "
            "See phase0/docs/gmail-oauth-setup.md."
        )
    return {
        "installed": {
            "client_id": cid,
            "client_secret": secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }


def _flow(state: str | None = None):
    from google_auth_oauthlib.flow import Flow

    return Flow.from_client_config(_client_config(), scopes=[GMAIL_SCOPE], redirect_uri=REDIRECT_URI, state=state)


def _safe(account: str) -> str:
    return account.replace("@", "_at_").replace("/", "_")


def _write_private(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(data)


def start(account: str, auth_dir: Path) -> str:
    flow = _flow()
    flow.autogenerate_code_verifier = True
    url, state = flow.authorization_url(access_type="offline", prompt="consent", login_hint=account)
    _write_private(auth_dir / f"pending-{_safe(account)}.json", json.dumps({"state": state, "verifier": flow.code_verifier}))
    return url


def finish(account: str, redirect_url: str, auth_dir: Path) -> str:
    pending_path = auth_dir / f"pending-{_safe(account)}.json"
    pending = json.loads(pending_path.read_text())
    flow = _flow(state=pending["state"])
    flow.code_verifier = pending["verifier"]
    # The loopback redirect is plain http://localhost (allowed for installed apps);
    # the token exchange itself goes over HTTPS.
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"  # we check scopes ourselves below
    try:
        flow.fetch_token(authorization_response=redirect_url.strip())
    finally:
        os.environ.pop("OAUTHLIB_INSECURE_TRANSPORT", None)
    creds = flow.credentials
    granted = set(creds.granted_scopes or flow.oauth2session.token.get("scope", "").split() or [])
    if granted and GMAIL_SCOPE not in granted:
        revoke_token(creds.token)
        raise SystemExit("Gmail read access was not granted (partial grant treated as no grant). Nothing was stored.")

    from googleapiclient.discovery import build

    profile = build("gmail", "v1", credentials=creds, cache_discovery=False).users().getProfile(userId="me").execute()
    if profile["emailAddress"].lower() != account.lower():
        revoke_token(creds.token)
        raise SystemExit(f"Signed in as {profile['emailAddress']}, expected {account}. Token revoked; nothing stored.")
    _write_private(auth_dir / f"token-{_safe(account)}.json", creds.to_json())
    pending_path.unlink(missing_ok=True)
    return profile["emailAddress"]


def load(account: str, auth_dir: Path):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    path = auth_dir / f"token-{_safe(account)}.json"
    if not path.exists():
        raise SystemExit(f"No token for {account}. Run: srt-phase0 auth start --account {account}")
    creds = Credentials.from_authorized_user_file(str(path), [GMAIL_SCOPE])
    if not creds.valid:
        creds.refresh(Request())
        _write_private(path, creds.to_json())
    return creds


def revoke_token(token: str) -> bool:
    r = httpx.post("https://oauth2.googleapis.com/revoke", params={"token": token}, timeout=30)
    return r.status_code == 200


def disconnect(account: str, auth_dir: Path) -> bool:
    """R1: revoke the token and delete it."""
    path = auth_dir / f"token-{_safe(account)}.json"
    if not path.exists():
        return False
    data = json.loads(path.read_text())
    ok = revoke_token(data.get("refresh_token") or data.get("token"))
    path.unlink()
    return ok

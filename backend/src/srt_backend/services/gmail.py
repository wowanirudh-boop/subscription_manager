"""Google side: OAuth code exchange (D8, flow #8), Gmail sources, push watch (R3), revoke (R1)."""

from __future__ import annotations

import datetime as dt
import json
from typing import Protocol

import httpx

from srt_phase0.sources import GMAIL_SCOPE, EmailSource, GmailSource

from ..config import settings
from ..db import GmailAccount
from ..security import cipher

TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"


class PartialGrant(Exception):
    pass


class GmailGateway(Protocol):
    def exchange_code(self, code: str) -> dict: ...  # {"email": str, "token": dict}
    def source_for(self, account: GmailAccount) -> EmailSource: ...
    def start_watch(self, account: GmailAccount) -> dict: ...  # {"historyId": str, "expiration": ms}
    def revoke(self, account: GmailAccount) -> bool: ...


def store_token(account: GmailAccount, token: dict) -> None:
    account.token_ciphertext = cipher().encrypt(json.dumps(token).encode())


def load_token(account: GmailAccount) -> dict:
    return json.loads(cipher().decrypt(account.token_ciphertext))


class GoogleGateway:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or httpx.Client(timeout=30)

    def exchange_code(self, code: str) -> dict:
        s = settings()
        # Server auth codes from the native Google Sign-In SDKs are exchanged with an empty redirect_uri.
        r = self.client.post(TOKEN_URL, data={"code": code, "client_id": s.google_client_id,
                                              "client_secret": s.google_client_secret, "grant_type": "authorization_code",
                                              "redirect_uri": ""})
        r.raise_for_status()
        tok = r.json()
        if GMAIL_SCOPE not in tok.get("scope", "").split():
            self.client.post(REVOKE_URL, params={"token": tok.get("access_token", "")})
            raise PartialGrant("Gmail read access was not granted")  # flow #8: partial grant = no grant
        from google.oauth2 import id_token as gid
        from google.auth.transport import requests as greq

        info = gid.verify_oauth2_token(tok["id_token"], greq.Request(), s.google_client_id)
        token = {"token": tok["access_token"], "refresh_token": tok.get("refresh_token"), "token_uri": TOKEN_URL,
                 "client_id": s.google_client_id, "client_secret": s.google_client_secret, "scopes": [GMAIL_SCOPE]}
        return {"email": info["email"].lower(), "token": token}

    def _creds(self, account: GmailAccount):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        creds = Credentials.from_authorized_user_info(load_token(account), [GMAIL_SCOPE])
        if not creds.valid:
            creds.refresh(Request())
            store_token(account, json.loads(creds.to_json()))
        return creds

    def source_for(self, account: GmailAccount) -> EmailSource:
        return GmailSource(self._creds(account), account.email)

    def start_watch(self, account: GmailAccount) -> dict:
        from googleapiclient.discovery import build

        svc = build("gmail", "v1", credentials=self._creds(account), cache_discovery=False)
        return svc.users().watch(userId="me", body={"topicName": settings().pubsub_topic}).execute()

    def revoke(self, account: GmailAccount) -> bool:
        tok = load_token(account)
        r = self.client.post(REVOKE_URL, params={"token": tok.get("refresh_token") or tok.get("token")})
        return r.status_code == 200


def watch_due(account: GmailAccount, now: dt.datetime) -> bool:
    """R3: renew before the 7-day expiry - renew daily once less than 2 days remain (or never set)."""
    exp = account.watch_expires_at
    if exp and exp.tzinfo is None:
        exp = exp.replace(tzinfo=dt.timezone.utc)
    return exp is None or exp - now < dt.timedelta(days=2)

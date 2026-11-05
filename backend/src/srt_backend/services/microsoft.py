"""Microsoft side: Outlook.com / Hotmail / Microsoft 365 via Microsoft Graph (read-only mail).

Sign-in: the app runs the OAuth authorization-code flow with PKCE against the Microsoft
identity platform as a *public* client (no secret on the phone) and hands the code +
verifier to the backend, which redeems it for a refresh token (``offline_access``).
Partial grant (no Mail.Read) = no grant (flow decision #8).

Continuous detection (R3): a Graph change-notification subscription on the inbox
(created messages). Mail subscriptions expire after about three days; the tick renews
them with < 1 day left, and a catch-up search runs on every notification.
"""

from __future__ import annotations

import datetime as dt
import json
import secrets

import httpx

from srt_phase0.sources import GRAPH, GRAPH_SCOPES, EmailSource, GraphSource

from ..config import settings
from ..db import GmailAccount
from .gmail import PartialGrant, load_token, store_token

SUBSCRIPTION_MINUTES = 4200  # just under the ~3-day maximum for message subscriptions


def _token_url() -> str:
    return f"https://login.microsoftonline.com/{settings().microsoft_tenant}/oauth2/v2.0/token"


class MicrosoftGateway:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or httpx.Client(timeout=30)

    def exchange_code(self, code: str, code_verifier: str, redirect_uri: str) -> dict:
        s = settings()
        r = self.client.post(_token_url(), data={
            "client_id": s.microsoft_client_id, "grant_type": "authorization_code", "code": code,
            "code_verifier": code_verifier, "redirect_uri": redirect_uri, "scope": " ".join(GRAPH_SCOPES)})
        r.raise_for_status()
        tok = r.json()
        granted = {x.split("/")[-1].lower() for x in tok.get("scope", "").split()}
        if "mail.read" not in granted:
            raise PartialGrant("Mail read access was not granted")
        me = self.client.get(f"{GRAPH}/me", params={"$select": "mail,userPrincipalName"},
                             headers={"Authorization": f"Bearer {tok['access_token']}"}).json()
        email = (me.get("mail") or me.get("userPrincipalName") or "").lower()
        token = {"access_token": tok["access_token"], "refresh_token": tok.get("refresh_token"),
                 "expires_at": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=int(tok.get("expires_in", 3600)) - 120)).isoformat()}
        return {"email": email, "token": token}

    def _access_token(self, account: GmailAccount) -> str:
        tok = load_token(account)
        if dt.datetime.fromisoformat(tok["expires_at"]) > dt.datetime.now(dt.timezone.utc):
            return tok["access_token"]
        r = self.client.post(_token_url(), data={"client_id": settings().microsoft_client_id, "grant_type": "refresh_token",
                                                  "refresh_token": tok["refresh_token"], "scope": " ".join(GRAPH_SCOPES)})
        r.raise_for_status()
        new = r.json()
        tok.update(access_token=new["access_token"], refresh_token=new.get("refresh_token", tok["refresh_token"]),
                   expires_at=(dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=int(new.get("expires_in", 3600)) - 120)).isoformat())
        store_token(account, tok)  # rolling refresh token
        return tok["access_token"]

    def source_for(self, account: GmailAccount) -> EmailSource:
        return GraphSource(lambda: self._access_token(account), account.email, client=self.client)

    def start_watch(self, account: GmailAccount) -> dict:
        h = {"Authorization": f"Bearer {self._access_token(account)}"}
        exp = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=SUBSCRIPTION_MINUTES)).isoformat().replace("+00:00", "Z")
        if account.watch_id:  # renew
            r = self.client.patch(f"{GRAPH}/subscriptions/{account.watch_id}", json={"expirationDateTime": exp}, headers=h)
            if r.status_code < 400:
                return {"id": account.watch_id, "expiration": exp, "clientState": account.watch_secret}
        secret = secrets.token_urlsafe(24)
        r = self.client.post(f"{GRAPH}/subscriptions", headers=h, json={
            "changeType": "created", "notificationUrl": settings().public_base_url.rstrip("/") + "/graph/notify",
            "resource": "me/mailFolders('inbox')/messages", "expirationDateTime": exp, "clientState": secret})
        r.raise_for_status()
        d = r.json()
        return {"id": d["id"], "expiration": d["expirationDateTime"], "clientState": secret}

    def revoke(self, account: GmailAccount) -> bool:
        """Microsoft has no per-app refresh-token revocation endpoint: we delete the change subscription and
        our copy of the token. The user can also remove the app at account.live.com/consent/Manage."""
        try:
            if account.watch_id:
                self.client.delete(f"{GRAPH}/subscriptions/{account.watch_id}",
                                   headers={"Authorization": f"Bearer {self._access_token(account)}"})
        except Exception:  # noqa: BLE001
            pass
        return True

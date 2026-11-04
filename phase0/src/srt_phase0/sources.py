"""Email sources: Gmail (stage 1) and synthetic fixtures.

Data minimisation (R4, R9): search returns ids only; stage 3 uses metadata
(headers + Gmail's ~200-char snippet), so non-matching or triage-rejected mail
bodies are never downloaded; full bodies are fetched only for stage-4/5
candidates and are never written to disk by the pipeline.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import threading
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path
from typing import Iterator, Optional, Protocol

from .models import EmailMessage
from .textutil import html_to_text


class EmailSource(Protocol):
    account: str

    def search(self, queries: list[str]) -> Iterator[str]:
        """Yield matching message ids, newest first, de-duplicated."""

    def metadata(self, message_id: str) -> EmailMessage:
        """Headers + snippet only (body_text is None)."""

    def full(self, msg: EmailMessage) -> EmailMessage:
        """Return ``msg`` with body_text populated."""


# ---- fixtures ------------------------------------------------------------------------


class FixtureSource:
    """Reads synthetic emails from JSONL. Every fixture matches stage 1 by construction
    unless it has "stage1_match": false (to simulate search misses)."""

    def __init__(self, path: Path, account: str) -> None:
        self.account = account
        self._by_id: dict[str, dict] = {}
        for line in path.read_text().splitlines():
            if line.strip():
                d = json.loads(line)
                if d["account"] == account:
                    self._by_id[d["message_id"]] = d

    @staticmethod
    def accounts(path: Path) -> list[str]:
        seen = []
        for line in path.read_text().splitlines():
            if line.strip():
                a = json.loads(line)["account"]
                if a not in seen:
                    seen.append(a)
        return seen

    def search(self, queries: list[str]) -> Iterator[str]:
        items = [d for d in self._by_id.values() if d.get("stage1_match", True)]
        items.sort(key=lambda d: d["date"], reverse=True)
        for d in items:
            yield d["message_id"]

    def metadata(self, message_id: str) -> EmailMessage:
        d = self._by_id[message_id]
        body = d["body"]
        return EmailMessage(
            message_id=message_id, account=self.account, from_addr=d["from_addr"], from_name=d.get("from_name", ""),
            subject=d["subject"], date=dt.datetime.fromisoformat(d["date"]),
            snippet=" ".join(body.split())[:200], attachment_names=d.get("attachments", []),
        )

    def full(self, msg: EmailMessage) -> EmailMessage:
        return msg.model_copy(update={"body_text": self._by_id[msg.message_id]["body"]})


# ---- Gmail ---------------------------------------------------------------------------


GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


class GmailSource:
    """gmail.readonly only (D8). One instance per connected account (D16).

    googleapiclient's HTTP transport is not thread-safe, so each thread builds
    its own service object.
    """

    def __init__(self, credentials, account: str) -> None:
        self.credentials = credentials
        self.account = account
        self._local = threading.local()

    @property
    def _svc(self):
        if not hasattr(self._local, "svc"):
            from googleapiclient.discovery import build

            self._local.svc = build("gmail", "v1", credentials=self.credentials, cache_discovery=False)
        return self._local.svc

    def search(self, queries: list[str]) -> Iterator[str]:
        # Gmail returns list results in reverse-chronological order per query. With
        # two queries we interleave by page so early results stay newest-first-ish;
        # the pipeline re-sorts each processed batch by date for display.
        seen: set[str] = set()
        tokens: list[Optional[str]] = [None] * len(queries)
        active = list(range(len(queries)))
        while active:
            for qi in list(active):
                resp = (
                    self._svc.users().messages()
                    .list(userId="me", q=queries[qi], maxResults=500, pageToken=tokens[qi], includeSpamTrash=False)
                    .execute()
                )
                for m in resp.get("messages", []):
                    if m["id"] not in seen:
                        seen.add(m["id"])
                        yield m["id"]
                tokens[qi] = resp.get("nextPageToken")
                if not tokens[qi]:
                    active.remove(qi)

    def metadata(self, message_id: str) -> EmailMessage:
        m = (
            self._svc.users().messages()
            .get(userId="me", id=message_id, format="metadata", metadataHeaders=["From", "Subject", "Date"])
            .execute()
        )
        return self._to_message(m)

    def full(self, msg: EmailMessage) -> EmailMessage:
        m = self._svc.users().messages().get(userId="me", id=msg.message_id, format="full").execute()
        plain, html_parts, attachments = [], [], []
        _walk(m.get("payload", {}), plain, html_parts, attachments)
        body = "\n".join(plain).strip() or html_to_text("\n".join(html_parts))
        return msg.model_copy(update={"body_text": body, "attachment_names": attachments})

    def _to_message(self, m: dict) -> EmailMessage:
        headers = {h["name"].lower(): h["value"] for h in m.get("payload", {}).get("headers", [])}
        name, addr = parseaddr(headers.get("from", ""))
        try:
            date = parsedate_to_datetime(headers["date"])
        except Exception:
            date = dt.datetime.fromtimestamp(int(m.get("internalDate", "0")) / 1000, tz=dt.timezone.utc)
        if date.tzinfo is None:
            date = date.replace(tzinfo=dt.timezone.utc)
        return EmailMessage(
            message_id=m["id"], account=self.account, thread_id=m.get("threadId"), from_addr=addr or "unknown@unknown",
            from_name=name, subject=headers.get("subject", ""), date=date, snippet=m.get("snippet", ""),
        )


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def _walk(part: dict, plain: list, html_parts: list, attachments: list) -> None:
    mime = part.get("mimeType", "")
    body = part.get("body", {})
    if part.get("filename"):
        attachments.append(part["filename"])
    elif mime == "text/plain" and body.get("data"):
        plain.append(_decode(body["data"]))
    elif mime == "text/html" and body.get("data"):
        html_parts.append(_decode(body["data"]))
    for p in part.get("parts", []) or []:
        _walk(p, plain, html_parts, attachments)

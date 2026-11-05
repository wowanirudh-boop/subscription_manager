"""Alert delivery: Expo push (iOS + Android, D12) and e-mail to the user's own address (D13)."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Protocol

import httpx

from ..config import settings


class Delivery(Protocol):
    def push(self, tokens: list[str], title: str, body: str, data: dict) -> list[dict]: ...
    def email(self, to: str, subject: str, body: str) -> None: ...
    def receipts(self, ticket_ids: list[str]) -> dict[str, dict]: ...


EXPO_RECEIPTS_URL = "https://exp.host/--/api/v2/push/getReceipts"


class RealDelivery:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or httpx.Client(timeout=20)

    def push(self, tokens: list[str], title: str, body: str, data: dict) -> list[dict]:
        if not tokens:
            return []
        msgs = [{"to": t, "title": title, "body": body, "data": data, "sound": "default", "priority": "high"} for t in tokens]
        r = self.client.post(settings().expo_push_url, json=msgs, headers={"Accept": "application/json"})
        r.raise_for_status()
        return r.json().get("data", [])  # per-token tickets: {"status": "ok"|"error", ...}

    def receipts(self, ticket_ids: list[str]) -> dict[str, dict]:
        """Expo push receipts: did Apple/Google actually accept delivery to the device (M5)."""
        if not ticket_ids:
            return {}
        r = self.client.post(EXPO_RECEIPTS_URL, json={"ids": ticket_ids}, headers={"Accept": "application/json"})
        r.raise_for_status()
        return r.json().get("data", {})

    def email(self, to: str, subject: str, body: str) -> None:
        s = settings()
        if not s.smtp_host:
            raise RuntimeError("SMTP_HOST not configured")
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = s.mail_from, to, subject
        msg.set_content(body)
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as smtp:
            smtp.starttls()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)


class FakeDelivery:
    """Development / tests: records what would have been sent."""

    def __init__(self) -> None:
        self.pushes: list[dict] = []
        self.emails: list[dict] = []

    def push(self, tokens, title, body, data):
        self.pushes.append({"tokens": tokens, "title": title, "body": body, "data": data})
        return [{"status": "ok", "id": f"ticket-{len(self.pushes)}-{i}"} for i, _ in enumerate(tokens)]

    def receipts(self, ticket_ids):
        self.receipt_calls = getattr(self, "receipt_calls", 0) + 1
        return {t: self.receipt_overrides.get(t, {"status": "ok"}) if hasattr(self, "receipt_overrides") else {"status": "ok"}
                for t in ticket_ids}

    def email(self, to, subject, body):
        self.emails.append({"to": to, "subject": subject, "body": body})

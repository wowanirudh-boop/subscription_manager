import datetime as dt
from pathlib import Path

import pytest

from srt_phase0.models import EmailMessage
from srt_phase0.sources import FixtureSource

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "synthetic_emails.jsonl"
A, B = "primary@example.com", "work@example.com"


@pytest.fixture
def fixtures_path() -> Path:
    return FIXTURES


@pytest.fixture
def full():
    """Load one fixture message with its body."""
    def _get(mid: str) -> EmailMessage:
        for acct in (A, B):
            src = FixtureSource(FIXTURES, acct)
            if mid in src._by_id:
                return src.full(src.metadata(mid))
        raise KeyError(mid)
    return _get


def make_msg(body: str, subject: str = "Receipt", date: str = "2026-10-05T08:00:00+05:30",
             attachments=None, sender="billing@merchant.example", name="Merchant") -> EmailMessage:
    return EmailMessage(
        message_id="m1", account=A, from_addr=sender, from_name=name, subject=subject,
        date=dt.datetime.fromisoformat(date), snippet=body[:200], body_text=body, attachment_names=attachments or [],
    )

import base64
import datetime as dt

from srt_phase0.queries import build_queries
from srt_phase0.sources import _walk
from srt_phase0.textutil import find_dates, html_to_text


def _b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")


def test_mime_walk_prefers_plain_and_lists_attachments():
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {"mimeType": "multipart/alternative", "parts": [
                {"mimeType": "text/plain", "body": {"data": _b64("Plain body ₹649")}},
                {"mimeType": "text/html", "body": {"data": _b64("<p>HTML body</p>")}},
            ]},
            {"mimeType": "application/pdf", "filename": "invoice.pdf", "body": {"attachmentId": "x"}},
        ],
    }
    plain, html_parts, att = [], [], []
    _walk(payload, plain, html_parts, att)
    assert plain == ["Plain body ₹649"] and att == ["invoice.pdf"]


def test_html_to_text_keeps_links_and_drops_style():
    t = html_to_text('<style>.x{}</style><p>To cancel, <a href="https://m.example/cancel">click here</a>.</p>')
    assert "https://m.example/cancel" in t and ".x{}" not in t


def test_queries_cover_24_months():
    q = build_queries(dt.date(2026, 11, 4))
    assert all(x.startswith("after:2024/11/04 ") for x in q)
    assert '"free trial"' in q[0] and "from:billing" in q[1]


def test_ambiguous_numeric_date_returns_both_readings():
    ds = {d for d, _ in find_dates("due 03/04/2026")}
    assert ds == {dt.date(2026, 4, 3), dt.date(2026, 3, 4)}


def test_cli_queries_command(capsys):
    from srt_phase0.cli import main

    main(["queries", "--today", "2026-11-04"])
    out = capsys.readouterr().out
    assert "after:2024/11/04" in out and out.count("after:") == 2

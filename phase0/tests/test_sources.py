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


def test_indian_biller_two_digit_year():
    assert {d for d, _ in find_dates("Due Date: 15-MAY-26 Due Amount: 450")} == {dt.date(2026, 5, 15)}


def _pdf_with_text(text: str) -> bytes:
    """Minimal one-page PDF with a text object (hand-built: no PDF writer dependency)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % x for x in offsets)
    return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)


def test_pdf_first_page_text():
    from srt_phase0.sources import pdf_first_page_text
    assert "Total Rs. 2,499.00" in pdf_first_page_text(_pdf_with_text("Total Rs. 2,499.00 billed for Gold"))
    assert pdf_first_page_text(b"not a pdf") is None


def test_pipeline_reads_attachment_when_body_has_no_amount(tmp_path):
    import json
    from srt_phase0.pipeline import Pipeline
    from srt_phase0.providers import FakeProvider
    from srt_phase0.sources import FixtureSource
    row = {"message_id": "att-1", "account": "a@x", "from_name": "HostNest", "from_addr": "billing@hostnest.example",
           "subject": "Your HostNest invoice", "date": "2026-10-12T10:00:00+05:30",
           "body": "Please find your invoice for your HostNest subscription attached.", "attachments": ["inv.pdf"],
           "attachment_text": "HostNest invoice. Monthly plan total: ₹1,299.00 charged on 12 October 2026."}
    p = tmp_path / "f.jsonl"
    p.write_text(json.dumps(row, ensure_ascii=False) + "\n")
    res = Pipeline(FakeProvider(), concurrency=1).run([FixtureSource(p, "a@x")], today=dt.date(2026, 11, 5))
    ex = res.extractions[0]
    assert res.traces[0].attachment_read and ex.amount.value == 1299 and ex.amount.state.value == "confirmed"
    assert "Attachment, page 1" in ex.amount.evidence.snippet or "₹1,299.00" in ex.amount.evidence.snippet

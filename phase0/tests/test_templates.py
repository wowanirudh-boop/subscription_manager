"""Stage 5: learn once per sender; apply only on structural match; fall back otherwise (R4)."""

import datetime as dt

from srt_phase0.models import FieldState
from srt_phase0.pipeline import _template_ok
from srt_phase0.providers import FakeProvider
from srt_phase0.providers.base import ExtractInput
from srt_phase0.templates import SenderTemplate, TemplateStore
from srt_phase0.verify import verify


def _learn(msg):
    raw = FakeProvider().extract(ExtractInput(sender=msg.from_addr, sender_name=msg.from_name, subject=msg.subject,
                                              sent_date=msg.date.date().isoformat(), body=msg.body_text))
    ex = verify(raw, msg)
    return SenderTemplate.learn(msg, ex, raw)


def test_template_extracts_other_month(full):
    t = _learn(full("sf-10"))
    assert t is not None and "amount" in t.found_fields
    later = full("sf-08")
    assert t.matches(later)
    raw = t.apply(later)
    ex = verify(raw, later, stage="stage5")
    assert _template_ok(t, ex)
    assert ex.amount.value == 649 and ex.amount.state == FieldState.CONFIRMED
    assert ex.next_charge_date.value == dt.date(2026, 9, 5) and ex.next_charge_date.state == FieldState.CONFIRMED
    assert ex.charge_date.value == dt.date(2026, 8, 5)


def test_template_not_used_for_different_structure(full):
    t = _learn(full("sf-10"))
    other = full("sf-08").model_copy(update={"body_text": "Your account settings were updated.\nNo action needed."})
    assert not t.matches(other)


def test_missing_previously_found_field_forces_fallback(full):
    t = _learn(full("sf-10"))
    msg = full("sf-08")
    # Same layout, but the amount line no longer has a number in it.
    body = msg.body_text.replace("We charged ₹649 for", "We charged your card for")
    msg = msg.model_copy(update={"body_text": body})
    # (One changed line out of six already drops below the similarity threshold, so
    # find() would skip the template; this checks apply()'s own correctness rule.)
    raw = t.apply(msg)
    assert raw is None or not _template_ok(t, verify(raw, msg, stage="stage5"))


def test_store_round_trip(tmp_path, full):
    t = _learn(full("sf-10"))
    store = TemplateStore(tmp_path / "t.json")
    store.add(t)
    store.save()
    again = TemplateStore(tmp_path / "t.json")
    assert len(again) == 1 and again.find(full("sf-09")) is not None

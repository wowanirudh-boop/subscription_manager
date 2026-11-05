import datetime as dt

from conftest import at, rec

from srt_phase0.models import BillingPeriod, FieldState, Kind
from srt_backend.domain import alerts, unknowns
from srt_backend.domain.lifecycle import State, UserRecordState, compute

D = dt.date
NOW = at("2026-11-05T00:00:00")


def _v(**kw):
    return compute(rec(**kw), UserRecordState(), D(2026, 11, 5))


def test_monthly_ladder_and_channels():
    plan = alerts.plan(_v(nxt=D(2026, 11, 20)), NOW)
    assert sorted({(p.days_before, p.channel) for p in plan}) == [(0, "email"), (0, "push"), (1, "email"), (1, "push")]


def test_annual_and_trial_ladder():
    assert {p.days_before for p in alerts.plan(_v(nxt=D(2026, 12, 20), period=BillingPeriod.ANNUAL), NOW)} == {7, 3, 1, 0}
    assert {p.days_before for p in alerts.plan(_v(nxt=D(2026, 12, 20), kind=Kind.TRIAL), NOW)} == {7, 3, 1, 0}  # D20
    assert {p.days_before for p in alerts.plan(_v(nxt=D(2026, 12, 20), period=None), NOW)} == {7, 3, 1, 0}  # D28


def test_send_time_is_9am_ist():  # decision #1
    p = [a for a in alerts.plan(_v(nxt=D(2026, 11, 20)), NOW) if a.days_before == 0][0]
    assert p.send_at == at("2026-11-20T03:30:00")  # 09:00 IST


def test_no_alerts_for_unknown_or_cancelled():
    assert alerts.plan(_v(nxt=None), NOW) == []
    assert alerts.plan(_v(nxt=D(2026, 12, 5), receipt_at=at("2026-10-01T00:00:00"), cancel_at=at("2026-11-01T00:00:00")), NOW) == []


def test_render_includes_required_content():
    v = _v(nxt=D(2026, 11, 20), nxt_state=FieldState.ESTIMATED)
    title, body = alerts.render(v, 1)
    assert "StreamFlix" in title and "INR 649.00" in body and "20 Nov 2026" in body and "estimated" in body


def test_queue_order_by_damage():
    vs = [compute(rec(key="m", merchant="M", period=BillingPeriod.MONTHLY, amount=999), UserRecordState(), D(2026, 11, 5)),
          compute(rec(key="a", merchant="A", period=BillingPeriod.ANNUAL, amount=100), UserRecordState(), D(2026, 11, 5)),
          compute(rec(key="u", merchant="U", period=None, amount=5000), UserRecordState(), D(2026, 11, 5)),
          compute(rec(key="a2", merchant="A2", period=BillingPeriod.ANNUAL, amount=900), UserRecordState(), D(2026, 11, 5))]
    assert [v.record_key for v in unknowns.queue(vs)] == ["a2", "a", "m", "u"]


def test_skip_returns_next_session_only():
    v = compute(rec(key="a", period=BillingPeriod.ANNUAL), UserRecordState(), D(2026, 11, 5))
    st = UserRecordState()
    unknowns.apply_answer(v, st, unknowns.Answer.SKIP, "s1", None, D(2026, 11, 5))
    assert unknowns.next_card([v], {"a": st}, "s1") is None
    assert unknowns.next_card([v], {"a": st}, "s2").record_key == "a"


def test_period_answer_with_confirmed_anchor_gives_estimated_next():
    r = rec(period=None, last=D(2026, 10, 16))
    v = compute(r, UserRecordState(), D(2026, 11, 5))
    st = UserRecordState()
    out = unknowns.apply_answer(v, st, unknowns.Answer.MONTHLY, "s", None, D(2026, 11, 5))
    assert out == {"needs_date": False, "event": "unknown_resolved"}
    v2 = compute(r, st, D(2026, 11, 5))
    assert v2.state == State.ACTIVE and v2.next_charge_date.value == D(2026, 11, 16)
    assert v2.next_charge_date.state == FieldState.ESTIMATED and v2.billing_period.state == FieldState.CONFIRMED


def test_period_answer_without_anchor_asks_for_date():
    v = compute(rec(period=None, last=None), UserRecordState(), D(2026, 11, 5))
    assert unknowns.apply_answer(v, UserRecordState(), unknowns.Answer.ANNUAL, "s", None, D(2026, 11, 5))["needs_date"]


def test_not_a_subscription_suppresses_and_logs_false_positive():
    st = UserRecordState()
    out = unknowns.apply_answer(_v(nxt=None), st, unknowns.Answer.NOT_SUBSCRIPTION, "s", None, D(2026, 11, 5))
    assert st.suppressed and out["event"] == "false_positive"

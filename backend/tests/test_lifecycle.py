import datetime as dt

from conftest import at, rec

from srt_phase0.models import BillingPeriod, FieldState
from srt_backend.domain.lifecycle import Notice, State, UserRecordState, compute

D = dt.date


def test_active_with_future_date_alerts():
    v = compute(rec(nxt=D(2026, 12, 5)), UserRecordState(), D(2026, 11, 5))
    assert v.state == State.ACTIVE and v.alerts_enabled


def test_unknown_date_never_alerts():  # D7
    v = compute(rec(nxt=None), UserRecordState(), D(2026, 11, 5))
    assert v.state == State.UNKNOWN_DATE and not v.alerts_enabled


def test_decision2_missed_receipt_stays_active_and_rolls_forward():
    # Silent merchant: charged monthly, never e-mails a receipt (seen in the Phase 0 run).
    v = compute(rec(nxt=D(2024, 12, 8)), UserRecordState(), D(2026, 11, 5))
    assert v.state == State.ACTIVE and Notice.NO_RECEIPT_SEEN in v.notices
    assert v.next_charge_date.value == D(2026, 11, 8) and v.next_charge_date.state == FieldState.ESTIMATED
    assert v.missed_date == D(2024, 12, 8)


def test_decision5_lookback_three_days():
    assert Notice.NO_RECEIPT_SEEN not in compute(rec(nxt=D(2026, 11, 2)), UserRecordState(), D(2026, 11, 5)).notices
    assert Notice.NO_RECEIPT_SEEN in compute(rec(nxt=D(2026, 11, 1)), UserRecordState(), D(2026, 11, 5)).notices


def test_missed_date_without_period_becomes_unknown():
    v = compute(rec(nxt=D(2026, 1, 1), period=None), UserRecordState(), D(2026, 11, 5))
    assert v.state == State.UNKNOWN_DATE


def test_i_cancelled_keeps_alerting_until_merchant_confirms():  # D9, R8
    us = UserRecordState(cancel_requested_at=at("2026-11-01T10:00:00"))
    v = compute(rec(nxt=D(2026, 12, 5)), us, D(2026, 11, 5))
    assert v.state == State.CANCELLATION_PENDING and v.alerts_enabled
    assert Notice.NO_MERCHANT_CONFIRMATION in v.notices


def test_pending_then_date_passes_without_receipt_is_likely_cancelled():  # D11
    us = UserRecordState(cancel_requested_at=at("2026-11-01T10:00:00"))
    v = compute(rec(nxt=D(2026, 11, 10)), us, D(2026, 11, 20))
    assert v.state == State.LIKELY_CANCELLED and not v.alerts_enabled


def test_merchant_cancellation_email_confirms():  # D10
    v = compute(rec(nxt=D(2026, 12, 5), receipt_at=at("2026-10-05T00:00:00"), cancel_at=at("2026-11-01T00:00:00")),
                UserRecordState(), D(2026, 11, 5))
    assert v.state == State.CANCELLED_CONFIRMED and not v.alerts_enabled


def test_force_confirm_is_user_confirmed():
    us = UserRecordState(cancel_requested_at=at("2026-11-01T00:00:00"), user_confirmed_cancel_at=at("2026-11-02T00:00:00"))
    assert compute(rec(nxt=D(2026, 12, 5)), us, D(2026, 11, 5)).state == State.CANCELLED_USER_CONFIRMED


def test_receipt_after_cancellation_reactivates_and_asks():  # D26, decision #7
    r = rec(nxt=D(2026, 12, 5), receipt_at=at("2026-11-04T00:00:00"), cancel_at=at("2026-09-01T00:00:00"))
    v = compute(r, UserRecordState(), D(2026, 11, 5))
    assert v.state == State.ACTIVE and Notice.RESUBSCRIBE_QUESTION in v.notices and v.alerts_enabled
    answered = UserRecordState(resubscribe_answers={at("2026-11-04T00:00:00").isoformat(): True})
    assert Notice.RESUBSCRIBE_QUESTION not in compute(r, answered, D(2026, 11, 5)).notices


def test_charge_while_pending_returns_active_with_notice():  # decision #3
    us = UserRecordState(cancel_requested_at=at("2026-11-01T00:00:00"))
    r = rec(nxt=D(2026, 12, 5), receipt_at=at("2026-11-04T00:00:00"))
    v = compute(r, us, D(2026, 11, 5))
    assert v.state == State.ACTIVE and Notice.CHARGED_WHILE_PENDING in v.notices
    assert Notice.RESUBSCRIBE_QUESTION not in v.notices


def test_user_override_is_confirmed_and_superseded_by_later_charge():
    us = UserRecordState(overrides={"next_charge_date": "2026-11-20", "billing_period": "annual"})
    v = compute(rec(nxt=None, period=None), us, D(2026, 11, 5))
    assert v.next_charge_date.value == D(2026, 11, 20) and v.billing_period.value == BillingPeriod.ANNUAL
    later = rec(nxt=None, period=None, last=D(2026, 11, 20))
    assert compute(later, us, D(2026, 11, 25)).next_charge_date.value != D(2026, 11, 20)


def test_mute_disables_alerts():
    assert not compute(rec(nxt=D(2026, 12, 5)), UserRecordState(muted=True), D(2026, 11, 5)).alerts_enabled

"""Merge rules: D16 cross-account, R4 most-recent-receipt-wins, 6.2 contradictions, Q7 win-backs."""

import datetime as dt

from srt_phase0.merge import merge
from srt_phase0.models import (
    EmailType,
    Evidence,
    Extraction,
    FieldState,
    FieldValue,
    Lifecycle,
)


def ex(mid, account, date, etype=EmailType.RECEIPT, merchant="VidMax", amount=None, charge=None, nxt=None, period=None,
       nxt_state=FieldState.CONFIRMED):
    def fv(v, state=FieldState.CONFIRMED):
        if v is None:
            return FieldValue()
        return FieldValue(value=v, state=state, evidence=Evidence(message_id=mid, account=account, snippet="s"))
    return Extraction(
        message_id=mid, account=account, email_date=dt.datetime.fromisoformat(date), sender="billing@vidmax.example",
        source_stage="stage4", is_subscription_related=True, email_type=etype, merchant=fv(merchant),
        amount=fv(amount), currency=fv("INR" if amount else None), charge_date=fv(charge),
        next_charge_date=fv(nxt, nxt_state), billing_period=fv(period),
    )


def test_cross_account_merge_and_latest_receipt_wins():
    recs = merge([
        ex("a", "a@x", "2026-07-03T09:00:00+00:00", amount=299, charge=dt.date(2026, 7, 3), period="monthly"),
        ex("b", "b@x", "2026-10-03T09:00:00+00:00", amount=349, charge=dt.date(2026, 10, 3), period="monthly"),
    ])
    assert len(recs) == 1
    r = recs[0]
    assert r.source_accounts == ["a@x", "b@x"]
    assert r.amount.value == 349 and any("amount changed" in f for f in r.flags)
    assert r.last_charge_date.value == dt.date(2026, 10, 3)
    assert r.next_charge_date.value == dt.date(2026, 11, 3) and r.next_charge_date.state == FieldState.ESTIMATED
    assert r.lifecycle_state == Lifecycle.ACTIVE


def test_cancellation_then_winback_stays_cancelled():
    recs = merge([
        ex("r", "a@x", "2026-06-01T00:00:00+00:00", amount=999, charge=dt.date(2026, 6, 1), period="monthly"),
        ex("c", "a@x", "2026-07-10T00:00:00+00:00", etype=EmailType.CANCELLATION_CONFIRMATION),
        ex("w", "a@x", "2026-09-01T00:00:00+00:00", etype=EmailType.WINBACK_OFFER),
    ])
    assert recs[0].lifecycle_state == Lifecycle.CANCELLED_CONFIRMED


def test_receipt_after_cancellation_reactivates():
    recs = merge([
        ex("c", "a@x", "2026-07-10T00:00:00+00:00", etype=EmailType.CANCELLATION_CONFIRMATION),
        ex("r", "a@x", "2026-09-01T00:00:00+00:00", amount=999, charge=dt.date(2026, 9, 1), period="monthly"),
    ])
    assert recs[0].lifecycle_state == Lifecycle.ACTIVE


def test_price_change_is_flagged_not_applied():
    recs = merge([
        ex("r", "a@x", "2026-09-15T00:00:00+00:00", amount=199, charge=dt.date(2026, 9, 15), period="monthly"),
        ex("p", "a@x", "2026-10-25T00:00:00+00:00", etype=EmailType.PRICE_CHANGE, amount=249),
    ])
    assert recs[0].amount.value == 199
    assert any("price change" in f for f in recs[0].flags)


def test_estimate_does_not_override_future_confirmed_date():
    recs = merge([
        ex("r1", "a@x", "2026-10-01T00:00:00+00:00", nxt=dt.date(2026, 12, 12)),
        ex("r2", "a@x", "2026-10-15T00:00:00+00:00", nxt=dt.date(2026, 11, 15), nxt_state=FieldState.ESTIMATED),
    ])
    assert recs[0].next_charge_date.value == dt.date(2026, 12, 12)
    assert any("contradicts" in f for f in recs[0].flags)


def test_unknown_next_date_gives_unknown_date_state():
    recs = merge([ex("t", "a@x", "2026-10-28T00:00:00+00:00", etype=EmailType.TRIAL_SIGNUP, merchant="PixelForge")])
    assert recs[0].lifecycle_state == Lifecycle.UNKNOWN_DATE


def test_list_sorted_with_unknowns_last():
    recs = merge([
        ex("t", "a@x", "2026-10-28T00:00:00+00:00", etype=EmailType.TRIAL_SIGNUP, merchant="PixelForge"),
        ex("r", "a@x", "2026-10-01T00:00:00+00:00", merchant="DomainHub", nxt=dt.date(2026, 12, 12)),
    ])
    assert [r.merchant.value for r in recs] == ["DomainHub", "PixelForge"]


def test_monthly_progression_does_not_flag():
    recs = merge([
        ex("r1", "a@x", "2026-08-16T00:00:00+00:00", amount=100, charge=dt.date(2026, 8, 16), nxt=dt.date(2026, 9, 16)),
        ex("r2", "a@x", "2026-09-16T00:00:00+00:00", amount=100, charge=dt.date(2026, 9, 16), nxt=dt.date(2026, 10, 16)),
    ])
    assert recs[0].next_charge_date.value == dt.date(2026, 10, 16)
    assert recs[0].flags == []


def test_stale_next_date_is_rederived_after_later_charge():
    recs = merge([
        ex("bill", "a@x", "2026-10-01T00:00:00+00:00", amount=450, nxt=dt.date(2026, 10, 15), period="monthly"),
        ex("paid", "a@x", "2026-11-01T00:00:00+00:00", amount=450, charge=dt.date(2026, 11, 1)),
    ])
    r = recs[0]
    assert r.next_charge_date.value == dt.date(2026, 12, 1) and r.next_charge_date.state == FieldState.ESTIMATED
    assert any("superseded" in f for f in r.flags)

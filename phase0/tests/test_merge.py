"""Merge rules: D16 cross-account, R4 most-recent-receipt-wins, 6.2 contradictions, Q7 win-backs."""

import datetime as dt

from srt_phase0.merge import merchant_key, merge
from srt_phase0.models import (
    EmailType,
    Evidence,
    Extraction,
    FieldState,
    FieldValue,
    Lifecycle,
    BillingPeriod,
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


# ---- bank/card alerts, cadence, instances (5 Nov 2026) -------------------------------------

def card(mid, date, amount, merchant="GOOGLE*YOUTUBE", etype=EmailType.CARD_TRANSACTION, reference=None, account="a@x"):
    e = ex(mid, account, date + "T10:00:00+00:00", etype=etype, merchant=merchant, amount=amount,
           charge=dt.date.fromisoformat(date) if etype != EmailType.PRE_DEBIT_NOTICE else None)
    if reference:
        e.reference = FieldValue(value=reference, state=FieldState.CONFIRMED)
    return e


def test_one_off_card_purchase_is_dropped():
    assert merge([card("c1", "2026-10-04", 2340, merchant="SHOPKART")]) == []


def test_repeating_card_charges_become_a_monthly_subscription():
    recs = merge([card(f"c{i}", d, 189) for i, d in enumerate(["2026-08-08", "2026-09-08", "2026-10-08"])])
    assert len(recs) == 1
    r = recs[0]
    assert r.billing_period.value == BillingPeriod.MONTHLY and r.billing_period.state == FieldState.ESTIMATED
    assert r.next_charge_date.value == dt.date(2026, 11, 8) and r.sources == ["bank"]


def test_irregular_card_charges_are_not_a_subscription():
    assert merge([card("a", "2026-08-02", 450, merchant="SWIGGY"), card("b", "2026-08-19", 300, merchant="SWIGGY"),
                  card("c", "2026-10-01", 520, merchant="SWIGGY")]) == []


def test_pre_debit_notice_alone_is_kept():
    e = card("p", "2026-11-01", 649, merchant="NETFLIX", etype=EmailType.PRE_DEBIT_NOTICE)
    e.next_charge_date = FieldValue(value=dt.date(2026, 11, 5), state=FieldState.CONFIRMED)
    recs = merge([e])
    assert len(recs) == 1 and recs[0].next_charge_date.value == dt.date(2026, 11, 5)


def test_cadence_fills_missing_period_for_merchant_receipts():
    recs = merge([ex(f"r{i}", "a@x", d + "T00:00:00+00:00", merchant="Anthropic", amount=100, charge=dt.date.fromisoformat(d))
                  for i, d in enumerate(["2026-07-16", "2026-08-16", "2026-09-16"])])
    assert recs[0].billing_period.value == BillingPeriod.MONTHLY and recs[0].next_charge_date.value == dt.date(2026, 10, 16)


def test_quarterly_cadence():
    recs = merge([card(f"q{i}", d, 299, merchant="ZOMATO") for i, d in enumerate(["2026-03-30", "2026-06-23", "2026-09-18"])])
    assert recs[0].billing_period.value == BillingPeriod.OTHER and recs[0].period_months == 3


def test_same_day_policies_split_by_amount_and_linked_across_years():
    # Synthetic pattern: four plans billed by one merchant, two cycles a year apart, amounts drifting ~2%.
    y25 = [("2025-04-17", 2040.00), ("2025-04-17", 3570.00), ("2025-05-01", 2550.00), ("2025-05-01", 4590.00)]
    y26 = [("2026-04-20", 2000.0), ("2026-04-20", 2500.0), ("2026-04-20", 3500.0), ("2026-04-20", 4500.0)]
    exs = [ex(f"l{i}", "a@x", d + "T00:00:00+00:00", merchant="Acme Insurance", amount=a, charge=dt.date.fromisoformat(d))
           for i, (d, a) in enumerate(y25 + y26)]
    recs = merge(exs)
    assert len(recs) == 4
    pairs = sorted(tuple(sorted(e.message_id for e in exs if e.message_id in r.message_ids)) for r in recs)
    by_amount = {e.message_id: e.amount.value for e in exs}
    for p in pairs:
        a, b = (by_amount[m] for m in p)
        assert abs(a - b) / max(a, b) < 0.05  # each plan links a 2025 premium to its ~2% different 2026 premium
    assert all(any("told apart by amount" in f for f in r.flags) for r in recs)
    assert all(r.billing_period.value == BillingPeriod.ANNUAL for r in recs)  # inferred from the yearly repeat


def test_reference_numbers_split_plans():
    recs = merge([card("x1", "2026-04-20", 3300, merchant="Acme Insurance", etype=EmailType.RECEIPT, reference="POL-111"),
                  card("x2", "2026-04-20", 3300, merchant="Acme Insurance", etype=EmailType.RECEIPT, reference="POL-222")])
    assert sorted(r.reference for r in recs) == ["POL-111", "POL-222"]


def test_card_descriptor_keys():
    assert merchant_key("GOOGLE*YOUTUBE") == "googleyoutube" and merchant_key("NETFLIX.COM") == "netflix"
    assert merchant_key("GOOGLE*YOUTUBE") != merchant_key("GOOGLE*GOOGLE ONE")


def test_two_google_billed_subscriptions_stay_separate():
    yt = [card(f"y{i}", d, 189, merchant="GOOGLE*YOUTUBE") for i, d in enumerate(["2026-08-08", "2026-09-08", "2026-10-08"])]
    g1 = [card(f"g{i}", d, 199, merchant="GOOGLE*GOOGLE ONE") for i, d in enumerate(["2026-08-16", "2026-09-16", "2026-10-16"])]
    recs = merge(yt + g1)
    assert len(recs) == 2 and all(r.billing_period.value == BillingPeriod.MONTHLY for r in recs)

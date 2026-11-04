"""D5-D7: confirmed only with verified evidence; estimated only by derivation; else unknown."""

import datetime as dt

from conftest import make_msg

from srt_phase0.models import BillingPeriod, EmailType, FieldState, Kind
from srt_phase0.providers.base import Quoted, QuotedAmount, QuotedInt, QuotedKind, QuotedPeriod, RawExtraction
from srt_phase0.verify import verify

BODY = "Thank you for your payment.\nWe charged ₹649 for your monthly plan on 5 October 2026."


def raw(**kw) -> RawExtraction:
    return RawExtraction(is_subscription_related=True, email_type=EmailType.RECEIPT, **kw)


def test_hallucinated_amount_is_rejected():
    r = raw(amount=QuotedAmount(value=99999, currency="INR", quote="We charged ₹649 for your monthly plan on 5 October 2026."))
    ex = verify(r, make_msg(BODY))
    assert ex.amount.state == FieldState.UNKNOWN
    assert "amount=99999.0" in ex.rejected_values


def test_quote_not_in_email_is_rejected():
    r = raw(amount=QuotedAmount(value=649, currency="INR", quote="We charged ₹649 yesterday."))
    ex = verify(r, make_msg(BODY))
    assert ex.amount.state == FieldState.UNKNOWN


def test_confirmed_amount_and_currency_with_evidence():
    q = "We charged ₹649 for your monthly plan on 5 October 2026."
    ex = verify(raw(amount=QuotedAmount(value=649, currency="INR", quote=q)), make_msg(BODY))
    assert ex.amount.state == FieldState.CONFIRMED and ex.amount.value == 649
    assert ex.currency.value == "INR"
    assert ex.amount.evidence.snippet == q and ex.amount.evidence.message_id == "m1"


def test_amount_without_thousands_separator():
    body = "Total: ₹2999 for your annual plan."
    ex = verify(raw(amount=QuotedAmount(value=2999, currency="INR", quote=body)), make_msg(body))
    assert ex.amount.value == 2999 and ex.currency.value == "INR"


def test_indian_digit_grouping():
    body = "Amount: ₹1,23,456.50 charged."
    ex = verify(raw(amount=QuotedAmount(value=123456.5, currency="INR", quote=body)), make_msg(body))
    assert ex.amount.state == FieldState.CONFIRMED


def test_currency_not_shown_stays_unknown():
    body = "Your plan renewed. Total 2999 for the year."
    ex = verify(raw(amount=QuotedAmount(value=2999, currency="INR", quote="Your plan renewed. Total 2999 for the year.")), make_msg(body))
    assert ex.amount.state == FieldState.CONFIRMED
    assert ex.currency.state == FieldState.UNKNOWN  # INR is not asserted just because it is the default


def test_next_date_estimated_from_charge_plus_period():
    q = "We charged ₹649 for your monthly plan on 5 October 2026."
    r = raw(
        billing_period=QuotedPeriod(value=BillingPeriod.MONTHLY, quote=q),
        charge_date=Quoted(value="2026-10-05", quote=q),
    )
    ex = verify(r, make_msg(BODY))
    assert ex.charge_date.state == FieldState.CONFIRMED
    assert ex.next_charge_date.state == FieldState.ESTIMATED
    assert ex.next_charge_date.value == dt.date(2026, 11, 5)


def test_receipt_without_date_uses_sent_date_as_estimate():
    body = "Your annual plan is active. Total: ₹2,999"
    r = raw(billing_period=QuotedPeriod(value=BillingPeriod.ANNUAL, quote="Your annual plan is active."))
    ex = verify(r, make_msg(body, date="2026-03-03T14:00:00+05:30"))
    assert ex.charge_date.state == FieldState.ESTIMATED and ex.charge_date.value == dt.date(2026, 3, 3)
    assert ex.next_charge_date.state == FieldState.ESTIMATED and ex.next_charge_date.value == dt.date(2027, 3, 3)


def test_trial_without_stated_length_is_unknown():
    body = "Your Pro trial is now active."
    r = RawExtraction(is_subscription_related=True, email_type=EmailType.TRIAL_SIGNUP,
                      kind=QuotedKind(value=Kind.TRIAL, quote=body))
    ex = verify(r, make_msg(body))
    assert ex.trial_end_date.state == FieldState.UNKNOWN
    assert ex.next_charge_date.state == FieldState.UNKNOWN


def test_model_cannot_invent_trial_length():
    body = "Your Pro trial is now active."
    r = RawExtraction(is_subscription_related=True, email_type=EmailType.TRIAL_SIGNUP,
                      trial_length_days=QuotedInt(value=14, quote=body))
    ex = verify(r, make_msg(body))
    assert ex.trial_end_date.state == FieldState.UNKNOWN


def test_stated_trial_length_gives_estimated_end():
    body = "Your 30-day free trial has started."
    r = RawExtraction(is_subscription_related=True, email_type=EmailType.TRIAL_SIGNUP,
                      trial_length_days=QuotedInt(value=30, quote=body))
    ex = verify(r, make_msg(body, date="2026-10-20T19:10:00+05:30"))
    assert ex.trial_end_date.state == FieldState.ESTIMATED and ex.trial_end_date.value == dt.date(2026, 11, 19)
    assert ex.next_charge_date.value == dt.date(2026, 11, 19)


def test_day_first_numeric_date_accepted():
    body = "Your premium of Rs. 18,500 is due on 28/11/2026."
    ex = verify(raw(next_charge_date=Quoted(value="2026-11-28", quote=body)), make_msg(body))
    assert ex.next_charge_date.state == FieldState.CONFIRMED


def test_period_word_must_be_in_quote():
    ex = verify(raw(billing_period=QuotedPeriod(value=BillingPeriod.ANNUAL, quote="Thank you for your payment.")), make_msg(BODY))
    assert ex.billing_period.state == FieldState.UNKNOWN


def test_cancel_path_must_appear_in_email():
    ex = verify(raw(cancel_path=Quoted(value="https://evil.example/cancel", quote=None)), make_msg(BODY))
    assert ex.cancel_path.state == FieldState.UNKNOWN


def test_merchant_must_be_visible():
    ex = verify(raw(merchant=Quoted(value="TrustedBank")), make_msg(BODY, name="StreamFlix"))
    assert ex.merchant.state == FieldState.UNKNOWN
    ex = verify(raw(merchant=Quoted(value="StreamFlix")), make_msg(BODY, name="StreamFlix"))
    assert ex.merchant.state == FieldState.CONFIRMED


def test_attachment_only_invoice_is_flagged():
    ex = verify(raw(), make_msg("Please find your invoice attached.", attachments=["invoice.pdf"]))
    assert ex.attachment_skipped


def test_not_related_has_no_fields():
    r = RawExtraction(is_subscription_related=False, amount=QuotedAmount(value=649, quote="We charged ₹649"))
    ex = verify(r, make_msg(BODY))
    assert not ex.amount.known

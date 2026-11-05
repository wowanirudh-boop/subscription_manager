import datetime as dt

from srt_phase0.models import (BillingPeriod, Evidence, FieldState, FieldValue, Kind, Lifecycle,
                               SubscriptionRecord)


def fv(v, state=FieldState.CONFIRMED):
    if v is None:
        return FieldValue()
    return FieldValue(value=v, state=state, evidence=Evidence(message_id="m", account="a@x", snippet="s"))


def rec(key="r1", merchant="StreamFlix", period=BillingPeriod.MONTHLY, amount=649.0, currency="INR",
        last=None, nxt=None, nxt_state=FieldState.CONFIRMED, kind=Kind.SUBSCRIPTION, lifecycle=Lifecycle.ACTIVE,
        receipt_at=None, cancel_at=None, period_months=None):
    return SubscriptionRecord(
        record_id=key, merchant=fv(merchant), source_accounts=["a@x"], kind=fv(kind),
        billing_period=fv(period), amount=fv(amount), currency=fv(currency), last_charge_date=fv(last),
        next_charge_date=fv(nxt, nxt_state), trial_end_date=FieldValue(), cancel_path=FieldValue(),
        lifecycle_state=lifecycle, message_ids=["m"], period_months=period_months,
        last_receipt_at=receipt_at, last_cancel_at=cancel_at,
    )


def at(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc)

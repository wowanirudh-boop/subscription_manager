"""End-to-end API tests on synthetic fixtures (no network, no Google, no model)."""

import datetime as dt
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from srt_phase0.providers.replay import ReplayProvider
from srt_phase0.sources import FixtureSource
from srt_backend import config, db, security
from srt_backend.api.app import Deps, create_app
from srt_backend.services.delivery import FakeDelivery
from srt_backend.services.gmail import PartialGrant

P0 = Path(__file__).resolve().parents[2] / "phase0" / "fixtures"
FIXTURES, ANSWERS = P0 / "synthetic_emails.jsonl", P0 / "claude_answers_synthetic.jsonl"
A, B = "primary@example.com", "work@example.com"


class FakeGateway:
    def __init__(self):
        self.revoked = []

    def exchange_code(self, code):
        if code == "partial":
            raise PartialGrant("Gmail read access was not granted")
        return {"email": code, "token": {"token": "t", "refresh_token": "r"}}

    def source_for(self, account):
        return FixtureSource(FIXTURES, account.email)

    def start_watch(self, account):
        return {"historyId": "1", "expiration": "1893456000000"}

    def revoke(self, account):
        self.revoked.append(account.email)
        return True


class Clock:
    def __init__(self):
        self.now = dt.datetime(2026, 11, 5, 3, 0, tzinfo=dt.timezone.utc)

    def __call__(self):
        return self.now


@pytest.fixture
def env(tmp_path, monkeypatch):
    import os
    url = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path}/t.db"  # set to a Postgres URL to test that engine
    monkeypatch.setenv("DATABASE_URL", url)
    if url.startswith("postgresql"):
        from sqlalchemy import create_engine
        from srt_backend.db import Base
        eng = create_engine(url)
        Base.metadata.drop_all(eng)
        eng.dispose()
    config.reset_settings()
    security.set_cipher(security.LocalCipher())
    gw, delivery, clock = FakeGateway(), FakeDelivery(), Clock()
    app = create_app(Deps(gw, delivery, lambda: ReplayProvider(ANSWERS), clock))
    client = TestClient(app)
    yield client, gw, delivery, clock
    db.drop_all()
    security.set_cipher(None)
    config.reset_settings()


def login(client, email, token=None, accepted=True):
    h = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post("/v1/auth/google", headers=h, json={"server_auth_code": email,
                       "disclosure_version": "mail-disclosure-v2", "disclosure_accepted": accepted})


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


def by_merchant(client, tok):
    return {r["merchant"]["value"]: r for r in client.get("/v1/records", headers=H(tok)).json()["records"]}


def test_disclosure_must_be_accepted_and_partial_grant_refused(env):  # R1, flow #8
    client, *_ = env
    assert login(client, A, accepted=False).status_code == 400
    assert login(client, "partial").status_code == 403


def test_first_sync_builds_the_list(env):  # R2, R4, R5
    client, *_ = env
    tok = login(client, A).json()["session_token"]
    recs = by_merchant(client, tok)
    assert "StreamFlix" in recs and "TrustedBank" not in recs and "Promo Deals" not in recs
    assert recs["GymPass"]["state"] == "cancelled_confirmed"
    assert recs["PixelForge"]["state"] == "unknown_date"
    me = client.get("/v1/me", headers=H(tok)).json()
    assert me["accounts"][0]["sync_status"] == "done" and me["unknowns"] >= 1
    # never stores bodies: a body-only sentence must not be in the DB
    with db.session() as s:
        blob = " ".join(str(r.data) for r in s.scalars(select(db.ExtractionRow)))
    assert "Enjoy all Pro features" not in blob


def test_second_account_merges_and_disconnect_keeps_other_evidence(env):  # D16, decision #4, R1
    client, gw, *_ = env
    tok = login(client, A).json()["session_token"]
    work = login(client, B, token=tok).json()
    recs = by_merchant(client, tok)
    assert sorted(recs["VidMax"]["source_accounts"]) == [A, B] and "TuneBox" in recs
    assert client.post(f"/v1/accounts/{work['account_id']}/disconnect", headers=H(tok)).json()["token_revoked"]
    recs = by_merchant(client, tok)
    assert recs["VidMax"]["source_accounts"] == [A] and "TuneBox" not in recs
    assert gw.revoked == [B]


def test_alerts_scheduled_and_sent_at_9am_ist(env):  # R7, D13, decision #1
    client, gw, delivery, clock = env
    tok = login(client, A).json()["session_token"]
    client.post("/v1/push-tokens", headers=H(tok), json={"token": "ExponentPushToken[x]", "platform": "android"})
    clock.now = dt.datetime(2026, 11, 5, 3, 31, tzinfo=dt.timezone.utc)  # 09:01 IST on StreamFlix's T-0
    out = client.post("/internal/tick", headers={"X-Internal-Token": "dev-internal"}).json()
    assert out["sent"] >= 2
    assert any("StreamFlix" in p["title"] for p in delivery.pushes)
    assert any("StreamFlix" in e["subject"] for e in delivery.emails)  # e-mail for T-0, always
    assert client.post("/internal/tick", headers={"X-Internal-Token": "wrong"}).status_code == 403


def test_cancellation_flow(env):  # R8
    client, *_ = env
    tok = login(client, A).json()["session_token"]
    key = by_merchant(client, tok)["StreamFlix"]["record_key"]
    r = client.post(f"/v1/records/{key}/cancelled", headers=H(tok)).json()
    assert r["state"] == "cancellation_pending" and r["alerts_enabled"]
    assert client.post(f"/v1/records/{key}/force-confirm-cancel", headers=H(tok),
                       json={"acknowledged_no_merchant_confirmation": False}).status_code == 400
    r = client.post(f"/v1/records/{key}/force-confirm-cancel", headers=H(tok),
                    json={"acknowledged_no_merchant_confirmation": True}).json()
    assert r["state"] == "cancelled_user_confirmed" and not r["alerts_enabled"]


def test_unknowns_one_card_then_resolve(env):  # R6
    client, *_ = env
    tok = login(client, A).json()["session_token"]
    card = client.get("/v1/unknowns/next", headers=H(tok), params={"session_id": "s1"}).json()
    assert card["card"] and card["prompt"] == "We couldn't find a renewal date in this email"
    key = card["card"]["record_key"]
    out = client.post(f"/v1/unknowns/{key}/answer", headers=H(tok), json={"answer": "skip", "session_id": "s1"}).json()
    nxt = client.get("/v1/unknowns/next", headers=H(tok), params={"session_id": "s1"}).json()["card"]
    assert nxt is None or nxt["record_key"] != key
    out = client.post(f"/v1/unknowns/{key}/answer", headers=H(tok),
                      json={"answer": "date", "session_id": "s2", "date": "2026-12-01"}).json()
    assert out["record"]["state"] == "active" and out["record"]["next_charge_date"]["state"] == "confirmed"


def test_field_confirm_and_correct_reschedules(env):  # R5, 6.2
    client, *_ = env
    tok = login(client, A).json()["session_token"]
    key = by_merchant(client, tok)["StreamFlix"]["record_key"]
    r = client.post(f"/v1/records/{key}/fields/next_charge_date", headers=H(tok),
                    json={"action": "correct", "value": "2026-11-25"}).json()
    assert r["next_charge_date"]["value"] == "2026-11-25" and r["next_charge_date"]["state"] == "confirmed"
    with db.session() as s:
        dates = {a.target_date for a in s.scalars(select(db.Alert).where(db.Alert.status == "scheduled", db.Alert.record_key == key))}
    assert dates == {dt.date(2026, 11, 25)}


def test_not_a_subscription_and_manual_add(env):  # R4, R5
    client, *_ = env
    tok = login(client, A).json()["session_token"]
    key = by_merchant(client, tok)["CloudNote"]["record_key"]
    assert client.post(f"/v1/records/{key}/not-subscription", headers=H(tok)).json()["removed"]
    assert "CloudNote" not in by_merchant(client, tok)
    m = client.post("/v1/records/manual", headers=H(tok), json={"merchant": "Gym", "amount": 1500, "currency": "INR",
                    "billing_period": "monthly", "next_charge_date": "2026-11-30"}).json()
    assert m["state"] == "active" and m["merchant"]["state"] == "confirmed"


def test_delete_everything(env):  # R9
    client, gw, delivery, _ = env
    tok = login(client, A).json()["session_token"]
    assert client.delete("/v1/me", headers=H(tok)).json()["deleted"]
    assert client.get("/v1/records", headers=H(tok)).status_code == 401
    assert delivery.emails[-1]["subject"] == "Your data has been deleted"
    with db.session() as s:
        assert s.scalar(select(db.ExtractionRow)) is None and s.scalar(select(db.GmailAccount)) is None


def test_gmail_push_triggers_sync(env):  # R3
    import base64, json as _j
    client, *_ = env
    login(client, A)
    data = base64.b64encode(_j.dumps({"emailAddress": A, "historyId": 42}).encode()).decode()
    assert client.post("/pubsub/gmail", json={"message": {"data": data}}).json()["ok"]
    with db.session() as s:
        assert s.scalar(select(db.GmailAccount)).history_id == "42"


def test_tokens_encrypted_at_rest(env):  # R10
    client, *_ = env
    login(client, A)
    with db.session() as s:
        ct = s.scalar(select(db.GmailAccount)).token_ciphertext
    assert b"refresh_token" not in ct and b'"r"' not in ct


def test_new_receipt_without_alert_is_a_surprise_charge(env, tmp_path):  # M1, R3
    import json as _j
    client, gw, delivery, clock = env
    tok = login(client, A).json()["session_token"]
    body = ("Hi Anirudh,\nThank you for your payment.\nWe charged ₹649 for your StreamFlix Premium monthly plan on "
            "5 December 2026.\nYour next billing date is 5 January 2027.\n"
            "Manage or cancel your membership at https://streamflix.example/account/cancel\nStreamFlix Entertainment Pvt Ltd")
    new = {"message_id": "sf-12", "account": A, "from_name": "StreamFlix", "from_addr": "billing@streamflix.example",
           "subject": "Your StreamFlix receipt", "date": "2026-12-05T08:00:00+05:30", "body": body, "truth": {}}
    fx = tmp_path / "fx.jsonl"
    fx.write_text(FIXTURES.read_text() + _j.dumps(new, ensure_ascii=False) + "\n")
    gw.source_for = lambda account: FixtureSource(fx, account.email)
    s12 = "We charged ₹649 for your StreamFlix Premium monthly plan on 5 December 2026."
    ans = {"message_id": "sf-12", "triage": True, "extraction": {
        "is_subscription_related": True, "email_type": "receipt", "merchant": {"value": "StreamFlix", "quote": None},
        "kind": {"value": "subscription", "quote": s12}, "billing_period": {"value": "monthly", "period_months": None, "quote": s12},
        "amount": {"value": 649, "currency": "INR", "quote": s12}, "charge_date": {"value": "2026-12-05", "quote": s12},
        "next_charge_date": {"value": "2027-01-05", "quote": "Your next billing date is 5 January 2027."},
        "trial_end_date": {"value": None, "quote": None}, "trial_length_days": {"value": None, "quote": None},
        "cancel_path": {"value": None, "quote": None}}}
    af = tmp_path / "answers.jsonl"
    af.write_text(ANSWERS.read_text() + _j.dumps(ans, ensure_ascii=False) + "\n")
    client.app.state.deps.provider_factory = lambda: ReplayProvider(af)
    clock.now = dt.datetime(2026, 12, 6, 3, 0, tzinfo=dt.timezone.utc)  # no tick ran, so no December alert was sent
    import base64
    data = base64.b64encode(_j.dumps({"emailAddress": A, "historyId": 99}).encode()).decode()
    client.post("/pubsub/gmail", json={"message": {"data": data}})
    with db.session() as s:
        events = [e for e in s.scalars(select(db.Event).where(db.Event.type == "surprise_charge"))]
    assert any(e.data.get("reason") == "no_alert_delivered" for e in events)
    assert by_merchant(client, tok)["StreamFlix"]["next_charge_date"]["value"] == "2027-01-05"


# ---- Outlook (Microsoft Graph), push receipts ----------------------------------------------

class FakeMsGateway:
    def __init__(self):
        self.revoked, self.watches = [], 0

    def exchange_code(self, code, code_verifier, redirect_uri):
        if code == "partial":
            raise PartialGrant("Mail read access was not granted")
        assert code_verifier and redirect_uri
        return {"email": code, "token": {"access_token": "a", "refresh_token": "r", "expires_at": "2099-01-01T00:00:00+00:00"}}

    def source_for(self, account):
        return FixtureSource(FIXTURES, account.email)  # work@example.com fixtures stand in for an Outlook inbox

    def start_watch(self, account):
        self.watches += 1
        return {"id": "sub-1", "expiration": "2026-11-08T00:00:00Z", "clientState": "secret-1"}

    def revoke(self, account):
        self.revoked.append(account.email)
        return True


def ms_login(client, email, token=None):
    h = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post("/v1/auth/microsoft", headers=h, json={"code": email, "code_verifier": "v" * 43,
                       "redirect_uri": "renewaltracker://auth", "disclosure_version": "mail-disclosure-v2",
                       "disclosure_accepted": True})


@pytest.fixture
def env_ms(env, monkeypatch):
    client, gw, delivery, clock = env
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://api.example")
    config.reset_settings()
    ms = FakeMsGateway()
    client.app.state.deps.ms_gateway = ms
    return client, gw, ms, delivery, clock


def test_outlook_account_joins_gmail_user_and_merges(env_ms):  # D16 across providers
    client, gw, ms, *_ = env_ms
    assert ms_login(client, "partial").status_code == 403  # flow #8
    tok = login(client, A).json()["session_token"]
    out = ms_login(client, B, token=tok).json()
    assert out["provider"] == "outlook"
    recs = by_merchant(client, tok)
    assert sorted(recs["VidMax"]["source_accounts"]) == [A, B]
    me = client.get("/v1/me", headers=H(tok)).json()
    assert {a["provider"] for a in me["accounts"]} == {"gmail", "outlook"}
    assert ms.watches == 1  # Graph change subscription created after first sync (R3)
    client.post(f"/v1/accounts/{out['account_id']}/disconnect", headers=H(tok))
    assert ms.revoked == [B] and "TuneBox" not in by_merchant(client, tok)


def test_graph_notification_handshake_and_client_state(env_ms):
    client, gw, ms, *_ = env_ms
    tok = login(client, A).json()["session_token"]
    ms_login(client, B, token=tok)
    r = client.post("/graph/notify?validationToken=abc123")
    assert r.status_code == 200 and r.text == "abc123" and r.headers["content-type"].startswith("text/plain")
    def syncs():
        with db.session() as s:
            return len(list(s.scalars(select(db.Event).where(db.Event.type == "sync"))))
    n0 = syncs()
    client.post("/graph/notify", json={"value": [{"subscriptionId": "sub-1", "clientState": "forged"}]})
    assert syncs() == n0  # forged clientState is ignored
    client.post("/graph/notify", json={"value": [{"subscriptionId": "sub-1", "clientState": "secret-1"}]})
    assert syncs() == n0 + 1  # genuine notification triggers an incremental sync (R3)


def test_push_receipts_promote_to_delivered(env):  # M5
    client, gw, delivery, clock = env
    tok = login(client, A).json()["session_token"]
    client.post("/v1/push-tokens", headers=H(tok), json={"token": "ExponentPushToken[x]", "platform": "ios"})
    clock.now = dt.datetime(2026, 11, 5, 3, 31, tzinfo=dt.timezone.utc)
    client.post("/internal/tick", headers={"X-Internal-Token": "dev-internal"})
    clock.now = dt.datetime(2026, 11, 5, 3, 50, tzinfo=dt.timezone.utc)
    out = client.post("/internal/tick", headers={"X-Internal-Token": "dev-internal"}).json()
    assert out["receipts"]["delivered"] >= 1
    with db.session() as s:
        assert s.scalar(select(db.Alert).where(db.Alert.channel == "push", db.Alert.status == "delivered")) is not None


def test_card_alert_emails_reveal_a_silent_subscription(env, tmp_path):  # D4 amended: bank/card alert e-mails
    import json as _j
    client, gw, delivery, clock = env
    rows, answers = [], []
    for i, (d, human) in enumerate([("2026-08-08", "08-08-2026"), ("2026-09-08", "08-09-2026"), ("2026-10-08", "08-10-2026")]):
        line = f"Rs.189.00 spent on your Credit Card XX1234 at GOOGLE*YOUTUBE on {human}."
        rows.append({"message_id": f"bank-{i}", "account": "bank@example.com", "from_name": "HDFC Bank",
                     "from_addr": "alerts@hdfcbank.example", "subject": "Alert: transaction on your credit card",
                     "date": d + "T14:00:00+05:30", "body": f"Dear Customer,\n{line}\nNot you? Call us.", "truth": {}})
        answers.append({"message_id": f"bank-{i}", "triage": True, "extraction": {
            "is_subscription_related": True, "email_type": "card_transaction", "merchant": {"value": "GOOGLE*YOUTUBE", "quote": line},
            "kind": {"value": None, "quote": None}, "billing_period": {"value": None, "period_months": None, "quote": None},
            "amount": {"value": 189.0, "currency": "INR", "quote": line}, "charge_date": {"value": d, "quote": line},
            "next_charge_date": {"value": None, "quote": None}, "trial_end_date": {"value": None, "quote": None},
            "trial_length_days": {"value": None, "quote": None}, "cancel_path": {"value": None, "quote": None},
            "reference": {"value": None, "quote": None}}})
    fx, af = tmp_path / "bank.jsonl", tmp_path / "bank-answers.jsonl"
    fx.write_text("".join(_j.dumps(r) + "\n" for r in rows))
    af.write_text("".join(_j.dumps(a) + "\n" for a in answers))
    gw.source_for = lambda account: FixtureSource(fx, account.email)
    client.app.state.deps.provider_factory = lambda: ReplayProvider(af)
    tok = login(client, "bank@example.com").json()["session_token"]
    recs = client.get("/v1/records", headers=H(tok)).json()["records"]
    assert len(recs) == 1
    r = recs[0]
    assert r["merchant"]["value"] == "GOOGLE*YOUTUBE" and r["state"] == "active"
    assert r["billing_period"]["value"] == "monthly" and r["billing_period"]["state"] == "estimated"
    assert r["next_charge_date"]["value"] == "2026-11-08" and r["next_charge_date"]["state"] == "estimated"

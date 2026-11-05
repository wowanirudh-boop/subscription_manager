"""HTTP API for the mobile app, Gmail push, and the scheduler tick."""


import base64
import datetime as dt
import json
from typing import Callable, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from srt_phase0.merge import merchant_key
from srt_phase0.models import BillingPeriod, FieldState
from srt_phase0.providers import get_provider

from .. import db
from ..config import settings
from ..db import (Alert, Consent, ExtractionRow, GmailAccount, ManualRecord, PushToken, SupportAccessLog,
                  SuppressedMerchant, User)
from ..domain import unknowns
from ..domain.lifecycle import Notice, State
from ..security import issue_session, verify_session
from ..services import alerts_service, ingest
from ..services.delivery import Delivery, FakeDelivery, RealDelivery
from ..services.gmail import GmailGateway, GoogleGateway, PartialGrant, store_token, watch_due
from ..services.records import build_views, find_view, log_event, save_state

EDITABLE = {"merchant", "amount", "currency", "billing_period", "next_charge_date", "trial_end_date", "last_charge_date"}


class Deps:
    def __init__(self, gateway: GmailGateway, delivery: Delivery, provider_factory: Callable, clock: Callable[[], dt.datetime]):
        self.gateway, self.delivery, self.provider_factory, self.clock = gateway, delivery, provider_factory, clock


def create_app(deps: Optional[Deps] = None) -> FastAPI:
    s = settings()
    db.init(s.database_url)
    deps = deps or Deps(GoogleGateway(), RealDelivery() if s.smtp_host else FakeDelivery(),
                        lambda: get_provider(s.provider), lambda: dt.datetime.now(dt.timezone.utc))
    app = FastAPI(title="Subscription Renewal Tracker API", version="0.1.0")
    app.state.deps = deps

    def get_db():
        session = db.session()
        try:
            yield session
        finally:
            session.close()

    def current_user(authorization: str = Header(default=""), s: Session = Depends(get_db)) -> User:
        if not authorization.startswith("Bearer "):
            raise HTTPException(401, "missing session")
        try:
            uid = verify_session(authorization[7:])
        except Exception:
            raise HTTPException(401, "invalid session")
        user = s.get(User, uid)
        if not user:
            raise HTTPException(401, "unknown user")
        return user

    def today() -> dt.date:
        return deps.clock().astimezone(dt.timezone(dt.timedelta(hours=5, minutes=30))).date()  # IST (D2)

    def run_sync(user_id: int, account_id: int, first: bool) -> None:
        session = db.session()
        try:
            user, acct = session.get(User, user_id), session.get(GmailAccount, account_id)
            if not user or not acct:
                return
            ingest.sync_account(session, user, acct, deps.gateway.source_for(acct), deps.provider_factory(),
                                deps.clock(), deps.delivery, first_sync=first)
            if watch_due(acct, deps.clock()) and settings().pubsub_topic:
                w = deps.gateway.start_watch(acct)
                acct.history_id = str(w.get("historyId"))
                acct.watch_expires_at = dt.datetime.fromtimestamp(int(w["expiration"]) / 1000, dt.timezone.utc)
                session.commit()
        except Exception as e:  # noqa: BLE001
            session.rollback()
            acct = session.get(GmailAccount, account_id)
            if acct:
                acct.sync_status = "error"
                log_event(session, user_id, "sync_error", None, error=str(e)[:300])
                session.commit()
        finally:
            session.close()

    # ---- auth & accounts (R1) --------------------------------------------------------------

    class GoogleAuthIn(BaseModel):
        server_auth_code: str
        disclosure_version: str
        disclosure_accepted: bool  # affirmative tap on the in-app disclosure, immediately before OAuth

    @app.post("/v1/auth/google")
    def auth_google(body: GoogleAuthIn, bg: BackgroundTasks, authorization: str = Header(default=""),
                    s: Session = Depends(get_db)):
        if not body.disclosure_accepted or body.disclosure_version != settings().disclosure_version:
            raise HTTPException(400, "the current disclosure must be accepted first")
        try:
            got = deps.gateway.exchange_code(body.server_auth_code)
        except PartialGrant as e:
            raise HTTPException(403, str(e))
        user = None
        if authorization.startswith("Bearer "):  # adding a second account (D16)
            user = s.get(User, verify_session(authorization[7:]))
        if user is None:
            acct = s.scalar(select(GmailAccount).where(GmailAccount.email == got["email"]))
            user = s.get(User, acct.user_id) if acct else s.scalar(select(User).where(User.email == got["email"]))
        if user is None:
            user = User(email=got["email"])
            s.add(user)
            s.flush()
        acct = s.scalar(select(GmailAccount).where(GmailAccount.user_id == user.id, GmailAccount.email == got["email"]))
        if acct is None:
            acct = GmailAccount(user_id=user.id, email=got["email"], token_ciphertext=b"")
            s.add(acct)
        store_token(acct, got["token"])
        s.add(Consent(user_id=user.id, kind="gmail_disclosure", version=body.disclosure_version, detail=got["email"]))
        s.commit()
        bg.add_task(run_sync, user.id, acct.id, acct.last_synced_at is None)
        return {"session_token": issue_session(user.id), "user_id": user.id, "account_id": acct.id, "email": acct.email}

    @app.get("/v1/me")
    def me(user: User = Depends(current_user), s: Session = Depends(get_db)):
        accts = s.scalars(select(GmailAccount).where(GmailAccount.user_id == user.id))
        views, _ = build_views(s, user, today())
        return {"email": user.email, "tz": user.tz,
                "accounts": [{"id": a.id, "email": a.email, "sync_status": a.sync_status, "matched": a.sync_matched,
                              "processed": a.sync_processed, "last_synced_at": a.last_synced_at} for a in accts],
                "unknowns": len(unknowns.queue(views))}

    @app.post("/v1/accounts/{account_id}/disconnect")
    def disconnect(account_id: int, user: User = Depends(current_user), s: Session = Depends(get_db)):
        acct = s.get(GmailAccount, account_id)
        if not acct or acct.user_id != user.id:
            raise HTTPException(404)
        revoked = deps.gateway.revoke(acct)
        # Records, evidence and token deleted now (R1 requires <= 24 h). Decision #4: a record merged from
        # two accounts survives with the other account's evidence, because records are rebuilt from what remains.
        for row in s.scalars(select(ExtractionRow).where(ExtractionRow.account_id == acct.id)):
            s.delete(row)
        s.delete(acct)
        s.flush()
        alerts_service.reschedule(s, user, build_views(s, user, today())[0], deps.clock())
        log_event(s, user.id, "account_disconnected", None, revoked=revoked)
        s.commit()
        return {"disconnected": True, "token_revoked": revoked}

    @app.delete("/v1/me")
    def delete_me(user: User = Depends(current_user), s: Session = Depends(get_db)):
        revoked = [deps.gateway.revoke(a) for a in s.scalars(select(GmailAccount).where(GmailAccount.user_id == user.id))]
        email = user.email
        for model in (Alert, ExtractionRow, ManualRecord, PushToken, SuppressedMerchant, SupportAccessLog, Consent):
            for row in s.scalars(select(model).where(model.user_id == user.id)):
                s.delete(row)
        from ..db import Event, RecordStateRow
        for model in (RecordStateRow, GmailAccount):
            for row in s.scalars(select(model).where(model.user_id == user.id)):
                s.delete(row)
        for ev in s.scalars(select(Event).where(Event.user_id == user.id)):
            ev.user_id = None  # aggregated metrics keep no link to the person
        s.delete(user)
        s.commit()
        try:
            deps.delivery.email(email, "Your data has been deleted",
                                "All your subscription records, evidence and Gmail tokens have been deleted.")
        except Exception:  # noqa: BLE001
            pass
        return {"deleted": True, "tokens_revoked": sum(revoked)}  # R9: confirmation to the user

    # ---- records (R5, R8) --------------------------------------------------------------------

    def view_json(v):
        return v.model_dump(mode="json")

    @app.get("/v1/records")
    def records(user: User = Depends(current_user), s: Session = Depends(get_db)):
        views, _ = build_views(s, user, today())
        return {"records": [view_json(v) for v in views], "unknowns": len(unknowns.queue(views))}

    def _get(s, user, key):
        v, st = find_view(s, user, key, today())
        if not v:
            raise HTTPException(404, "record not found")
        return v, st

    @app.get("/v1/records/{key}")
    def record(key: str, user: User = Depends(current_user), s: Session = Depends(get_db)):
        return view_json(_get(s, user, key)[0])

    class FieldIn(BaseModel):
        action: str  # confirm | correct
        value: Optional[object] = None

    @app.post("/v1/records/{key}/fields/{field}")
    def edit_field(key: str, field: str, body: FieldIn, user: User = Depends(current_user), s: Session = Depends(get_db)):
        if field not in EDITABLE:
            raise HTTPException(400, "field not editable")
        v, st = _get(s, user, key)
        if body.action == "confirm":  # estimated -> confirmed is a user action only (6.2)
            cur = getattr(v, field)
            if not cur.known:
                raise HTTPException(400, "nothing to confirm")
            st.overrides[field] = cur.value.isoformat() if hasattr(cur.value, "isoformat") else (
                cur.value.value if hasattr(cur.value, "value") else cur.value)
        elif body.action == "correct":
            if field == "billing_period":
                BillingPeriod(body.value)
            st.overrides[field] = body.value
            if field == "next_charge_date":
                st.overrides.pop("_estimated_next", None)
        else:
            raise HTTPException(400, "action must be confirm or correct")
        save_state(s, user.id, key, st)
        return _commit_and_view(s, user, key)

    def _commit_and_view(s, user, key):
        s.flush()
        views, _ = build_views(s, user, today())
        alerts_service.reschedule(s, user, views, deps.clock())  # R7: correcting a date reschedules
        s.commit()
        v = next((x for x in views if x.record_key == key), None)
        return view_json(v) if v else {"record_key": key, "removed": True}

    @app.post("/v1/records/{key}/cancelled")
    def i_cancelled(key: str, user: User = Depends(current_user), s: Session = Depends(get_db)):
        v, st = _get(s, user, key)
        st.cancel_requested_at = deps.clock()  # -> cancellation_pending; alerts continue (R8)
        save_state(s, user.id, key, st)
        log_event(s, user.id, "user_cancelled", key)
        return _commit_and_view(s, user, key)

    class ForceIn(BaseModel):
        acknowledged_no_merchant_confirmation: bool

    @app.post("/v1/records/{key}/force-confirm-cancel")
    def force_confirm(key: str, body: ForceIn, user: User = Depends(current_user), s: Session = Depends(get_db)):
        v, st = _get(s, user, key)
        if v.state != State.CANCELLATION_PENDING:
            raise HTTPException(409, "only a pending cancellation can be force-confirmed")
        if not body.acknowledged_no_merchant_confirmation:
            raise HTTPException(400, "the no-merchant-confirmation warning must be acknowledged")
        st.user_confirmed_cancel_at = deps.clock()
        save_state(s, user.id, key, st)
        return _commit_and_view(s, user, key)

    @app.post("/v1/records/{key}/confirm-cancelled")
    def confirm_likely(key: str, user: User = Depends(current_user), s: Session = Depends(get_db)):
        v, st = _get(s, user, key)
        if v.state != State.LIKELY_CANCELLED:
            raise HTTPException(409, "record is not 'likely cancelled'")
        st.user_confirmed_cancel_at = deps.clock()  # D26 one-tap confirm
        save_state(s, user.id, key, st)
        return _commit_and_view(s, user, key)

    class ResubIn(BaseModel):
        resubscribed: bool

    @app.post("/v1/records/{key}/resubscribe")
    def resubscribe(key: str, body: ResubIn, user: User = Depends(current_user), s: Session = Depends(get_db)):
        v, st = _get(s, user, key)
        if Notice.RESUBSCRIBE_QUESTION not in v.notices or not v.pending_receipt_at:
            raise HTTPException(409, "no open re-subscribe question")
        st.resubscribe_answers[v.pending_receipt_at.isoformat()] = body.resubscribed
        save_state(s, user.id, key, st)
        if not body.resubscribed:
            log_event(s, user.id, "surprise_charge", key, reason="resubscribe_no")  # M1 includes "No" answers
        out = _commit_and_view(s, user, key)
        out["show_cancel_path"] = not body.resubscribed
        return out

    @app.post("/v1/records/{key}/not-subscription")
    def not_subscription(key: str, user: User = Depends(current_user), s: Session = Depends(get_db)):
        v, st = _get(s, user, key)
        st.suppressed = True
        save_state(s, user.id, key, st)
        if v.merchant.known:
            mk = merchant_key(v.merchant.value)
            if not s.scalar(select(SuppressedMerchant).where(SuppressedMerchant.user_id == user.id,
                                                             SuppressedMerchant.merchant_key == mk)):
                s.add(SuppressedMerchant(user_id=user.id, merchant_key=mk))
        log_event(s, user.id, "false_positive", key)  # M3
        return _commit_and_view(s, user, key)

    class MuteIn(BaseModel):
        muted: bool

    @app.post("/v1/records/{key}/mute")
    def mute(key: str, body: MuteIn, user: User = Depends(current_user), s: Session = Depends(get_db)):
        v, st = _get(s, user, key)
        st.muted = body.muted
        save_state(s, user.id, key, st)
        return _commit_and_view(s, user, key)

    class ManualIn(BaseModel):
        merchant: str
        amount: Optional[float] = None
        currency: Optional[str] = "INR"
        billing_period: BillingPeriod
        next_charge_date: Optional[dt.date] = None
        kind: str = "subscription"

    @app.post("/v1/records/manual")
    def manual(body: ManualIn, user: User = Depends(current_user), s: Session = Depends(get_db)):
        row = ManualRecord(user_id=user.id, data=body.model_dump(mode="json"))
        s.add(row)
        s.flush()
        log_event(s, user.id, "manual_add", f"manual-{row.id}")  # M2 proxy
        return _commit_and_view(s, user, f"manual-{row.id}")

    # ---- unknowns (R6) ------------------------------------------------------------------------

    @app.get("/v1/unknowns/next")
    def next_unknown(session_id: str, user: User = Depends(current_user), s: Session = Depends(get_db)):
        views, states = build_views(s, user, today())
        card = unknowns.next_card(views, states, session_id)
        return {"card": view_json(card) if card else None, "remaining": len(unknowns.queue(views)),
                "prompt": "We couldn't find a renewal date in this email"}

    class AnswerIn(BaseModel):
        answer: str
        session_id: str
        date: Optional[dt.date] = None

    @app.post("/v1/unknowns/{key}/answer")
    def answer_unknown(key: str, body: AnswerIn, user: User = Depends(current_user), s: Session = Depends(get_db)):
        v, st = _get(s, user, key)
        try:
            out = unknowns.apply_answer(v, st, body.answer, body.session_id, body.date, today())
        except ValueError as e:
            raise HTTPException(400, str(e))
        save_state(s, user.id, key, st)
        if out["event"]:
            log_event(s, user.id, out["event"], key)
        if body.answer == unknowns.Answer.NOT_SUBSCRIPTION and v.merchant.known:
            s.add(SuppressedMerchant(user_id=user.id, merchant_key=merchant_key(v.merchant.value)))
        rec = _commit_and_view(s, user, key)
        return {"needs_date": out["needs_date"], "record": rec}

    class TapIn(BaseModel):
        date: dt.date

    @app.post("/v1/unknowns/{key}/tap-date")
    def tap_date(key: str, body: TapIn, user: User = Depends(current_user), s: Session = Depends(get_db)):
        v, st = _get(s, user, key)
        out = unknowns.tapped_date_in_snippet(st, body.date)
        save_state(s, user.id, key, st)
        log_event(s, user.id, out["event"], key)
        return _commit_and_view(s, user, key)

    # ---- push, alerts, support ----------------------------------------------------------------

    class PushIn(BaseModel):
        token: str
        platform: str = Field(pattern="^(ios|android)$")

    @app.post("/v1/push-tokens")
    def push_token(body: PushIn, user: User = Depends(current_user), s: Session = Depends(get_db)):
        if not s.scalar(select(PushToken).where(PushToken.user_id == user.id, PushToken.token == body.token)):
            s.add(PushToken(user_id=user.id, token=body.token, platform=body.platform))
            s.commit()
        return {"ok": True}

    @app.post("/v1/alerts/{alert_id}/opened")
    def alert_opened(alert_id: int, user: User = Depends(current_user), s: Session = Depends(get_db)):
        a = s.get(Alert, alert_id)
        if not a or a.user_id != user.id:
            raise HTTPException(404)
        log_event(s, user.id, "alert_opened", a.record_key, channel=a.channel, days_before=a.days_before)  # M5
        s.commit()
        return {"ok": True}

    class SupportIn(BaseModel):
        reason: str
        hours: int = Field(default=24, ge=1, le=72)

    @app.post("/v1/support/consent")
    def support_consent(body: SupportIn, user: User = Depends(current_user), s: Session = Depends(get_db)):
        c = Consent(user_id=user.id, kind="support_access", version="v1", detail=body.reason,
                    expires_at=deps.clock() + dt.timedelta(hours=body.hours))
        s.add(c)
        s.commit()
        return {"consent_id": c.id, "expires_at": c.expires_at}

    # ---- Gmail push + scheduler (R3, R7) ------------------------------------------------------

    @app.post("/pubsub/gmail")
    async def gmail_push(request: Request, bg: BackgroundTasks, s: Session = Depends(get_db)):
        _verify_pubsub(request)
        envelope = await request.json()
        data = json.loads(base64.b64decode(envelope["message"]["data"]))
        acct = s.scalar(select(GmailAccount).where(GmailAccount.email == data["emailAddress"].lower()))
        if acct:
            acct.history_id = str(data.get("historyId"))
            s.commit()
            bg.add_task(run_sync, acct.user_id, acct.id, False)  # R3: processed within minutes (D27)
        return {"ok": True}  # always 2xx so Pub/Sub does not redeliver for unknown accounts

    @app.post("/internal/tick")
    def internal_tick(bg: BackgroundTasks, x_internal_token: str = Header(default=""), s: Session = Depends(get_db)):
        if x_internal_token != settings().internal_token:
            raise HTTPException(403)
        now = deps.clock()
        result = alerts_service.tick(s, now, deps.delivery)
        s.commit()
        renew = 0
        for acct in s.scalars(select(GmailAccount)):
            if watch_due(acct, now):
                # Lapsed or expiring watch: catch-up sync from last processed time, then re-watch (R3).
                bg.add_task(run_sync, acct.user_id, acct.id, acct.last_synced_at is None)
                renew += 1
        return {**result, "watch_renewals": renew}

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "region": settings().region}

    def _verify_pubsub(request: Request) -> None:
        st = settings()
        if not st.pubsub_audience:
            return  # development
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            raise HTTPException(401)
        from google.auth.transport import requests as greq
        from google.oauth2 import id_token as gid

        claims = gid.verify_oauth2_token(auth[7:], greq.Request(), audience=st.pubsub_audience)
        if st.pubsub_service_account and claims.get("email") != st.pubsub_service_account:
            raise HTTPException(403)

    return app

# Backend — Phase 1 (private beta)

Python/FastAPI service for the Subscription Renewal Tracker. It reuses the Phase 0 pipeline (`../phase0`) for detection and extraction, and adds accounts, the lifecycle engine, alerts and data controls. Target: Cloud Run + Cloud SQL (PostgreSQL) in **asia-south1 (Mumbai)** (R9).

## Design in one paragraph

The database stores **e-mail facts** (extracted fields + one evidence sentence per field, never bodies) and **user actions** ("I cancelled", corrections, mute, answers). Everything the user sees is **derived on read** by `domain/lifecycle.py`, combining merged facts, actions and today's date. A late e-mail, a disconnected account or a corrected date can't leave a record stale, and every rule is a pure function with tests.

## Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ./phase0 -e "./backend[test]"
cd backend && python -m pytest -q                                  # 35 tests, SQLite
TEST_DATABASE_URL=postgresql+psycopg://user@host/db python -m pytest -q   # same tests on PostgreSQL
uvicorn srt_backend.main:app --reload                              # dev server; EXTRACTION_PROVIDER=fake by default
```

## PRD v1.1 traceability (P0)

| Req | What | Where | Tests |
|---|---|---|---|
| R1 | Read-only OAuth; affirmative disclosure before handoff; multiple accounts; disconnect revokes and deletes | `api/app.py` `/v1/auth/google`, `/v1/accounts/{id}/disconnect`; `services/gmail.py`; app `disclosure.tsx` | `test_disclosure_must_be_accepted…`, `test_second_account_merges_and_disconnect…` |
| R2 | First sync: 24 months, newest first, progressive results | `services/ingest.py` (background task); `queries.build_app_queries` | `test_first_sync_builds_the_list` |
| R3 | Gmail Pub/Sub watch; renew before 7-day expiry; catch-up on lapse | `/pubsub/gmail` (OIDC-verified), `/internal/tick` → `watch_due` | `test_gmail_push_triggers_sync`, `test_new_receipt_without_alert_is_a_surprise_charge` |
| R4 | Funnel stages 1/3/4/5; evidence-verified field states; merge; "not a subscription" | Phase 0 pipeline + `SuppressedMerchant` | Phase 0 suite (59) + `test_not_a_subscription_and_manual_add` |
| R5 | One merged list sorted by date (unknowns last); evidence on tap; correct/confirm; manual add | `services/records.py`, `/v1/records*` | `test_field_confirm_and_correct_reschedules` |
| R6 | Unknowns queue by damage; one card; skip until next session; period answer → estimated date | `domain/unknowns.py`, `/v1/unknowns/*` | `test_queue_order_by_damage`, `test_unknowns_one_card_then_resolve` |
| R7 | Ladder (monthly T−1/T−0, else T−7/3/1/0); push all steps, e-mail T−1/T−0 always; mute; reschedule | `domain/alerts.py`, `services/alerts_service.py` | `test_monthly_ladder…`, `test_alerts_scheduled_and_sent_at_9am_ist` |
| R8 | "I cancelled" → pending with alerts; merchant e-mail confirms; likely cancelled; force-confirm with warning; reactivation question | `domain/lifecycle.py`, record endpoints | `test_lifecycle.py` (13), `test_cancellation_flow` |
| R9 | India region; delete account; no bodies stored; support access only with logged consent | `config.region`, `DELETE /v1/me`, `SupportAccessLog` | `test_delete_everything`, body-leak assertion in `test_first_sync…` |
| R10 | Tokens envelope-encrypted with Cloud KMS; prompt-injection defences; ZDR provider routing | `security.py`, Phase 0 `prompts.py` / `verify.py` | `test_tokens_encrypted_at_rest` |
| M1–M8 | Events: `surprise_charge`, `false_positive`, `alert_sent/failed/opened`, `unknown_resolved`, `manual_add`, `sync` (with model usage) | `events` table | `test_new_receipt_without_alert_is_a_surprise_charge` |

## Flow decisions encoded (adopted 5 Nov 2026)

1. **Alert time:** alerts go out at 09:00 local time (`alerts.SEND_HOUR`, IST).
2. **No receipt by the expected date:** the record stays active, the next date rolls forward as *estimated*, and a "no receipt seen" notice shows. A real merchant in the Phase 0 run charges monthly and never e-mails.
3. **Charge while cancellation is pending:** the record goes back to active and the user gets an immediate push. It isn't an M1 surprise if an alert was delivered.
4. **Disconnecting one of two accounts:** records are rebuilt from the remaining evidence, so a merged record survives.
5. **Late receipts:** "no receipt" is judged at the expected date + 3 days.
6. **PDF attachments:** page 1 of a PDF is read only when the body has no amount (Phase 0 pipeline).
7. **Unanswered re-subscribe question:** tracking resumes and the question stays on the record. M1 is counted on a "No" answer.
8. **Partial OAuth grant:** treated as no grant. The token is revoked and nothing is stored.

## Known gaps (not done, or not verifiable here)

- **Production model untested.** `EXTRACTION_PROVIDER=openrouter` is wired, but no cheap model has run on real mail: openrouter.ai is blocked from the build environment. Q2 and M8 cost remain open. Run Phase 0 with the chosen model before the beta.
- **D29 timings are unmeasured on real Gmail with a real model** (first result ≤ 30 s; ≤ 2,000 matches in ≤ 10 min). First sync runs as a FastAPI background task on one Cloud Run instance (`--min-instances 1 --no-cpu-throttling`). That's fine for a ≤ 100-user beta; move it to Cloud Tasks for scale.
- **M5 delivery:** M5 counts Expo push *tickets*, not delivery receipts. Receipts aren't polled yet.
- **Several subscriptions from one merchant** (e.g. several insurance policies paid through one biller) merge into one record.
- **Silent merchants** (no e-mails) can only be added manually. The disclosure says so.
- **Not built here:** privacy policy and Limited Use page (need the domain, D31), Google verification and CASA (R10/§10), and app-store listings.
- **Not run here:** no Docker daemon was available, so the image wasn't built. Its install was replicated in a clean venv and the server ran on PostgreSQL 16.

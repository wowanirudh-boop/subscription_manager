# Subscription Renewal Tracker — PRD v1.1

**Working title:** Subscription Renewal Tracker (name deferred — see D31)
**Status:** Draft 1.1 — supersedes v1
**Date:** 6 September 2026
**Author:** Anirudh (drafted with Claude)

---

## 0. How to read this document

- Every decision was made explicitly in the scoping conversation. Section 1 lists all of them; nothing else in this document introduces a new choice.
- Items marked **[verify]** are factual claims that should be checked before they're relied on.
- P0 = cannot ship without it. P1 = fast follow. P2 = design for it, do not build it.
- Changes from v1 are summarised in Section 15.

---

## 1. Decisions log

| # | Decision |
|---|----------|
| D1 | Core value is a **warning before a recurring charge**, not a subscription list. The list is the means. |
| D2 | **MVP is India-only.** Global is not a v1 constraint; global-readiness is explicitly dropped to move faster (see D30 for what that means concretely). |
| D3 | v1 catches **all recurring charges**: free trials that convert, active paid subscriptions, and non-subscription renewals (domains, insurance, annual fees). |
| D4 | **Email is the only data source.** No bank, card, SMS, UPI-app, or app-store data. |
| D5 | The product **never asserts a value it did not read or derive**. Three field states: confirmed / estimated / unknown. |
| D6 | A date derivable from stated facts (last charge + billing period) is **estimated**: shown with a tag, user-correctable, alerts fire on it. |
| D7 | A date that cannot be read or derived is **unknown**: no alert until the user resolves it (via D22). |
| D8 | Gmail access via **our own OAuth app**, `gmail.readonly` only, **CASA assessment done by us**. |
| D9 | Alerts enable both a **cancel path** (link/instructions from the merchant's email) and an **"I cancelled"** action. |
| D10 | Cancellation is **confirmed only by a merchant cancellation email**, or by the user's explicit force-confirm after a warning. |
| D11 | If no cancellation email arrives and the expected charge date passes with no receipt → **likely cancelled** (see D26 for the full rule). |
| D12 | **Mobile app, iOS + Android, push notifications.** |
| D13 | **Email fallback is mandatory for the 1-day and 0-day alerts**, sent from our servers to the user's own address. Confirmed. |
| D14 | First sync scans the **last 24 months**. |
| D15 | After first sync, the product **listens via Gmail push (Pub/Sub watch)** with auto-renewal and catch-up scan on lapse. Confirmed. |
| D16 | **Multiple Gmail accounts** per user, **merged into one list**. |
| D17 | **Primary metric: surprise charges.** Eight metrics defined in Section 9. |
| D18 | **Free in v1.** No monetization decisions. |
| D19 | Alert ladder: **annual + trials 7/3/1/0 days; monthly 1/0 days.** |
| D20 | **All trials use the 7/3/1/0 ladder** regardless of what they convert to. Confirmed. |
| D21 | **One data model**; billing period is a field; only alert cadence differs. Confirmed. |
| D22 | Unknowns are resolved **one at a time in a bottom sheet** showing the email evidence, asking for the **billing period (one tap), not the date**; queue **sorted by damage**; **one card per session**. |
| D23 | Extraction runs **server-side via an LLM in v1**; on-device is P2; extraction is a swappable module. No BYO subscription or BYO API key. |
| D24 | **Funnel for v1: stages 1, 3, 4, 5** (Gmail search → cheap triage → LLM extraction → learned per-sender templates). **Stage 2 (billing-platform templates) is P1.** |
| D25 | **Phase 0 harness is Codex.** Inference provider / hosting for production is **deferred**; Phase 0 measures recall/precision, not cost, until a production candidate is run. |
| D26 | **Likely cancelled** is a separate state with a one-tap **"Confirm it's cancelled"** → cancelled (user-confirmed). Nothing is ever deleted: a later receipt from that merchant **reactivates** the record and the app asks "Did you re-subscribe?" (Yes → normal; No → surprise charge). |
| D27 | New relevant emails are processed **within 5 minutes** of arrival. |
| D28 | **Any non-monthly or unknown period uses the 7/3/1/0 ladder.** |
| D29 | First sync: **first result ≤ 30 s** (newest-first); **≤ 2,000 matched emails complete in ≤ 10 min**; larger inboxes show progress and set expectations. |
| D30 | **Single region, hosted in India.** Concretely, "drop global-readiness" means: INR default; foreign amounts shown in the stated currency with **no conversion** (foreign-merchant charges stay in scope — they are the founding incident); English-only extraction acceptable; no per-country data plumbing; no country tag. |
| D31 | **App name and website are done after Phase 0 succeeds**, not in parallel. Placeholder name until then. |

---

## 2. Problem statement

People sign up for free trials and subscriptions, forget them, and are charged — sometimes a year later, sometimes a large amount — with no warning they could act on. The merchant's sign-up email is often the only record, and it rarely contains a renewal reminder.

**India-specific sharpening.** For recurring card payments set up as mandates, RBI rules require the card issuer to send a pre-debit notification before the charge **[verify — moderate-high confidence]**. So Indian users already get some warning for domestic mandated charges. Where they get none is: foreign merchants billing an international card directly (the founding incident), app-store subscriptions, trials converting to paid, and any recurring charge not set up as a mandate. That is the product's target.

**Evidence:** one founder incident. No user research yet (Q1).

---

## 3. Target user

An adult in India who uses Gmail (one or more accounts) as the inbox where sign-up and receipt emails land, has a payment card on file with online services (including foreign ones), and has signed up for at least one free trial or recurring plan in the last 24 months.

**Not the v1 user:** people whose receipts land in non-Gmail inboxes; subscriptions with no email trail (SMS/UPI-app only); businesses managing team subscriptions; users outside India.

**Stated limitation (A1, R1):** merchants that send no email are invisible to this product.

---

## 4. Goals

1. **No surprise charges** for anything the product can see (M1).
2. **An honest list** — every field labelled confirmed / estimated / unknown; the user is never shown a guess as a fact.
3. **Cancel with confidence** — the product keeps warning until the merchant confirms, and tells the user which it is.
4. **Earn and keep Gmail restricted-scope approval** (annual CASA). Without it the product is capped at 100 users.

---

## 5. Non-goals (v1)

| Non-goal | Why |
|----------|-----|
| Bank, card, SMS, UPI-app, or app-store data sources | D4. |
| Non-Gmail providers | D2/D4. |
| Users outside India; multi-region hosting; multi-language extraction | D2/D30. |
| Currency conversion / totals in INR | D30. Amounts shown as stated. |
| Cancelling on the user's behalf | Needs write access to merchant accounts; out of scope. |
| Spend analytics, budgets, categories | Not the problem; constrained by Google Limited Use. |
| Refund/dispute assistance | Post-charge; the promise is pre-charge. |
| Monetization | D18. |
| On-device inference; BYO subscription / API key | D23. |
| Web app | D12. |
| Billing-platform templates (funnel stage 2) | D24 — P1. |

---

## 6. Data model and states

### 6.1 Subscription record

Stores **extracted fields only** — never the raw email (Google ToS).

| Field | Notes |
|-------|-------|
| merchant | Display name, normalised across emails from the same sender |
| source_account | Which connected Gmail produced it (D16) |
| kind | trial / subscription / renewal (non-subscription recurring) |
| billing_period | monthly / annual / other / unknown |
| amount, currency | As stated; ISO currency; no conversion (D30) |
| last_charge_date | From the most recent receipt |
| next_charge_date | See 6.2 |
| trial_end_date | Trials only |
| cancel_path | URL or text from the merchant's email, if present |
| lifecycle_state | See 6.3 |
| evidence | (message_id, account, field, snippet) per field; snippet = the sentence containing the value |

### 6.2 Field confidence states (D5–D7)

| State | Meaning | Alerts? | UI |
|-------|---------|---------|----|
| **confirmed** | Read directly from an email, or user-entered / user-promoted | Yes | Plain |
| **estimated** | Deterministically derived from confirmed facts | Yes | "Estimated" tag; one tap to correct or confirm |
| **unknown** | Not read and not derivable | **No** | Enters the Unknowns flow (D22) |

Rules: derivation only from stated facts; **an unstated trial length is unknown, never estimated**; promotion estimated → confirmed is a user action only; a new email that contradicts a field overwrites an estimated value and flags a confirmed one for the user.

### 6.3 Lifecycle states (D9–D11, D26)

| State | Alerts? | Enter when | Exit to |
|-------|---------|-----------|---------|
| **active** | Yes | Detected; or reactivated by a new receipt | cancellation_pending, cancelled (confirmed), unknown_date |
| **cancellation_pending** | **Yes** | User taps "I cancelled" | cancelled (confirmed) on merchant email; likely_cancelled on date passing with no receipt; cancelled (user-confirmed) on force-confirm |
| **cancelled (confirmed)** | No | Merchant cancellation email | active, on a new receipt (with the re-subscribe question) |
| **likely_cancelled** | No | Expected date passed, no receipt seen. Label: **"Likely cancelled — no charge seen"** | cancelled (user-confirmed) via one-tap "Confirm it's cancelled"; active on a new receipt |
| **cancelled (user-confirmed)** | No | Force-confirm from pending, or confirm from likely_cancelled; user saw the "no merchant confirmation exists" warning | active on a new receipt |
| **unknown_date** | No | next_charge_date unknown | active once resolved via D22 |

**Reactivation rule (D26):** a receipt arriving for any cancelled / likely record returns it to **active**, reschedules alerts from the new date, and asks one question: *"[Merchant] charged you again. Did you re-subscribe?"* — **Yes** → normal tracking; **No** → logged as a **surprise charge** (M1) and the alert shows the cancel path.

---

## 7. User stories (priority order)

**Onboarding**
- As a new user, I want to connect my Gmail and see subscriptions appear within seconds, so I know what I'm exposed to before doing anything else.
- As a new user, I want to know exactly what the app reads and stores before I grant access.
- As a user with two Gmail accounts, I want both in one list so nothing hides in the account I check less.

**Core**
- As a user, I want warnings 7, 3, 1 and 0 days before an annual renewal or trial conversion.
- As a user, I want warnings 1 and 0 days before a monthly charge, without being nagged.
- As a user, I want each alert to show merchant, amount, currency, date, and how to cancel.
- As a user, I want to see which dates are confirmed and which are estimated.
- As a user, I want to be asked one simple question at a time ("monthly or annual?") about subscriptions with missing dates, so I can turn on alerts without hunting for information.
- As a user, I want the most expensive or annual unknowns asked about first.

**Cancellation**
- As a user who has cancelled, I want to tell the app — and I want it to keep warning me until the merchant confirms, so a failed cancellation doesn't cost me.
- As a user, I want the app to detect the merchant's confirmation and stop the alerts itself.
- As a user whose merchant never confirms, I want a way to close it out myself after a clear warning.
- As a user who re-subscribes after a gap, I want tracking to resume automatically.

**Correctness and control**
- As a user, I want to mark a detected item as "not a subscription".
- As a user, I want to add a subscription manually.
- As a user, I want to see the sentence in the email a value came from.
- As a user, I want to disconnect an account, or delete everything, in one action.

---

## 8. Requirements

### 8.1 P0 — Must have

**R1. Gmail connection**
- [ ] OAuth with `gmail.readonly` only.
- [ ] In-app disclosure screen immediately before the OAuth handoff: what is read, what is stored (extracted fields + short snippets), what is not (raw email), that email content is sent to an LLM provider solely for extraction, and that no human reads it. Affirmative tap required; not in settings or ToS only.
- [ ] Multiple accounts per user; each record tagged with source_account.
- [ ] Given a connected account, when the user disconnects it, then its records, evidence and token are deleted within 24 h and the token revoked.

**R2. First sync (D14, D29)**
- [ ] Scans the last 24 months, **newest-first**.
- [ ] **First detected subscription visible within 30 s** of connection.
- [ ] **≤ 2,000 matched emails (stage 1 output) complete within 10 min.** Above that, a progress indicator states that it will take longer; the app remains usable throughout.
- [ ] Results appear progressively, not only at the end.

**R3. Continuous detection (D15, D27)**
- [ ] Gmail Pub/Sub watch on every connected account; watch renewed before its 7-day expiry; lapsed watch triggers a catch-up scan from the last processed history id.
- [ ] A new relevant email is processed **within 5 minutes** of arrival.

**R4. Detection funnel and extraction (D23, D24)**
- [ ] **Stage 1 — Gmail search.** Server-side Gmail queries on subject/body terms (receipt, invoice, trial, renewal, subscription, payment confirmation, and variants) and sender patterns (billing@, noreply@, no-reply@). Only matching message IDs and snippets are returned; non-matching mail is never fetched. Query set is versioned and its recall measured against the labelled set (M2).
- [ ] **Stage 3 — cheap triage.** For each match, a small-model call on subject + first ~200 characters: subscription-related yes/no. Non-relevant mail stops here.
- [ ] **Stage 4 — LLM extraction.** Survivors only; body truncated to ~1,500 tokens; structured (JSON-schema) output of the fields in 6.1, each with a confidence state and evidence pointer.
- [ ] **Stage 5 — learn once per sender.** After a successful extraction from a sender template, cache the extractor and reuse it for later emails from that sender. **Correctness rule:** the cached extractor applies only when the new email's structure matches; if it returns as unknown a field it previously found, fall back to stage 4.
- [ ] Recognises at minimum: trial sign-up confirmations, receipts/invoices, renewal reminders, cancellation confirmations, price-change notices.
- [ ] Given a receipt with a charge date and billing period but no next date → next_charge_date **estimated**. Given a trial email with no stated length → trial_end_date **unknown**.
- [ ] Multiple emails from one merchant across accounts merge into one record; most recent receipt wins for amount and last_charge_date.
- [ ] Extraction is general-purpose (works on unseen merchants), English-only acceptable in v1 (D30).
- [ ] Extraction is a **swappable module** (email in → fields + states + evidence out) so the server implementation can later be replaced (P2).
- [ ] Only minimal content (headers + body text; attachments only if the body has no amount) goes to the LLM provider.
- [ ] Pre-filter pass rate (stage 1 → stage 4) is measured and reported (M8).
- [ ] "Not a subscription" suppresses that merchant for that user and logs a false positive (M3).

**R5. Subscription list**
- [ ] One merged list, sorted by next_charge_date (unknowns last).
- [ ] Row shows merchant, amount + currency as stated, next date with state tag, lifecycle state, source account.
- [ ] Tapping a field shows its evidence snippet and allows correct / confirm.
- [ ] Manual add: merchant, amount, currency, period, next date — all confirmed (user-entered).

**R6. Unknowns resolution (D22)**
- [ ] Records with next_charge_date = unknown enter a queue ordered by expected damage: annual/trial first, then amount descending, then monthly, then period-unknown. Different currencies compare by stated amount — no conversion (known limitation, D30).
- [ ] Home screen shows **one** unknown as a single card. The full queue is reachable but never the default view; never shown as a list at first sync.
- [ ] Card opens a **bottom sheet**: merchant, evidence snippet, the line "We couldn't find a renewal date in this email", buttons **Monthly / Annual / Not a subscription / Skip**; "Enter a date" secondary.
- [ ] Monthly/Annual with a confirmed anchor date → period confirmed (user-stated), next_charge_date **estimated**, record leaves the queue, ladder scheduled. Without an anchor date → follow-up asks for the date; period still stored.
- [ ] Direct date entry → confirmed.
- [ ] Skip → next card; skipped record returns no sooner than the next session.
- [ ] Tapping a date visible in the snippet that the parser missed → confirmed, logged as a parser miss.
- [ ] A new email from that merchant re-runs extraction before re-surfacing the card.
- [ ] Unresolved count visible on the home screen, not as the primary UI.

**R7. Alerts (D13, D19, D20, D28)**
- [ ] Ladder: **monthly → T−1, T−0. Everything else (annual, trial, other, unknown period) → T−7, T−3, T−1, T−0.**
- [ ] Alert content: merchant, amount, currency, date, date state, cancel path if known.
- [ ] Push for all steps. **Email from our servers to the user's own address for T−1 and T−0, always** — not only on detected push failure.
- [ ] Alerts fire for active and cancellation_pending; not for unknown_date, cancelled, likely_cancelled.
- [ ] Correcting next_charge_date reschedules the ladder.
- [ ] Per-subscription mute.

**R8. Cancellation and reactivation (D9–D11, D26)**
- [ ] "I cancelled" → cancellation_pending; alerts continue.
- [ ] Merchant cancellation email → cancelled (confirmed); alerts stop. Detection must distinguish a confirmation from a win-back offer (Q7).
- [ ] Expected date passes, no receipt → likely_cancelled; alerts stop; label "Likely cancelled — no charge seen"; one-tap "Confirm it's cancelled" → cancelled (user-confirmed).
- [ ] Force-confirm from pending shows a warning that no merchant confirmation exists; on confirm → cancelled (user-confirmed).
- [ ] **Nothing is deleted.** A receipt for any cancelled/likely record → active, ladder rescheduled, and the re-subscribe question is asked; **No** logs a surprise charge and surfaces the cancel path.

**R9. Account and data (D30)**
- [ ] All processing and storage in an India cloud region.
- [ ] Delete account: all records, evidence, tokens removed within 24 h; user receives confirmation.
- [ ] Raw email bodies never persisted beyond processing; evidence snippets limited to the sentence containing the value.
- [ ] Support tooling cannot display extracted content without the user's explicit, logged consent for that request.

**R10. Security and compliance (CASA — functional requirements)**
- [ ] OAuth tokens encrypted at rest; keys in a KMS/HSM.
- [ ] All user data encrypted at rest and in transit.
- [ ] No use of extracted data for ads, resale, lending/credit, or model training beyond the user's own personalisation.
- [ ] LLM provider under **zero-data-retention / no-training** terms; the transfer disclosed in the consent screen and privacy policy; provider, region and terms recorded in CASA scope.
- [ ] Prompt-injection protection on all LLM calls (email content is untrusted input).
- [ ] Limited Use statement on the website; privacy policy on the same domain as the home page.
- [ ] Security incident notification process to Google defined before launch.

### 8.2 P1 — Fast follows

- **Funnel stage 2 — billing-platform templates (D24):** regex/markup extraction for Razorpay, Apple, Google Play, Stripe, PayU, and schema.org `Order`/`Invoice` markup where present. Makes the commonest receipts free.
- Price-change alert (amount differs from last receipt).
- Trial nudge on detection: "remind me to decide 1 day before it ends".
- Cancel-path enrichment from a maintained merchant table (labelled as not from the email).
- Per-subscription ladder customisation.
- CSV export.

### 8.3 P2 — Design for, don't build

- **On-device extraction (D23):** Apple Foundation Models / Gemini Nano via ML Kit, or a shipped Gemma-4-E-class model. The R4 module interface must make this a drop-in.
- Self-hosted inference (Anirudh's GPU or a cloud GPU) vs API — decided on M8 data.
- Additional providers and signals: keep the ingestion adapter separate from lifecycle logic.
- Global expansion: multi-language extraction, multi-currency, multi-region — deliberately not designed for in v1 (D30); revisit only after India M1 is stable.
- Monetization: any paid tier must not gate the core alert.

---

## 9. Success metrics

Primary in bold. All computed on extracted fields, aggregated (Google Limited Use).

| # | Metric | Definition | Observable? | Target (hypothesis) |
|---|--------|------------|-------------|---------------------|
| **M1** | **Surprise charges** | Receipt received for a charge with no prior alert delivered, incl. "No" answers to the re-subscribe question, per active user-month | Yes | < 0.1 per user-month at 90 days |
| M2 | Recall (proxy) | Manual adds + receipts for previously undetected merchants ÷ total records | Proxy; calibrate with an opt-in audit sample (~50 users) | Proxy < 10%; audited > 85% |
| M3 | Precision | 1 − (dismissed ÷ detected) | Yes | > 90% |
| M4 | Field confidence | % records with next_charge_date confirmed / estimated / unknown at first sync and D+7 | Yes | Unknown < 20% at first sync; < 10% at D+7 |
| M5 | Alert delivery | Sent → delivered → opened per step and channel | Yes | T−1/T−0 delivered (any channel) > 98% |
| M6 | Prevention (partial) | Of delivered alerts, % followed by a cancellation email or no-charge-seen | Partial — can't separate "because of us" from "anyway" | Report only |
| M7 | Adoption / retention | Accounts per user; D7/D30 retention; unknowns resolved per user | Yes | D30 > 40% |
| M8 | Unit cost | Pre-filter pass rate; LLM + infra cost per user for first sync and per month | Yes | Set after a production candidate is measured (Q9) |

Evaluate M1–M5 weekly for 8 weeks, then monthly. M6–M8 at 30/60/90 days.

---

## 10. Google platform constraints (verified 6 Sep 2026)

| Constraint | Consequence | Confidence |
|------------|-------------|------------|
| Every Gmail read scope (`gmail.readonly`, `gmail.metadata`) is restricted; no filter-limited scope exists | Whole-inbox read is the only option | High |
| Restricted → Google verification + annual CASA by an approved assessor; unverified apps capped at 100 users; "can take several weeks" | CASA on the critical path; 100 users = beta size | High |
| Permitted use case: "reporting or monitoring services for the benefit of users" (Google cites package/flight tracking) | Our use case fits the category | Moderate-high |
| Limited Use: no ads, resale, lending use, cross-user ML training, or human access without consent | Rules out data-monetised models; constrains support tooling | High |
| ToS prohibits permanent copies of Gmail data | Extracted fields + snippets only | High |
| In-app disclosure + affirmative consent immediately before the request | R1 | High |
| Prompt-injection protection required for AI processing | R10 | High |
| Gmail "Manage subscriptions" (2025) lists newsletters via List-Unsubscribe; it does not track paid renewals | Not a competitor for this problem | High |
| CASA cost ~$500–4,500/yr | Budget line | Low-moderate (secondary sources) |

---

## 11. Assumptions and risks

**Assumptions**
- A1. Most subscriptions the target user cares about generate at least one email to the connected Gmail.
- A2. Users will answer "monthly or annual?" one at a time; M4 at D+7 is the check.
- A3. General-purpose LLM extraction can reach > 85% recall and > 90% precision on unseen merchants. **Untested — the Phase 0 gate.**
- A4. The 7/3/1/0 ladder helps rather than annoys for annuals. No data.
- A5. RBI pre-debit notification rules cover domestic card mandates but not foreign direct card charges. **[verify]**

**Risks**

| # | Risk | Impact | Mitigation |
|---|------|--------|------------|
| R1 | Silent merchants (no email); UPI-Autopay subscriptions with SMS/app-only trails | Misses on exactly some of the charges that hurt | State the limitation in onboarding; manual add; P2 signals |
| R2 | CASA/verification slower than planned or fails | Capped at 100 users | Start verification as soon as Phase 0 passes; `gmail.readonly` only |
| R3 | Extraction below A3 | False positives kill trust; misses kill M1 | Labelled eval set from founder + beta inboxes before scaling; extraction quality is the v1 gate |
| R4 | Long Unknowns queue at first sync | Abandonment before first alert | D22; if unresolved > 20% at D+7, prioritise billing-period extraction, then revisit D7 |
| R5 | Push fails silently | Surprise charge despite detection | D13 email on T−1/T−0 |
| R6 | Founder-locale bias in the eval set | Recall varies across Indian merchants/platforms | Include Razorpay, PayU, Apple, Google Play, and foreign-merchant receipts in the labelled set |
| R7 | Users hesitant to grant whole-inbox read | Low OAuth conversion | Disclosure quality; "what we store / don't"; one-tap delete; "data stays in India" |
| R8 | Server extraction cost scales while free | Burn grows with adoption | Funnel (R4); M8 ceiling that pulls P2 self-hosting/on-device forward |
| R9 | Naming deferred (D31) delays verification submission by the time it takes to set up name, domain and site after Phase 0 | Weeks of calendar time | Accepted trade-off; have the privacy-policy draft ready from this PRD so setup is days, not weeks |

---

## 12. Open questions

| # | Question | Owner | Blocking? |
|---|----------|-------|-----------|
| Q1 | Evidence beyond one incident: a short survey (n ≥ 30) of Indian Gmail users on frequency/size of surprise charges, and how many were foreign-merchant vs domestic. | Product | No — before launch |
| Q2 | Which LLM provider/model for stage 3 and stage 4, or self-hosted. Deferred by D25 until a production candidate is run against the labelled set. Requires zero-retention terms and structured output. | Engineering / Anirudh | Yes — before Phase 1 build |
| Q6 | Beta cohort (≤100) and consent for the recall audit (M2). | Product | No |
| Q7 | Distinguishing a cancellation confirmation from a win-back offer; needs labelled examples. | Engineering | No |
| Q9 | Unit cost (M8) from a production candidate run; sets the ceiling in R8. | Engineering / Anirudh | Yes — before Phase 1 build |
| Q10 | Verify A5 (RBI pre-debit notification scope) and DPDP transfer rules as of launch. | Legal | No — before launch |

Closed in this revision: Q3 (D30), Q4 (D29), Q5 (D13, D15, D20, D21, D26–D28), Q8 (D31).

---

## 13. Timeline and phasing

No hard deadline. Sequencing is driven by the Phase 0 gate and Google verification.

**Phase 0 — Feasibility gate**
- Harness: **Codex** (D25) builds the pipeline (stages 1, 3, 4, 5) and runs it over the founder's own 24 months of Gmail, plus one or two consenting others.
- Label by hand; measure recall, precision, stage-1 match count, pre-filter pass rate, first-result time, and time-to-complete per 1,000 matches (feeds D29).
- Cost (Q9) is measured only when a production candidate is run — sequencing at your discretion, but recommended before Phase 1 code.
- Exit criterion: A3 met on the founder set. If not, revisit D4 before building the app.

**Between Phase 0 and Phase 1 (D31)**
- Choose app name; register domain; publish home page, privacy policy (draft from Sections 8–10), and Limited Use statement; verify domain in Search Console.
- Choose provider (Q2) with zero-retention terms.

**Phase 1 — Private beta (≤ 100 users, Testing mode)**
- P0 requirements R1–R10.
- Submit Google verification and start CASA immediately; don't wait for feature-complete.
- Weekly M1–M5. Exit criterion: M2/M3 targets and M4 at D+7.

**Phase 2 — Public launch (India), after verification**
- Remove the 100-user cap. P1 items, stage 2 templates first.
- Decide self-hosting vs API on M8.

**Phase 3 — Only after M1 is stable**
- Revisit D4 (signals), D18 (monetization), D30 (global).

---

## 14. Sources

- Google, *Restricted scope verification* — developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification (updated 19 Aug 2026)
- Google, *Google Workspace user data and developer policy* — developers.google.com/workspace/workspace-api-user-data-developer-policy (updated 22 Jul 2026)
- Google, *Google API Services User Data Policy* — developers.google.com/terms/api-services-user-data-policy
- Google, *Restricted Scopes* list — support.google.com/cloud/answer/13464325
- Google, *Email Markup overview* — developers.google.com/workspace/gmail/markup/overview
- Google, *ML Kit GenAI APIs* — developers.google.com/ml-kit/genai
- Gmail "Manage subscriptions": Google announcement 8 Jul 2025, via secondary coverage
- CASA cost figures, Gemma 4 E-series memory claims: secondary sources only; not verified against primary pricing or Google's release notes

---

## 15. Changes from v1

- **Scope:** global → India-only MVP; global-readiness dropped (D2, D30). Target user, non-goals, risks and phasing rewritten accordingly.
- **Defaults confirmed:** D13, D15, D20, D21, D27, D28.
- **Lifecycle:** "likely cancelled" gains a one-tap confirm; reactivation rule and re-subscribe question added (D26).
- **Funnel:** stages 1, 3, 4, 5 in v1; stage 2 moved to P1 (D24). Stage 5 correctness rule added.
- **Phase 0:** Codex as harness; provider deferred (D25).
- **First sync:** concrete targets (D29).
- **Region:** India (D30).
- **Naming/site:** after Phase 0 (D31), with R9 noting the accepted delay.
- Metrics: M8 unit cost added; M1 now includes "No" answers to the re-subscribe question.
- Open questions: Q3, Q4, Q5, Q8 closed; Q10 added.

# Subscription Renewal Tracker

An early-stage product concept to help people discover recurring subscriptions and trials, understand upcoming charges, and act before unwanted renewals.

> **Status:** Phase 1 built for a private beta. Phase 0 ran on the founder's real inbox (24 months, Claude as extractor). The [backend](backend/README.md) (35 tests, SQLite and PostgreSQL) and the [iOS/Android app](mobile/README.md) (typechecked, Android bundle built) exist. **Not yet deployed:** see the [launch checklist](deploy/README.md). The cheap production model hasn't been measured yet.

## What's in this repository

| File | Purpose | Status |
| --- | --- | --- |
| [PRD v1.1](docs/subscription-renewal-tracker-prd-v1-1.md) | Original decisions, P0 requirements, metrics, and risks | Original draft v1.1 |
| [Product brief](docs/product-brief.md) | Problem, user hypothesis, proposed v1 scope, and open questions | Working draft |
| [Competitor research](docs/competitor-research.md) | September 2026 competitor landscape and strategic takeaways | Archived snapshot; not refreshed |
| [Flow review guide](docs/flow-review.md) | Navigation for the flow diagram and eight decisions requiring sign-off | Working draft |
| [Flow diagram v0.1](artifacts/flow-diagram-v0-1.html) | Original, self-contained interactive HTML flow | Original artifact; awaiting sign-off |
| [Phase 0 pipeline](phase0/README.md) | Gmail search → triage → extraction → per-sender templates, plus judge and scorer for assumption A3 | Built; run on founder inbox (dev mode) |
| [Backend](backend/README.md) | FastAPI service: accounts, lifecycle, alerts, Gmail push, data controls (R1–R10) | Built; 35 tests |
| [Mobile app](mobile/README.md) | Expo / React Native iOS + Android app | Built; typechecked, bundled |
| [Launch checklist](deploy/README.md) | GCP Mumbai setup script, OAuth, EAS builds | Ready to run; needs founder accounts |

Open `artifacts/flow-diagram-v0-1.html` in a browser to review the flows. It covers account connection, first sync, detection, merging, unknown fields, alerts, cancellation/reactivation, ongoing detection, and deletion.

## Working direction

- **Problem:** Trials and subscriptions can renew without the user noticing, causing unexpected charges.
- **Target-user hypothesis:** Adults in India with one or more Gmail accounts. This is a design assumption to validate, not a proven market definition.
- **Proposed approach:** Use read-only Gmail access to identify subscription-related messages, extract structured fields, surface uncertainty, and warn users about upcoming renewal dates.
- **Privacy direction in the diagram:** Avoid retaining raw email bodies; offer account disconnection and data deletion. These are proposals, not evidence of a deployed system.

See the [product brief](docs/product-brief.md) for scope and unresolved questions.

## Source and migration status

The [original PRD v1.1](docs/subscription-renewal-tracker-prd-v1-1.md) and the v0.1 flow diagram are both dated **6 September 2026**. The PRD documents decisions D1–D31 and requirements R1–R10. The PRD is a **draft**, and the flow remains **awaiting sign-off**. The brief and review guide summarize these sources; they do not supersede them.

The PRD marks some regulatory and platform claims for verification. They were preserved as written, not independently revalidated as part of this upload.

The [competitor research](docs/competitor-research.md) has now been migrated from the [original shared conversation](https://chatgpt.com/share/6aeb0dfb-1c0c-83ec-b14d-b0ada3415cc6). The original analysis and confidence labels were preserved, and chat-specific citation markers were converted to direct source links. The research reflects **6 September 2026**; product features, adoption figures, and platform policies have not been rechecked since.

## Next steps

1. Work through the [launch checklist](deploy/README.md): Google OAuth clients, the GCP deploy script, EAS builds.
2. Measure the cheap production model: Phase 0 with an OpenRouter model (needs openrouter.ai allowed) to settle Q2 and M8.
3. Publish the privacy policy and Limited Use statement, then start Google verification and CASA (needed above 100 users).
4. Refresh time-sensitive competitor claims before using them for launch or positioning decisions.

# Subscription Renewal Tracker

An early-stage product concept to help people discover recurring subscriptions and trials, understand upcoming charges, and act before unwanted renewals.

> **Status:** Product discovery / flow review. This repository does **not** contain a working application. The included flow diagram is v0.1 and is **awaiting sign-off**.

## What's in this repository

| File | Purpose | Status |
| --- | --- | --- |
| [PRD v1.1](docs/subscription-renewal-tracker-prd-v1-1.md) | Original decisions, P0 requirements, metrics, and risks | Original draft v1.1 |
| [Product brief](docs/product-brief.md) | Problem, user hypothesis, proposed v1 scope, and open questions | Working draft |
| [Competitor research](docs/competitor-research.md) | September 2026 competitor landscape and strategic takeaways | Archived snapshot; not refreshed |
| [Flow review guide](docs/flow-review.md) | Navigation for the flow diagram and eight decisions requiring sign-off | Working draft |
| [Flow diagram v0.1](artifacts/flow-diagram-v0-1.html) | Original, self-contained interactive HTML flow | Original artifact; awaiting sign-off |

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

1. Review and resolve the [eight flow sign-off questions](docs/flow-review.md).
2. Refresh time-sensitive competitor claims before using them for launch or positioning decisions.
3. Validate the target-user and Gmail-only assumptions with potential users.
4. Convert approved flows into implementation requirements and tests.

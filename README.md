# Subscription Renewal Tracker

An early-stage product concept to help people discover recurring subscriptions and trials, understand upcoming charges, and act before unwanted renewals.

> **Status:** Product discovery / flow review. This repository does **not** contain a working application. The included flow diagram is v0.1 and is **awaiting sign-off**.

## What's in this repository

| File | Purpose | Status |
| --- | --- | --- |
| [Product brief](docs/product-brief.md) | Problem, user hypothesis, proposed v1 scope, and open questions | Working draft |
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

The v0.1 flow diagram is dated **6 September 2026** and states that it was derived from **PRD v1.1** (decisions D1–D31 and requirements R1–R10). That PRD has **not** been supplied to this repository, so the documents here should not be treated as a substitute for it.

Earlier competitor research exists in a separate project conversation but has **not** been migrated verbatim. No research findings have been invented or attributed without the original text.

## Next steps

1. Review and resolve the [eight flow sign-off questions](docs/flow-review.md).
2. Add the original PRD v1.1 and competitor-research write-up when available.
3. Validate the target-user and Gmail-only assumptions with potential users.
4. Convert approved flows into implementation requirements and tests.

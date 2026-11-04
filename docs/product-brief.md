# Product brief — working draft

> **Provenance:** A secondary summary of the project's stated problem and supplied [flow diagram v0.1](../artifacts/flow-diagram-v0-1.html). The [original PRD v1.1](subscription-renewal-tracker-prd-v1-1.md) is the primary source for decisions and requirements. This brief does not replace it or imply sign-off.

## Problem

A free trial or recurring subscription may renew long after sign-up. If the user has forgotten the deadline or does not know where to look, the charge can be a costly surprise.

The product opportunity is to help users **find, understand, and act on** their renewal commitments before a charge happens.

## Target-user hypothesis

The current flow assumes:

- Adults in India.
- People who use one or more Gmail accounts.
- People with subscriptions, trials, or recurring bills that leave evidence in email.

**Validation needed:** Gmail coverage, how often email contains a reliable renewal date, willingness to grant read-only inbox access, alert preferences, and whether users would maintain ambiguous records. These are hypotheses, not established findings.

## Jobs to be done

1. Discover current and past subscriptions from account-linked email evidence.
2. See upcoming renewal or trial-end dates and amounts when known.
3. Distinguish an extracted fact from an estimate or an unknown.
4. Get timely reminders and a path to cancel before an unwanted charge.
5. Update a record when a service is cancelled, charged again, or reactivated.
6. Disconnect email accounts and delete stored personal data.

## Proposed v1 boundary (from flow diagram)

| Included in the proposed design | Explicitly outside proposed v1 |
| --- | --- |
| iOS and Android app | Bank, card, SMS, and UPI-app data |
| One or more Gmail accounts via read-only OAuth | Non-Gmail inbox providers |
| Initial email scan and continuing inbox changes | Direct app-store data integration |
| Staged detection, field extraction, evidence, and unknown states | On-device inference |
| Renewal alerts and cancellation-state tracking | Currency conversion and multiple server regions |
| Consent, account disconnection, and deletion flows | Automatic subscription cancellation |

The HTML proposes an India-region server, selective email fetching, an LLM extraction step with minimal content, push notifications, and email fallback. These should be treated as **design proposals** until the PRD, privacy assessment, and technical implementation are reviewed.

## Open product questions

- Does a Gmail-only starting point cover enough of the target user's subscriptions?
- What is the acceptable rate of missed subscriptions versus false positives?
- What should the app do when it knows a merchant but not the renewal date or amount?
- How should the app express and manage uncertainty in extracted or estimated fields?
- What level of Gmail access and AI-assisted processing will users trust?
- Which alert timings and cancellation states lead to meaningful action?
- What is the minimum successful outcome for a first-time user?

The [flow review guide](flow-review.md) records specific design decisions that still require sign-off.

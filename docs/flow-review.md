# Flow diagram v0.1 — review guide

> **Decision status (5 Nov 2026):** the founder adopted all eight proposals below. Decision #2 was informed by the Phase 0 real-inbox run: a subscription that sends no receipts (it charges silently) would otherwise be marked likely cancelled while still charging.
>
> **Sources:** The original [PRD v1.1](subscription-renewal-tracker-prd-v1-1.md) and supplied [HTML artifact v0.1](../artifacts/flow-diagram-v0-1.html), both dated 6 September 2026. The HTML is a first-draft interpretation of the PRD. **Nothing below records a sign-off.**

## Sections

| # | Flow |
| --- | --- |
| 0 | System map |
| 1 | Connect a Gmail account |
| 2 | First sync |
| 3 | Detection funnel (per matched email) |
| 4 | Merge into a record and assign field states |
| 5 | Resolve unknowns |
| 6 | Alerts |
| 7 | Cancellation and reactivation |
| 8 | Continuous detection |
| 9 | Disconnect an account, delete everything, and support access |

## Eight proposals requiring a decision

The diagram presents these as choices not settled in the underlying PRD. Summaries below retain the original proposal; consult the HTML for the full branch logic.

| # | Decision | Proposal in the diagram | Status |
| --- | --- | --- | --- |
| 1 | Alert send time | Send at 09:00 local time rather than at the exact minute of the charge date. | **Adopted** (founder, 5 Nov 2026) |
| 2 | Active subscription passes its expected date without a receipt | Keep it active, advance an **estimated** next date, and flag the missing receipt. Alternative: mark likely cancelled. | **Adopted** (founder, 5 Nov 2026) |
| 3 | Charge occurs while cancellation is pending | Return to active and notify the user, but do not count it in M1 because an alert was delivered. | **Adopted** (founder, 5 Nov 2026) |
| 4 | Disconnect one of two email accounts contributing to a merged record | Remove only that account's evidence; retain the record if evidence from the other account remains. | **Adopted** (founder, 5 Nov 2026) |
| 5 | Lookback when no receipt is seen | Check at T+3 days to allow for late receipts. | **Adopted** (founder, 5 Nov 2026) |
| 6 | PDF attachment processing | Read the first page only when the email body contains no amount. | **Adopted** (founder, 5 Nov 2026) |
| 7 | Unanswered re-subscribe question | Resume tracking, leave the question on the record, and do not count M1 until answered. | **Adopted** (founder, 5 Nov 2026) |
| 8 | Partial OAuth grant | Treat a partial grant as no grant. | **Adopted** (founder, 5 Nov 2026) |

## Review checklist

- [x] Approve or revise each of the eight proposals (all adopted, 5 Nov 2026).
- [ ] Reconcile the flow against the original PRD v1.1, decisions D1–D31, and requirements R1–R10 when available.
- [ ] Test the handling of unknown dates, false positives, cancellations, and reactivations with realistic examples.
- [ ] Confirm that all data-access, storage, deletion, and third-party processing descriptions match the eventual implementation.
- [ ] Only then mark the flow version as approved.

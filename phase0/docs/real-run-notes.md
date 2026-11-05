# First real-inbox dev run: engineering notes

Run: November 2026, founder inbox, last 6 months only, Claude as the extractor (replay provider), query set `q2`.
These notes are deliberately merchant-agnostic; the founder approved committing them. The run's data stays under the gitignored `data/` directory.

## Funnel
- Stage 1 (`q2`, subject-only): 130 threads in 6 months. With `q1` (subject + body terms), one 50-thread page covered only 11 days, almost all newsletters and promotions.
- Stage 3: 36 of 130 passed (28%).
- Stages 4 and 5: 31 model extractions plus 5 stage-5 template hits gave 6 subscription records.
- Gmail's `resultCountEstimate` was useless (it reported 201 for a query with roughly 3,000 matches). Volume has to be measured by paging.
- Changing the query string between pages while reusing a `pageToken` is undefined. The run re-checked for gaps and found none, but don't rely on it.

## Bugs found and fixed
1. `Rs:450` (colon) was not parsed as INR, so currency was lost on a major Indian broadband provider's receipts. Fixed in `textutil`; regression test added.
2. A confirmed next-charge date from a bill stayed "next" after a later payment, showing a date already in the past. Merge now treats a next date on or before the latest charge as superseded, and re-derives it.
3. Monthly receipts raised a "changed" flag every month. Forward progression of charge dates is no longer flagged; amount changes still are.

## Open product and engineering issues surfaced
- **Image-only receipts** (the whole email is an image; the invoice is a PDF): the amount is unknowable from the body. The subject line still carried the period ("renewed for 3 months"). Flow sign-off #6 (PDF parsing) matters more than expected.
- **Receipts that never say "monthly"**: one large AI-subscription merchant states only a service period ("Oct 16–Nov 16"). Billing period stays unknown, although six receipts 30 days apart make it obvious. Consider inferring the period from receipt cadence (≥2 receipts), marked *estimated*. This is not in the PRD, so it needs a decision.
- **Proration**: an upgrade receipt showed a prorated charge (new price minus a credit). "Most recent receipt wins" then reports the prorated amount, not the next full charge.
- **Future price steps**: one subscription-update email stated a price that rises about 10× after a year. It is captured only as a price-change flag with no effective date. Alert-worthy (P1 price-change alert).
- **Failed-renewal loops**: monthly "confirm your renewal with your bank" emails (likely India's additional-authentication rule for recurring card payments; PRD A5) are evidence of a recurring charge but carry no amount or date.
- **Voucher-to-paid conversions**: a "free year" voucher converted to a paid annual plan in a foreign currency. The merchant sent two warnings; the charge was still a surprise and was refunded. This is the PRD's founding-incident pattern, observed in the wild.
- **Mixed cadences from one merchant** (a monthly bill plus a periodic multi-month plan charge) collapse into one record with conflicting period and amount flags.
- **Labelling caveat**: in this run Claude was the extractor, so no independent judge exists. The founder's review of the final list is the accuracy check.

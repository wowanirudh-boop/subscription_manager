# Decision log: changes to PRD v1.1 during Phase 1

PRD v1.1 is kept as the original record. These decisions were made by the founder after it; where they conflict, they supersede it.

| Date | Change | Supersedes | Why |
|---|---|---|---|
| 5 Nov 2026 | All eight flow sign-off proposals adopted | flow review "Open" items | #2 informed by real data: a merchant that charges monthly but never e-mails |
| 5 Nov 2026 | Mobile: React Native + Expo. Backend: Python on Google Cloud, asia-south1 | (stack was undecided) | Reuses the tested Phase 0 pipeline; India region (R9/D30) |
| 5 Nov 2026 | **Bank/card alert e-mails are in scope** (transaction alerts, pre-debit/e-mandate notices). Bank APIs, SMS and UPI apps stay out | **D4** ("no bank, card… data") | Catches merchants that never e-mail (A1/R1 risk). The data still arrives by e-mail |
| 5 Nov 2026 | **Outlook / Hotmail / Microsoft 365 inboxes** supported via Microsoft Graph, read-only (`Mail.Read`) | **Non-goal "Non-Gmail providers"**; D8 extended to Microsoft | Founder's bank alerts arrive in non-Gmail inboxes |
| 5 Nov 2026 | Billing period may be **inferred from charge cadence** (≥ 2 charges at ~30/91/182/365 days), shown as *estimated* | Adds to D6 (derivation from stated facts) | Receipts that never say "monthly"; bank alerts never do |
| 5 Nov 2026 | **Several plans from one merchant** are split by stated reference number, else by amount (marked estimated) | Adds to R4 merge rule | Four insurance policies paid the same day |
| 5 Nov 2026 | Disclosure text v2 (`mail-disclosure-v2`) covers Outlook and bank alerts; users re-consent | R1 text | R1 requires the disclosure to match what is read |
| 5 Nov 2026 | T−1/T−0 alert e-mails may be sent from the product's own Gmail/Workspace mailbox over SMTP (no third-party provider needed for the beta) | (D13 transport unspecified) | Avoids asking users for a send scope |

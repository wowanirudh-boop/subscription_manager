"""Stage 1 query set (R4). Versioned so recall can be attributed to a version (M2).

Gmail search syntax notes (from Gmail's search-operator help; re-check before
relying on edge cases):
- `{a b c}` is OR; quoted phrases match exact phrases; `after:YYYY/MM/DD` bounds dates.
- `from:billing` matches senders whose address contains "billing" - treated
  here as a sender-pattern heuristic; its exact tokenisation is not documented
  precisely, so its contribution should be measured, not assumed.
"""

from __future__ import annotations

import datetime as dt

from dateutil.relativedelta import relativedelta

QUERY_SET_VERSION = "q1-2026-11"

SUBJECT_BODY_TERMS = [
    "receipt",
    "invoice",
    '"free trial"',
    "trial",
    "renewal",
    "renews",
    '"auto-renew"',
    "subscription",
    "membership",
    '"payment confirmation"',
    '"payment received"',
    '"payment successful"',
    '"thank you for your payment"',
    '"your plan"',
    '"billing"',
    '"auto debit"',
    "autopay",
    "mandate",
    "premium",
    '"policy renewal"',
    '"domain renewal"',
    '"has been cancelled"',
    '"has been canceled"',
    '"price change"',
]

SENDER_PATTERNS = ["from:billing", "from:noreply", "from:no-reply", "from:receipts", "from:invoice", "from:payments"]

# Common false-positive sources that stage 3 would reject anyway; excluding them
# saves calls. Kept small on purpose: every exclusion risks recall.
EXCLUSIONS = ['-subject:"one time password"', "-subject:OTP"]


def build_queries(today: dt.date, months: int = 24) -> list[str]:
    """D14: last 24 months. Two queries (terms, senders); results are de-duplicated by id."""
    after = (today - relativedelta(months=months)).strftime("%Y/%m/%d")
    terms = "{" + " ".join(SUBJECT_BODY_TERMS) + "}"
    senders = "{" + " ".join(SENDER_PATTERNS) + "}"
    excl = " ".join(EXCLUSIONS)
    return [f"after:{after} {terms} {excl}", f"after:{after} {senders} {excl}"]


# q2: subject-only variant used for the first real-inbox dev run (Nov 2026). q1's body terms
# ("premium", "your plan", "subscription") matched every newsletter: ~50 threads per 11 days,
# mostly noise. Subject-only cut that to ~50 per 40 days. Trade-off: receipts whose subject
# lacks these words (e.g. "Thanks for your order") are missed - measure before adopting.
QUERY_SET_V2 = "q2-subject-2026-11"
SUBJECT_TERMS_V2 = (
    'receipt OR invoice OR renewal OR renew OR renews OR renewed OR subscription OR trial OR membership OR '
    '"payment successful" OR "payment received" OR "payment confirmation" OR "payment notification" OR autopay OR '
    '"auto debit" OR "auto-debit" OR mandate OR "premium due" OR cancelled OR canceled OR "price change" OR billing OR "your plan"'
)


def build_queries_v2(today: dt.date, months: int = 24) -> list[str]:
    after = (today - relativedelta(months=months)).strftime("%Y/%m/%d")
    return [f"after:{after} subject:({SUBJECT_TERMS_V2}) -category:social"]

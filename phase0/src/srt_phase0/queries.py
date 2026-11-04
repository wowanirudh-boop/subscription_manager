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

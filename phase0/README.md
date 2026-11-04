# Phase 0 — feasibility pipeline

Phase 0 tests **A3**: can general-purpose model extraction reach **>85% recall and >90% precision** on unseen merchants, using the founder's own Gmail? It is the gate in PRD v1.1 §13. If A3 fails, D4 (email as the only data source) is revisited before any app is built.

Status: **built and tested on synthetic data only.** No real inbox has been processed. No real model has been called.

## What it implements

| PRD item | Where | Notes |
|---|---|---|
| R4 stage 1: Gmail search | `queries.py`, `sources.py` | Versioned query set `q1-2026-11`; ids only; newest first; last 24 months (D14) |
| R4 stage 3: cheap triage | `providers/*`, `pipeline.py` | Subject + first ~200 chars (Gmail snippet). Bodies of rejected mail are never downloaded |
| R4 stage 4: model extraction | `providers/openrouter.py`, `prompts.py` | JSON-schema output; body truncated to ~1,500 tokens (≈4 chars/token) |
| R4 stage 5: learn once per sender | `templates.py` | Regex extractor per sender layout; falls back to stage 4 when a previously found field comes back unknown |
| D5–D7 field states | `verify.py` | A value is **confirmed** only when its verbatim quote occurs in the email and the quote contains the value. **Estimated** values come only from stated facts. Everything else is **unknown** |
| R4 merge across accounts (D16) | `merge.py` | Most recent receipt wins (flagged when it contradicts a confirmed value); win-back offers never cancel or reactivate (Q7) |
| R10 prompt-injection protection | `prompts.py`, `verify.py` | Schema-only output, quote verification, and a per-call random delimiter. See limits below |
| Phase 0 measurements | `score.py`, `pipeline.py` | Precision and recall with Wilson 95% intervals; funnel pass rate (M8); tokens and cost; first-result and total time (D29) |

## Decisions taken for Phase 0 (and where they depart from the PRD)

| Decision | PRD position | Status |
|---|---|---|
| Built in Python by Claude, not Codex | D25 says the Phase 0 harness is Codex | **Departs from D25.** Founder's call in the build session |
| Runs in a Claude Code cloud container | R9 requires India-region processing (written for production) | **Departs from R9 in spirit.** Raw email passes through a non-India container. Founder's call |
| Operational model via OpenRouter (model chosen later) | Q2 open | Provider is swappable (R4). Requests ask OpenRouter for `data_collection: deny` and `zdr: true`. **Not yet verified** against OpenRouter's current docs (openrouter.ai is blocked by this environment's network policy). Verify before relying on them for R10 |
| Reference labels by Claude (blind), not hand labels | §13 says "label by hand" | **Departs from §13.** Results measure agreement with Claude, not ground truth. See below |
| Judge batches store email bodies | R9: raw bodies never persisted | Phase 0-only exception. Stored under gitignored `data/judge/`; delete with `srt-phase0 purge` |

## Running it

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -e 'phase0[test]'
cd phase0 && python -m pytest -q          # 52 tests, no network

# synthetic end-to-end (fake provider: exercises the code, NOT a result)
srt-phase0 run --source fixtures --provider fake --today 2026-11-04 --run-id syn
srt-phase0 fixture-labels
srt-phase0 score --run data/runs/syn --labels data/judge/fixture-labels.jsonl
```

### Dev mode: Claude as the model, inbox via the Gmail connector (current plan)

No Google Cloud project, keys or OpenRouter needed. The founder switches on the claude.ai **Gmail connector** for the session. Then:

1. `srt-phase0 queries` prints the stage-1 search queries. Claude runs them through the Gmail connector and saves the matching emails to `data/inbox/emails.jsonl`, in the same format as `fixtures/synthetic_emails.jsonl` minus `truth`.
2. Claude writes `data/answers/answers.jsonl`: one line per email with its stage-3 (`triage`) and stage-4 (`extraction`) answers, following the rules in `prompts.py`. Triage answers must use only the sender, subject and preview, as a real stage 3 would. See `fixtures/make_claude_answers.py` for the format.
3. `srt-phase0 run --source file --fixtures data/inbox/emails.jsonl --provider replay --answers data/answers/answers.jsonl`
4. **Accuracy check:** the founder reviews the resulting subscription list (`records.json`, summarised by Claude) and marks missed or wrong items. Claude can't judge its own answers.
5. `srt-phase0 purge` deletes the saved emails, answers and runs.

What this measures: Claude's accuracy as the extractor, not the cheap production model's. It doesn't exercise the app's own Gmail code (`GmailSource`).

### Real inbox via the app's own Gmail access (later: once the OAuth client and OpenRouter key exist)

1. **Network:** add `openrouter.ai` to the environment's allowed domains (environment menu in the session title bar → Edit → Network access). The default policy blocks it; Gmail and Google OAuth endpoints are already reachable.
2. Follow [docs/gmail-oauth-setup.md](docs/gmail-oauth-setup.md), then run `srt-phase0 auth start/finish` for each account.
3. `srt-phase0 check --accounts a@gmail.com,b@gmail.com`. All checks must pass before going further.
4. `srt-phase0 run --source gmail --accounts a@gmail.com,b@gmail.com --provider openrouter`
5. `srt-phase0 judge-export --run data/runs/<id>`. This writes shuffled, blind batches of 25: about 300 triage-passed emails plus 100 triage-rejected ones (so triage recall can be measured).
6. Claude reads `data/judge/<id>/RUBRIC.md`, labels each batch without seeing pipeline output, and writes `labels.jsonl`. Then `srt-phase0 judge-check --run data/runs/<id>` confirms every email is labelled and the labels are consistent.
7. `srt-phase0 score --run data/runs/<id> --labels data/judge/<id>/labels.jsonl` writes `scorecard.md`.
8. `srt-phase0 purge` deletes the judge batches, runs and templates.

## How to read the scorecard

- **A3 is judged at merchant level**, because a missed merchant is what causes a missed alert (M1). The verdict is **pass** only if the 95% interval's lower bound clears the target, **fail** if its upper bound is below the target, and **inconclusive** otherwise. Small samples will be inconclusive. That's deliberate.
- **`wrong` in the field table** means the pipeline *asserted* a value that differs from the reference label. That's the failure D5 exists to prevent, and the most important number after recall.

## Known limits (stated plainly)

1. **Claude-as-judge isn't ground truth.** The scores measure agreement with Claude. Both models can make the same mistake, which would inflate the numbers. The judge's own error rate isn't measured.
2. **Recall is measured after stage 1 (Gmail search).** Emails the Gmail search never matched are invisible to both pipeline and judge, so measured recall overstates true recall by an unknown amount. (The fixture `mh-1` demonstrates this.)
3. **Prompt injection:** quote verification stops a model from inventing values, but not from choosing a value that's literally in a malicious email. Fixture `inj-1` shows the fake provider being fooled that way. A real model should resist, but that's untested until the OpenRouter run.
4. **Ambiguous numeric dates** (03/04/2026) accept either reading. Indian senders write day-first, many foreign senders month-first.
5. **Attachments aren't parsed.** Flow sign-off #6 is still open; emails where the amount is only in an attachment are counted as `attachments skipped`.
6. **Out of Phase 0 scope:** lifecycle states that depend on time or user actions (`likely_cancelled`, `cancellation_pending`), Pub/Sub watch (R3), alerts (R7), the unknowns queue (R6), and the funnel's stage 2 (P1).
7. **Tokens are protected by file permissions only** (no KMS/HSM), so R10 isn't met. Fine for a single founder inbox, not for beta users.
8. **Template reuse is lower with concurrency above 1.** Stage-5 templates learned in one thread may not be ready for emails already in flight; use `--concurrency 1` to maximise reuse, at the cost of wall-clock time.

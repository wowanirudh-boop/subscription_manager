"""Command line for Phase 0.

  srt-phase0 auth start  --account you@gmail.com
  srt-phase0 auth finish --account you@gmail.com --redirect-url 'http://localhost:8765/?state=...&code=...'
  srt-phase0 auth revoke --account you@gmail.com
  srt-phase0 check --accounts you@gmail.com   # preflight before a real run
  srt-phase0 run --source gmail --accounts a@gmail.com,b@gmail.com --provider openrouter
  srt-phase0 run --source fixtures --provider fake
  srt-phase0 judge-export --run data/runs/<id>
  srt-phase0 fixture-labels                 # synthetic truth -> labels file
  srt-phase0 judge-check --run data/runs/<id>  # labels cover every exported email
  srt-phase0 score --run data/runs/<id> --labels data/judge/<id>/labels.jsonl
  srt-phase0 purge                          # delete judge batches (email bodies) and runs

All output goes under $SRT_DATA_DIR (default ./data), which is gitignored.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import sys
from pathlib import Path

from . import auth
from .judge import export, labels_from_fixtures, load_labels
from .pipeline import Pipeline, load_run, save_run
from .providers import get_provider
from .score import report, score
from .sources import FixtureSource, GmailSource
from .templates import TemplateStore

DEFAULT_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "synthetic_emails.jsonl"


def data_dir() -> Path:
    return Path(os.environ.get("SRT_DATA_DIR", "data")).resolve()


def _sources(meta: dict) -> dict:
    if meta["source"] in ("fixtures", "file"):
        path = Path(meta["fixtures"])
        accounts = meta.get("accounts") or FixtureSource.accounts(path)
        return {a: FixtureSource(path, a) for a in accounts}
    return {a: GmailSource(auth.load(a, data_dir() / "auth"), a) for a in meta["accounts"]}


def cmd_auth(args) -> None:
    d = data_dir() / "auth"
    if args.action == "start":
        url = auth.start(args.account, d)
        print("Open this URL, sign in as", args.account, "and approve read-only Gmail access:\n")
        print(url)
        print("\nYour browser will then fail to load a http://localhost:8765/ page. That is expected.")
        print("Copy that full localhost URL from the address bar and run:")
        print(f"  srt-phase0 auth finish --account {args.account} --redirect-url '<pasted URL>'")
    elif args.action == "finish":
        email = auth.finish(args.account, args.redirect_url, d)
        print(f"Connected {email} (gmail.readonly).")
    elif args.action == "revoke":
        ok = auth.disconnect(args.account, d)
        print("Token revoked and deleted." if ok else "No token found, or revoke call failed (local token deleted if present).")


def cmd_run(args) -> None:
    run_id = args.run_id or dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = data_dir() / "runs" / run_id
    meta = {
        "source": args.source,
        "fixtures": str(Path(args.fixtures).resolve()) if args.source in ("fixtures", "file") else None,
        "accounts": [a.strip() for a in args.accounts.split(",")] if args.accounts else [],
        "provider": args.provider,
        "started": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    if args.source == "gmail" and not meta["accounts"]:
        sys.exit("--accounts is required for --source gmail")
    sources = _sources(meta)
    meta["accounts"] = list(sources)
    store = TemplateStore(data_dir() / "templates.json" if args.persist_templates else None)
    found = [0]

    def progress(ex):
        found[0] += 1
        if found[0] % 25 == 0 or found[0] == 1:
            print(f"  … {found[0]} subscription-related emails so far", file=sys.stderr)

    if args.provider == "replay" and not args.answers:
        sys.exit("--answers is required for --provider replay")
    pipe = Pipeline(get_provider(args.provider, Path(args.answers) if args.answers else None), store, concurrency=args.concurrency, on_extraction=progress)
    result = pipe.run(sources.values(), today=dt.date.fromisoformat(args.today) if args.today else None)
    save_run(result, run_dir)
    (run_dir / "run_meta.json").write_text(json.dumps(meta, indent=2))
    store.save()
    s = result.stats
    print(f"Run {run_id}: {s.stage1_matches} stage-1 matches, {s.triage_passed} passed triage, "
          f"{s.stage4_calls} model extractions, {s.stage5_hits} template hits, {len(result.records)} records, "
          f"{s.errors} errors. First result {s.first_result_seconds}s, total {s.total_seconds}s.")
    print(f"Output: {run_dir}")


def cmd_judge_export(args) -> None:
    run_dir = Path(args.run).resolve()
    meta = json.loads((run_dir / "run_meta.json").read_text())
    _, traces, _, _ = load_run(run_dir)
    out = data_dir() / "judge" / run_dir.name
    paths = export(traces, _sources(meta), out, n_passed=args.n_passed, n_rejected=args.n_rejected, seed=args.seed)
    print(f"Wrote {len(paths)} batch file(s) to {out} (contains email bodies — purge after scoring).")


def cmd_fixture_labels(args) -> None:
    out = Path(args.out).resolve() if args.out else data_dir() / "judge" / "fixture-labels.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    n = labels_from_fixtures(Path(args.fixtures), out)
    print(f"Wrote {n} labels to {out}")


def cmd_score(args) -> None:
    run_dir = Path(args.run).resolve()
    stats, traces, exs, recs = load_run(run_dir)
    labels = load_labels(Path(args.labels))
    judge_name = next(iter(labels.values())).judge if labels else "none"
    sc = score(traces, exs, recs, labels)
    md = report(sc, stats, judge_name)
    (run_dir / "scorecard.md").write_text(md)
    (run_dir / "scorecard.json").write_text(sc.model_dump_json(indent=2))
    print(md)


def cmd_check(args) -> None:
    from .preflight import run_preflight

    accounts = [a.strip() for a in args.accounts.split(",")] if args.accounts else []
    checks = run_preflight(accounts, data_dir() / "auth")
    for c in checks:
        print(f"[{c.status}] {c.name}: {c.detail}")
    failed = [c for c in checks if c.status == "FAIL"]
    print(f"\n{len(failed)} failing check(s)." if failed else "\nReady for a real-inbox run.")
    if failed:
        sys.exit(1)


def cmd_judge_check(args) -> None:
    from .judge_check import check_labels

    judge_dir = data_dir() / "judge" / Path(args.run).name
    problems, n_exp, n_lab = check_labels(judge_dir)
    print(f"{n_lab} labels for {n_exp} exported emails in {judge_dir}")
    for p in problems:
        print(" -", p)
    if problems:
        sys.exit(1)
    print("Labels complete and consistent.")


def cmd_queries(args) -> None:
    from .queries import QUERY_SET_VERSION, build_queries

    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    print(f"# stage-1 query set {QUERY_SET_VERSION}")
    for q in build_queries(today):
        print(q)


def cmd_purge(args) -> None:
    d = data_dir()
    targets = [d / "judge"] + ([] if args.judge_only else [d / "runs", d / "templates.json", d / "inbox", d / "answers"])
    for t in targets:
        if t.is_dir():
            shutil.rmtree(t)
        elif t.exists():
            t.unlink()
    print("Deleted:", ", ".join(str(t) for t in targets))


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="srt-phase0", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("auth", help="connect / disconnect a Gmail account")
    a.add_argument("action", choices=["start", "finish", "revoke"])
    a.add_argument("--account", required=True)
    a.add_argument("--redirect-url")
    a.set_defaults(func=cmd_auth)

    r = sub.add_parser("run", help="run the funnel over one or more accounts")
    r.add_argument("--source", choices=["gmail", "fixtures", "file"], default="fixtures",
                   help="file = emails saved as JSONL (e.g. read via the Gmail connector)")
    r.add_argument("--fixtures", default=str(DEFAULT_FIXTURES), help="JSONL path for --source fixtures/file")
    r.add_argument("--accounts", help="comma-separated Gmail addresses")
    r.add_argument("--provider", choices=["fake", "openrouter", "replay"], default="fake")
    r.add_argument("--answers", help="answers JSONL for --provider replay (Claude as the model)")
    r.add_argument("--concurrency", type=int, default=8)
    r.add_argument("--persist-templates", action="store_true", help="reuse stage-5 templates across runs")
    r.add_argument("--today", help="override today's date (YYYY-MM-DD) for the 24-month window")
    r.add_argument("--run-id")
    r.set_defaults(func=cmd_run)

    j = sub.add_parser("judge-export", help="write blind batches for the judge")
    j.add_argument("--run", required=True)
    j.add_argument("--n-passed", type=int, default=300)
    j.add_argument("--n-rejected", type=int, default=100)
    j.add_argument("--seed", type=int, default=7)
    j.set_defaults(func=cmd_judge_export)

    fl = sub.add_parser("fixture-labels", help="write synthetic truth as a labels file")
    fl.add_argument("--fixtures", default=str(DEFAULT_FIXTURES))
    fl.add_argument("--out")
    fl.set_defaults(func=cmd_fixture_labels)

    s = sub.add_parser("score", help="score a run against labels")
    s.add_argument("--run", required=True)
    s.add_argument("--labels", required=True)
    s.set_defaults(func=cmd_score)

    c = sub.add_parser("check", help="preflight: keys, network, model capability, Gmail tokens")
    c.add_argument("--accounts", help="comma-separated Gmail addresses whose tokens to test")
    c.set_defaults(func=cmd_check)

    jc = sub.add_parser("judge-check", help="validate labels.jsonl against exported batches")
    jc.add_argument("--run", required=True)
    jc.set_defaults(func=cmd_judge_check)

    qy = sub.add_parser("queries", help="print the stage-1 Gmail search queries")
    qy.add_argument("--today")
    qy.set_defaults(func=cmd_queries)

    pg = sub.add_parser("purge", help="delete judge batches (and, by default, runs and templates)")
    pg.add_argument("--judge-only", action="store_true")
    pg.set_defaults(func=cmd_purge)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()

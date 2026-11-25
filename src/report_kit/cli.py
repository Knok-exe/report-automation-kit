"""report-kit command line interface."""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from . import __version__
from .catalog import check_overrides, load_reports, run_report
from .db import DataError, load_csv_dir
from .history import History
from .pdf import write_pdf
from .synth import generate
from .xlsx import write_xlsx


def _date(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a date (use YYYY-MM-DD): {text}") from None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="report-kit", description=__doc__)
    p.add_argument("--version", action="version", version=f"report-kit {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate-data", help="write synthetic Synthea-style CSVs")
    g.add_argument("--out", default="data")
    g.add_argument("--patients", type=int, default=150)
    g.add_argument("--seed", type=int, default=7)

    ls = sub.add_parser("list", help="list available reports")
    ls.add_argument("--reports-dir")

    r = sub.add_parser("run", help="run reports and write Excel/PDF files")
    r.add_argument("--data", default="data", help="folder of Synthea-style CSV files")
    r.add_argument("--out", default="out")
    r.add_argument("--report", default="all", help="report name or 'all'")
    r.add_argument("--as-of", type=_date, help="report date, default today (UTC)")
    r.add_argument("--param", action="append", default=[], metavar="KEY=VALUE")
    r.add_argument("--formats", default="xlsx,pdf")
    r.add_argument("--history", help="history database, default <out>/history.db")
    r.add_argument("--reports-dir", help="folder of your own .sql reports")
    r.add_argument("--no-record", action="store_true", help="do not store this run in history")

    h = sub.add_parser("history", help="show previous runs")
    h.add_argument("--out", default="out")
    h.add_argument("--history")
    h.add_argument("--report")
    return p


def _cmd_generate(args: argparse.Namespace) -> int:
    counts = generate(args.out, patients=args.patients, seed=args.seed)
    print(f"Wrote synthetic data to {args.out}/ (seed={args.seed})")
    for name, n in counts.items():
        print(f"  {name}.csv  {n} rows")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    for name, rep in load_reports(args.reports_dir).items():
        print(f"{name:20} {rep.title}\n{'':20} {rep.question}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    reports = load_reports(args.reports_dir)
    if args.report != "all" and args.report not in reports:
        print(f"Unknown report {args.report!r}. Available: {', '.join(reports)}", file=sys.stderr)
        return 2
    selected = reports if args.report == "all" else {args.report: reports[args.report]}
    overrides = {}
    for item in args.param:
        key, sep, value = item.partition("=")
        if not sep:
            print(f"--param needs KEY=VALUE, got {item!r}", file=sys.stderr)
            return 2
        overrides[key.strip()] = value
    check_overrides(selected, overrides)
    formats = {f.strip().lower() for f in args.formats.split(",") if f.strip()}
    unknown = formats - {"xlsx", "pdf"}
    if unknown:
        print(
            f"Unknown format(s): {', '.join(sorted(unknown))}. Use xlsx and/or pdf.",
            file=sys.stderr,
        )
        return 2

    as_of = args.as_of or datetime.now(timezone.utc).date()
    run_at = datetime.now(timezone.utc)
    conn = load_csv_dir(args.data)
    history = History(args.history or Path(args.out) / "history.db")
    try:
        for name, report in selected.items():
            result = run_report(conn, report, as_of, overrides, run_at)
            diff = history.diff_against_last(result)
            first_run = diff is None
            stem = Path(args.out) / f"{name}_{as_of.isoformat()}"
            written = []
            if "xlsx" in formats:
                written.append(write_xlsx(result, diff, first_run, stem.with_suffix(".xlsx")))
            if "pdf" in formats:
                written.append(write_pdf(result, diff, first_run, stem.with_suffix(".pdf")))
            if not args.no_record:
                history.record(result)
            change = (
                "first run"
                if first_run
                else f"{len(diff.added)} added, {len(diff.removed)} removed, "
                f"{len(diff.changed)} changed"
            )
            print(f"{name}: {len(result.rows)} rows ({change})")
            for path in written:
                print(f"  -> {path}")
    finally:
        history.close()
    return 0


def _cmd_history(args: argparse.Namespace) -> int:
    path = Path(args.history or Path(args.out) / "history.db")
    if not path.exists():
        print(f"No history yet at {path}")
        return 0
    history = History(path)
    for run_id, report, run_at, as_of, rows in history.runs(args.report):
        print(f"#{run_id:<3} {report:20} run {run_at}  as of {as_of}  {rows} rows")
    history.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {
        "generate-data": _cmd_generate,
        "list": _cmd_list,
        "run": _cmd_run,
        "history": _cmd_history,
    }
    try:
        return handlers[args.command](args)
    except DataError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

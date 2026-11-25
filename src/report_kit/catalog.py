"""Report definitions: .sql files with a metadata header of `-- key: value` lines."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from importlib import resources
from pathlib import Path

from .db import DataError, tables


@dataclass(frozen=True)
class Report:
    name: str
    title: str
    question: str
    key: str
    sql: str
    requires: tuple[str, ...] = ()
    summary: str | None = None
    limitations: str = ""
    params: dict[str, str] = field(default_factory=dict)
    # Columns derived from the report date (age, days since...). They change on every run, so
    # the "what changed since last run" diff ignores them.
    diff_ignore: tuple[str, ...] = ()


@dataclass
class Result:
    report: Report
    columns: list[str]
    rows: list[tuple]
    params: dict[str, object]
    run_at: datetime


def parse_report(name: str, text: str) -> Report:
    meta: dict[str, str] = {}
    params: dict[str, str] = {}
    for line in text.splitlines():
        if not line.startswith("--"):
            break
        body = line[2:].strip()
        if ":" not in body:
            continue
        key, _, value = body.partition(":")
        key, value = key.strip(), value.strip()
        if key.startswith("param "):
            params[key[6:].strip()] = value
        else:
            meta[key] = value
    for needed in ("title", "question", "key"):
        if needed not in meta:
            raise DataError(f"Report {name!r} is missing a '-- {needed}:' header line")
    return Report(
        name=name,
        title=meta["title"],
        question=meta["question"],
        key=meta["key"],
        sql=text,
        requires=tuple(t.strip() for t in meta.get("requires", "").split(",") if t.strip()),
        summary=meta.get("summary"),
        limitations=meta.get("limitations", ""),
        params=params,
        diff_ignore=tuple(c.strip() for c in meta.get("diff_ignore", "").split(",") if c.strip()),
    )


def load_reports(directory: str | Path | None = None) -> dict[str, Report]:
    """Built-in reports, or every *.sql file in `directory`."""
    found: dict[str, Report] = {}
    if directory is None:
        for item in sorted(resources.files("report_kit.sql").iterdir(), key=lambda p: p.name):
            if item.name.endswith(".sql"):
                found[item.name[:-4]] = parse_report(item.name[:-4], item.read_text("utf-8"))
    else:
        for path in sorted(Path(directory).glob("*.sql")):
            found[path.stem] = parse_report(path.stem, path.read_text("utf-8"))
    return found


def run_report(
    conn: sqlite3.Connection,
    report: Report,
    as_of: date,
    overrides: dict[str, str] | None = None,
    run_at: datetime | None = None,
) -> Result:
    missing = [t for t in report.requires if t not in tables(conn)]
    if missing:
        raise DataError(
            f"Report {report.name!r} needs table(s) {', '.join(missing)} "
            "which are not in the data folder"
        )
    params: dict[str, object] = {"as_of": as_of.isoformat()}
    for key, default in report.params.items():
        params[key] = _param_value(report, key, default, (overrides or {}).get(key))
    cursor = conn.execute(report.sql, params)
    columns = [d[0] for d in cursor.description]
    rows = cursor.fetchall()
    _check_key(report, columns, rows)
    return Result(report, columns, rows, params, run_at or datetime.now(timezone.utc))


def _param_value(report: Report, key: str, default: str, override: str | None) -> object:
    """Integer defaults need non-negative integer overrides. A bad value is an error, never a
    silent fallback: in SQL a non-number quietly turns date arithmetic into NULL."""
    try:
        int(default)
    except ValueError:
        return default if override is None else override
    raw = default if override is None else override.strip()
    if not raw.isdigit():
        raise DataError(
            f"Report {report.name!r}: parameter {key!r} must be a whole number >= 0, got {raw!r}"
        )
    return int(raw)


def _check_key(report: Report, columns: list[str], rows: list[tuple]) -> None:
    """The key column identifies rows for the run-to-run diff, so it must exist and be unique."""
    if report.key not in columns:
        raise DataError(
            f"Report {report.name!r}: key column {report.key!r} is not in the results "
            f"(columns: {', '.join(columns)})"
        )
    idx = columns.index(report.key)
    seen: set[str] = set()
    for row in rows:
        value = str(row[idx])
        if value in seen:
            raise DataError(
                f"Report {report.name!r}: key {report.key!r} is not unique "
                f"(value {value!r} appears more than once)"
            )
        seen.add(value)


def check_overrides(reports: dict[str, Report], overrides: dict[str, str]) -> None:
    """Every --param must be declared by at least one selected report (catches typos)."""
    known = {k for r in reports.values() for k in r.params}
    unknown = sorted(set(overrides) - known)
    if unknown:
        raise DataError(
            f"Unknown parameter(s): {', '.join(unknown)}. "
            f"These reports accept: {', '.join(sorted(known)) or 'no parameters'}"
        )

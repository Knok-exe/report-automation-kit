"""Run history (SQLite file) and the 'what changed since last run' diff."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from .catalog import Result


@dataclass
class Diff:
    previous_run_at: str
    previous_as_of: str
    added: list[dict] = field(default_factory=list)
    removed: list[dict] = field(default_factory=list)
    changed: list[tuple[str, dict[str, tuple]]] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.changed)


def _rows(result: Result) -> dict[str, dict]:
    keyed = {}
    idx = result.columns.index(result.report.key)
    for row in result.rows:
        keyed[str(row[idx])] = dict(zip(result.columns, row, strict=True))
    return keyed


class History:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, report TEXT NOT NULL, run_at TEXT NOT NULL,
                as_of TEXT NOT NULL, params TEXT NOT NULL, row_count INTEGER NOT NULL,
                rows_json TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS ix_runs_report ON runs(report, id);
        """)

    def diff_against_last(self, result: Result) -> Diff | None:
        """Compare to the most recent stored run of the same report. None on first run."""
        row = self.conn.execute(
            "SELECT run_at, as_of, rows_json FROM runs WHERE report = ? ORDER BY id DESC LIMIT 1",
            (result.report.name,),
        ).fetchone()
        if row is None:
            return None
        previous = json.loads(row[2])
        current = _rows(result)
        diff = Diff(previous_run_at=row[0], previous_as_of=row[1])
        diff.added = [current[k] for k in current if k not in previous]
        diff.removed = [previous[k] for k in previous if k not in current]
        for key in current:
            if key in previous and current[key] != previous[key]:
                delta = {
                    c: (previous[key].get(c), v)
                    for c, v in current[key].items()
                    if previous[key].get(c) != v
                }
                diff.changed.append((key, delta))
        return diff

    def record(self, result: Result) -> int:
        cur = self.conn.execute(
            "INSERT INTO runs (report, run_at, as_of, params, row_count, rows_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                result.report.name,
                result.run_at.isoformat(timespec="seconds"),
                str(result.params["as_of"]),
                json.dumps(result.params, sort_keys=True),
                len(result.rows),
                json.dumps(_rows(result), default=str),
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid or 0)

    def runs(self, report: str | None = None) -> list[tuple]:
        sql = "SELECT id, report, run_at, as_of, row_count FROM runs"
        args: tuple = ()
        if report:
            sql, args = sql + " WHERE report = ?", (report,)
        return self.conn.execute(sql + " ORDER BY id", args).fetchall()

    def close(self) -> None:
        self.conn.close()

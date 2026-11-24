"""Load Synthea-style CSV files into an in-memory SQLite database."""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

DATE_COLUMNS = {"start", "stop", "date", "birthdate", "deathdate"}
INDEXES = {
    "observations": ("patient", "code"),
    "conditions": ("patient", "code"),
    "medications": ("patient", "code"),
    "appointments": ("patient",),
}


class DataError(Exception):
    """Raised for problems with the input data directory."""


def _clean(column: str, value: str) -> str | None:
    value = value.strip()
    if value == "":
        return None
    if column in DATE_COLUMNS:
        return value[:10]  # Synthea timestamps like 2024-01-15T09:30:00Z -> 2024-01-15
    return value


def load_csv_dir(data_dir: str | Path) -> sqlite3.Connection:
    """Every `<name>.csv` becomes table `<name>`; headers are lower-cased; all values are TEXT
    (dates truncated to YYYY-MM-DD) so SQL decides how to cast them."""
    folder = Path(data_dir)
    files = sorted(folder.glob("*.csv")) if folder.is_dir() else []
    if not files:
        raise DataError(
            f"No CSV files found in {folder}. "
            f"Run `report-kit generate-data --out {folder}` or point at Synthea CSVs."
        )
    conn = sqlite3.connect(":memory:")
    for path in files:
        table = path.stem.lower()
        with path.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.reader(fh)
            header = [h.strip().lower() for h in next(reader, [])]
            if not header:
                raise DataError(f"{path.name} is empty")
            quoted = ", ".join(f'"{h}" TEXT' for h in header)
            conn.execute(f'CREATE TABLE "{table}" ({quoted})')
            marks = ", ".join("?" for _ in header)
            batch = ([_clean(h, v) for h, v in zip(header, row, strict=False)] for row in reader)
            conn.executemany(f'INSERT INTO "{table}" VALUES ({marks})', batch)
        for cols in [INDEXES.get(table)] if INDEXES.get(table) else []:
            for col in cols:
                if col in header:
                    conn.execute(f'CREATE INDEX "ix_{table}_{col}" ON "{table}"("{col}")')
    conn.commit()
    return conn


def tables(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

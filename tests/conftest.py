import csv
from pathlib import Path

import pytest

TODAY = "2026-11-01"


def write(folder: Path, name: str, header: list[str], rows: list[list]) -> None:
    with (folder / f"{name}.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """A tiny hand-built database where every expected result can be checked by eye."""
    d = tmp_path / "data"
    d.mkdir()
    pat = ["Id", "BIRTHDATE", "DEATHDATE", "FIRST", "LAST", "GENDER", "RACE"]
    write(
        d,
        "patients",
        pat,
        [
            ["p1", "1960-01-01", "", "Ann", "One", "F", "white"],
            ["p2", "1950-06-15", "", "Bob", "Two", "M", "black"],
            ["p3", "1970-03-03", "", "Cy", "Three", "M", "asian"],  # diabetes resolved
            ["p4", "1980-12-31", "", "Di", "Four", "F", "other"],  # diabetic, never tested
            ["p5", "1965-05-05", "", "Ed", "Five", "M", "white"],  # A1c exactly 7.0
            ["p6", "1955-07-07", "", "Flo", "Six", "F", "white"],  # A1c exactly 9.0
        ],
    )
    cond = ["START", "STOP", "PATIENT", "ENCOUNTER", "CODE", "DESCRIPTION"]
    write(
        d,
        "conditions",
        cond,
        [
            ["2015-01-01", "", "p1", "e", "44054006", "Diabetes"],
            ["2015-01-01", "", "p2", "e", "44054006", "Diabetes"],
            ["2010-01-01", "2020-01-01", "p3", "e", "44054006", "Diabetes (resolved)"],
            ["2018-01-01", "", "p4", "e", "44054006", "Diabetes"],
            ["2018-01-01", "", "p5", "e", "44054006", "Diabetes"],
            ["2018-01-01", "", "p6", "e", "44054006", "Diabetes"],
        ],
    )
    obs = ["DATE", "PATIENT", "ENCOUNTER", "CODE", "DESCRIPTION", "VALUE", "UNITS"]
    write(
        d,
        "observations",
        obs,
        [
            ["2026-03-01T08:00:00Z", "p1", "e", "4548-4", "HbA1c", "8.2", "%"],  # older reading
            ["2026-09-01T08:00:00Z", "p1", "e", "4548-4", "HbA1c", "6.5", "%"],  # latest -> control
            ["2025-01-01T08:00:00Z", "p2", "e", "4548-4", "HbA1c", "9.5", "%"],  # >365 days old
            ["2026-10-01", "p5", "e", "4548-4", "HbA1c", "7.0", "%"],
            ["2026-10-01", "p6", "e", "4548-4", "HbA1c", "9.0", "%"],
            ["2026-12-15", "p4", "e", "4548-4", "HbA1c", "6.0", "%"],  # after report date
            ["2026-01-01", "p1", "e", "2160-0", "Creatinine", "1.0", "mg/dL"],  # recent renal test
            ["2024-01-01", "p5", "e", "2160-0", "Creatinine", "1.1", "mg/dL"],  # stale renal test
        ],
    )
    med = ["START", "STOP", "PATIENT", "ENCOUNTER", "CODE", "DESCRIPTION"]
    write(
        d,
        "medications",
        med,
        [
            ["2022-01-01", "", "p1", "e", "861007", "Metformin 500 MG"],  # tested -> ok
            ["2022-01-01", "", "p2", "e", "861007", "Metformin 500 MG"],  # never -> flag
            ["2022-01-01", "2025-01-01", "p4", "e", "861007", "Metformin 500 MG"],  # stopped -> no
            ["2022-01-01", "", "p3", "e", "861007", "Metformin 500 MG"],  # not diabetic, flag
            ["2022-01-01", "", "p5", "e", "861007", "Metformin 500 MG"],  # stale -> flag
            ["2022-01-01", "", "p6", "e", "999999", "Some other drug"],  # not metformin
        ],
    )
    write(
        d,
        "appointments",
        ["Id", "DATE", "PATIENT", "DEPARTMENT", "STATUS"],
        [
            ["a1", "2026-10-02", "p1", "Primary Care", "fulfilled"],
            ["a2", "2026-10-09", "p2", "Primary Care", "fulfilled"],
            ["a3", "2026-10-15", "p3", "Primary Care", "fulfilled"],
            ["a4", "2026-10-20", "p4", "Primary Care", "noshow"],
            ["a5", "2026-10-21", "p5", "Primary Care", "noshow"],
            ["a6", "2026-10-22", "p6", "Primary Care", "cancelled"],
            ["a7", "2026-11-05", "p1", "Primary Care", "fulfilled"],  # after report date
        ],
    )
    return d

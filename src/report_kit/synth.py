"""Deterministic synthetic data in the shape of Synthea's CSV export.

Everything here is invented. Column names follow Synthea (a subset). The `appointments` table is
NOT part of Synthea (Synthea has no scheduling/no-show data); it is a clearly labelled extension
so the no-show report has something to run on.
"""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

FIRST = [
    "Alex",
    "Sam",
    "Jordan",
    "Casey",
    "Riley",
    "Morgan",
    "Taylor",
    "Jamie",
    "Avery",
    "Quinn",
    "Drew",
    "Reese",
    "Rowan",
    "Skyler",
    "Parker",
    "Emerson",
    "Harper",
    "Finley",
    "Sage",
    "Blake",
]
LAST = [
    "Smith",
    "Johnson",
    "Brown",
    "Garcia",
    "Miller",
    "Davis",
    "Lopez",
    "Wilson",
    "Moore",
    "Clark",
    "Lewis",
    "Walker",
    "Hall",
    "Young",
    "King",
    "Wright",
    "Scott",
    "Green",
    "Baker",
]
RACE = ["white", "black", "asian", "hispanic", "other"]
DEPARTMENTS = ["Primary Care", "Endocrinology", "Cardiology", "Internal Medicine"]

DIABETES = ("44054006", "Diabetes mellitus type 2 (disorder)")
HYPERTENSION = ("59621000", "Essential hypertension (disorder)")
HBA1C = ("4548-4", "Hemoglobin A1c/Hemoglobin.total in Blood")
CREATININE = ("2160-0", "Creatinine [Mass/volume] in Serum or Plasma")
METFORMIN = ("861007", "Metformin hydrochloride 500 MG Oral Tablet")

FILES = {
    "patients": ["Id", "BIRTHDATE", "DEATHDATE", "FIRST", "LAST", "GENDER", "RACE"],
    "encounters": ["Id", "START", "STOP", "PATIENT", "ENCOUNTERCLASS", "CODE", "DESCRIPTION"],
    "conditions": ["START", "STOP", "PATIENT", "ENCOUNTER", "CODE", "DESCRIPTION"],
    "observations": ["DATE", "PATIENT", "ENCOUNTER", "CODE", "DESCRIPTION", "VALUE", "UNITS"],
    "medications": ["START", "STOP", "PATIENT", "ENCOUNTER", "CODE", "DESCRIPTION"],
    "appointments": ["Id", "DATE", "PATIENT", "DEPARTMENT", "STATUS"],
}


def _uid(rng: random.Random) -> str:
    h = f"{rng.getrandbits(128):032x}"
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def _day(d: date) -> str:
    return d.isoformat()


def generate(
    out_dir: str | Path, patients: int = 150, seed: int = 7, end: date = date(2026, 10, 31)
) -> dict[str, int]:
    """Write CSVs into `out_dir`; returns row counts per file. Same seed -> identical files."""
    rng = random.Random(seed)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows: dict[str, list[list[str]]] = {name: [] for name in FILES}
    start_window = date(2023, 1, 1)

    def encounter(pid: str, when: date, cls: str = "ambulatory") -> str:
        eid = _uid(rng)
        rows["encounters"].append(
            [
                eid,
                _day(when),
                _day(when),
                pid,
                cls,
                "185349003",
                "Encounter for check up (procedure)",
            ]
        )
        return eid

    for _ in range(patients):
        pid = _uid(rng)
        birth = date(1940, 1, 1) + timedelta(days=rng.randrange(0, 365 * 62))
        rows["patients"].append(
            [
                pid,
                _day(birth),
                "",
                rng.choice(FIRST),
                rng.choice(LAST),
                rng.choice("MF"),
                rng.choice(RACE),
            ]
        )
        span = (end - start_window).days

        diabetic = rng.random() < 0.20
        if diabetic:
            onset = start_window - timedelta(days=rng.randrange(30, 2500))
            rows["conditions"].append(
                [_day(onset), "", pid, encounter(pid, onset), DIABETES[0], DIABETES[1]]
            )
        if rng.random() < 0.25:
            onset = start_window - timedelta(days=rng.randrange(30, 3000))
            rows["conditions"].append(
                [_day(onset), "", pid, encounter(pid, onset), HYPERTENSION[0], HYPERTENSION[1]]
            )

        on_metformin = diabetic and rng.random() < 0.7
        if on_metformin:
            began = start_window + timedelta(days=rng.randrange(0, 300))
            rows["medications"].append(
                [_day(began), "", pid, encounter(pid, began), METFORMIN[0], METFORMIN[1]]
            )

        if diabetic:  # periodic HbA1c, some patients lapse
            when = start_window + timedelta(days=rng.randrange(0, 120))
            value = rng.uniform(6.0, 10.5)
            lapse_at = (
                start_window + timedelta(days=rng.randrange(200, span))
                if rng.random() < 0.2
                else None
            )
            while when <= end and (lapse_at is None or when < lapse_at):
                value = min(13.0, max(5.0, value + rng.gauss(0, 0.5)))
                rows["observations"].append(
                    [_day(when), pid, encounter(pid, when), HBA1C[0], HBA1C[1], f"{value:.1f}", "%"]
                )
                when += timedelta(days=rng.choice([90, 120, 180, 270]))

        if (on_metformin and rng.random() < 0.65) or rng.random() < 0.15:  # renal function labs
            when = start_window + timedelta(days=rng.randrange(0, 400))
            while when <= end:
                rows["observations"].append(
                    [
                        _day(when),
                        pid,
                        encounter(pid, when),
                        CREATININE[0],
                        CREATININE[1],
                        f"{rng.uniform(0.7, 1.5):.2f}",
                        "mg/dL",
                    ]
                )
                when += timedelta(days=rng.choice([300, 365, 400]))

        for _ in range(rng.randrange(3, 11)):  # appointments over the last 24 months
            when = date(2024, 11, 1) + timedelta(
                days=rng.randrange(0, (end - date(2024, 11, 1)).days)
            )
            roll = rng.random()
            status = "noshow" if roll < 0.12 else "cancelled" if roll < 0.20 else "fulfilled"
            rows["appointments"].append(
                [_uid(rng), _day(when), pid, rng.choice(DEPARTMENTS), status]
            )

    counts = {}
    for name, header in FILES.items():
        with (out / f"{name}.csv").open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(header)
            writer.writerows(rows[name])
        counts[name] = len(rows[name])
    return counts

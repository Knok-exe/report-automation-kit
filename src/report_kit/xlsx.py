"""Excel workbook: Summary, Data (as an Excel table) and Changes sheets."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

from .catalog import Result
from .history import Diff

HEADER_FILL = PatternFill("solid", fgColor="1F3A5F")
HEADER_FONT = Font(bold=True, color="FFFFFF")
BANNER = "SYNTHETIC DATA ONLY. Educational demo, not clinical decision support."


def _as_text(ws) -> None:
    """openpyxl writes any string starting with '=' as a live formula. Data values must never
    run as formulas (CSV/formula injection), so force those cells back to plain text."""
    for row in ws.iter_rows():
        for cell in row:
            if cell.data_type == "f":
                cell.data_type = "s"


def _autosize(ws, rows: list[list], minimum: int = 10, maximum: int = 48) -> None:
    for idx in range(1, max((len(r) for r in rows), default=0) + 1):
        width = max(
            (len(str(r[idx - 1])) for r in rows if idx <= len(r) and r[idx - 1] is not None),
            default=minimum,
        )
        ws.column_dimensions[get_column_letter(idx)].width = max(minimum, min(maximum, width + 2))


def write_xlsx(result: Result, diff: Diff | None, first_run: bool, path: str | Path) -> Path:
    report = result.report
    wb = Workbook()

    # ---- Summary
    ws = wb.active
    ws.title = "Summary"
    ws["A1"] = report.title
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = BANNER
    ws["A2"].font = Font(italic=True, color="9C2B2B")
    lines: list[tuple[str, object]] = [
        ("Clinical question", report.question),
        ("Report date (as of)", result.params["as_of"]),
        ("Run at (UTC)", result.run_at.isoformat(timespec="seconds")),
        ("Rows", len(result.rows)),
    ]
    for key, value in result.params.items():
        if key != "as_of":
            lines.append((f"Parameter: {key}", value))
    if report.limitations:
        lines.append(("Limitations", report.limitations))
    row = 4
    for label, value in lines:
        ws.cell(row, 1, label).font = Font(bold=True)
        cell = ws.cell(row, 2, value)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        row += 1

    if report.summary and report.summary in result.columns:  # pivot-style counts
        row += 1
        ws.cell(row, 1, f"Count by {report.summary}").font = Font(bold=True)
        row += 1
        for head, col in (("Value", 1), ("Patients/rows", 2)):
            cell = ws.cell(row, col, head)
            cell.fill, cell.font = HEADER_FILL, HEADER_FONT
        idx = result.columns.index(report.summary)
        for value, count in sorted(
            Counter(r[idx] for r in result.rows).items(), key=lambda kv: str(kv[0])
        ):
            row += 1
            ws.cell(row, 1, value)
            ws.cell(row, 2, count)

    row += 2
    ws.cell(row, 1, "Changes since last run").font = Font(bold=True)
    if first_run or diff is None:
        ws.cell(row, 2, "First run, nothing to compare against.")
    else:
        ws.cell(
            row,
            2,
            f"{len(diff.added)} added, {len(diff.removed)} removed, "
            f"{len(diff.changed)} changed (vs run on {diff.previous_run_at}, "
            f"as of {diff.previous_as_of}). See the Changes sheet.",
        )
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 90

    # ---- Data
    data = wb.create_sheet("Data")
    data.append(result.columns)
    for r in result.rows:
        data.append(list(r))
    for cell in data[1]:
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
    _as_text(data)
    data.freeze_panes = "A2"
    if result.rows:
        ref = f"A1:{get_column_letter(len(result.columns))}{len(result.rows) + 1}"
        table = Table(displayName="ReportData", ref=ref)
        table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
        data.add_table(table)
    _autosize(data, [result.columns, *[list(r) for r in result.rows[:200]]])

    # ---- Changes
    changes = wb.create_sheet("Changes")
    changes.append(["Change", report.key, "Detail"])
    for cell in changes[1]:
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
    if diff is not None:
        for item in diff.added:
            changes.append(["Added", item.get(report.key), ""])
        for item in diff.removed:
            changes.append(["Removed", item.get(report.key), ""])
        for key, delta in diff.changed:
            detail = "; ".join(f"{c}: {old} -> {new}" for c, (old, new) in delta.items())
            changes.append(["Changed", key, detail])
    elif first_run:
        changes.append(["", "", "First run, nothing to compare against."])
    _as_text(changes)
    changes.column_dimensions["A"].width = 12
    changes.column_dimensions["B"].width = 40
    changes.column_dimensions["C"].width = 90

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return out

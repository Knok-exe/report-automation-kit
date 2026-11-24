import json
from datetime import date, datetime, timezone

import openpyxl

from report_kit.catalog import load_reports, run_report
from report_kit.db import load_csv_dir
from report_kit.history import History
from report_kit.pdf import write_pdf
from report_kit.xlsx import write_xlsx


def make_result(data_dir, name="diabetes_cohort", as_of=date(2026, 11, 1)):
    return run_report(
        load_csv_dir(data_dir),
        load_reports()[name],
        as_of,
        run_at=datetime(2026, 11, 2, tzinfo=timezone.utc),
    )


def test_first_run_has_no_diff_and_second_run_detects_changes(data_dir, tmp_path):
    history = History(tmp_path / "h.db")
    first = make_result(data_dir)
    assert history.diff_against_last(first) is None
    history.record(first)

    # new patient p7 becomes diabetic; p6's result changes
    with (data_dir / "patients.csv").open("a", newline="") as fh:
        fh.write("p7,1975-01-01,,Gus,Seven,M,white\n")
    with (data_dir / "conditions.csv").open("a", newline="") as fh:
        fh.write("2019-01-01,,p7,e,44054006,Diabetes\n")
    with (data_dir / "observations.csv").open("a", newline="") as fh:
        fh.write("2026-10-20,p6,e,4548-4,HbA1c,6.1,%\n")
    second = make_result(data_dir)
    diff = history.diff_against_last(second)
    assert [r["patient_id"] for r in diff.added] == ["p7"]
    assert diff.removed == []
    changed = dict(diff.changed)
    assert set(changed) == {"p6"}
    assert changed["p6"]["a1c_value"] == (9.0, 6.1)
    assert changed["p6"]["control_status"] == ("Poor control (>=9)", "In control (<7)")


def test_identical_rerun_has_empty_diff(data_dir, tmp_path):
    history = History(tmp_path / "h.db")
    history.record(make_result(data_dir))
    assert history.diff_against_last(make_result(data_dir)).is_empty


def test_removed_rows_detected(data_dir, tmp_path):
    history = History(tmp_path / "h.db")
    history.record(make_result(data_dir))
    text = (data_dir / "conditions.csv").read_text().replace(",,p4,e,", ",2020-01-01,p4,e,")
    (data_dir / "conditions.csv").write_text(text)  # p4's diabetes now has an end date
    diff = history.diff_against_last(make_result(data_dir))
    assert [r["patient_id"] for r in diff.removed] == ["p4"]


def test_history_is_per_report_and_listed(data_dir, tmp_path):
    history = History(tmp_path / "h.db")
    history.record(make_result(data_dir))
    other = make_result(data_dir, "medication_safety")
    assert history.diff_against_last(other) is None  # different report, no baseline
    history.record(other)
    assert [r[1] for r in history.runs()] == ["diabetes_cohort", "medication_safety"]
    assert len(history.runs("medication_safety")) == 1
    stored = history.conn.execute("SELECT rows_json FROM runs WHERE id=1").fetchone()[0]
    assert "p1" in json.loads(stored)


def test_xlsx_structure(data_dir, tmp_path):
    result = make_result(data_dir)
    path = write_xlsx(result, None, True, tmp_path / "r.xlsx")
    wb = openpyxl.load_workbook(path)
    assert wb.sheetnames == ["Summary", "Data", "Changes"]
    data = wb["Data"]
    assert [c.value for c in data[1]] == result.columns
    assert data.max_row == len(result.rows) + 1
    assert "ReportData" in data.tables
    summary = [r for r in wb["Summary"].iter_rows(values_only=True) if r[0]]
    labels = {r[0]: r[1] for r in summary}
    assert labels["Rows"] == 5
    assert labels["Count by control_status"] is None
    assert "First run" in str(labels["Changes since last run"])


def test_xlsx_with_zero_rows_does_not_crash(data_dir, tmp_path):
    result = make_result(data_dir, as_of=date(2000, 1, 1))
    assert result.rows == []
    wb = openpyxl.load_workbook(write_xlsx(result, None, True, tmp_path / "e.xlsx"))
    assert not wb["Data"].tables


def test_xlsx_changes_sheet_lists_differences(data_dir, tmp_path):
    history = History(tmp_path / "h.db")
    history.record(make_result(data_dir))
    later = make_result(data_dir, as_of=date(2026, 12, 20))  # p5/p6 readings age out
    diff = history.diff_against_last(later)
    assert not diff.is_empty
    wb = openpyxl.load_workbook(write_xlsx(later, diff, False, tmp_path / "c.xlsx"))
    kinds = [r[0] for r in wb["Changes"].iter_rows(min_row=2, values_only=True)]
    assert "Changed" in kinds


def test_pdf_is_valid_and_mentions_title(data_dir, tmp_path):
    result = make_result(data_dir)
    path = write_pdf(result, None, True, tmp_path / "r.pdf")
    raw = path.read_bytes()
    assert raw.startswith(b"%PDF") and len(raw) > 1500


def test_pdf_with_zero_rows_and_many_rows(data_dir, tmp_path):
    empty = make_result(data_dir, as_of=date(2000, 1, 1))
    assert write_pdf(empty, None, True, tmp_path / "e.pdf").read_bytes().startswith(b"%PDF")

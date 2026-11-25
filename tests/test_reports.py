from datetime import date

import pytest

from report_kit.catalog import load_reports, parse_report, run_report
from report_kit.db import DataError, load_csv_dir

AS_OF = date(2026, 11, 1)


def run(data_dir, name, as_of=AS_OF, **overrides):
    conn = load_csv_dir(data_dir)
    result = run_report(conn, load_reports()[name], as_of, overrides)
    return [dict(zip(result.columns, row, strict=True)) for row in result.rows]


def by(rows, key="patient_id"):
    return {r[key]: r for r in rows}


# ---- diabetes cohort ------------------------------------------------------------------------


def test_diabetes_cohort_membership(data_dir):
    rows = by(run(data_dir, "diabetes_cohort"))
    assert set(rows) == {"p1", "p2", "p4", "p5", "p6"}  # p3 resolved, so excluded


def test_diabetes_uses_latest_hba1c_not_worst(data_dir):
    p1 = by(run(data_dir, "diabetes_cohort"))["p1"]
    assert p1["a1c_value"] == 6.5 and p1["a1c_date"] == "2026-09-01"
    assert p1["control_status"] == "In control (<7)"


def test_diabetes_old_or_missing_results_are_no_recent_test(data_dir):
    rows = by(run(data_dir, "diabetes_cohort"))
    assert rows["p2"]["control_status"] == "No recent test"  # only result is >365 days old
    assert rows["p4"]["control_status"] == "No recent test"  # only result is after the report date
    assert rows["p4"]["a1c_date"] is None


def test_diabetes_threshold_boundaries(data_dir):
    rows = by(run(data_dir, "diabetes_cohort"))
    assert rows["p5"]["control_status"] == "Above goal (7 to <9)"  # exactly 7.0
    assert rows["p6"]["control_status"] == "Poor control (>=9)"  # exactly 9.0


def test_diabetes_window_parameter_changes_the_answer(data_dir):
    rows = by(run(data_dir, "diabetes_cohort", window_days="30"))
    assert rows["p1"]["control_status"] == "No recent test"  # 2026-09-01 is 61 days before


def test_diabetes_ignores_results_after_report_date(data_dir):
    early = by(run(data_dir, "diabetes_cohort", as_of=date(2026, 6, 1)))
    assert early["p1"]["a1c_value"] == 8.2  # the 2026-09 reading did not exist yet


def test_timestamps_are_truncated_to_dates(data_dir):
    assert by(run(data_dir, "diabetes_cohort"))["p2"]["a1c_date"] == "2025-01-01"


# ---- medication safety ---------------------------------------------------------------------


def test_medication_safety_flags(data_dir):
    rows = by(run(data_dir, "medication_safety"))
    assert set(rows) == {"p2", "p3", "p5"}
    assert rows["p2"]["last_renal_test"] is None
    assert rows["p5"]["last_renal_test"] == "2024-01-01"


def test_medication_safety_excludes_tested_stopped_and_other_drugs(data_dir):
    rows = by(run(data_dir, "medication_safety"))
    assert "p1" not in rows  # recent creatinine
    assert "p4" not in rows  # metformin stopped
    assert "p6" not in rows  # different drug


def test_medication_safety_lookback_window(data_dir):
    # 2024-01-01 -> 2026-11-01 is 1,035 days
    assert "p5" in by(run(data_dir, "medication_safety", window_days="1000"))
    assert "p5" not in by(run(data_dir, "medication_safety", window_days="1100"))


# ---- no-shows ------------------------------------------------------------------------------


def test_noshow_summary_october(data_dir):
    rows = by(run(data_dir, "noshow_summary"), key="month")
    october = rows["2026-10"]
    assert (
        october["scheduled"],
        october["fulfilled"],
        october["noshow"],
        october["cancelled"],
    ) == (6, 3, 2, 1)
    assert october["noshow_rate_pct"] == 33.3
    assert "2026-11" not in rows  # appointment after the report date is ignored


# ---- plumbing ------------------------------------------------------------------------------


def test_missing_table_gives_clear_error(data_dir):
    (data_dir / "appointments.csv").unlink()
    conn = load_csv_dir(data_dir)
    with pytest.raises(DataError, match="appointments"):
        run_report(conn, load_reports()["noshow_summary"], AS_OF)


def test_empty_data_dir_gives_clear_error(tmp_path):
    with pytest.raises(DataError, match="No CSV files"):
        load_csv_dir(tmp_path)


def test_report_header_validation():
    with pytest.raises(DataError, match="title"):
        parse_report("x", "-- question: q\n-- key: k\nSELECT 1;")


def test_custom_reports_directory(tmp_path, data_dir):
    (tmp_path / "mine.sql").write_text(
        "-- title: Mine\n-- question: How many patients?\n-- key: n\n"
        "SELECT COUNT(*) AS n FROM patients;"
    )
    reports = load_reports(tmp_path)
    result = run_report(load_csv_dir(data_dir), reports["mine"], AS_OF)
    assert result.rows == [(6,)]


# ---- parameter, key and window checks ------------------------------------------------------


@pytest.mark.parametrize("bad", ["abc", "-5", "3.5", ""])
def test_non_integer_parameter_is_an_error_not_a_silent_change(data_dir, bad):
    with pytest.raises(DataError, match="window_days"):
        run(data_dir, "diabetes_cohort", window_days=bad)


def test_unknown_parameter_is_rejected():
    from report_kit.catalog import check_overrides

    reports = load_reports()
    with pytest.raises(DataError, match="window_day"):
        check_overrides(reports, {"window_day": "30"})
    check_overrides(reports, {"window_days": "30", "months": "6"})  # both declared somewhere


def test_custom_report_with_missing_or_duplicate_key(tmp_path, data_dir):
    (tmp_path / "missing.sql").write_text(
        "-- title: T\n-- question: Q\n-- key: nope\nSELECT id FROM patients;"
    )
    (tmp_path / "dupes.sql").write_text(
        "-- title: T\n-- question: Q\n-- key: gender\nSELECT gender FROM patients;"
    )
    reports, conn = load_reports(tmp_path), load_csv_dir(data_dir)
    with pytest.raises(DataError, match="not in the results"):
        run_report(conn, reports["missing"], AS_OF)
    with pytest.raises(DataError, match="not unique"):
        run_report(conn, reports["dupes"], AS_OF)


def test_age_is_exact_around_birthdays(data_dir):
    rows = by(run(data_dir, "diabetes_cohort", as_of=date(2026, 6, 14)))
    assert rows["p2"]["age"] == 75  # born 1950-06-15: turns 76 tomorrow
    rows = by(run(data_dir, "diabetes_cohort", as_of=date(2026, 6, 15)))
    assert rows["p2"]["age"] == 76


def test_noshow_uses_whole_months_only(data_dir):
    rows = by(run(data_dir, "noshow_summary", as_of=date(2026, 11, 20)), key="month")
    assert set(rows) == {"2026-10"}  # 2026-11 is the current, incomplete month
    rows = by(run(data_dir, "noshow_summary", as_of=date(2026, 11, 20), months="1"), key="month")
    assert rows["2026-10"]["scheduled"] == 6

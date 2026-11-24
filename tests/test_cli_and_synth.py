from pathlib import Path

from report_kit.cli import main
from report_kit.synth import generate


def test_generator_is_deterministic_and_seed_sensitive(tmp_path):
    a, b, c = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    generate(a, patients=40, seed=3)
    generate(b, patients=40, seed=3)
    generate(c, patients=40, seed=4)
    assert (a / "patients.csv").read_text() == (b / "patients.csv").read_text()
    assert (a / "patients.csv").read_text() != (c / "patients.csv").read_text()


def test_generator_output_shape(tmp_path):
    counts = generate(tmp_path, patients=60, seed=1)
    assert counts["patients"] == 60
    header = (tmp_path / "patients.csv").read_text().splitlines()[0]
    assert header.startswith("Id,BIRTHDATE")


def test_cli_end_to_end(tmp_path, capsys):
    data, out = tmp_path / "data", tmp_path / "out"
    assert main(["generate-data", "--out", str(data), "--patients", "80"]) == 0
    assert main(["run", "--data", str(data), "--out", str(out), "--as-of", "2026-08-01"]) == 0
    assert main(["run", "--data", str(data), "--out", str(out), "--as-of", "2026-11-01"]) == 0
    files = sorted(p.name for p in Path(out).iterdir())
    assert "diabetes_cohort_2026-11-01.xlsx" in files and "noshow_summary_2026-08-01.pdf" in files
    text = capsys.readouterr().out
    assert "first run" in text and "changed" in text
    assert main(["history", "--out", str(out)]) == 0
    assert capsys.readouterr().out.count("#") == 6


def test_cli_single_report_and_format(tmp_path):
    data, out = tmp_path / "data", tmp_path / "out"
    main(["generate-data", "--out", str(data), "--patients", "30"])
    assert (
        main(
            [
                "run",
                "--data",
                str(data),
                "--out",
                str(out),
                "--report",
                "noshow_summary",
                "--formats",
                "xlsx",
                "--as-of",
                "2026-11-01",
                "--param",
                "months=6",
            ]
        )
        == 0
    )
    assert [p.suffix for p in out.glob("noshow*")] == [".xlsx"]


def test_cli_errors_are_clean(tmp_path, capsys):
    assert main(["run", "--data", str(tmp_path / "nope"), "--out", str(tmp_path / "o")]) == 2
    assert "No CSV files" in capsys.readouterr().err
    data = tmp_path / "data"
    main(["generate-data", "--out", str(data), "--patients", "10"])
    assert main(["run", "--data", str(data), "--report", "bogus"]) == 2
    assert main(["run", "--data", str(data), "--formats", "docx"]) == 2
    assert main(["run", "--data", str(data), "--param", "oops"]) == 2


def test_no_record_flag_keeps_history_clean(tmp_path, capsys):
    data, out = tmp_path / "data", tmp_path / "out"
    main(["generate-data", "--out", str(data), "--patients", "20"])
    main(["run", "--data", str(data), "--out", str(out), "--as-of", "2026-11-01", "--no-record"])
    capsys.readouterr()
    main(["history", "--out", str(out)])
    assert "#" not in capsys.readouterr().out

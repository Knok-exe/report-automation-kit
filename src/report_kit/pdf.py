"""One- or two-page PDF summary of a report run (reportlab)."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .catalog import Result
from .history import Diff

MAX_ROWS = 20
MAX_COLS = 7


def _cell(value: object, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape("" if value is None else str(value)), style)


def _table(
    header: list[str], rows: list[list], body: ParagraphStyle, head: ParagraphStyle, width: float
) -> Table:
    data = [[_cell(h, head) for h in header]] + [[_cell(v, body) for v in r] for r in rows]
    # column widths proportional to content length (bounded), so IDs don't wrap awkwardly
    lengths = [
        min(36, max(10, len(str(h)), *(len(str(r[i])) if r[i] is not None else 0 for r in rows)))
        if rows
        else max(10, len(str(h)))
        for i, h in enumerate(header)
    ]
    total = sum(lengths)
    table = Table(data, colWidths=[width * n / total for n in lengths], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3A5F")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#BBBBBB")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F6FA")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def write_pdf(result: Result, diff: Diff | None, first_run: bool, path: str | Path) -> Path:
    report = result.report
    sheet = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=sheet["BodyText"], fontSize=7.5, leading=9)
    head_small = ParagraphStyle(
        "hsmall", parent=small, textColor=colors.white, fontName="Helvetica-Bold"
    )
    banner = ParagraphStyle(
        "banner",
        parent=sheet["BodyText"],
        textColor=colors.HexColor("#9C2B2B"),
        fontName="Helvetica-Oblique",
        fontSize=8.5,
    )
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(out),
        pagesize=letter,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
        title=report.title,
        author="report-automation-kit",
    )
    width = letter[0] - 1.4 * inch
    story: list = [
        Paragraph(escape(report.title), sheet["Title"]),
        Paragraph("SYNTHETIC DATA ONLY. Educational demo, not clinical decision support.", banner),
        Spacer(1, 8),
        Paragraph("<b>Clinical question.</b> " + escape(report.question), sheet["BodyText"]),
        Paragraph(
            f"<b>Report date:</b> {result.params['as_of']} &nbsp; "
            f"<b>Run at (UTC):</b> {result.run_at.isoformat(timespec='seconds')} &nbsp; "
            f"<b>Rows:</b> {len(result.rows)}",
            sheet["BodyText"],
        ),
    ]
    extra = {k: v for k, v in result.params.items() if k != "as_of"}
    if extra:
        story.append(
            Paragraph(
                "<b>Parameters:</b> " + escape(", ".join(f"{k}={v}" for k, v in extra.items())),
                sheet["BodyText"],
            )
        )
    story.append(Spacer(1, 10))

    if report.summary and report.summary in result.columns:
        idx = result.columns.index(report.summary)
        counts = sorted(Counter(r[idx] for r in result.rows).items(), key=lambda kv: str(kv[0]))
        story += [
            Paragraph(f"Count by {escape(report.summary)}", sheet["Heading3"]),
            _table(["Value", "Count"], [[k, v] for k, v in counts], small, head_small, width * 0.5),
            Spacer(1, 10),
        ]

    cols = result.columns[:MAX_COLS]
    shown = [list(r[:MAX_COLS]) for r in result.rows[:MAX_ROWS]]
    story.append(
        Paragraph(f"Results (first {len(shown)} of {len(result.rows)} rows)", sheet["Heading3"])
    )
    if shown:
        story.append(_table(cols, shown, small, head_small, width))
    else:
        story.append(Paragraph("No rows matched.", sheet["BodyText"]))
    if len(result.rows) > MAX_ROWS or len(result.columns) > MAX_COLS:
        story.append(Paragraph("The Excel workbook contains every row and column.", small))

    story.append(Paragraph("Changes since last run", sheet["Heading3"]))
    if first_run or diff is None:
        story.append(Paragraph("First run, nothing to compare against.", sheet["BodyText"]))
    else:
        story.append(
            Paragraph(
                f"{len(diff.added)} added, {len(diff.removed)} removed, "
                f"{len(diff.changed)} changed since the run on "
                f"{diff.previous_run_at} (as of {diff.previous_as_of}).",
                sheet["BodyText"],
            )
        )
        sample = (
            [["Added", str(d.get(report.key)), ""] for d in diff.added[:5]]
            + [["Removed", str(d.get(report.key)), ""] for d in diff.removed[:5]]
            + [
                ["Changed", k, "; ".join(f"{c}: {o} -> {n}" for c, (o, n) in dl.items())]
                for k, dl in diff.changed[:5]
            ]
        )
        if sample:
            story.append(_table(["Change", report.key, "Detail"], sample, small, head_small, width))

    if report.limitations:
        story += [
            Spacer(1, 10),
            Paragraph("Limitations", sheet["Heading3"]),
            Paragraph(escape(report.limitations), small),
        ]
    doc.build(story)
    return out

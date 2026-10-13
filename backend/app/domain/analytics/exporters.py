"""CSV + PDF export of filtered interaction reports."""

import csv
import io
from datetime import datetime

from app.core.config import settings
from app.schemas.interaction import InteractionOut

EXPORT_COLUMNS = [
    "occurred_at",
    "user_email",
    "ai_tool",
    "domain",
    "is_known_platform",
    "is_first_seen",
    "shadow_risk",
    "risk_category",
    "risk_score",
    "is_flagged",
    "applied_action",
    "was_blocked",
    "classification_status",
    "prompt_hash",
    "redacted_preview",
]


def _rows(interactions: list[InteractionOut]) -> list[list[str]]:
    out = []
    for item in interactions:
        out.append(
            [
                item.occurred_at.isoformat(sep=" ", timespec="seconds"),
                item.user_email or "",
                item.ai_tool.value,
                item.domain,
                "yes" if item.is_known_platform else "no",
                "yes" if item.is_first_seen else "no",
                item.shadow_risk.value if item.shadow_risk else "",
                item.risk_category.value,
                f"{item.risk_score:.3f}",
                "yes" if item.is_flagged else "no",
                item.applied_action.value if item.applied_action else "",
                "yes" if item.was_blocked else "no",
                item.classification_status.value,
                item.prompt_hash or "",
                (item.redacted_preview or "").replace("\n", " ")[:400],
            ]
        )
    return out


def to_csv(interactions: list[InteractionOut]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(EXPORT_COLUMNS)
    writer.writerows(_rows(interactions))
    return buffer.getvalue()


def to_pdf(interactions: list[InteractionOut], title: str = "AI usage report") -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4), leftMargin=10 * mm, rightMargin=10 * mm,
        topMargin=12 * mm, bottomMargin=12 * mm,
        title=title,
    )
    header = ["Time (UTC)", "User", "Tool", "Domain", "Category", "Score", "Action", "Preview"]
    data: list[list] = [header]
    for item in _rows(interactions)[:400]:  # keep the PDF readable
        data.append(
            [
                item[0], item[1], item[2], item[3],
                item[7], item[8], item[10] or "log_only",
                Paragraph(item[14][:160] or "-", styles["BodyText"]),
            ]
        )

    table = Table(data, repeatRows=1, colWidths=[32 * mm, 45 * mm, 20 * mm, 42 * mm,
                                                 24 * mm, 14 * mm, 20 * mm, 75 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story = [
        Paragraph(title, styles["Title"]),
        Paragraph(
            f"Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC · "
            f"{len(interactions)} rows · {settings.storage_mode} storage mode",
            styles["BodyText"],
        ),
        Spacer(1, 6 * mm),
        table,
    ]
    doc.build(story)
    return buffer.getvalue()

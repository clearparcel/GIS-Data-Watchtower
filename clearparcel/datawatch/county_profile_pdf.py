"""Render a paginated PDF from one sanitized public county snapshot."""

from __future__ import annotations

import datetime as dt
import io
import json
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode
from xml.sax.saxutils import escape, quoteattr

from .public_values import safe_public_url

_TEMPLATE_VERSION = 2
_MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024
_MAX_PDF_BYTES = 4 * 1024 * 1024
_OPERATIONAL_FIELDS = {"worker", "execution_profile", "monitoring_assessment", "permission"}


def _public_tree(value):
    if isinstance(value, dict):
        return {key: _public_tree(child) for key, child in value.items() if key not in _OPERATIONAL_FIELDS}
    if isinstance(value, list):
        return [_public_tree(item) for item in value]
    return value


def _sections(snapshot):
    directory = snapshot.get("county_directory") or {}
    access = snapshot.get("parcel_access") or {}
    identity = (snapshot.get("parcel_source_profile") or {}).get("county") or {}
    slug = identity.get("slug") or ""
    summary = {key: value for key, value in snapshot.items() if key not in {
        "county", "contacts", "county_directory", "direct_sources", "gac", "mngac",
        "parcel_access", "parcel_source_profile",
    }}
    summary["county_profile_url"] = "https://gis-watchtower.clear-parcel.com/county?" + urlencode({"slug": slug})
    summary["public_revision"] = directory.get("public_revision")
    summary["directory_published_at"] = directory.get("published_at")
    profile = snapshot.get("parcel_source_profile")
    if directory and profile:
        profile = {key: value for key, value in profile.items() if key != "county_directory"}
        profile["packaged_access_research"] = profile.pop("access", {})
    if directory:
        access = {"basis": "Packaged research; current settings are in County GIS data access.", **access}
    sections = {
        "County overview": summary,
        "County GIS contacts": directory.get("contacts", snapshot.get("contacts", [])),
        "County GIS data access": directory.get("access"),
        "County GIS policy": directory.get("policy"),
        "Packaged parcel access research": access,
        "County monitoring and source inventories": profile,
        "Monitored county sources": snapshot.get("direct_sources"),
    }
    standards = snapshot.get("gac") or {}
    for key, title in (("parcel", "Parcel Polygons"), ("road", "Road Centerlines"), ("address", "Address Points")):
        sections[f"MN GAC standard · {title}"] = standards.get(key) or (snapshot.get("mngac") if key == "parcel" else None)
    return _public_tree(sections)


def _rows(value, path=""):
    if isinstance(value, dict) and value:
        for key, child in value.items():
            label = key.replace("_", " ").replace("-", " ").capitalize()
            yield from _rows(child, f"{path} / {label}" if path else label)
    elif isinstance(value, list) and value:
        for index, item in enumerate(value, 1):
            yield from _rows(item, f"{path} [{index}]" if path else f"Record {index}")
    else:
        if value is None or isinstance(value, (list, dict)) or value == "":
            value = "Not available"
        elif isinstance(value, bool):
            value = "Yes" if value else "No"
        yield path or "Status", str(value)


def _text(value: str) -> str:
    clean = re.sub(r"[\x00-\x08\x0b-\x1f\x7f\ud800-\udfff]", " ", value.replace("\r\n", "\n"))
    return escape(clean).replace("\n", "<br/>")


@lru_cache(maxsize=16)
def _render(template: int, title: str, payload: bytes) -> bytes:
    # Imports stay local so installations without the PDF extra retain the dashboard.
    import reportlab
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle
    from reportlab.platypus.doctemplate import LayoutError

    font = "WatchtowerVera"
    if font not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(font, str(Path(reportlab.__file__).with_name("fonts") / "Vera.ttf")))
    ink = colors.HexColor("#152d42")
    styles = {
        "title": ParagraphStyle("WT-title", fontName=font, fontSize=20, leading=25, textColor=ink, spaceAfter=8),
        "section": ParagraphStyle("WT-section", fontName=font, fontSize=13, leading=18, textColor=ink,
                                  spaceBefore=12, spaceAfter=5, keepWithNext=True),
        "body": ParagraphStyle("WT-body", fontName=font, fontSize=9, leading=13, alignment=TA_LEFT),
    }
    generated = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    story = [Paragraph(_text(title), styles["title"]),
             Paragraph(_text(f"Generated {generated} · Public county snapshot · Template {template}"), styles["body"]),
             Spacer(1, 8)]
    for section, content in json.loads(payload).items():
        story.append(Paragraph(_text(section), styles["section"]))
        data = [[Paragraph("Field", styles["body"]), Paragraph("Public value", styles["body"])]]
        for label, value in _rows(content):
            value_markup = _text(value)
            if url := safe_public_url(value):
                value_markup = f'<link href={quoteattr(url)} color="#075888">{value_markup}</link>'
            data.append([Paragraph(_text(label), styles["body"]), Paragraph(value_markup, styles["body"])])
        table = LongTable(data, colWidths=(185, 333), repeatRows=1, splitInRow=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dcebf3")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), (colors.white, colors.HexColor("#f3f7fa"))),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(table)

    def footer(canvas, document):
        canvas.setFont(font, 8)
        canvas.setFillColor(ink)
        canvas.drawString(42, 27, "GIS Data Watchtower")
        canvas.drawRightString(570, 27, f"Page {document.page}")

    output = io.BytesIO()
    document = SimpleDocTemplate(output, pagesize=LETTER, title=title, author="GIS Data Watchtower",
                                 leftMargin=42, rightMargin=42, topMargin=44, bottomMargin=47, lang="en-US")
    try:
        document.build(story, onFirstPage=footer, onLaterPages=footer)
    except LayoutError:
        raise ValueError("county snapshot could not be paginated") from None
    pdf = output.getvalue()
    if len(pdf) > _MAX_PDF_BYTES:
        raise ValueError("county PDF exceeds the output limit")
    return pdf


def county_profile_pdf(snapshot: dict) -> bytes:
    """Build a bounded, cached report keyed by the complete public data and template."""
    sections = _sections(snapshot)
    payload = json.dumps(sections, ensure_ascii=True, allow_nan=False).encode("ascii")
    if len(payload) > _MAX_SNAPSHOT_BYTES:
        raise ValueError("public county snapshot exceeds the PDF limit")
    return _render(_TEMPLATE_VERSION, f'{snapshot["county"]} County profile', payload)

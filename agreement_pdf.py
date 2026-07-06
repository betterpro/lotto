"""Themed PDF export for LottoChee agreements (matches mini app palette)."""

from io import BytesIO

from fpdf import FPDF

# Mini app design tokens (index.css)
THEME = {
    "bg": (23, 33, 43),
    "bg2": (35, 46, 60),
    "surface": (30, 42, 54),
    "hairline": (42, 55, 74),
    "tx": (231, 238, 245),
    "tx2": (133, 150, 168),
    "tx3": (94, 114, 134),
    "accent": (46, 166, 255),
    "money": (78, 208, 122),
    "gold": (245, 199, 59),
}

_MARGIN = 18
_CONTENT_W = 210 - _MARGIN * 2


def _pdf_text(text: str) -> str:
    """Helvetica is Latin-1 only; normalize common Unicode punctuation."""
    return (
        text.replace("\u2014", " - ")
        .replace("\u2013", "-")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
    )


class _AgreementPDF(FPDF):
    def footer(self):
        self.set_y(-16)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*THEME["tx3"])
        self.cell(0, 5, "LottoChee · BC, Canada", align="C")


def _paint_page_bg(pdf: FPDF) -> None:
    pdf.set_fill_color(*THEME["bg"])
    pdf.rect(0, 0, 210, 297, "F")


def _draw_header(pdf: FPDF, title: str, subtitle: str | None = None) -> None:
    pdf.set_fill_color(*THEME["accent"])
    pdf.rect(0, 0, 210, 3, "F")

    pdf.set_xy(_MARGIN, 14)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*THEME["accent"])
    pdf.cell(0, 5, "LOTTO CHEE", ln=1)

    pdf.set_x(_MARGIN)
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_text_color(*THEME["tx"])
    pdf.multi_cell(_CONTENT_W, 7, _pdf_text(title))

    if subtitle:
        pdf.set_x(_MARGIN)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(*THEME["tx2"])
        pdf.multi_cell(_CONTENT_W, 5, _pdf_text(subtitle))

    y = pdf.get_y() + 4
    pdf.set_draw_color(*THEME["hairline"])
    pdf.set_line_width(0.4)
    pdf.line(_MARGIN, y, 210 - _MARGIN, y)
    pdf.set_y(y + 8)


def _draw_highlights(pdf: FPDF, rows: list[tuple[str, str]], box_title: str = "YOUR ROUND") -> None:
    if not rows:
        return
    x, y = _MARGIN, pdf.get_y()
    row_h = 9
    box_h = 10 + len(rows) * row_h
    pdf.set_fill_color(*THEME["surface"])
    pdf.set_draw_color(*THEME["accent"])
    pdf.set_line_width(0.35)
    pdf.rect(x, y, _CONTENT_W, box_h, style="DF")

    pdf.set_xy(x + 8, y + 6)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*THEME["gold"])
    pdf.cell(0, 5, box_title.upper(), ln=1)

    inner_y = y + 14
    for label, value in rows:
        pdf.set_xy(x + 8, inner_y)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*THEME["tx3"])
        pdf.cell(42, row_h - 2, _pdf_text(label))
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*THEME["money"])
        pdf.cell(0, row_h - 2, _pdf_text(value), ln=0)
        inner_y += row_h

    pdf.set_y(y + box_h + 10)


def _is_section_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if s.startswith("—"):
        return False
    if s.isupper() and len(s) < 60:
        return True
    return s.endswith(":") and len(s) < 48 and not s.startswith("  ")


def _section_key(line: str) -> str:
    return line.strip().upper()


def _draw_body(
    pdf: FPDF,
    body: str,
    *,
    skip_until_blank_after: str | None = None,
    skip_sections: list[str] | None = None,
) -> None:
    """Render agreement body; optionally skip sections shown in the highlight card."""
    lines = body.split("\n")
    skipping = False
    skip_target = (skip_until_blank_after or "").strip().upper()
    skip_set = {_section_key(s) for s in (skip_sections or [])}

    for line in lines:
        raw = line.rstrip()
        stripped = raw.strip()
        key = _section_key(stripped)

        if skip_target and key == skip_target:
            skipping = True
            continue
        if key in skip_set:
            skipping = True
            continue
        if skipping:
            if not stripped:
                continue
            if _is_section_line(raw) and key not in skip_set:
                skipping = False
            else:
                continue

        if not stripped:
            pdf.ln(3)
            continue

        pdf.set_x(_MARGIN)
        if _is_section_line(raw):
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(*THEME["tx"])
            pdf.multi_cell(_CONTENT_W, 5, _pdf_text(stripped))
            pdf.ln(1)
        elif stripped.startswith("—") or stripped.startswith("-"):
            pdf.set_font("Helvetica", "I", 9)
            pdf.set_text_color(*THEME["tx3"])
            pdf.multi_cell(_CONTENT_W, 5, _pdf_text(stripped))
        elif raw.startswith("  "):
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(*THEME["tx2"])
            pdf.multi_cell(_CONTENT_W, 5, _pdf_text(stripped))
        else:
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(*THEME["tx2"])
            pdf.multi_cell(_CONTENT_W, 5, _pdf_text(stripped))


def _draw_kv(pdf: FPDF, title: str, rows: list[tuple[str, str]]) -> None:
    if pdf.get_y() > 250:
        pdf.add_page()
        _paint_page_bg(pdf)
    pdf.set_x(_MARGIN)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*THEME["tx"])
    pdf.multi_cell(_CONTENT_W, 6, _pdf_text(title))
    pdf.ln(1)
    for label, value in rows:
        pdf.set_x(_MARGIN)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*THEME["tx3"])
        pdf.cell(40, 5, _pdf_text(label))
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*THEME["tx2"])
        pdf.multi_cell(_CONTENT_W - 40, 5, _pdf_text(value or "-"))
    pdf.ln(4)


def _draw_participants_table(pdf: FPDF, participants: list[dict], pool: float) -> None:
    cols = [("Member", 46), ("City", 42), ("Prov.", 20), ("Share", 24), ("Amount", 42)]
    pdf.set_x(_MARGIN)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(*THEME["tx3"])
    pdf.set_fill_color(*THEME["bg2"])
    for name, w in cols:
        pdf.cell(w, 7, _pdf_text(name), fill=True)
    pdf.ln(7)
    pdf.set_draw_color(*THEME["hairline"])
    pdf.set_line_width(0.2)
    for p in participants:
        if pdf.get_y() > 262:
            pdf.add_page()
            _paint_page_bg(pdf)
        pdf.set_x(_MARGIN)
        me = p.get("is_me")
        pdf.set_font("Helvetica", "B" if me else "", 9)
        pdf.set_text_color(*(THEME["accent"] if me else THEME["tx"]))
        vals = [
            str(p.get("member") or "-"),
            str(p.get("city") or "-"),
            str(p.get("province") or "-"),
            f'{p.get("pct", 0)}%',
            f'${float(p.get("amount") or 0):.2f}',
        ]
        for (name, w), v in zip(cols, vals):
            pdf.cell(w, 7, _pdf_text(v))
        pdf.ln(7)
        y = pdf.get_y()
        pdf.line(_MARGIN, y, 210 - _MARGIN, y)
    # Total row
    pdf.set_x(_MARGIN)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*THEME["money"])
    pdf.cell(cols[0][1] + cols[1][1] + cols[2][1], 8, "TOTAL POOL")
    pdf.cell(cols[3][1], 8, "100%")
    pdf.cell(cols[4][1], 8, f"${float(pool or 0):.2f}")
    pdf.ln(10)


def build_group_play_pdf(
    *,
    title: str,
    subtitle: str,
    round_rows: list[tuple[str, str]],
    trustee: dict,
    you: dict,
    participants: list[dict],
    pool: float,
    body: str | None = None,
) -> bytes:
    """Group play agreement form: round details, trustee + downloader personal
    details, and an anonymized participant table (others show only LottoChee id,
    city, province, share and amount)."""
    pdf = _AgreementPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=22)
    pdf.set_margins(_MARGIN, _MARGIN, _MARGIN)
    pdf.add_page()
    _paint_page_bg(pdf)
    _draw_header(pdf, title, subtitle)
    _draw_highlights(pdf, round_rows, box_title="ROUND DETAILS")

    _draw_kv(pdf, "GROUP TRUSTEE", [
        ("Name", trustee.get("name")),
        ("Address", trustee.get("address")),
        ("Phone", trustee.get("phone")),
        ("Email", trustee.get("email")),
    ])
    _draw_kv(pdf, "YOUR DETAILS", [
        ("Name", you.get("name")),
        ("Address", you.get("address")),
        ("Phone", you.get("phone")),
        ("Email", you.get("email")),
        ("Your shares", you.get("shares")),
        ("Your stake", you.get("amount")),
        ("Pool share", you.get("pct")),
    ])

    if pdf.get_y() > 235:
        pdf.add_page()
        _paint_page_bg(pdf)
    pdf.set_x(_MARGIN)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*THEME["tx"])
    pdf.multi_cell(_CONTENT_W, 6, "GROUP MEMBERS")
    pdf.set_x(_MARGIN)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*THEME["tx3"])
    pdf.multi_cell(_CONTENT_W, 4, _pdf_text(
        "Other members are shown by their LottoChee id only; names and contact "
        "details are withheld for privacy."))
    pdf.ln(2)
    _draw_participants_table(pdf, participants, pool)

    if body:
        _draw_body(pdf, body)

    buf = BytesIO()
    pdf.output(buf)
    return buf.getvalue()


def build_agreement_pdf(
    *,
    title: str,
    body: str,
    subtitle: str | None = None,
    highlights: list[tuple[str, str]] | None = None,
    highlights_title: str = "YOUR ROUND",
    skip_sections: list[str] | None = None,
) -> bytes:
    pdf = _AgreementPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=22)
    pdf.set_margins(_MARGIN, _MARGIN, _MARGIN)
    pdf.add_page()
    _paint_page_bg(pdf)
    _draw_header(pdf, title, subtitle)
    if highlights:
        _draw_highlights(pdf, highlights, box_title=highlights_title)
    skip_participation = highlights_title == "YOUR ROUND"
    _draw_body(
        pdf,
        body,
        skip_until_blank_after="YOUR PARTICIPATION" if skip_participation else None,
        skip_sections=skip_sections,
    )

    buf = BytesIO()
    pdf.output(buf)
    return buf.getvalue()

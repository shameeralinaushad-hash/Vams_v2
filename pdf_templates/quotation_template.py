import os
import re as _re
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT
from reportlab.pdfbase.pdfmetrics import stringWidth as _sw
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, KeepTogether, PageBreak

from pdf_templates.theme_config import get_theme, get_doc_title
from pdf_templates.shared import sanitize_text, get_image_dimensions, VisionHeading


def fit_column_widths(contents, content_width, bold_font, body_font, font_size=8.5,
                      padding=8.0, max_frac=0.28):
    """Return column widths (pt) sized to the widest header/cell text.

    contents: list of (header_text, [cell_texts...]). Each column is measured
    with exact font metrics via stringWidth so short columns take only the room
    they need. A column whose content would run wider than max_frac *
    content_width is treated as a wrapping column: it is capped at max_frac so
    long descriptions still wrap. The table is allowed to end up narrower than
    content_width when the data is short -- that extra space is left empty
    instead of padding any column.
    """
    naturals = []
    floors = []
    for header, cells in contents:
        needed = _sw(header, bold_font, font_size)
        longest_word = _sw(header, bold_font, font_size)
        for cell in cells:
            if cell:
                needed = max(needed, _sw(cell, body_font, font_size))
                longest_word = max(longest_word, max(
                    (_sw(w, body_font, font_size) for w in _re.split(r"\s+", cell) if w),
                    default=0.0,
                ))
        naturals.append(needed + padding)
        floors.append(min(longest_word + padding, max_frac * content_width))

    cap = max_frac * content_width
    wrapping = [i for i, n in enumerate(naturals) if n > cap]
    widths = naturals[:]

    total = sum(widths)
    if not wrapping:
        # All content is short: every column takes exactly what it needs; the
        # table may end up narrower than the content width, which is fine --
        # no column holds padding it does not need.
        return widths

    if total <= content_width:
        # Give the unused space back to the wrapping columns (they wrap less),
        # up to their caps, so the table still fills the content width.
        slack = content_width - total
        order = sorted(wrapping, key=lambda i: naturals[i], reverse=True)
        for i in order:
            if slack <= 0:
                break
            room = cap - widths[i]
            if room <= 0:
                continue
            add = min(room, slack)
            widths[i] += add
            slack -= add
        return widths

    # Overflow: short columns keep their natural width; reduce only the
    # wrapping columns (largest first) down to their floor so long text wraps
    # instead of overflowing.
    overflow = total - content_width
    order = sorted(range(len(widths)), key=lambda i: widths[i] - floors[i], reverse=True)
    for i in order:
        if overflow <= 0:
            break
        room = widths[i] - floors[i]
        if room <= 0:
            continue
        cut = min(room, overflow)
        widths[i] -= cut
        overflow -= cut
    if overflow > 0:
        scale = content_width / sum(widths)
        widths = [w * scale for w in widths]
    return widths


def build_heading(theme, title_text, content_width, company=None):
    if company and getattr(company, "pdf_theme", None) == "Rostam":
        return VisionHeading(sanitize_text(title_text), content_width, theme)

    align = theme.get("heading_align", "left")
    style_align = TA_CENTER if align == "center" else TA_LEFT

    if theme.get("heading_style") == "banner":
        banner_style = ParagraphStyle(
            "heading_banner", fontName=theme["font_bold"], fontSize=14,
            alignment=TA_CENTER, textColor=theme["table_header_text_color"]
        )
        p = Paragraph(sanitize_text(title_text).upper(), banner_style)
        t = Table([[p]], colWidths=[content_width])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), theme["table_header_bg"]),
            ("BOX", (0, 0), (-1, -1), theme.get("outer_border_width", 0.75),
             theme.get("outer_border_color", colors.black)),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ]))
        return t

    plain_style = ParagraphStyle(
        "heading_plain", fontName=theme["font_bold"], fontSize=16,
        alignment=style_align, textColor=theme["accent_color"]
    )
    return Paragraph(sanitize_text(title_text), plain_style)


def build_shipper_receiver_block(theme, company, client, quotation, content_width):
    border_color = theme.get("outer_border_color", colors.black)
    border_width = theme.get("outer_border_width", 0.5)

    label_style = ParagraphStyle("sr_label", fontName=theme["font_bold"], fontSize=9,
                                 alignment=TA_CENTER)
    body_style = ParagraphStyle("sr_body", fontName=theme["font_body"], fontSize=9, leading=12)

    shipper_text = sanitize_text(company.name)

    if getattr(quotation, "recipient", None):
        receiver_lines = [sanitize_text(line) for line in quotation.recipient.split("\n")]
    else:
        receiver_lines = [sanitize_text(client.name)]
        if getattr(client, "address", None):
            for line in client.address.split("\n"):
                receiver_lines.append(sanitize_text(line))

    receiver_text = "<br/>".join(receiver_lines)

    data = [
        [Paragraph("SHIPPER", label_style), Paragraph("RECEIVER", label_style)],
        [Paragraph(shipper_text, body_style), Paragraph(receiver_text, body_style)],
    ]
    t = Table(data, colWidths=[content_width / 2, content_width / 2])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), theme["table_header_bg"]),
        ("GRID", (0, 0), (-1, -1), border_width, border_color),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def build_subject_ref_bar(theme, subject_text, ref_label, ref_value, content_width):
    border_color = theme.get("outer_border_color", colors.black)
    border_width = theme.get("outer_border_width", 0.5)

    style_l = ParagraphStyle("sub_l", fontName=theme["font_bold"], fontSize=9)
    style_r = ParagraphStyle("sub_r", fontName=theme["font_bold"], fontSize=9, alignment=TA_RIGHT)

    left_cell = Paragraph(sanitize_text(subject_text or ""), style_l)
    right_cell = Paragraph(f"{ref_label} {sanitize_text(ref_value or '')}".strip(), style_r)

    t = Table([[left_cell, right_cell]], colWidths=[content_width * 0.62, content_width * 0.38])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), theme["table_header_bg"]),
        ("GRID", (0, 0), (-1, -1), border_width, border_color),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def get_table_columns(theme, content_width):
    mode = theme.get("table_columns", "full")
    if mode == "no_unit":
        col_widths = [content_width * 0.12, content_width * 0.36, content_width * 0.15, content_width * 0.185,
                      content_width * 0.185]
        return (["S. No", "Description", "Quantity", "Rate", "Amount"], col_widths, mode)
    if mode == "no_srno":
        col_widths = [content_width * 0.42, content_width * 0.12, content_width * 0.14, content_width * 0.16,
                      content_width * 0.16]
        return (["Description", "Unit", "Quantity", "Unit Price", "Total"], col_widths, mode)

    col_widths = [
        content_width * 0.08,  # Sr. No
        content_width * 0.36,  # Items
        content_width * 0.12,  # Unit
        content_width * 0.12,  # Quantity
        content_width * 0.16,  # Unit Price
        content_width * 0.16  # Total
    ]
    return (["Sr. No", "Items", "Unit", "Quantity", "Unit Price", "Total"], col_widths, mode)


def resolve_quotation_columns(company, quotation):
    """Returns the explicit column key list for a quotation, or None for
    automatic (data-driven) columns. Company-level defaults (company.pdf_columns)
    are used unless the quotation itself overrides them."""
    configured = None
    company_cols = getattr(company, "pdf_columns", None)
    if company_cols and isinstance(company_cols, dict):
        configured = company_cols.get("quotation")
    vc = getattr(quotation, "visible_columns", None)
    if vc and isinstance(vc, dict) and "columns" in vc:
        configured = vc["columns"]
    return configured


def resolve_quotation_custom_fields(quotation):
    """Returns {str(field_id): field_name} for the custom-field columns enabled
    on this specific quotation (stored in quotation.visible_columns)."""
    vc = getattr(quotation, "visible_columns", None)
    if vc and isinstance(vc, dict) and isinstance(vc.get("custom_fields"), dict):
        return vc["custom_fields"]
    return {}


def build_item_row(mode, idx, item, style_normal):
    line_total = item.qty * item.unit_price
    desc = Paragraph(sanitize_text(item.description), style_normal)
    unit = sanitize_text(item.unit) or "Nos"
    if mode == "no_unit":
        return [str(idx), desc, f"{item.qty:g}", f"{item.unit_price:,.2f}", f"{line_total:,.2f}"], line_total
    if mode == "no_srno":
        return [desc, unit, f"{item.qty:g}", f"{item.unit_price:,.2f}", f"{line_total:,.2f}"], line_total
    return [str(idx), desc, unit, f"{item.qty:g}", f"{item.unit_price:,.2f}", f"{line_total:,.2f}"], line_total


def build_item_table_style(theme, total_row_idx, mode, num_rows):
    if mode in ("no_unit", "no_srno"):
        num_col, price_col, total_col = 2, 3, 4
    else:
        num_col, price_col, total_col = 3, 4, 5
    first_col_align = "CENTER" if mode != "no_srno" else "LEFT"

    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), theme["table_header_bg"]),
        ("TEXTCOLOR", (0, 0), (-1, 0), theme["table_header_text_color"]),
        ("FONTNAME", (0, 0), (-1, 0), theme["font_bold"]),
        ("FONTNAME", (0, 1), (-1, -1), theme["font_body"]),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, -1), first_col_align),
        ("ALIGN", (num_col - 1, 0), (num_col, -1), "CENTER"),
        ("ALIGN", (price_col, 0), (total_col, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]

    border_style = theme["table_border_style"]
    border_color = theme.get("outer_border_color", colors.black)
    border_width = theme.get("outer_border_width", 0.5)
    if border_style == "grid":
        commands.append(("GRID", (0, 0), (-1, -1), border_width, border_color))
    elif border_style == "horizontal_only":
        commands.append(("LINEABOVE", (0, 0), (-1, 0), 0.75, colors.black))
        commands.append(("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.Color(0.6, 0.6, 0.6)))
    elif border_style == "zebra":
        commands.append(("LINEBELOW", (0, 0), (-1, 0), 0.75, colors.black))
        commands.append(("LINEBELOW", (0, total_row_idx - 1), (-1, total_row_idx - 1), 0.75, colors.black))
        commands.append(("ROWBACKGROUNDS", (0, 1), (-1, total_row_idx - 1),
                         [colors.white, theme["zebra_color"]]))

    last_label_col = total_col - 1

    for r in range(total_row_idx, num_rows):
        is_last = (r == num_rows - 1)
        commands.append(("SPAN", (0, r), (last_label_col, r)))
        commands.append(("FONTNAME", (0, r), (-1, r), theme["font_bold"]))
        commands.append(("FONTSIZE", (0, r), (-1, r), 9.5))
        commands.append(("ALIGN", (0, r), (last_label_col, r), "LEFT"))
        commands.append(("RIGHTPADDING", (total_col, r), (total_col, r), 5))

        if theme["total_row_style"] == "boxed" and is_last:
            commands.append(("BACKGROUND", (0, r), (-1, r), theme["table_header_bg"]))
            commands.append(("TEXTCOLOR", (0, r), (-1, r), theme["table_header_text_color"]))
        else:
            if r == total_row_idx:
                commands.append(("LINEABOVE", (0, r), (-1, r), 1.2, theme["accent_color"]))
            commands.append(("TEXTCOLOR", (0, r), (-1, r), colors.black))

    return commands


def build_charge_summary(theme, subtotal, discount, installation, transportation, summary_width):
    label_style = ParagraphStyle("chg_label", fontName=theme["font_bold"], fontSize=9, alignment=TA_RIGHT)
    val_style = ParagraphStyle("chg_val", fontName=theme["font_body"], fontSize=9, alignment=TA_RIGHT)
    grand_label_style = ParagraphStyle("chg_grand_label", fontName=theme["font_bold"], fontSize=10, alignment=TA_RIGHT)
    grand_val_style = ParagraphStyle("chg_grand_val", fontName=theme["font_bold"], fontSize=10, alignment=TA_RIGHT)

    def fmt(v):
        return f"{v:,.2f}" if v else "-"

    subtotal_less_discount = subtotal - discount
    grand_total = subtotal_less_discount + installation + transportation

    rows = [
        [Paragraph("SUBTOTAL LESS DISCOUNT", label_style), Paragraph(fmt(subtotal_less_discount), val_style)],
        [Paragraph("Installation Charges", label_style), Paragraph(fmt(installation), val_style)],
        [Paragraph("Transportation Charges", label_style), Paragraph(fmt(transportation), val_style)],
        [Paragraph("GRAND TOTAL", grand_label_style), Paragraph(fmt(grand_total), grand_val_style)],
    ]
    t = Table(rows, colWidths=[summary_width * 0.62, summary_width * 0.38])
    t.hAlign = "RIGHT"
    t.setStyle(TableStyle([
        ("LINEABOVE", (0, 3), (-1, 3), 0.75, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t, grand_total


FALLBACK_HEADER_HEIGHT = 34 * mm
LOGO_MAX_SIZE = 28 * mm
ACCENT_BAR_HEIGHT = 1.2 * mm
MAX_HEADER_MM = 80
MAX_FOOTER_MM = 35

BLANK_MARGIN_MM = 38


def _tech_photo_flowable(photo_path, size_mm, col_width_mm):
    """Returns a ReportLab Image for a stored photo path (relative to static/),
    or None when the file cannot be rendered. size_mm is the requested image
    height; width = height * 4/3. The image is clamped to the photo column
    width (minus padding) so a large setting never overflows the column."""
    if not photo_path:
        return None
    full = os.path.join("static", photo_path.lstrip("/"))
    if not os.path.exists(full):
        return None
    pt_per_mm = 72.0 / 25.4
    height = float(size_mm) * pt_per_mm
    width = height * (4.0 / 3.0)
    if col_width_mm:
        usable = max(float(col_width_mm) * pt_per_mm - 2 * mm, 1)
        if width > usable:
            width = usable
            height = width * 0.75
    try:
        img = Image(full, width=width, height=height, kind="proportional")
        img.hAlign = "CENTER"
        return img
    except Exception:
        return None


def _build_technical_offer_story(theme, company, quotation, line_items, content_width,
                                 style_normal, style_terms_head, style_terms_body, style_name):
    is_vision = company and getattr(company, "pdf_theme", None) == "Rostam"

    style_recipient = ParagraphStyle("recipient_v", fontName=theme["font_body"], fontSize=9.5, leading=12.5)
    style_bold = ParagraphStyle("bold_v", fontName=theme["font_bold"], fontSize=9.5)
    style_meta = ParagraphStyle("meta_v", fontName=theme["font_bold"], fontSize=9.5, alignment=TA_RIGHT)
    style_title = ParagraphStyle(
        "title_v", fontName=theme["font_bold"], fontSize=14, leading=18,
        alignment=TA_CENTER, textColor=theme["accent_color"],
    )
    style_subject = ParagraphStyle("subject_v", fontName=theme["font_bold"], fontSize=9.5, leading=12.5)

    story = []
    if is_vision:
        story.append(VisionHeading("TECHNICAL OFFER", content_width, theme))
    else:
        story.append(Paragraph("TECHNICAL OFFER", style_title))
    story.append(Spacer(1, 4 * mm))

    top_style = ParagraphStyle("top_v", fontName=theme["font_bold"], fontSize=9, leading=11.5)
    top_cells = [
        Paragraph(f"Offer No.<br/>{sanitize_text(quotation.quote_number)}", top_style),
        Paragraph(f"Offer Date<br/>{quotation.quote_date.strftime('%d-%B-%Y') if quotation.quote_date else ''}", top_style),
    ]
    if quotation.client_ref_number:
        top_cells.append(Paragraph(f"Client Ref.<br/>{sanitize_text(quotation.client_ref_number)}", top_style))
    top_tbl = Table([top_cells], colWidths=[content_width / len(top_cells)])
    top_tbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(top_tbl)
    story.append(Spacer(1, 4 * mm))

    to_lines = [sanitize_text(line) for line in (quotation.recipient or "").split("\n")] if quotation.recipient else []
    left_part = Paragraph("<b>TO:</b><br/><br/>" + ("<br/>".join(to_lines) if to_lines else "&nbsp;"), style_recipient)
    from_part = Paragraph(
        f"<b>FROM:</b> {sanitize_text(company.name)}<br/>{sanitize_text(company.address or '')}",
        style_recipient,
    ) if company.address else Paragraph(f"<b>FROM:</b> {sanitize_text(company.name)}", style_recipient)
    to_tbl = Table([[left_part, from_part]], colWidths=[content_width / 2, content_width / 2])
    to_tbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(to_tbl)
    story.append(Spacer(1, 3 * mm))

    if quotation.subject:
        subject_tbl = Table(
            [[Paragraph(f"Subject: {sanitize_text(quotation.subject)}", style_subject)]],
            colWidths=[content_width],
        )
        subject_tbl.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(subject_tbl)
        story.append(Spacer(1, 4 * mm))

    hdr_cell = ParagraphStyle("vh", fontName=theme["font_bold"], fontSize=8.5, leading=11,
                              textColor=theme["table_header_text_color"])
    hdr_c = ParagraphStyle("vhc", parent=hdr_cell, alignment=TA_CENTER)
    cell_c = ParagraphStyle("vc_c", parent=style_normal, alignment=TA_CENTER)
    cell_l = ParagraphStyle("vc_l", parent=style_normal)
    cell_r = ParagraphStyle("vc_r", parent=style_normal, alignment=TA_RIGHT)

    has_photos = any(getattr(item, "photo_path", None) for item in line_items)

    vc = getattr(quotation, "visible_columns", None)
    photo_size_mm = 18
    if isinstance(vc, dict):
        try:
            photo_size_mm = int(vc.get("photo_size_mm") or 18)
        except (TypeError, ValueError):
            photo_size_mm = 18

    col_defs = [
        ("Ser", 0.035, "C", cell_c, lambda idx, item: str(idx)),
        ("Part No", 0.10, "c", cell_c, lambda idx, item: sanitize_text(item.part_no or "")),
        ("Nomenclature", 0.20, "l", cell_l, lambda idx, item: sanitize_text(item.description)),
        ("A/U", 0.045, "c", cell_c, lambda idx, item: sanitize_text(item.unit or "Nos")),
        ("Req Qty", 0.05, "c", cell_c, lambda idx, item: f"{item.qty:g}"),
        ("Details Specs", 0.24, "l", cell_l, lambda idx, item: sanitize_text(item.specs or "")),
        ("COO", 0.055, "c", cell_c, lambda idx, item: sanitize_text(item.coo or "")),
        ("Quoted/NQ", 0.08, "c", cell_c, lambda idx, item: sanitize_text(item.quoted or "")),
        ("Remarks", 0.11, "l", cell_l, lambda idx, item: sanitize_text(item.remark or "")),
    ]
    # The Photo column auto-widens to fit the requested photo height. Photos are
    # rendered at a 4:3 aspect ratio (width = height * 4/3) with ~2mm column
    # padding, so the column needs need_mm of width to honour the request. It is
    # capped at 55% of the content width so the other columns keep usable space;
    # requests beyond that saturate at the cap (photo still grows, just capped).
    if has_photos:
        content_mm = content_width / mm
        max_col_mm = 0.55 * content_mm
        need_mm = photo_size_mm * 4.0 / 3.0 + 2.0
        photo_col_mm = min(need_mm, max_col_mm)
    else:
        photo_col_mm = None

    # Content-aware widths: measure each column against its widest header/cell
    # text (exact font metrics via stringWidth). Short columns shrink to their
    # content; long description columns (Nomenclature / Details Specs) wrap but
    # only claim a capped share of the width. The Photo column keeps its own
    # computed size so it never depends on the text fitting.
    avail = (content_width - photo_col_mm * mm) if photo_col_mm else content_width
    contents = []
    for label, _, _, _, fn in col_defs:
        cells = [fn(idx, item) for idx, item in enumerate(line_items, start=1)]
        contents.append((label, cells))
    widths = fit_column_widths(contents, avail, theme["font_bold"], theme["font_body"])
    if photo_col_mm:
        widths.append(photo_col_mm * mm)
        cols = col_defs + [("Photo", 0.0, "c", None, None)]
    else:
        cols = col_defs

    header_row = [Paragraph(label, hdr_cell) for label, _, _, _, _ in cols]

    # Group items by annexure
    annexure_groups = _group_items_by_annexure(line_items, quotation)

    for group_name, group_items, page_break in annexure_groups:
        if page_break:
            from reportlab.platypus import PageBreak as _PB
            story.append(_PB())

        if group_name:
            story.append(_make_annexure_header(group_name, theme, content_width))
            story.append(Spacer(1, 3 * mm))

        idata = [header_row]
        for idx, item in enumerate(group_items, start=1):
            row = []
            for label, frac, align, cell_style, fn in cols:
                if label == "Photo":
                    ph = _tech_photo_flowable(item.photo_path, photo_size_mm, photo_col_mm)
                    row.append(ph if ph is not None else Paragraph("&nbsp;", cell_c))
                else:
                    row.append(Paragraph(fn(idx, item), cell_style or cell_l))
            idata.append(row)

        it = Table(idata, colWidths=widths, repeatRows=1)
        rcmds = [
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("BACKGROUND", (0, 0), (-1, 0), theme["table_header_bg"]),
            ("TEXTCOLOR", (0, 0), (-1, 0), theme["table_header_text_color"]),
            ("FONTNAME", (0, 0), (-1, 0), theme["font_bold"]),
            ("FONTNAME", (0, 1), (-1, -1), theme["font_body"]),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]
        for c, (label, frac, align, cell_style, fn) in enumerate(cols):
            if align == "c":
                rcmds.append(("ALIGN", (c, 0), (c, -1), "CENTER"))
            elif align == "r":
                rcmds.append(("ALIGN", (c, 0), (c, -1), "RIGHT"))
        it.setStyle(TableStyle(rcmds))
        story.append(it)
        story.append(Spacer(1, 4 * mm))

    if quotation.terms_conditions:
        terms_block = [Paragraph("Terms &amp; Conditions:", style_terms_head), Spacer(1, 2 * mm)]
        for line in quotation.terms_conditions.split("\n"):
            if line.strip():
                terms_block.append(Paragraph(sanitize_text(line), style_terms_body))
        story.append(KeepTogether(terms_block))
        story.append(Spacer(1, 10 * mm))

    sig_block = []
    if company.signature_filename:
        sig_path = os.path.join("static", "signatures", company.signature_filename)
        if os.path.exists(sig_path):
            sig_img = Image(sig_path, width=theme["signature_width_mm"] * mm,
                            height=theme["signature_height_mm"] * mm, kind="proportional")
            sig_img.hAlign = theme["signature_align"].upper()
            sig_block.append(sig_img)
            sig_block.append(Spacer(1, 2 * mm))
    if company.authorized_name:
        sig_block.append(Paragraph(sanitize_text(company.authorized_name), style_name))
    if theme.get("show_company_name_under_signature"):
        sig_block.append(Paragraph(sanitize_text(company.name), style_name))
    story.append(KeepTogether(sig_block))

    return story


# ---------------------------------------------------------------------------
# CASD EME tender-annex layout ("layout": "tender_annex" in theme_config.py)
#
# Space Enterprises and The Expert International both respond to the same
# client's (CASD EME) tenders, on that client's own Annexure 'A' form. The
# two companies' PDFs need to reproduce that form field-for-field -- same
# headings, same "To:" / tender-no block, same table columns -- so the
# submitted quotation matches what the client expects to receive. The two
# only differ in header arrangement and a few column labels, both captured
# by theme["tender_style"] ("space" | "expert") and the theme["tender_*"]
# label overrides below.
# ---------------------------------------------------------------------------

def _build_tender_header(theme, quotation, doc_title, content_width):
    """Builds the recipient / annexure / tender-no block above the item
    table, matching either the Space Enterprises or The Expert International
    tender-annex arrangement (theme["tender_style"])."""
    style = theme.get("tender_style", "space")
    font_body = theme["font_body"]
    font_bold = theme["font_bold"]
    story = []

    recipient_lines = []
    if getattr(quotation, "recipient", None):
        recipient_lines = [sanitize_text(line) for line in quotation.recipient.split("\n") if line.strip()]
    to_text = "<font name=\"%s\">To: </font>" % font_bold + ("<br/>".join(recipient_lines) if recipient_lines else "")

    tender_no = getattr(quotation, "client_ref_number", None)
    tender_line = f"TENDER NO: {sanitize_text(tender_no)}" if tender_no else "TENDER NO:"
    date_text = quotation.quote_date.strftime("%d %b %Y") if getattr(quotation, "quote_date", None) else ""

    if style == "expert":
        title_style = ParagraphStyle("tender_title", fontName=font_bold, fontSize=16,
                                     alignment=TA_CENTER, textColor=theme["accent_color"])
        story.append(Paragraph(sanitize_text(doc_title).upper(), title_style))
        story.append(Spacer(1, 4 * mm))

        to_style = ParagraphStyle("tender_to", fontName=font_body, fontSize=10, leading=13)
        story.append(Paragraph(to_text, to_style))
        story.append(Spacer(1, 5 * mm))

        row_style_l = ParagraphStyle("tender_row_l", fontName=font_bold, fontSize=10)
        row_style_r = ParagraphStyle("tender_row_r", fontName=font_bold, fontSize=10, alignment=TA_RIGHT)
        row = Table(
            [[Paragraph(tender_line, row_style_l),
              Paragraph(sanitize_text(theme.get("tender_annexure_label", "Anx A")), row_style_r)]],
            colWidths=[content_width * 0.62, content_width * 0.38],
        )
        row.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(row)

        date_style = ParagraphStyle("tender_date", fontName=font_bold, fontSize=10)
        story.append(Paragraph(f"Dated: {sanitize_text(date_text)}" if date_text else "Dated:", date_style))
        story.append(Spacer(1, 6 * mm))
    else:
        ref_lines = []
        if getattr(quotation, "quote_number", None):
            ref_lines.append(f"Quotation Ref No: {sanitize_text(quotation.quote_number)}")
        if date_text:
            ref_lines.append(f"Dated: {sanitize_text(date_text)}")
        if ref_lines:
            ref_style = ParagraphStyle("tender_ref", fontName=font_body, fontSize=10,
                                       alignment=TA_RIGHT, leading=13)
            story.append(Paragraph("<br/>".join(ref_lines), ref_style))
            story.append(Spacer(1, 3 * mm))

        to_style = ParagraphStyle("tender_to", fontName=font_body, fontSize=10, leading=13)
        story.append(Paragraph(to_text, to_style))
        story.append(Spacer(1, 3 * mm))

        annex_style = ParagraphStyle("tender_annex", fontName=font_bold, fontSize=10, alignment=TA_RIGHT)
        story.append(Paragraph(sanitize_text(theme.get("tender_annexure_label", "Annexure 'A'")), annex_style))
        story.append(Spacer(1, 2 * mm))

        title_style = ParagraphStyle("tender_title", fontName=font_bold, fontSize=14,
                                     alignment=TA_CENTER, textColor=theme["accent_color"])
        story.append(Paragraph(sanitize_text(doc_title).upper(), title_style))
        story.append(Spacer(1, 2 * mm))

        tender_style_p = ParagraphStyle("tender_no", fontName=font_bold, fontSize=10)
        story.append(Paragraph(tender_line, tender_style_p))
        story.append(Spacer(1, 6 * mm))

    return story


def _build_tender_commercial_table(theme, line_items, content_width):
    """Ser / Part No / Nomenclature / A/U / Price per Item-Unit / Remarks --
    the CASD EME "COMMERCIAL QUOTATION/OFFER" Annexure 'A' columns. There is
    no qty or total column on the client's form (pricing is quoted per unit
    for evaluation), so none is rendered here either."""
    part_no_label = theme.get("tender_part_no_label", "Part No")
    price_label = theme.get("tender_price_label", "Price per Item/unit")
    headers = ["Ser", part_no_label, "Nomenclature", "A/U", price_label, "Remarks"]
    fracs = [0.055, 0.145, 0.335, 0.075, 0.16, 0.23]
    col_widths = [content_width * f for f in fracs]

    hdr_style = ParagraphStyle("tc_hdr", fontName=theme["font_bold"], fontSize=8.5,
                               alignment=TA_CENTER, textColor=theme["table_header_text_color"], leading=11)
    cell_c = ParagraphStyle("tc_c", fontName=theme["font_body"], fontSize=8.5, leading=11, alignment=TA_CENTER)
    cell_l = ParagraphStyle("tc_l", fontName=theme["font_body"], fontSize=8.5, leading=11)
    cell_r = ParagraphStyle("tc_r", fontName=theme["font_body"], fontSize=8.5, leading=11, alignment=TA_RIGHT)

    data = [[Paragraph(h, hdr_style) for h in headers]]
    subtotal = 0.0
    for idx, item in enumerate(line_items, start=1):
        subtotal += item.qty * item.unit_price
        data.append([
            Paragraph(str(idx), cell_c),
            Paragraph(sanitize_text(item.part_no or ""), cell_l),
            Paragraph(sanitize_text(item.description), cell_l),
            Paragraph(sanitize_text(item.unit or "Nos"), cell_c),
            Paragraph(f"{item.unit_price:,.2f}", cell_r),
            Paragraph(sanitize_text(item.remark or ""), cell_l),
        ])

    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), theme["table_header_bg"]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t, subtotal


def _build_tender_technical_table(theme, line_items, content_width):
    """Ser / Part No / Nomenclature / A/U / ReqQty / Details Specs / Photo /
    COO / Quoted-NQ / Remarks -- the CASD EME "TECHNICAL QUOTATION/OFFER"
    Annexure 'A' columns, with the photo column in its actual position
    (between Details Specs and COO) rather than trailing the row."""
    photo_label = theme.get("tender_photo_label", "Photo")
    quoted_label = theme.get("tender_quoted_label", "Quoted /NQ (Not Quoted)")
    part_no_label = theme.get("tender_tech_part_no_label", "Part No")

    hdr_cell = ParagraphStyle("tt_hdr", fontName=theme["font_bold"], fontSize=8.5, leading=11,
                              textColor=theme["table_header_text_color"], alignment=TA_CENTER)
    cell_c = ParagraphStyle("tt_c", fontName=theme["font_body"], fontSize=8.5, leading=11, alignment=TA_CENTER)
    cell_l = ParagraphStyle("tt_l", fontName=theme["font_body"], fontSize=8.5, leading=11)

    has_photos = any(getattr(item, "photo_path", None) for item in line_items)

    col_defs = [
        ("Ser", "c", cell_c, lambda idx, item: str(idx)),
        (part_no_label, "c", cell_c, lambda idx, item: sanitize_text(item.part_no or "")),
        ("Nomenclature", "l", cell_l, lambda idx, item: sanitize_text(item.description)),
        ("A/U", "c", cell_c, lambda idx, item: sanitize_text(item.unit or "Nos")),
        ("ReqQty", "c", cell_c, lambda idx, item: f"{item.qty:g}"),
        ("Details Specs", "l", cell_l, lambda idx, item: sanitize_text(item.specs or "")),
    ]
    if has_photos:
        col_defs.append((photo_label, "c", None, None))
    col_defs += [
        ("COO", "c", cell_c, lambda idx, item: sanitize_text(item.coo or "")),
        (quoted_label, "c", cell_c, lambda idx, item: sanitize_text(item.quoted or "")),
        ("Remarks", "l", cell_l, lambda idx, item: sanitize_text(item.remark or "")),
    ]

    photo_size_mm = 18
    if has_photos:
        content_mm = content_width / mm
        photo_col_mm = min(photo_size_mm * 4.0 / 3.0 + 2.0, 0.20 * content_mm)
        avail = content_width - photo_col_mm * mm
    else:
        photo_col_mm = None
        avail = content_width

    contents = []
    for label, align, cell_style, fn in col_defs:
        if label == photo_label:
            continue
        cells = [fn(idx, item) for idx, item in enumerate(line_items, start=1)]
        contents.append((label, cells))
    text_widths = fit_column_widths(contents, avail, theme["font_bold"], theme["font_body"])

    final_widths = []
    wi = 0
    for label, align, cell_style, fn in col_defs:
        if label == photo_label:
            final_widths.append(photo_col_mm * mm)
        else:
            final_widths.append(text_widths[wi])
            wi += 1

    header_row = [Paragraph(label, hdr_cell) for label, _, _, _ in col_defs]
    data = [header_row]
    for idx, item in enumerate(line_items, start=1):
        row = []
        for label, align, cell_style, fn in col_defs:
            if label == photo_label:
                ph = _tech_photo_flowable(item.photo_path, photo_size_mm, photo_col_mm)
                row.append(ph if ph is not None else Paragraph("&nbsp;", cell_c))
            else:
                row.append(Paragraph(fn(idx, item), cell_style or cell_l))
        data.append(row)

    t = Table(data, colWidths=final_widths, repeatRows=1)
    cmds = [
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), theme["table_header_bg"]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    for c, (label, align, _, _) in enumerate(col_defs):
        if align == "c":
            cmds.append(("ALIGN", (c, 0), (c, -1), "CENTER"))
    t.setStyle(TableStyle(cmds))
    return t


def _build_tender_annex_story(theme, company, quotation, line_items, content_width, doc_type_key,
                              style_terms_head, style_terms_body, style_name):
    doc_title = get_doc_title(theme, doc_type_key)
    story = _build_tender_header(theme, quotation, doc_title, content_width)

    if doc_type_key == "technical":
        story.append(_build_tender_technical_table(theme, line_items, content_width))
        subtotal = sum(item.qty * item.unit_price for item in line_items)
    else:
        table, subtotal = _build_tender_commercial_table(theme, line_items, content_width)
        story.append(table)

    story.append(Spacer(1, 8 * mm))

    if quotation.terms_conditions:
        terms_block = [Paragraph("Terms &amp; Conditions:", style_terms_head), Spacer(1, 2 * mm)]
        for line in quotation.terms_conditions.split("\n"):
            if line.strip():
                terms_block.append(Paragraph(sanitize_text(line), style_terms_body))
        story.append(KeepTogether(terms_block))
        story.append(Spacer(1, 10 * mm))

    sig_block = []
    if company.signature_filename:
        sig_path = os.path.join("static", "signatures", company.signature_filename)
        if os.path.exists(sig_path):
            sig_img = Image(sig_path, width=theme["signature_width_mm"] * mm,
                            height=theme["signature_height_mm"] * mm, kind="proportional")
            sig_img.hAlign = theme["signature_align"].upper()
            sig_block.append(sig_img)
            sig_block.append(Spacer(1, 2 * mm))
    if company.authorized_name:
        sig_block.append(Paragraph(sanitize_text(company.authorized_name), style_name))
    if theme.get("show_company_name_under_signature"):
        sig_block.append(Paragraph(sanitize_text(company.name), style_name))
    story.append(KeepTogether(sig_block))

    return story, subtotal


def _group_items_by_annexure(line_items, quotation):
    """Group line items by annexure. Returns list of (annexure_name, items, page_break)
    tuples. Items with no annexure come first (name=None)."""
    annexures = quotation.annexures if hasattr(quotation, 'annexures') else []
    if not annexures:
        return [(None, line_items, False)]

    ann_map = {ann.id: ann for ann in annexures}
    main_items = []
    groups = {}  # ann_id -> [items]

    for li in line_items:
        if li.annexure_id and li.annexure_id in ann_map:
            groups.setdefault(li.annexure_id, []).append(li)
        else:
            main_items.append(li)

    result = []
    if main_items:
        result.append((None, main_items, False))

    for ann in annexures:
        items = groups.get(ann.id, [])
        if items:
            result.append((ann.name, items, ann.page_break_before))

    return result if result else [(None, line_items, False)]


def _make_annexure_header(name, theme, content_width):
    """Create a bold paragraph for annexure section header."""
    style = ParagraphStyle(
        "annexure_header",
        fontName=theme["font_bold"],
        fontSize=12,
        leading=15,
        alignment=TA_LEFT,
        spaceAfter=4,
    )
    return Paragraph(sanitize_text(name), style)


def generate_quotation_pdf(company, client, quotation, line_items, output_path, skip_letterhead=False):
    page_width, page_height = A4
    left_margin = right_margin = 20 * mm
    bottom_margin_default = 20 * mm

    theme = get_theme(company)
    is_vision = getattr(company, "pdf_theme", None) == "Rostam"

    header_path = None
    header_w = header_h = 0
    footer_path = None
    footer_w = footer_h = 0
    logo_path = None

    if not skip_letterhead:
        if getattr(company, "letterhead_filename", None):
            candidate = os.path.join("static", "letterheads", company.letterhead_filename)
            if os.path.exists(candidate):
                dims = get_image_dimensions(candidate, page_width / mm, MAX_HEADER_MM)
                if dims:
                    header_path = candidate
                    header_w, header_h = dims[0] * mm, dims[1] * mm

        if getattr(company, "letterhead_footer_filename", None):
            candidate = os.path.join("static", "letterheads", company.letterhead_footer_filename)
            if os.path.exists(candidate):
                dims = get_image_dimensions(candidate, page_width / mm, MAX_FOOTER_MM)
                if dims:
                    footer_path = candidate
                    footer_w, footer_h = dims[0] * mm, dims[1] * mm

        if not header_path and getattr(company, "logo_filename", None):
            candidate = os.path.join("static", "company_logos", company.logo_filename)
            if os.path.exists(candidate):
                logo_path = candidate

    if skip_letterhead:
        top_margin = BLANK_MARGIN_MM * mm
        bottom_margin = BLANK_MARGIN_MM * mm
    else:
        top_margin = (header_h + 6 * mm) if header_path else (FALLBACK_HEADER_HEIGHT + 8 * mm)
        bottom_margin = (footer_h + 8 * mm) if footer_path else bottom_margin_default

    def draw_header(canv, doc):
        if skip_letterhead:
            return
        top_y = page_height
        if header_path:
            x = (page_width - header_w) / 2
            canv.drawImage(header_path, x, top_y - header_h, width=header_w, height=header_h,
                           preserveAspectRatio=True, mask="auto")
        else:
            band_top = top_y - 4 * mm
            band_bottom = top_y - FALLBACK_HEADER_HEIGHT + ACCENT_BAR_HEIGHT + 4 * mm
            band_height = band_top - band_bottom
            band_center = (band_top + band_bottom) / 2

            text_x = left_margin
            lines = [(theme["font_bold"], 13, sanitize_text(company.name))]
            if company.address:
                lines.append((theme["font_body"], 8.5, sanitize_text(company.address)))
            contact_bits = []
            if getattr(company, "phone", None):
                contact_bits.append(company.phone)
            if getattr(company, "email", None):
                contact_bits.append(company.email)
            if contact_bits:
                lines.append((theme["font_body"], 8.5, sanitize_text("  |  ".join(contact_bits))))

            line_gap = 4.6 * mm
            text_block_height = line_gap * len(lines)
            text_top_baseline = band_center + (text_block_height / 2) - 3 * mm

            if logo_path:
                try:
                    with PILImage.open(logo_path) as img:
                        w, h = img.size
                        ratio = h / w
                        max_size = min(LOGO_MAX_SIZE, band_height)
                        if ratio <= 1:
                            draw_w = max_size
                            draw_h = max_size * ratio
                        else:
                            draw_h = max_size
                            draw_w = max_size / ratio
                    logo_y = band_center - (draw_h / 2)
                    canv.drawImage(logo_path, left_margin, logo_y, width=draw_w, height=draw_h,
                                   preserveAspectRatio=True, mask="auto")
                    text_x = left_margin + draw_w + 6 * mm
                except Exception:
                    pass

            y = text_top_baseline
            for font_name, font_size, text in lines:
                canv.setFont(font_name, font_size)
                canv.setFillColor(theme["accent_color"] if font_name == theme["font_bold"] else colors.black)
                canv.drawString(text_x, y, text)
                y -= line_gap

            canv.setFillColor(theme["accent_color"])
            canv.rect(0, top_y - FALLBACK_HEADER_HEIGHT, page_width, ACCENT_BAR_HEIGHT, fill=1, stroke=0)
            canv.setFillColor(colors.black)

        if footer_path:
            x = (page_width - footer_w) / 2
            canv.drawImage(footer_path, x, 0, width=footer_w, height=footer_h,
                           preserveAspectRatio=True, mask="auto")

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=left_margin, rightMargin=right_margin,
        topMargin=top_margin, bottomMargin=bottom_margin,
    )

    story = []
    style_normal = ParagraphStyle("normal", fontName=theme["font_body"], fontSize=8.5, leading=10)
    style_recipient = ParagraphStyle("recipient", fontName=theme["font_body"], fontSize=10, leading=12)
    style_bold = ParagraphStyle("bold", fontName=theme["font_bold"], fontSize=10)
    style_bold_right = ParagraphStyle("bold_right", fontName=theme["font_bold"], fontSize=10, alignment=TA_RIGHT)
    style_ref = ParagraphStyle("ref", fontName=theme["font_bold"], fontSize=10, alignment=TA_RIGHT)
    style_subject = ParagraphStyle("subject", fontName=theme["font_body"], fontSize=10, leading=12)
    style_terms_head = ParagraphStyle("terms_head", fontName=theme["font_bold"], fontSize=9, alignment=TA_LEFT)
    style_terms_body = ParagraphStyle("terms_body", fontName=theme["font_body"], fontSize=8.5, leading=13,
                                      alignment=TA_LEFT, leftIndent=12)

    sig_alignment = TA_CENTER if theme["signature_align"] == "center" else TA_LEFT
    style_name = ParagraphStyle("name", fontName=theme["font_bold"], fontSize=9, alignment=sig_alignment)

    content_width = page_width - left_margin - right_margin
    layout = theme.get("layout", "standard")
    doc_type_key = getattr(quotation, "doc_type", None) or "commercial"

    if layout == "tender_annex":
        story, subtotal = _build_tender_annex_story(
            theme, company, quotation, line_items, content_width, doc_type_key,
            style_terms_head, style_terms_body, style_name,
        )
        doc.build(story, onFirstPage=draw_header, onLaterPages=draw_header)
        return subtotal

    if doc_type_key == "technical":
        story = _build_technical_offer_story(
            theme, company, quotation, line_items, content_width,
            style_normal, style_terms_head, style_terms_body, style_name,
        )
        doc.build(story, onFirstPage=draw_header, onLaterPages=draw_header)
        return None

    if is_vision:
        title_style = ParagraphStyle("q_title", fontName=theme["font_bold"], fontSize=18, leading=22, alignment=TA_CENTER)
        story.append(Paragraph("QUOTATION", title_style))
        story.append(Spacer(1, 5 * mm))

        hdr_style = ParagraphStyle("qhdr", fontName=theme["font_bold"], fontSize=10, leading=13, alignment=TA_CENTER)
        hdr_cells = [
            Paragraph(f"Quotation No.<br/>{sanitize_text(quotation.quote_number)}", hdr_style),
            Paragraph(f"Quotation Date<br/>{quotation.quote_date.strftime('%d-%B-%Y') if quotation.quote_date else ''}", hdr_style),
        ]
        if quotation.client_ref_number:
            hdr_cells.append(Paragraph(f"Client Ref. Order<br/>{sanitize_text(quotation.client_ref_number)}", hdr_style))
        ncols = len(hdr_cells)
        hdr_tbl = Table([hdr_cells], colWidths=[content_width / ncols] * ncols)
        hdr_tbl.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(hdr_tbl)
        story.append(Spacer(1, 4 * mm))

        body_sm = ParagraphStyle("qbody", fontName=theme["font_body"], fontSize=9, leading=12)
        to_lines = [sanitize_text(line) for line in (quotation.recipient or "").split("\n")] if quotation.recipient else [sanitize_text(client.name)]
        to_text = "<b>TO:</b><br/><br/>" + "<br/>".join(to_lines)

        from_parts = [f"<b>FROM: {sanitize_text(company.name)}</b>"]
        if company.authorized_name:
            from_parts.append(f"Contact Person: {sanitize_text(company.authorized_name)}")
        if company.address:
            from_parts.append(f"Office Add: {sanitize_text(company.address)}")
        if company.phone:
            from_parts.append(f"Office Tel: {sanitize_text(company.phone)}")
        if company.email:
            from_parts.append(f"E-mail Add: {sanitize_text(company.email)}")
        from_text = "<br/>".join(from_parts)

        tf_tbl = Table(
            [[Paragraph(to_text, body_sm), Paragraph(from_text, body_sm)]],
            colWidths=[content_width / 2, content_width / 2],
        )
        tf_tbl.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(tf_tbl)
        story.append(Spacer(1, 4 * mm))

        if quotation.subject:
            sub_style = ParagraphStyle("qsubj", fontName=theme["font_bold"], fontSize=9, alignment=TA_LEFT)
            sub_tbl = Table(
                [[Paragraph(f"Subject: {sanitize_text(quotation.subject)}", sub_style)]],
                colWidths=[content_width],
            )
            sub_tbl.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]))
            story.append(sub_tbl)
            story.append(Spacer(1, 4 * mm))

        has_part_no = any(item.part_no for item in line_items)
        has_tax = any((item.tax_percent or 0) > 0 for item in line_items)
        configured = resolve_quotation_columns(company, quotation)
        custom_fields = resolve_quotation_custom_fields(quotation)

        def col_enabled(key):
            return configured is None or key in configured

        item_tax_pct = 0.0
        for item in line_items:
            if item.tax_percent:
                item_tax_pct = float(item.tax_percent)
                break
        hdr_style = ParagraphStyle("qhdr", fontName=theme["font_bold"], fontSize=8.5, leading=11, textColor=theme["table_header_text_color"])
        hdr_style_c = ParagraphStyle("qhdr_c", parent=hdr_style, alignment=TA_CENTER)
        hdr_style_r = ParagraphStyle("qhdr_r", parent=hdr_style, alignment=TA_RIGHT)
        cell_style = ParagraphStyle("qcell", parent=style_normal)
        cell_style_c = ParagraphStyle("qcell_c", parent=style_normal, alignment=TA_CENTER)
        cell_style_r = ParagraphStyle("qcell_r", parent=style_normal, alignment=TA_RIGHT)
        gst_label = f"GST {item_tax_pct:g}%" if item_tax_pct else "GST"

        def make_col(key):
            """Return (label, width_fraction, align, cell_fn) for a column key,
            or None when the key cannot be rendered."""
            if key == "sr":
                return ("Sr.", 0.04, "CENTER", lambda idx, item, lt, g: Paragraph(str(idx), cell_style_c))
            if key == "part_no":
                return ("Part No/Code", 0.12, "CENTER", lambda idx, item, lt, g: Paragraph(sanitize_text(item.part_no or ""), cell_style_c))
            if key == "nomenclature":
                return ("Nomenclature", 0.31, "LEFT", lambda idx, item, lt, g: Paragraph(sanitize_text(item.description), cell_style))
            if key == "unit":
                return ("A/U", 0.05, "CENTER", lambda idx, item, lt, g: Paragraph(sanitize_text(item.unit or "Nos"), cell_style_c))
            if key == "qty":
                return ("Qty", 0.05, "CENTER", lambda idx, item, lt, g: Paragraph(f"{item.qty:g}", cell_style_c))
            if key == "price":
                return ("Price" if not has_tax else "Excl. GST", 0.11, "RIGHT", lambda idx, item, lt, g: Paragraph(f"{lt:,.2f}", cell_style_r))
            if key == "gst":
                return (gst_label, 0.10, "RIGHT", lambda idx, item, lt, g: Paragraph(f"{g:,.2f}", cell_style_r))
            if key == "total":
                return ("Total" if not has_tax else "Incl. GST", 0.12, "RIGHT", lambda idx, item, lt, g: Paragraph(f"{lt + g:,.2f}", cell_style_r))
            if key.startswith("custom_"):
                cid = key[len("custom_"):]
                name = custom_fields.get(cid)
                if not name:
                    return None
                return (name, 0.08, "CENTER",
                        lambda idx, item, lt, g, cid=cid: Paragraph(sanitize_text(str((item.custom_values or {}).get(cid, ""))), cell_style_c))
            return None

        if configured is not None:
            keys = list(configured)
        else:
            keys = ["sr"]
            if has_part_no:
                keys.append("part_no")
            keys.append("nomenclature")
            if col_enabled("unit"):
                keys.append("unit")
            if col_enabled("qty"):
                keys.append("qty")
            keys.append("price")
            if has_tax:
                keys.append("gst")
            for cf_id in custom_fields:
                keys.append(f"custom_{cf_id}")
            keys.append("total")

        vc = getattr(quotation, "visible_columns", None)
        col_widths_px = {}
        if isinstance(vc, dict):
            cw = vc.get("column_widths")
            if isinstance(cw, dict):
                col_widths_px = cw

        # Rendered line totals/taxes feed both the cell text and the width fit.
        lt_by_idx = {}
        g_by_idx = {}
        for idx, item in enumerate(line_items, start=1):
            lt = item.qty * item.unit_price
            lt_by_idx[idx] = lt
            g_by_idx[idx] = round(lt * (item.tax_percent or 0) / 100, 2)

        def col_weight(key, frac):
            """Column width weight (points). Explicit per-quotation widths (px,
            stored in visible_columns.column_widths) override the auto-fit width.
            frac*1500 keeps the default (160px == 120pt == 0.08 fraction)
            identical to the pre-widths layout when no fitting applies."""
            w = col_widths_px.get(key)
            if w:
                try:
                    return float(w) * 0.75
                except (TypeError, ValueError):
                    pass
            return frac * 1500.0

        columns = []
        width_keys = []
        for key in keys:
            col = make_col(key)
            if col is not None:
                columns.append(col)
                width_keys.append(key)

        explicit_any = any(width_keys and col_widths_px.get(k) for k in width_keys)
        if explicit_any:
            col_weights = [col_weight(key, columns[i][1]) for i, key in enumerate(width_keys)]
        else:
            contents = []
            for label, _, _, fn in columns:
                cell_texts = [fn(idx, item, lt_by_idx[idx], g_by_idx[idx]).text
                              for idx, item in enumerate(line_items, start=1)]
                contents.append((label, cell_texts))
            col_weights = fit_column_widths(contents, content_width,
                                            theme["font_bold"], theme["font_body"])

        ncols = len(columns)
        total_weight = sum(col_weights) or 1.0

        def make_header(label, align):
            return Paragraph(label, hdr_style_c)

        item_headers = [make_header(h, align) for h, _, align, _ in columns]
        roww = [content_width * (w / total_weight) for w in col_weights]

        # Group items by annexure
        annexure_groups = _group_items_by_annexure(line_items, quotation)

        subtotal = 0.0
        total_gst = 0.0

        for group_name, group_items, page_break in annexure_groups:
            if page_break:
                story.append(PageBreak())

            if group_name:
                story.append(_make_annexure_header(group_name, theme, content_width))
                story.append(Spacer(1, 3 * mm))

            # Build table for this group
            idata = [item_headers]
            group_subtotal = 0.0
            group_gst = 0.0

            # Compute line totals for this group
            group_lt = {}
            group_g = {}
            for gidx, item in enumerate(group_items, start=1):
                lt = item.qty * item.unit_price
                g = round(lt * (item.tax_percent or 0) / 100, 2)
                group_lt[gidx] = lt
                group_g[gidx] = g
                group_subtotal += lt
                group_gst += g

            for gidx, item in enumerate(group_items, start=1):
                lt = group_lt[gidx]
                g = group_g[gidx]
                idata.append([fn(gidx, item, lt, g) for _, _, _, fn in columns])

            subtotal += group_subtotal
            total_gst += group_gst

            it = Table(idata, colWidths=roww, repeatRows=1)
            rcmds = [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), theme["table_header_bg"]),
                ("TEXTCOLOR", (0, 0), (-1, 0), theme["table_header_text_color"]),
                ("FONTNAME", (0, 0), (-1, 0), theme["font_bold"]),
                ("FONTNAME", (0, 1), (-1, -1), theme["font_body"]),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
            for c, (_, _, align, _) in enumerate(columns):
                if align == "CENTER":
                    rcmds.append(("ALIGN", (c, 0), (c, -1), "CENTER"))
                elif align == "RIGHT":
                    rcmds.append(("ALIGN", (c, 0), (c, -1), "RIGHT"))
            it.setStyle(TableStyle(rcmds))
            story.append(it)
            story.append(Spacer(1, 4 * mm))

        # Summary rows (after all annexure groups)
        tax_pct = float(getattr(quotation, "tax_amount", 0) or 0)
        discount = float(getattr(quotation, "discount_amount", 0) or 0)
        installation = float(getattr(quotation, "installation_charges", 0) or 0)
        transportation = float(getattr(quotation, "transportation_charges", 0) or 0)

        if total_gst:
            gst_value = round(total_gst, 2)
            gst_value_label = gst_label
        elif tax_pct:
            gst_value = round(subtotal * tax_pct / 100, 2)
            gst_value_label = f"GST ({tax_pct:g}%)"
        else:
            gst_value = None
            gst_value_label = None

        # Build summary table
        summary_data = []
        def summary_row(label, value):
            row = [""] * ncols
            row[0] = label
            row[-1] = value
            summary_data.append(row)

        if gst_value is not None:
            summary_row(gst_value_label, f"{gst_value:,.2f}")
        summary_row("Subtotal", f"{subtotal:,.2f}")
        if discount:
            summary_row("Discount", f"-{discount:,.2f}")
        if installation:
            summary_row("Installation Charges", f"{installation:,.2f}")
        if transportation:
            summary_row("Transportation Charges", f"{transportation:,.2f}")
        grand_total_ros = subtotal - discount + installation + transportation
        if gst_value is not None:
            grand_total_ros += gst_value
        summary_row("Grand Total", f"{grand_total_ros:,.2f}")

        if summary_data:
            stbl = Table(summary_data, colWidths=roww)
            summary_rcmds = []
            for r in range(len(summary_data)):
                summary_rcmds.append(("SPAN", (0, r), (ncols - 2, r)))
                summary_rcmds.append(("FONTNAME", (0, r), (-1, r), theme["font_bold"]))
                summary_rcmds.append(("FONTSIZE", (0, r), (-1, r), 9))
                summary_rcmds.append(("ALIGN", (0, r), (ncols - 2, r), "LEFT"))
                summary_rcmds.append(("ALIGN", (ncols - 1, r), (ncols - 1, r), "RIGHT"))
                summary_rcmds.append(("LEFTPADDING", (0, r), (ncols - 2, r), 4))
                summary_rcmds.append(("TOPPADDING", (0, r), (-1, r), 3))
                summary_rcmds.append(("BOTTOMPADDING", (0, r), (-1, r), 3))
            if len(summary_data) > 1:
                summary_rcmds.append(("LINEABOVE", (0, 0), (-1, 0), 0.75, colors.black))
            summary_rcmds.append(("BACKGROUND", (0, len(summary_data) - 1), (-1, len(summary_data) - 1), theme["table_header_bg"]))
            summary_rcmds.append(("TEXTCOLOR", (0, len(summary_data) - 1), (-1, len(summary_data) - 1), theme["table_header_text_color"]))
            stbl.setStyle(TableStyle(summary_rcmds))
            story.append(stbl)
        story.append(it)
        story.append(Spacer(1, 8 * mm))

        if quotation.terms_conditions:
            terms_block = [Paragraph("Terms &amp; Conditions:", style_terms_head), Spacer(1, 2 * mm)]
            for line in quotation.terms_conditions.split("\n"):
                if line.strip():
                    terms_block.append(Paragraph(sanitize_text(line), style_terms_body))
            story.append(KeepTogether(terms_block))
            story.append(Spacer(1, 10 * mm))

        sig_block = []
        if company.signature_filename:
            sig_path = os.path.join("static", "signatures", company.signature_filename)
            if os.path.exists(sig_path):
                sig_img = Image(sig_path, width=theme["signature_width_mm"] * mm,
                                height=theme["signature_height_mm"] * mm, kind="proportional")
                sig_img.hAlign = theme["signature_align"].upper()
                sig_block.append(sig_img)
                sig_block.append(Spacer(1, 2 * mm))
        if company.authorized_name:
            sig_block.append(Paragraph(sanitize_text(company.authorized_name), style_name))
        if theme["show_company_name_under_signature"]:
            sig_block.append(Paragraph(sanitize_text(company.name), style_name))
        story.append(KeepTogether(sig_block))

        doc.build(story, onFirstPage=draw_header, onLaterPages=draw_header)
        return grand_total_ros

    story.append(build_heading(theme, get_doc_title(theme, "quotation"), content_width, company=company))
    story.append(Spacer(1, 6 * mm))

    if layout == "shipper_receiver":
        meta_style = ParagraphStyle("meta", fontName=theme["font_bold"], fontSize=9, alignment=TA_RIGHT)
        story.append(Paragraph(f"Date: {quotation.quote_date.strftime('%d %B, %Y') if quotation.quote_date else ''}", meta_style))
        story.append(Paragraph(f"Quotation # {sanitize_text(quotation.quote_number)}", meta_style))
        story.append(Spacer(1, 5 * mm))
        story.append(build_shipper_receiver_block(theme, company, client, quotation, content_width))
        story.append(Spacer(1, 2 * mm))
        story.append(build_subject_ref_bar(
            theme, quotation.subject, "Quotation REF #", quotation.client_ref_number, content_width
        ))
        story.append(Spacer(1, 2 * mm))

    elif layout == "billed_summary":
        style_client_block = ParagraphStyle("client_block", fontName=theme["font_body"], fontSize=9.5, leading=13)
        style_meta_bold = ParagraphStyle("meta_bold", fontName=theme["font_bold"], fontSize=10,
                                         alignment=TA_RIGHT, textColor=theme["accent_color"])

        if getattr(quotation, "recipient", None):
            client_lines = [sanitize_text(line) for line in quotation.recipient.split("\n")]
        else:
            client_lines = [sanitize_text(client.name)]
            if getattr(client, "address", None):
                for line in client.address.split("\n"):
                    client_lines.append(sanitize_text(line))

        left_cell = Paragraph("<br/>".join(client_lines), style_client_block)
        right_cell = Paragraph(
            f"Quotation #{sanitize_text(quotation.quote_number)}<br/>"
            f"{quotation.quote_date.strftime('%d/%m/%Y') if quotation.quote_date else ''}", style_meta_bold
        )
        top_row = Table([[left_cell, right_cell]], colWidths=[content_width * 0.6, content_width * 0.4])
        top_row.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(top_row)
        story.append(Spacer(1, 6 * mm))

    else:
        header_row = Table(
            [[Paragraph(f"Quotation # {sanitize_text(quotation.quote_number)}", style_bold),
              Paragraph(f"Date: {quotation.quote_date.strftime('%d-%m-%Y') if quotation.quote_date else ''}", style_bold_right)]],
            colWidths=[content_width / 2, content_width / 2],
        )
        header_row.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(header_row)
        story.append(Spacer(1, 4 * mm))

        if getattr(quotation, "recipient", None):
            recipient_lines = [f'<font name="{theme["font_bold"]}">To: </font>']
            for line in quotation.recipient.split("\n"):
                recipient_lines.append(sanitize_text(line))
            rec_p = Paragraph("<br/>".join(recipient_lines), style_recipient)
            rec_table = Table([[rec_p]], colWidths=[content_width])
            rec_table.setStyle(TableStyle([
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]))
            story.append(rec_table)
            story.append(Spacer(1, 3 * mm))

        if quotation.subject or quotation.client_ref_number:
            subject_cell = Paragraph(
                f'<font name="{theme["font_bold"]}">Subject: </font>{sanitize_text(quotation.subject)}', style_subject
            ) if quotation.subject else Paragraph("", style_normal)
            ref_cell = Paragraph(
                f"Ref # {sanitize_text(quotation.client_ref_number)}", style_ref
            ) if quotation.client_ref_number else Paragraph("", style_normal)
            sub_row = Table([[subject_cell, ref_cell]], colWidths=[content_width / 2, content_width / 2])
            sub_row.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]))
            story.append(sub_row)
            story.append(Spacer(1, 6 * mm))

    # --- Item table ---
    header_labels, col_widths, mode = get_table_columns(theme, content_width)

    # Group items by annexure
    annexure_groups = _group_items_by_annexure(line_items, quotation)

    subtotal = 0
    for group_name, group_items, page_break in annexure_groups:
        if page_break:
            story.append(PageBreak())

        if group_name:
            story.append(_make_annexure_header(group_name, theme, content_width))
            story.append(Spacer(1, 3 * mm))

        table_data = [header_labels]
        group_subtotal = 0
        for idx, item in enumerate(group_items, start=1):
            row, line_total = build_item_row(mode, idx, item, style_normal)
            table_data.append(row)
            group_subtotal += line_total

        subtotal += group_subtotal

        item_table = Table(table_data, colWidths=col_widths, repeatRows=1)
        item_table.setStyle(TableStyle(build_item_table_style(theme, 0, mode, len(table_data))))
        story.append(item_table)
        story.append(Spacer(1, 4 * mm))

    tax_pct = float(getattr(quotation, "tax_amount", 0) or 0)
    discount = float(getattr(quotation, "discount_amount", 0) or 0)
    installation = float(getattr(quotation, "installation_charges", 0) or 0)
    transportation = float(getattr(quotation, "transportation_charges", 0) or 0)

    tax = round(subtotal * tax_pct / 100, 2) if tax_pct else 0
    charges = None

    if layout == "billed_summary":
        summary_table_data = [["Total"] + [""] * (len(header_labels) - 2) + [f"{subtotal:,.2f}"]]
        grand_total_placeholder = subtotal
    else:
        charges = []
        if is_vision:
            final_total = subtotal
            if tax_pct:
                tax_val = round(subtotal * tax_pct / 100, 2)
                charges.append((f"GST ({tax_pct:g}%)", tax_val))
                final_total += tax_val
            if discount:
                charges.append(("Discount", discount))
                final_total -= discount
            if installation:
                charges.append(("Installation Charges", installation))
                final_total += installation
            if transportation:
                charges.append(("Transportation Charges", transportation))
                final_total += transportation
        else:
            final_total = subtotal + tax
        if charges:
            summary_table_data = [["Total"] + [""] * (len(header_labels) - 2) + [f"{subtotal:,.2f}"]]
            first_summary = 0
            for label, val in charges:
                summary_table_data.append([label] + [""] * (len(header_labels) - 2) + [f"{val:,.2f}"])
            summary_table_data.append(["Grand Total"] + [""] * (len(header_labels) - 2) + [f"{final_total:,.2f}"])
            total_row_idx = first_summary
        else:
            summary_rows = theme.get("total_summary_rows")
            if summary_rows:
                summary_amounts = {
                    "Total Amount": subtotal, "Subtotal": subtotal,
                    "Tax": tax, "Grand Total": final_total,
                }
                summary_table_data = []
                for label in summary_rows:
                    amount = summary_amounts.get(label, final_total)
                    row = [label] + [""] * (len(header_labels) - 2) + [f"{amount:,.2f}"]
                    summary_table_data.append(row)
                total_row_idx = 0
            else:
                summary_table_data = [["Total"] + [""] * (len(header_labels) - 2) + [f"{final_total:,.2f}"]]
                total_row_idx = 0
        grand_total_placeholder = final_total

    # Render summary table
    if layout == "billed_summary":
        summary_table = Table(summary_table_data, colWidths=col_widths, repeatRows=1)
        summary_table.setStyle(TableStyle(build_item_table_style(theme, 0, mode, len(summary_table_data))))
        story.append(summary_table)
        story.append(Spacer(1, 8 * mm))
    elif charges:
        summary_table = Table(summary_table_data, colWidths=col_widths)
        summary_table.setStyle(TableStyle(build_item_table_style(theme, total_row_idx, mode, len(summary_table_data))))
        extra = []
        for r in range(total_row_idx, len(summary_table_data) - 1):
            extra.append(("FONTSIZE", (0, r), (-1, r), 9))
            extra.append(("ALIGN", (0, r), (0, r), "LEFT"))
            extra.append(("LEFTPADDING", (0, r), (0, r), 4))
            extra.append(("LINEABOVE", (0, r), (-1, r), 1.2, theme["accent_color"]))
        summary_table.setStyle(TableStyle(extra))
        story.append(summary_table)
        story.append(Spacer(1, 8 * mm))
    else:
        summary_table = Table(summary_table_data, colWidths=col_widths)
        summary_table.setStyle(TableStyle(build_item_table_style(theme, total_row_idx, mode, len(summary_table_data))))
        story.append(summary_table)
        story.append(Spacer(1, 8 * mm))

    if layout == "billed_summary":
        summary_col_width = content_width * 0.46
        summary_table, grand_total = build_charge_summary(
            theme, subtotal, discount, installation, transportation, summary_col_width
        )

        sig_cell = []
        if company.signature_filename:
            sig_path = os.path.join("static", "signatures", company.signature_filename)
            if os.path.exists(sig_path):
                sig_cell.append(Image(sig_path, width=theme["signature_width_mm"] * mm,
                                      height=theme["signature_height_mm"] * mm, kind="proportional"))
                sig_cell.append(Spacer(1, 2 * mm))
        if company.authorized_name:
            sig_cell.append(Paragraph(sanitize_text(company.authorized_name), style_name))
        if getattr(company, "designation", None):
            style_designation = ParagraphStyle("designation", fontName=theme["font_body"], fontSize=9)
            sig_cell.append(Paragraph(sanitize_text(company.designation), style_designation))

        two_col = Table([[sig_cell, summary_table]], colWidths=[content_width * 0.54, content_width * 0.46])
        two_col.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(two_col)
        story.append(Spacer(1, 8 * mm))
    else:
        grand_total = grand_total_placeholder

    if quotation.terms_conditions:
        terms_block = [Paragraph("Terms & Conditions:", style_terms_head), Spacer(1, 2 * mm)]
        for line in quotation.terms_conditions.split("\n"):
            if line.strip():
                terms_block.append(Paragraph(sanitize_text(line), style_terms_body))
        story.append(KeepTogether(terms_block))
        story.append(Spacer(1, 10 * mm))

    if layout != "billed_summary":
        sig_block = []
        if company.signature_filename:
            sig_path = os.path.join("static", "signatures", company.signature_filename)
            if os.path.exists(sig_path):
                sig_img = Image(sig_path, width=theme["signature_width_mm"] * mm,
                                height=theme["signature_height_mm"] * mm, kind="proportional")
                sig_img.hAlign = theme["signature_align"].upper()
                sig_block.append(sig_img)
                sig_block.append(Spacer(1, 2 * mm))
        if company.authorized_name:
            sig_block.append(Paragraph(sanitize_text(company.authorized_name), style_name))
        if theme["show_company_name_under_signature"]:
            sig_block.append(Paragraph(sanitize_text(company.name), style_name))
        story.append(KeepTogether(sig_block))

    doc.build(story, onFirstPage=draw_header, onLaterPages=draw_header)
    return grand_total
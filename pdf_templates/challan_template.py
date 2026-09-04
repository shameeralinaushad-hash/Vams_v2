import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

from pdf_templates.theme_config import get_theme
from pdf_templates.shared import (
    sanitize_text, get_image_dimensions,
    build_header_callback,
    FALLBACK_HEADER_HEIGHT, MAX_HEADER_MM, MAX_FOOTER_MM, BLANK_MARGIN_MM,
)


def build_item_table_style(theme):
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), theme["table_header_bg"]),
        ("TEXTCOLOR", (0, 0), (-1, 0), theme["table_header_text_color"]),
        ("FONTNAME", (0, 0), (-1, 0), theme["font_bold"]),
        ("FONTNAME", (0, 1), (-1, -1), theme["font_body"]),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (3, 0), (4, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]

    border_style = theme["table_border_style"]
    if border_style == "grid":
        commands.append(("GRID", (0, 0), (-1, -1), 0.5, colors.black))
    elif border_style == "horizontal_only":
        commands.append(("LINEABOVE", (0, 0), (-1, 0), 0.75, colors.black))
        commands.append(("LINEBELOW", (0, 1), (-1, -1), 0.5, colors.Color(0.6, 0.6, 0.6)))
    elif border_style == "zebra":
        commands.append(("GRID", (0, 0), (-1, -1), 0.25, colors.Color(0.7, 0.7, 0.7)))
        commands.append(("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, theme["zebra_color"]]))

    return commands


def build_info_box_item_table(theme, line_items, content_width):
    headers = ["Ser", "Part No", "Nomenclature", "A/U", "Qty", "Remarks"]
    # Relative fractions that sum to 1.0 — scale to actual content_width
    fracs = [0.067, 0.194, 0.417, 0.100, 0.083, 0.139]
    col_widths = [content_width * f for f in fracs]
    table_data = [headers]

    for idx, item in enumerate(line_items, start=1):
        table_data.append([
            str(idx),
            sanitize_text(item.part_no or ""),
            sanitize_text(item.description),
            sanitize_text(item.unit or ""),
            f"{item.qty:g}",
            "",
        ])

    unit_col = 3
    qty_col = 4
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.92, 0.92, 0.92)),
        ("FONTNAME", (0, 0), (-1, 0), theme["font_bold"]),
        ("FONTNAME", (0, 1), (-1, -1), theme["font_body"]),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (unit_col, 0), (unit_col, -1), "CENTER"),
        ("ALIGN", (qty_col, 0), (qty_col, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


RECEIVED_BY_LABEL_W = 25 * mm  # wide enough for "Received By:" bold 10pt on one line
RECEIVED_BY_BLANK_W = 42 * mm
RECEIVED_BY_BLOCK_W = RECEIVED_BY_LABEL_W + RECEIVED_BY_BLANK_W


def build_received_by_block(theme):
    """Received By title + label/blank rows, all as ONE table so the whole
    block moves together as a single unit and every row — including the
    title — right-aligns to the same column edge. Table.hAlign is unreliable
    once nested inside another table's cell (it renders left-flush
    regardless), so instead of floating this block right, the caller sizes
    the outer footer table's right column to exactly RECEIVED_BY_BLOCK_W —
    that pins it flush against the page's right margin by construction."""
    title_style = ParagraphStyle("recv_title", fontName=theme["font_bold"], fontSize=10, leading=13,
                                 alignment=TA_RIGHT)
    label_style = ParagraphStyle("recv_label", fontName=theme["font_bold"], fontSize=10, leading=15,
                                 alignment=TA_RIGHT)
    blank_style = ParagraphStyle("recv_blank", fontName=theme["font_bold"], fontSize=10, leading=15,
                                 alignment=TA_LEFT)

    rows = [
        [Paragraph("Received By:", title_style), ""],
        [Paragraph("No:", label_style), Paragraph("___________________", blank_style)],
        [Paragraph("Rank:", label_style), Paragraph("___________________", blank_style)],
        [Paragraph("Name:", label_style), Paragraph("___________________", blank_style)],
        [Paragraph("Sig:", label_style), Paragraph("___________________", blank_style)],
    ]
    block = Table(rows, colWidths=[RECEIVED_BY_LABEL_W, RECEIVED_BY_BLANK_W])
    block.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (0, -1), 4),
        ("RIGHTPADDING", (1, 0), (1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (1, 0), 4),
    ]))
    return block


def generate_challan_pdf(company, client, challan, line_items, output_path, skip_letterhead=False):
    page_width, page_height = A4
    left_margin = right_margin = 20 * mm
    bottom_margin_default = 20 * mm

    theme = get_theme(company)

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
        top_margin = header_h + 6 * mm if header_path else (FALLBACK_HEADER_HEIGHT + 8 * mm)
        bottom_margin = (footer_h + 8 * mm) if footer_path else bottom_margin_default

    draw_header = build_header_callback(
        page_width, left_margin, page_height, company, theme,
        header_path, header_w, header_h,
        footer_path, footer_w, footer_h,
        logo_path, skip_letterhead,
    )

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=left_margin, rightMargin=right_margin,
        topMargin=top_margin, bottomMargin=bottom_margin,
    )

    story = []
    content_width = page_width - left_margin - right_margin

    po_number = ""
    linked_po = challan.purchase_order if challan.purchase_order_id else (challan.order.purchase_order if challan.order else None)
    if linked_po:
        po_number = linked_po.po_number or ""

    challan_layout = theme.get("challan_layout", "standard")

    if challan_layout == "info_box":
        title_style = ParagraphStyle("challan_titlei", fontName=theme["font_bold"], fontSize=16, leading=20, alignment=TA_CENTER)
        title_cell = Paragraph("DELIVERY CHALLAN", title_style)
        title_wrapper = Table([[title_cell]], colWidths=[content_width])
        title_wrapper.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, 0), 1.5, colors.black),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, -1), (-1, -1), 0),
            ("BOTTOMPADDING", (0, -1), (-1, -1), 4),
        ]))
        story.append(title_wrapper)
        story.append(Spacer(1, 3 * mm))

        sub_style = ParagraphStyle("challan_subi", fontName=theme["font_bold"], fontSize=9, leading=12, alignment=TA_CENTER)
        story.append(Paragraph("Following Items are delivered herewith against", sub_style))
        story.append(Spacer(1, 6 * mm))

        info_left = ParagraphStyle("info_lefti", fontName=theme["font_bold"], fontSize=10, leading=13)
        info_right = ParagraphStyle("info_righti", fontName=theme["font_bold"], fontSize=10, leading=13, alignment=TA_RIGHT)

        dispatch_str = challan.dispatch_date.strftime("%d/%m/%Y") if challan.dispatch_date else ""
        buyer_str = f"To / Buyer: {sanitize_text(client.name)}" if client else "To / Buyer:"
        challan_str = f"Challan No: {sanitize_text(challan.challan_number)}" if challan.challan_number else "Challan No: ____"
        dated_str = f"Dated: {dispatch_str}" if dispatch_str else "Dated: ____"
        ref_str = f"Ref /ULPO No: {sanitize_text(po_number)}" if po_number else "Ref /ULPO No:"

        info_data = [
            [Paragraph(buyer_str, info_left), Paragraph(challan_str, info_right)],
            [Paragraph("", info_left), Paragraph(dated_str, info_right)],
            [Paragraph(ref_str, info_left), Paragraph("", info_right)],
        ]
        info_table = Table(info_data, colWidths=[content_width * 0.5, content_width * 0.5])
        info_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(info_table)
        story.append(Spacer(1, 6 * mm))

        story.append(build_info_box_item_table(theme, line_items, content_width))
        story.append(Spacer(1, 14 * mm))

        footer_left_style = ParagraphStyle("footer_left_i", fontName=theme["font_bold"], fontSize=10, leading=13)
        ft = Table(
            [[
                Paragraph("Delivered By:<br/><br/>", footer_left_style),
                build_received_by_block(theme),
            ]],
            colWidths=[content_width - RECEIVED_BY_BLOCK_W, RECEIVED_BY_BLOCK_W],
        )
        ft.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(ft)

        doc.build(story, onFirstPage=draw_header, onLaterPages=draw_header)
        return

    dispatch_str = challan.dispatch_date.strftime("%d/%m/%Y") if challan.dispatch_date else ""

    title_style = ParagraphStyle("challan_title", fontName=theme["font_bold"], fontSize=16, leading=20, alignment=TA_CENTER)
    title_cell = Paragraph("DELIVERY CHALLAN", title_style)
    title_wrapper = Table([[title_cell]], colWidths=[content_width])
    title_wrapper.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 1.5, colors.black),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, -1), (-1, -1), 0),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 4),
    ]))
    story.append(title_wrapper)
    story.append(Spacer(1, 3 * mm))

    sub_style = ParagraphStyle("challan_sub", fontName=theme["font_bold"], fontSize=9, leading=12, alignment=TA_CENTER)
    story.append(Paragraph("Following Items are delivered herewith against", sub_style))
    story.append(Spacer(1, 6 * mm))

    info_left = ParagraphStyle("info_left", fontName=theme["font_bold"], fontSize=10, leading=13)
    info_right = ParagraphStyle("info_right", fontName=theme["font_bold"], fontSize=10, leading=13, alignment=TA_RIGHT)

    buyer_str = f"To / Buyer: {sanitize_text(client.name)}" if client else "To / Buyer:"
    challan_str = f"Challan No: {sanitize_text(challan.challan_number)}" if challan.challan_number else "Challan No: ____"
    dated_str = f"Dated: {dispatch_str}" if dispatch_str else "Dated: ____"
    ref_str = f"Ref /ULPO No: {sanitize_text(po_number)}" if po_number else "Ref /ULPO No:"

    info_data = [
        [Paragraph(buyer_str, info_left), Paragraph(challan_str, info_right)],
        [Paragraph("", info_left), Paragraph(dated_str, info_right)],
        [Paragraph(ref_str, info_left), Paragraph("", info_right)],
    ]
    info_table = Table(info_data, colWidths=[content_width * 0.5, content_width * 0.5])
    info_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 6 * mm))

    style_normal = ParagraphStyle("normal", fontName=theme["font_body"], fontSize=9, leading=11)

    table_data = [["Ser", "Part No", "Nomenclature", "A/U", "Qty", "Remarks"]]
    for idx, item in enumerate(line_items, start=1):
        table_data.append([
            str(idx),
            Paragraph(sanitize_text(item.part_no or ""), style_normal),
            Paragraph(sanitize_text(item.description), style_normal),
            sanitize_text(item.unit or ""),
            f"{item.qty:g}",
            "",
        ])

    # Relative fractions that sum to 1.0 — scale to actual content_width
    fracs = [0.067, 0.194, 0.417, 0.100, 0.083, 0.139]
    col_widths = [content_width * f for f in fracs]

    item_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    item_table.setStyle(TableStyle(build_item_table_style(theme)))
    story.append(item_table)
    story.append(Spacer(1, 14 * mm))

    footer_left_style = ParagraphStyle("footer_left", fontName=theme["font_bold"], fontSize=10, leading=13)
    ft = Table(
        [[
            Paragraph("Delivered By:<br/><br/>", footer_left_style),
            build_received_by_block(theme),
        ]],
        colWidths=[content_width - RECEIVED_BY_BLOCK_W, RECEIVED_BY_BLOCK_W],
    )
    ft.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(ft)

    doc.build(story, onFirstPage=draw_header, onLaterPages=draw_header)
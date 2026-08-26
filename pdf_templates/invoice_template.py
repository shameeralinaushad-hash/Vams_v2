import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, KeepTogether

from pdf_templates.theme_config import get_theme, get_doc_title
from pdf_templates.shared import (
    NumberedCanvas, sanitize_text, get_image_dimensions, VisionHeading,
    build_header_callback,
    FALLBACK_HEADER_HEIGHT, LOGO_MAX_SIZE, ACCENT_BAR_HEIGHT,
    MAX_HEADER_MM, MAX_FOOTER_MM, BLANK_MARGIN_MM,
)


def build_item_table_style(theme, total_row_idx):
    """Builds the TableStyle command list for the item table, driven entirely
    by the company's theme config."""
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), theme["table_header_bg"]),
        ("TEXTCOLOR", (0, 0), (-1, 0), theme["table_header_text_color"]),
        ("FONTNAME", (0, 0), (-1, 0), theme["font_bold"]),
        ("FONTNAME", (0, 1), (-1, -1), theme["font_body"]),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 0), (3, -1), "CENTER"),
        ("ALIGN", (4, 0), (5, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (1, 0), (1, -1), 4),
    ]

    border_style = theme["table_border_style"]
    if border_style == "grid":
        commands.append(("GRID", (0, 0), (-1, -1), 0.5, colors.black))
    elif border_style == "horizontal_only":
        commands.append(("LINEABOVE", (0, 0), (-1, 0), 0.75, colors.black))
        commands.append(("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.Color(0.6, 0.6, 0.6)))
    elif border_style == "zebra":
        commands.append(("GRID", (0, 0), (-1, -1), 0.25, colors.Color(0.7, 0.7, 0.7)))
        commands.append(("ROWBACKGROUNDS", (0, 1), (-1, total_row_idx - 1),
                         [colors.white, theme["zebra_color"]]))

    commands.append(("SPAN", (0, total_row_idx), (4, total_row_idx)))
    commands.append(("FONTNAME", (0, total_row_idx), (-1, total_row_idx), theme["font_bold"]))
    commands.append(("FONTSIZE", (0, total_row_idx), (-1, total_row_idx), 9))
    commands.append(("ALIGN", (0, total_row_idx), (0, total_row_idx), "LEFT"))
    commands.append(("LEFTPADDING", (0, total_row_idx), (0, total_row_idx), 4))

    if theme["total_row_style"] == "boxed":
        commands.append(("BACKGROUND", (0, total_row_idx), (-1, total_row_idx), theme["table_header_bg"]))
        commands.append(("TEXTCOLOR", (0, total_row_idx), (-1, total_row_idx), theme["table_header_text_color"]))
    else:  # "line_only"
        commands.append(("LINEABOVE", (0, total_row_idx), (-1, total_row_idx), 1.2, theme["accent_color"]))
        commands.append(("TEXTCOLOR", (0, total_row_idx), (-1, total_row_idx), colors.black))

    return commands


def get_table_columns(theme, content_width):
    """Returns (header_row, col_widths, mode) for the item table."""
    mode = theme.get("invoice_table_columns", "full")
    if mode == "no_srno":
        unit_w = 15 * mm
        qty_w = 16 * mm
        price_w = 27 * mm
        total_w = 27 * mm
        desc_w = content_width - (unit_w + qty_w + price_w + total_w)
        return (
            ["Description", "Unit", "Quantity", "Unit Price", "Total"],
            [desc_w, unit_w, qty_w, price_w, total_w],
            mode
        )

    # Full mode: fixed widths for small columns, remainder assigned to Items
    sr_w = 12 * mm
    unit_w = 15 * mm
    qty_w = 16 * mm
    price_w = 27 * mm
    total_w = 35 * mm
    items_w = content_width - (sr_w + unit_w + qty_w + price_w + total_w)
    return (
        ["Sr. No", "Items", "Unit", "Quantity", "Unit Price", "Total"],
        [sr_w, items_w, unit_w, qty_w, price_w, total_w],
        mode
    )

def build_item_row(mode, idx, item, style_normal):
    line_total = item.qty * item.unit_price
    desc = Paragraph(sanitize_text(item.description), style_normal)
    unit = sanitize_text(getattr(item, "unit", None)) or "Nos"
    if mode == "no_srno":
        return [desc, unit, f"{item.qty:g}", f"{item.unit_price:,.2f}", f"{line_total:,.2f}"], line_total
    return [str(idx), desc, unit, f"{item.qty:g}", f"{item.unit_price:,.2f}", f"{line_total:,.2f}"], line_total


def build_billed_summary_table_style(theme, total_row_idx, discount_row_idx, mode):
    if mode == "no_srno":
        num_col, price_col, total_col = 2, 3, 4
        first_align = "LEFT"
    else:
        num_col, price_col, total_col = 3, 4, 5
        first_align = "CENTER"

    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), theme["table_header_bg"]),
        ("TEXTCOLOR", (0, 0), (-1, 0), theme["table_header_text_color"]),
        ("FONTNAME", (0, 0), (-1, 0), theme["font_bold"]),
        ("FONTNAME", (0, 1), (-1, -1), theme["font_body"]),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, -1), first_align),
        ("ALIGN", (num_col - 1, 0), (num_col, -1), "CENTER"),
        ("ALIGN", (price_col, 0), (total_col, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]

    border_style = theme["table_border_style"]
    if border_style == "grid":
        commands.append(("GRID", (0, 0), (-1, -1), 0.5, colors.black))
    elif border_style == "horizontal_only":
        commands.append(("LINEABOVE", (0, 0), (-1, 0), 0.75, colors.black))
        commands.append(("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.Color(0.6, 0.6, 0.6)))
    elif border_style == "zebra":
        commands.append(("LINEBELOW", (0, 0), (-1, 0), 0.75, colors.black))
        commands.append(("LINEBELOW", (0, total_row_idx - 1), (-1, total_row_idx - 1), 0.75, colors.black))
        commands.append(("ROWBACKGROUNDS", (0, 1), (-1, total_row_idx - 1),
                         [colors.white, theme["zebra_color"]]))

    last_label_col = total_col - 1
    for row_idx in (total_row_idx, discount_row_idx):
        commands.append(("SPAN", (0, row_idx), (last_label_col, row_idx)))
        commands.append(("FONTNAME", (0, row_idx), (-1, row_idx), theme["font_bold"]))
        commands.append(("FONTSIZE", (0, row_idx), (-1, row_idx), 9.5))
        commands.append(("ALIGN", (0, row_idx), (last_label_col, row_idx), "RIGHT"))

    return commands


def build_charge_summary(theme, subtotal, discount, installation, transportation, content_width):
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
    t = Table(rows, colWidths=[content_width * 0.6, content_width * 0.4])
    t.hAlign = "RIGHT"
    t.setStyle(TableStyle([
        ("LINEABOVE", (0, 3), (-1, 3), 0.75, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t, grand_total


def build_boxed_modern_invoice(theme, company, invoice, line_items, content_width):
    title_color = theme.get("invoice_title_color", theme["accent_color"])
    header_bg = theme.get("invoice_header_bg", theme["table_header_bg"])
    header_text_color = theme.get("invoice_header_text_color", colors.white)
    subtotal_bg = theme.get("invoice_subtotal_bg", colors.Color(0.9, 0.93, 0.98))

    style_title = ParagraphStyle("boxed_title", fontName=theme["font_bold"], fontSize=22, leading=27,
                                 alignment=TA_CENTER, textColor=title_color)
    style_hdr = ParagraphStyle("boxed_hdr", fontName=theme["font_bold"], fontSize=9.5,
                               alignment=TA_CENTER, textColor=header_text_color)
    style_val = ParagraphStyle("boxed_val", fontName=theme["font_body"], fontSize=9.5, alignment=TA_CENTER)
    style_item = ParagraphStyle("boxed_item", fontName=theme["font_body"], fontSize=9, leading=11)
    style_num = ParagraphStyle("boxed_num", fontName=theme["font_body"], fontSize=9, alignment=TA_CENTER)
    style_amt = ParagraphStyle("boxed_amt", fontName=theme["font_body"], fontSize=9, alignment=TA_RIGHT)
    style_thankyou = ParagraphStyle("boxed_thankyou", fontName=theme["font_bold"], fontSize=13,
                                    alignment=TA_CENTER, textColor=title_color)
    style_label = ParagraphStyle("boxed_label", fontName=theme["font_bold"], fontSize=9, alignment=TA_CENTER)
    style_label_amt = ParagraphStyle("boxed_label_amt", fontName=theme["font_bold"], fontSize=9.5,
                                     alignment=TA_RIGHT)
    style_contact_intro = ParagraphStyle("boxed_contact_intro", fontName="Helvetica-Oblique", fontSize=8.5,
                                         alignment=TA_CENTER)
    style_contact_line = ParagraphStyle("boxed_contact_line", fontName=theme["font_body"], fontSize=9,
                                        alignment=TA_CENTER)

    c0, c1, c2, c3 = 0, 1, 2, 3

    rows = []
    span_commands = []
    bg_commands = []
    line_commands = []
    align_commands = []
    padding_commands = []

    # Row 0: title
    rows.append([Paragraph("INVOICE", style_title), "", "", ""])
    span_commands.append(("SPAN", (c0, 0), (c3, 0)))
    padding_commands += [("TOPPADDING", (c0, 0), (c3, 0), 10), ("BOTTOMPADDING", (c0, 0), (c3, 0), 8)]

    # Row 1: INVOICE NO. / DATE headers
    row1 = len(rows)
    rows.append([Paragraph("INVOICE NO.", style_hdr), "", Paragraph("DATE", style_hdr), ""])
    span_commands += [("SPAN", (c0, row1), (c1, row1)), ("SPAN", (c2, row1), (c3, row1))]
    bg_commands.append(("BACKGROUND", (c0, row1), (c3, row1), header_bg))
    line_commands.append(("LINEAFTER", (c1, row1), (c1, row1), 0.5, colors.black))

    # Row 2: invoice number / date values
    row2 = len(rows)
    rows.append([
        Paragraph(sanitize_text(invoice.invoice_number), style_val), "",
        Paragraph(invoice.invoice_date.strftime("%d/%m/%Y"), style_val), "",
    ])
    span_commands += [("SPAN", (c0, row2), (c1, row2)), ("SPAN", (c2, row2), (c3, row2))]
    line_commands += [
        ("LINEBELOW", (c0, row2), (c3, row2), 0.5, colors.black),
        ("LINEAFTER", (c1, row2), (c1, row2), 0.5, colors.black),
    ]

    # Row 3: item table header
    row3 = len(rows)
    rows.append([
        Paragraph("DESCRIPTION", style_hdr), Paragraph("QTY", style_hdr),
        Paragraph("UNIT PRICE", style_hdr), Paragraph("AMOUNT", style_hdr),
    ])
    bg_commands.append(("BACKGROUND", (c0, row3), (c3, row3), header_bg))
    line_commands.append(("LINEBELOW", (c0, row3), (c3, row3), 0.5, colors.black))

    # Item rows
    grand_total = 0
    first_item_row = len(rows)
    for item in line_items:
        line_total = item.qty * item.unit_price
        grand_total += line_total
        rows.append([
            Paragraph(sanitize_text(item.description), style_item),
            Paragraph(f"{item.qty:g}", style_num),
            Paragraph(f"{item.unit_price:,.2f}", style_amt),
            Paragraph(f"{line_total:,.2f}", style_amt),
        ])
    last_item_row = len(rows) - 1
    if last_item_row >= first_item_row:
        line_commands.append(("LINEBELOW", (c0, first_item_row), (c3, last_item_row), 0.4, colors.Color(0.8, 0.8, 0.8)))

    subtotal = grand_total
    total = subtotal

    # THANK YOU / SUBTOTAL row
    thank_row1 = len(rows)
    rows.append([
        Paragraph("THANK YOU", style_thankyou), "",
        Paragraph("SUBTOTAL", style_label), Paragraph(f"{subtotal:,.2f}", style_label_amt),
    ])
    # THANK YOU / TOTAL row
    thank_row2 = len(rows)
    rows.append(["", "", Paragraph("TOTAL", style_label), Paragraph(f"{total:,.2f}", style_label_amt)])

    span_commands.append(("SPAN", (c0, thank_row1), (c1, thank_row2)))
    bg_commands.append(("BACKGROUND", (c2, thank_row1), (c3, thank_row2), subtotal_bg))
    line_commands += [
        ("LINEAFTER", (c1, thank_row1), (c1, thank_row2), 0.5, colors.black),
        ("LINEAFTER", (c2, thank_row1), (c2, thank_row2), 0.5, colors.black),
        ("LINEBELOW", (c2, thank_row1), (c3, thank_row1), 0.5, colors.black),
        ("LINEBELOW", (c0, thank_row2), (c3, thank_row2), 0.5, colors.black),
    ]
    padding_commands += [
        ("TOPPADDING", (c0, thank_row1), (c1, thank_row2), 6),
        ("VALIGN", (c0, thank_row1), (c1, thank_row2), "MIDDLE"),
    ]

    # Contact-us blurb
    contact_bits = []
    if getattr(company, "phone", None):
        contact_bits.append(company.phone)
    if getattr(company, "email", None):
        contact_bits.append(company.email)
    contact_html = ""
    if company.authorized_name:
        contact_html += f'<font name="{theme["font_bold"]}">{sanitize_text(company.authorized_name)}</font>'
    if contact_bits:
        contact_html += (", " if contact_html else "") + sanitize_text(", ".join(contact_bits))

    contact_row1 = len(rows)
    rows.append([Paragraph("For questions concerning this invoice, please contact", style_contact_intro), "", "", ""])
    span_commands.append(("SPAN", (c0, contact_row1), (c3, contact_row1)))
    padding_commands.append(("TOPPADDING", (c0, contact_row1), (c3, contact_row1), 8))

    contact_row2 = len(rows)
    rows.append([Paragraph(contact_html, style_contact_line), "", "", ""])
    span_commands.append(("SPAN", (c0, contact_row2), (c3, contact_row2)))
    padding_commands.append(("BOTTOMPADDING", (c0, contact_row2), (c3, contact_row2), 10))

    col_widths = [content_width * 0.55, content_width * 0.12, content_width * 0.165, content_width * 0.165]
    t = Table(rows, colWidths=col_widths)
    t.setStyle(TableStyle(
        [("BOX", (0, 0), (-1, -1), 0.75, colors.black),
         ("LEFTPADDING", (0, 0), (-1, -1), 6),
         ("RIGHTPADDING", (0, 0), (-1, -1), 6),
         ("TOPPADDING", (0, 0), (-1, -1), 4),
         ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
         ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]
        + span_commands + bg_commands + line_commands + align_commands + padding_commands
    ))
    return t, total



def generate_invoice_pdf(company, client, invoice, line_items, output_path, skip_letterhead=False):
    page_width, page_height = A4
    left_margin = right_margin = 20 * mm
    bottom_margin_default = 20 * mm

    theme = get_theme(company)
    is_vision = getattr(company, "pdf_theme", None) == "Rostam"

    # --- Resolve header image ---
    header_path = None
    header_w = header_h = 0
    if not skip_letterhead and getattr(company, "letterhead_filename", None):
        candidate = os.path.join("static", "letterheads", company.letterhead_filename)
        if os.path.exists(candidate):
            dims = get_image_dimensions(candidate, page_width / mm, MAX_HEADER_MM)
            if dims:
                header_path = candidate
                header_w, header_h = dims[0] * mm, dims[1] * mm

    # --- Resolve footer image ---
    footer_path = None
    footer_w = footer_h = 0
    if not skip_letterhead and getattr(company, "letterhead_footer_filename", None):
        candidate = os.path.join("static", "letterheads", company.letterhead_footer_filename)
        if os.path.exists(candidate):
            dims = get_image_dimensions(candidate, page_width / mm, MAX_FOOTER_MM)
            if dims:
                footer_path = candidate
                footer_w, footer_h = dims[0] * mm, dims[1] * mm

    logo_path = None
    if not skip_letterhead and not header_path and getattr(company, "logo_filename", None):
        candidate = os.path.join("static", "company_logos", company.logo_filename)
        if os.path.exists(candidate):
            logo_path = candidate

    # Margins reserved for letterhead
    if skip_letterhead:
        top_margin = BLANK_MARGIN_MM * mm
        bottom_margin = BLANK_MARGIN_MM * mm
    else:
        top_margin = (header_h + 6 * mm) if header_path else (FALLBACK_HEADER_HEIGHT + 8 * mm)
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

    invoice_layout = theme.get("invoice_layout", "standard")

    if invoice_layout == "boxed_modern":
        box, grand_total = build_boxed_modern_invoice(theme, company, invoice, line_items, content_width)
        story.append(box)
        story.append(Spacer(1, 8 * mm))

        # --- Bank details block ---
        if company.bank_details:
            style_bank_head = ParagraphStyle("bank_head", fontName=theme["font_bold"], fontSize=10,
                                             textColor=theme.get("invoice_title_color", theme["accent_color"]))
            style_bank_body = ParagraphStyle("bank_body", fontName=theme["font_bold"], fontSize=9, leading=13)
            story.append(Paragraph("<u>Company Account Details</u>", style_bank_head))
            story.append(Spacer(1, 3 * mm))
            bank_lines = [sanitize_text(line) for line in company.bank_details.split("\n") if line.strip()]
            story.append(Paragraph("<br/>".join(bank_lines), style_bank_body))
            story.append(Spacer(1, 12 * mm))

        # --- Signature block ---
        if is_vision:
            style_sig_name = ParagraphStyle("sig_name", fontName=theme["font_bold"], fontSize=11)
            style_sig_designation = ParagraphStyle("sig_designation", fontName="Helvetica-Oblique", fontSize=9.5)

            sig_rows = []
            if company.signature_filename:
                sig_path = os.path.join("static", "signatures", company.signature_filename)
                if os.path.exists(sig_path):
                    img = Image(sig_path, width=theme["signature_width_mm"] * mm,
                                height=theme["signature_height_mm"] * mm, kind="proportional")
                    img.hAlign = "LEFT"
                    sig_rows.append([img])
            if company.authorized_name:
                sig_rows.append([Paragraph(sanitize_text(company.authorized_name), style_sig_name)])
            if getattr(company, "designation", None):
                sig_rows.append([Paragraph(f"<u>{sanitize_text(company.designation)}</u>", style_sig_designation)])

            if sig_rows:
                sig_table = Table(sig_rows, colWidths=[content_width])
                sig_table.setStyle(TableStyle([
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 1),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ]))
                sig_table.hAlign = "LEFT"
                story.append(KeepTogether(sig_table))

        elif getattr(company, "pdf_theme", None) == "Space Enterprises":
            style_sig_name = ParagraphStyle("sig_name", fontName=theme["font_bold"], fontSize=11)
            style_sig_designation = ParagraphStyle("sig_designation", fontName="Helvetica-Oblique", fontSize=9.5)

            sig_rows = []
            if company.signature_filename:
                sig_path = os.path.join("static", "signatures", company.signature_filename)
                if os.path.exists(sig_path):
                    img = Image(sig_path, width=theme["signature_width_mm"] * mm,
                                height=theme["signature_height_mm"] * mm, kind="proportional")
                    img.hAlign = "LEFT"
                    sig_rows.append([img])
            if company.authorized_name:
                sig_rows.append([Paragraph(sanitize_text(company.authorized_name), style_sig_name)])
            if getattr(company, "designation", None):
                sig_rows.append([Paragraph(f"<u>{sanitize_text(company.designation)}</u>", style_sig_designation)])

            if sig_rows:
                sig_table = Table(sig_rows, colWidths=[content_width])
                sig_table.setStyle(TableStyle([
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 1),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ]))
                sig_table.hAlign = "LEFT"
                story.append(KeepTogether(sig_table))

        else:
            style_sig_name = ParagraphStyle("sig_name", fontName=theme["font_bold"], fontSize=11)
            style_sig_designation = ParagraphStyle("sig_designation", fontName="Helvetica-Oblique", fontSize=9.5)
            sig_block = []
            if company.signature_filename:
                sig_path = os.path.join("static", "signatures", company.signature_filename)
                if os.path.exists(sig_path):
                    sig_block.append(Image(sig_path, width=theme["signature_width_mm"] * mm,
                                           height=theme["signature_height_mm"] * mm, kind="proportional"))
                    sig_block.append(Spacer(1, 2 * mm))
            if company.authorized_name:
                sig_block.append(Paragraph(sanitize_text(company.authorized_name), style_sig_name))
            if getattr(company, "designation", None):
                sig_block.append(Paragraph(f"<u>{sanitize_text(company.designation)}</u>", style_sig_designation))
            if sig_block:
                story.append(KeepTogether(sig_block))

        doc.build(story, onFirstPage=draw_header, onLaterPages=draw_header, canvasmaker=NumberedCanvas)
        return grand_total

    if invoice_layout == "billed_summary":
        style_normal = ParagraphStyle("normal", fontName=theme["font_body"], fontSize=8.5, leading=10)
        style_bill_label = ParagraphStyle("bill_label", fontName=theme["font_bold"], fontSize=9)
        style_client_block = ParagraphStyle("client_block", fontName=theme["font_body"], fontSize=9.5, leading=13)
        style_meta_bold = ParagraphStyle("meta_bold", fontName=theme["font_bold"], fontSize=10,
                                         alignment=TA_RIGHT, textColor=theme["accent_color"])

        story.append(Paragraph(get_doc_title(theme, "invoice"),
                               ParagraphStyle("title", fontName=theme["font_bold"], fontSize=16,
                                              alignment=TA_CENTER, textColor=theme["accent_color"])))
        story.append(Spacer(1, 6 * mm))

        # --- RECIPIENT / BILL TO SECTION ---
        recipient_text = getattr(invoice, "recipient", None)
        if recipient_text and recipient_text.strip():
            bill_lines = [f'<font name="{theme["font_bold"]}">BILL TO:</font>']
            for line in recipient_text.split("\n"):
                if line.strip():
                    bill_lines.append(sanitize_text(line.strip()))
            left_cell = Paragraph("<br/>".join(bill_lines), style_client_block)
            right_cell = Paragraph(
                f"Invoice # {sanitize_text(invoice.invoice_number)}<br/>"
                f"{invoice.invoice_date.strftime('%d/%m/%Y')}", style_meta_bold
            )
            top_row = Table([[left_cell, right_cell]], colWidths=[content_width * 0.6, content_width * 0.4])
            top_row.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]))
            story.append(top_row)
        else:
            right_cell = Paragraph(
                f"Invoice # {sanitize_text(invoice.invoice_number)}<br/>"
                f"{invoice.invoice_date.strftime('%d/%m/%Y')}", style_meta_bold
            )
            top_row = Table([[right_cell]], colWidths=[content_width])
            top_row.setStyle(TableStyle([
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]))
            story.append(top_row)
        story.append(Spacer(1, 6 * mm))

        header_labels, col_widths, mode = get_table_columns(theme, content_width)
        table_data = [header_labels]
        subtotal = 0
        for idx, item in enumerate(line_items, start=1):
            row, line_total = build_item_row(mode, idx, item, style_normal)
            table_data.append(row)
            subtotal += line_total

        discount = float(getattr(invoice, "discount_amount", 0) or 0)
        installation = float(getattr(invoice, "installation_charges", 0) or 0)
        transportation = float(getattr(invoice, "transportation_charges", 0) or 0)

        table_data.append(["Total"] + [""] * (len(header_labels) - 2) + [f"{subtotal:,.2f}"])
        total_row_idx = len(table_data) - 1
        table_data.append(["Discount"] + [""] * (len(header_labels) - 2) + [f"{discount:,.2f}" if discount else "-"])
        discount_row_idx = len(table_data) - 1

        item_table = Table(table_data, colWidths=col_widths, repeatRows=1)
        item_table.setStyle(TableStyle(build_billed_summary_table_style(theme, total_row_idx, discount_row_idx, mode)))
        story.append(item_table)
        story.append(Spacer(1, 8 * mm))

        summary_table, grand_total = build_charge_summary(
            theme, subtotal, discount, installation, transportation, content_width * 0.45
        )

        if is_vision:
            style_name = ParagraphStyle("name", fontName=theme["font_bold"], fontSize=9)
            style_designation = ParagraphStyle("designation", fontName=theme["font_body"], fontSize=9)

            sig_rows = []
            if company.signature_filename:
                sig_path = os.path.join("static", "signatures", company.signature_filename)
                if os.path.exists(sig_path):
                    img = Image(sig_path, width=theme["signature_width_mm"] * mm,
                                height=theme["signature_height_mm"] * mm, kind="proportional")
                    img.hAlign = "LEFT"
                    sig_rows.append([img])
            if company.authorized_name:
                sig_rows.append([Paragraph(sanitize_text(company.authorized_name), style_name)])
            if getattr(company, "designation", None):
                sig_rows.append([Paragraph(sanitize_text(company.designation), style_designation)])

            if sig_rows:
                sig_inner_table = Table(sig_rows, colWidths=[content_width * 0.55])
                sig_inner_table.setStyle(TableStyle([
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 1),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ]))
                sig_cell = [sig_inner_table]
            else:
                sig_cell = []
        else:
            style_name = ParagraphStyle("name", fontName=theme["font_bold"], fontSize=9)
            style_designation = ParagraphStyle("designation", fontName=theme["font_body"], fontSize=9)
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
                sig_cell.append(Paragraph(sanitize_text(company.designation), style_designation))

        two_col = Table([[sig_cell, summary_table]], colWidths=[content_width * 0.55, content_width * 0.45])
        two_col.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))

        story.append(KeepTogether(two_col))
        story.append(Spacer(1, 10 * mm))

        if company.bank_details:
            style_bank_head = ParagraphStyle("bank_head", fontName=theme["font_bold"], fontSize=10,
                                             textColor=theme["accent_color"])
            style_bank_body = ParagraphStyle("bank_body", fontName=theme["font_bold"], fontSize=9, leading=13)
            story.append(Paragraph("<u>Company Account Details</u>", style_bank_head))
            story.append(Spacer(1, 3 * mm))
            bank_lines = [sanitize_text(line) for line in company.bank_details.split("\n") if line.strip()]
            story.append(Paragraph("<br/>".join(bank_lines), style_bank_body))

        doc.build(story, onFirstPage=draw_header, onLaterPages=draw_header, canvasmaker=NumberedCanvas)
        return grand_total

    # --- Standard layout ---
    style_normal = ParagraphStyle("normal", fontName=theme["font_body"], fontSize=8.5, leading=10)
    style_bold = ParagraphStyle("bold", fontName=theme["font_bold"], fontSize=10)
    style_bold_right = ParagraphStyle("bold_right", fontName=theme["font_bold"], fontSize=10, alignment=TA_RIGHT)
    style_client = ParagraphStyle("client", fontName=theme["font_body"], fontSize=9.5, leading=13)
    style_ref = ParagraphStyle("ref", fontName=theme["font_bold"], fontSize=10, alignment=TA_RIGHT)

    po_number = ""
    if invoice.order and invoice.order.purchase_order:
        po_number = invoice.order.purchase_order.po_number or ""

    if is_vision:
        story.append(VisionHeading("INVOICE", content_width, theme))
        story.append(Spacer(1, 6 * mm))

    header_row = Table(
        [[Paragraph(f"Invoice # {sanitize_text(invoice.invoice_number)}", style_bold),
          Paragraph(f"Date: {invoice.invoice_date.strftime('%d-%m-%Y')}", style_bold_right)]],
        colWidths=[content_width / 2, content_width / 2],
    )
    header_row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header_row)
    story.append(Spacer(1, 4 * mm))

    # --- RECIPIENT / BILLED TO SECTION ---
    recipient_text = getattr(invoice, "recipient", None)
    if recipient_text and recipient_text.strip():
        billed_lines = []
        first_line = True
        for line in recipient_text.split("\n"):
            if line.strip():
                if first_line:
                    billed_lines.append(f'<font name="{theme["font_bold"]}">Billed To: </font>{sanitize_text(line.strip())}')
                    first_line = False
                else:
                    billed_lines.append(sanitize_text(line.strip()))

        billed_cell = Paragraph("<br/>".join(billed_lines), style_client)
        po_cell = Paragraph(f"PO No: {sanitize_text(po_number)}", style_ref) if po_number else Paragraph("", style_normal)

        sub_row = Table([[billed_cell, po_cell]], colWidths=[content_width / 2, content_width / 2])
        sub_row.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(sub_row)
    elif po_number:
        po_cell = Paragraph(f"PO No: {sanitize_text(po_number)}", style_ref)
        sub_row = Table([[po_cell]], colWidths=[content_width])
        sub_row.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(sub_row)
    story.append(Spacer(1, 6 * mm))

    has_part_no = any(item.part_no for item in line_items)
    has_tax = any((item.tax_percent or 0) > 0 for item in line_items)
    item_tax_pct = next((float(item.tax_percent) for item in line_items if item.tax_percent), 0)
    gst_label = f"GST {item_tax_pct:g}%" if item_tax_pct else "GST"

    hdr_style = ParagraphStyle("inv_hdr", fontName=theme["font_bold"], fontSize=8.5, leading=11,
                               textColor=theme["table_header_text_color"])
    hdr_style_c = ParagraphStyle("inv_hdr_c", parent=hdr_style, alignment=TA_CENTER)
    hdr_style_r = ParagraphStyle("inv_hdr_r", parent=hdr_style, alignment=TA_RIGHT)

    columns = [
        ("Sr.", 0.05, "CENTER", lambda idx, item, lt, g: str(idx)),
    ]
    if has_part_no:
        columns.append(("Part No/Code", 0.11, "CENTER", lambda idx, item, lt, g: sanitize_text(item.part_no or "")))
    columns += [
        ("Items", 0.30, "LEFT", lambda idx, item, lt, g: Paragraph(sanitize_text(item.description), style_normal)),
        ("Unit", 0.06, "CENTER", lambda idx, item, lt, g: sanitize_text(getattr(item, "unit", None) or "Nos")),
        ("Qty", 0.06, "CENTER", lambda idx, item, lt, g: f"{item.qty:g}"),
        ("Unit Price", 0.13, "RIGHT", lambda idx, item, lt, g: f"{item.unit_price:,.2f}"),
    ]
    if has_tax:
        columns.append((gst_label, 0.11, "RIGHT", lambda idx, item, lt, g: f"{g:,.2f}"))
    columns.append(("Total", 0.16, "RIGHT", lambda idx, item, lt, g: f"{lt + g:,.2f}"))
    ncols = len(columns)
    total_frac = sum(frac for _, frac, _, _ in columns)

    def make_header(label, align):
        if align == "CENTER":
            return Paragraph(label, hdr_style_c)
        if align == "RIGHT":
            return Paragraph(label, hdr_style_r)
        return Paragraph(label, hdr_style)

    table_data = [[make_header(h, align) for h, _, align, _ in columns]]
    col_widths = [content_width * (frac / total_frac) for _, frac, _, _ in columns]
    subtotal = 0.0
    total_gst = 0.0
    for idx, item in enumerate(line_items, start=1):
        lt = item.qty * item.unit_price
        g = round(lt * (item.tax_percent or 0) / 100, 2)
        subtotal += lt
        total_gst += g
        table_data.append([fn(idx, item, lt, g) for _, _, _, fn in columns])

    items_total = subtotal
    charges = []
    if is_vision:
        discount_val = float(getattr(invoice, "discount_amount", 0) or 0)
        installation_val = float(getattr(invoice, "installation_charges", 0) or 0)
        transportation_val = float(getattr(invoice, "transportation_charges", 0) or 0)
        tax_pct = float(getattr(invoice, "tax_amount", 0) or 0)
        if total_gst:
            tax_val = round(total_gst, 2)
            tax_label = gst_label
        elif tax_pct:
            tax_val = round(items_total * tax_pct / 100, 2)
            tax_label = f"GST ({tax_pct:g}%)"
        else:
            tax_val = 0
            tax_label = None
        if tax_val:
            charges.append((tax_label, tax_val))
            items_total += tax_val
        if discount_val:
            charges.append(("Discount", discount_val))
            items_total -= discount_val
        if installation_val:
            charges.append(("Installation Charges", installation_val))
            items_total += installation_val
        if transportation_val:
            charges.append(("Transportation Charges", transportation_val))
            items_total += transportation_val

    def summary_row(label, value):
        row = [""] * ncols
        row[0] = label
        row[-1] = value
        table_data.append(row)

    if charges:
        summary_row("Total", f"{subtotal:,.2f}")
        first_summary = len(table_data) - 1
        for label, val in charges:
            summary_row(label, f"{val:,.2f}")
        summary_row("Grand Total", f"{items_total:,.2f}")
        total_row_idx = len(table_data) - 1
    else:
        summary_row("Total", f"{items_total:,.2f}")
        first_summary = len(table_data) - 1
        total_row_idx = len(table_data) - 1
    grand_total = items_total

    rcmds = [
        ("BACKGROUND", (0, 0), (-1, 0), theme["table_header_bg"]),
        ("TEXTCOLOR", (0, 0), (-1, 0), theme["table_header_text_color"]),
        ("FONTNAME", (0, 0), (-1, 0), theme["font_bold"]),
        ("FONTNAME", (0, 1), (-1, -1), theme["font_body"]),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, first_summary - 1), 0.5, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    for c, (_, _, align, _) in enumerate(columns):
        if align == "CENTER":
            rcmds.append(("ALIGN", (c, 0), (c, first_summary - 1), "CENTER"))
        elif align == "RIGHT":
            rcmds.append(("ALIGN", (c, 0), (c, first_summary - 1), "RIGHT"))
    for r in range(first_summary, total_row_idx + 1):
        rcmds.append(("SPAN", (0, r), (ncols - 2, r)))
        rcmds.append(("FONTNAME", (0, r), (-1, r), theme["font_bold"]))
        rcmds.append(("FONTSIZE", (0, r), (-1, r), 9))
        rcmds.append(("ALIGN", (0, r), (ncols - 2, r), "LEFT"))
        rcmds.append(("ALIGN", (ncols - 1, r), (ncols - 1, r), "RIGHT"))
        rcmds.append(("LEFTPADDING", (0, r), (ncols - 2, r), 4))
    rcmds.append(("LINEABOVE", (0, first_summary), (-1, first_summary), 0.75, colors.black))
    rcmds.append(("BACKGROUND", (0, total_row_idx), (-1, total_row_idx), theme["table_header_bg"]))
    rcmds.append(("TEXTCOLOR", (0, total_row_idx), (-1, total_row_idx), theme["table_header_text_color"]))

    item_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    item_table.setStyle(TableStyle(rcmds))
    story.append(item_table)
    story.append(Spacer(1, 8 * mm))

    if company.bank_details:
        style_bank_head = ParagraphStyle("bank_head", fontName=theme["font_bold"], fontSize=10,
                                         textColor=theme["accent_color"])
        style_bank_body = ParagraphStyle("bank_body", fontName=theme["font_bold"], fontSize=9, leading=13)
        story.append(Paragraph("<u>Company Account Details</u>", style_bank_head))
        story.append(Spacer(1, 3 * mm))
        bank_lines = [sanitize_text(line) for line in company.bank_details.split("\n") if line.strip()]
        story.append(Paragraph("<br/>".join(bank_lines), style_bank_body))
        story.append(Spacer(1, 8 * mm))

    if is_vision:
        style_name = ParagraphStyle("name", fontName=theme["font_bold"], fontSize=9)

        sig_rows = []
        if company.signature_filename:
            sig_path = os.path.join("static", "signatures", company.signature_filename)
            if os.path.exists(sig_path):
                img = Image(sig_path, width=theme["signature_width_mm"] * mm,
                            height=theme["signature_height_mm"] * mm, kind="proportional")
                img.hAlign = "LEFT"
                sig_rows.append([img])
        if company.authorized_name:
            sig_rows.append([Paragraph(sanitize_text(company.authorized_name), style_name)])
        if theme.get("show_company_name_under_signature", True):
            sig_rows.append([Paragraph(sanitize_text(company.name), style_name)])

        if sig_rows:
            sig_table = Table(sig_rows, colWidths=[content_width])
            sig_table.setStyle(TableStyle([
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ]))
            sig_table.hAlign = "LEFT"
            story.append(KeepTogether(sig_table))

    elif getattr(company, "pdf_theme", None) == "Space Enterprises":
        style_name = ParagraphStyle("name", fontName=theme["font_bold"], fontSize=9)

        sig_rows = []
        if company.signature_filename:
            sig_path = os.path.join("static", "signatures", company.signature_filename)
            if os.path.exists(sig_path):
                img = Image(sig_path, width=theme["signature_width_mm"] * mm,
                            height=theme["signature_height_mm"] * mm, kind="proportional")
                img.hAlign = "LEFT"
                sig_rows.append([img])
        if company.authorized_name:
            sig_rows.append([Paragraph(sanitize_text(company.authorized_name), style_name)])
        if theme.get("show_company_name_under_signature", True):
            sig_rows.append([Paragraph(sanitize_text(company.name), style_name)])

        if sig_rows:
            sig_table = Table(sig_rows, colWidths=[content_width])
            sig_table.setStyle(TableStyle([
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ]))
            sig_table.hAlign = "LEFT"
            story.append(KeepTogether(sig_table))

    else:
        style_name = ParagraphStyle("name", fontName=theme["font_bold"], fontSize=9)
        sig_block = []
        if company.signature_filename:
            sig_path = os.path.join("static", "signatures", company.signature_filename)
            if os.path.exists(sig_path):
                img = Image(sig_path, width=theme["signature_width_mm"] * mm,
                                       height=theme["signature_height_mm"] * mm, kind="proportional")
                sig_block.append(img)
                sig_block.append(Spacer(1, 2 * mm))
        if company.authorized_name:
            sig_block.append(Paragraph(sanitize_text(company.authorized_name), style_name))
        if theme.get("show_company_name_under_signature", True):
            sig_block.append(Paragraph(sanitize_text(company.name), style_name))
        if sig_block:
            story.append(KeepTogether(sig_block))

    doc.build(story, onFirstPage=draw_header, onLaterPages=draw_header, canvasmaker=NumberedCanvas)
    return grand_total
"""
Per-company PDF styling. A company's `pdf_theme` column (models.py) is a key
into THEMES below. Anything not overridden falls back to "default", so a
company with no theme set (or an unrecognized one) still renders correctly.

To add a new company-specific look: copy one of the existing dicts, change
the key, tweak the values, then set that company's pdf_theme to the new key
(via the edit-company form or directly in the DB).
"""

from reportlab.lib import colors

DEFAULT_DOC_TITLES = {
    "quotation": "Quotation",
    "invoice": "Invoice",
    "challan": "Delivery Challan",
}

THEMES = {
    "default": {
        "table_border_style": "grid",          # "grid" | "horizontal_only" | "zebra"
        "table_header_bg": colors.Color(0.92, 0.92, 0.92),
        "table_header_text_color": colors.black,
        "zebra_color": colors.Color(0.96, 0.96, 0.96),
        "total_row_style": "boxed",            # "boxed" | "line_only"
        "accent_color": colors.Color(0.05, 0.09, 0.28),  # navy — fallback header bar, tax line
        "font_body": "Helvetica",
        "font_bold": "Helvetica-Bold",
        "signature_align": "left",             # "left" | "center" | "right"
        "signature_width_mm": 35,
        "signature_height_mm": 25,
        "show_company_name_under_signature": True,
        "heading_style": "plain",              # "plain" | "banner"
        "heading_align": "left",               # "left" | "center"
        "doc_titles": {},                      # overrides DEFAULT_DOC_TITLES per doc_type; {} = use defaults
    },

    "Rostam": {
        "table_border_style": "grid",          # "grid" | "horizontal_only" | "zebra"
        "table_header_bg": colors.Color(0.92, 0.92, 0.92),   # light grey header row
        "table_header_text_color": colors.black,
        "zebra_color": colors.Color(0.96, 0.96, 0.96),
        "total_row_style": "boxed",
        "accent_color": colors.Color(0.98, 0.78, 0.05),      # Vision Yellow
        "font_body": "Helvetica",
        "font_bold": "Helvetica-Bold",
        "signature_align": "left",            # Right-aligned signature & stamp
        "signature_width_mm": 35,
        "signature_height_mm": 25,
        "show_company_name_under_signature": True,
        "heading_style": "plain",
        "heading_align": "center",
        "doc_titles": {"commercial": "COMMERCIAL OFFER"},
    },

    "The Expert International": {
        "table_border_style": "zebra",
        "table_header_bg": colors.Color(0.92, 0.92, 0.92),   # light grey header bar
        "table_header_text_color": colors.black,
        "zebra_color": colors.Color(0.93, 0.93, 0.93),
        "total_row_style": "line_only",
        "accent_color": colors.Color(0.09, 0.13, 0.35),      # navy
        "font_body": "Helvetica",
        "font_bold": "Helvetica-Bold",
        "signature_align": "left",
        "signature_width_mm": 32,
        "signature_height_mm": 22,
        "show_company_name_under_signature": False,
        "heading_style": "plain",
        "heading_align": "center",
        "doc_titles": {
            "invoice": "Sales Tax Invoice",
            "commercial": "COMMERCIAL OFFER",
            "technical": "TECHNICAL OFFER",
        },
        # Quotation (commercial/technical) is rendered as the CASD EME tender
        # annex format used for this client's actual tender submissions -- see
        # "tender_style" below and _build_tender_annex_story() in
        # quotation_template.py. Invoices/challans are unaffected (they use
        # invoice_layout / challan_layout, not "layout").
        "layout": "tender_annex",
        "tender_style": "expert",
        "tender_annexure_label": "Anx  A",
        "tender_part_no_label": "Part No / Alt Part No",
        "tender_price_label": "Price Per Unit",
        "tender_photo_label": "Picture",
        "tender_quoted_label": "Quoted /NQ",
        "table_columns": "no_srno",
        "invoice_layout": "billed_summary",
        "invoice_table_columns": "no_srno",
        "challan_layout": "info_box",
        "challan_heading_bg": colors.Color(0.82, 0.82, 0.82),
        "challan_heading_text_color": colors.white,
        "challan_signature_align": "left",
        "challan_show_unit": True,
        "challan_receiver_label": "Receiver Signatory",
    },

    "Space Enterprises": {
        "table_border_style": "grid",
        "table_header_bg": colors.Color(0.92, 0.92, 0.92),   # light grey header bar
        "table_header_text_color": colors.black,
        "zebra_color": colors.Color(0.94, 0.96, 0.99),
        "total_row_style": "line_only",
        "accent_color": colors.Color(0.16, 0.32, 0.62),      # medium blue, matches wordmark
        "font_body": "Helvetica",
        "font_bold": "Helvetica-Bold",
        "signature_align": "left",            # <--- Changed from "left" to "right"
        "signature_width_mm": 48,
        "signature_height_mm": 34,
        "show_company_name_under_signature": True,
        "heading_style": "banner",
        "heading_align": "center",
        "doc_titles": {
            "commercial": "COMMERCIAL  QUOTATION",
            "technical": "TECHNICAL  QUOTATION",
        },
        # Quotation (commercial/technical) is rendered as the CASD EME tender
        # annex format used for this client's actual tender submissions -- see
        # "tender_style" below and _build_tender_annex_story() in
        # quotation_template.py. Invoices/challans are unaffected (they use
        # invoice_layout / challan_layout, not "layout").
        "layout": "tender_annex",
        "tender_style": "space",
        "tender_annexure_label": "Annexure  'A'",
        "outer_border_color": colors.Color(0.0, 0.42, 0.15),   # green box borders
        "outer_border_width": 1.2,
        "table_columns": "no_unit",
        "total_summary_rows": ["Total Amount", "Grand Total"],
        "challan_layout": "info_box",
        "challan_heading_bg": colors.Color(0.75, 0.75, 0.75),
        "challan_signature_align": "right",
        "invoice_layout": "boxed_modern",
        "invoice_title_color": colors.Color(0.10, 0.35, 0.75),
        "invoice_header_bg": colors.Color(0.18, 0.45, 0.78),
        "invoice_header_text_color": colors.white,
        "invoice_subtotal_bg": colors.Color(0.85, 0.91, 0.97),
    },
}


THEME_DISPLAY_NAMES = {
    "default": "Default",
    "Rostam": "Rostam",
    "The Expert International": "The Expert International",
    "Space Enterprises": "Space Enterprises",
}


def get_theme(company):
    """Returns the theme config dict for a company, falling back to 'default'
    if the company has no pdf_theme set or it doesn't match a known key."""
    key = getattr(company, "pdf_theme", None) or "default"
    return THEMES.get(key, THEMES["default"])


def get_doc_title(theme, doc_type):
    """Returns the heading text for a document type, using the theme's
    override if set, otherwise the system-wide default (e.g. 'Invoice')."""
    overrides = theme.get("doc_titles", {}) or {}
    return overrides.get(doc_type, DEFAULT_DOC_TITLES.get(doc_type, doc_type.capitalize()))
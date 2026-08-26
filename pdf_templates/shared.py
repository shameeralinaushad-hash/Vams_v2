import os
from xml.sax.saxutils import escape
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Flowable
from PIL import Image as PILImage


def sanitize_text(text):
    if not text:
        return ""
    clean = text.encode("latin-1", errors="ignore").decode("latin-1")
    return escape(clean)


def get_image_dimensions(image_path, max_width_mm, max_height_mm):
    try:
        with PILImage.open(image_path) as img:
            w, h = img.size
            ratio = h / w
            height_at_full_width = max_width_mm * ratio
            if height_at_full_width <= max_height_mm:
                return max_width_mm, height_at_full_width
            height_mm = max_height_mm
            width_mm = height_mm / ratio
            return width_mm, height_mm
    except Exception:
        return None


class VisionHeading(Flowable):
    def __init__(self, title_text, width, theme):
        super().__init__()
        self.title_text = title_text.strip()
        self.width = width
        self.font_name = theme.get("font_bold", "Helvetica-Bold")
        self.font_size = 20
        self.height = 28
        self.fill_color = colors.HexColor("#FFD700")

    def wrap(self, availWidth, availHeight):
        return self.width, self.height

    def draw(self):
        canv = self.canv
        canv.saveState()
        canv.setFont(self.font_name, self.font_size)
        text_w = canv.stringWidth(self.title_text, self.font_name, self.font_size)
        center_x = self.width / 2.0
        text_x = center_x - (text_w / 2.0)
        text_y = 6
        line_y = text_y + (self.font_size * 0.35)
        gap = 14
        left_line_end = text_x - gap
        right_line_start = text_x + text_w + gap
        canv.setStrokeColor(colors.black)
        canv.setLineWidth(1.5)
        if left_line_end > 0:
            canv.line(0, line_y, left_line_end, line_y)
        if right_line_start < self.width:
            canv.line(right_line_start, line_y, self.width, line_y)
        canv.setFillColor(self.fill_color)
        canv.drawString(text_x, text_y, self.title_text)
        canv.restoreState()


FALLBACK_HEADER_HEIGHT = 34 * mm
LOGO_MAX_SIZE = 28 * mm
ACCENT_BAR_HEIGHT = 1.2 * mm
MAX_HEADER_MM = 80
MAX_FOOTER_MM = 35
BLANK_MARGIN_MM = 38


class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            super().showPage()
        super().save()

    def draw_page_number(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#666666"))
        page_text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(A4[0] - 20 * mm, 12 * mm, page_text)
        self.restoreState()


def build_header_callback(page_width, left_margin, page_height, company, theme,
                          header_path, header_w, header_h,
                          footer_path, footer_w, footer_h,
                          logo_path, skip_letterhead):
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
                    canv.drawImage(
                        logo_path, left_margin, logo_y,
                        width=draw_w, height=draw_h,
                        preserveAspectRatio=True, mask="auto"
                    )
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

    return draw_header

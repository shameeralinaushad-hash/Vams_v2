import os
import io
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from flask import current_app
from PIL import Image


def stamp_last_page(input_pdf_path, output_pdf_path, company, app_root_path=None):
    if not company.signature_filename:
        return False

    if app_root_path is None:
        try:
            app_root_path = current_app.root_path
        except RuntimeError:
            app_root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    image_path = os.path.join(app_root_path, 'static', 'signatures', company.signature_filename)

    if not os.path.exists(image_path):
        return False

    try:
        # 1. Open image with PIL to calculate proportions
        with Image.open(image_path) as img:
            orig_w, orig_h = img.size

        # Target width for the stamp (adjust as needed, 100 points wide)
        target_width = 100
        aspect_ratio = orig_h / orig_w
        target_height = target_width * aspect_ratio

        # 2. Create a temporary PDF from the image in memory
        packet = io.BytesIO()
        can = canvas.Canvas(packet, pagesize=letter)

        # Draw image with calculated width/height
        # 450 = X position (right side), 50 = Y position (bottom)
        can.drawImage(image_path, 450, 50, width=target_width, height=target_height, mask='auto')
        can.save()
        packet.seek(0)

        # 3. Open the original PDF and the stamp PDF
        reader = PdfReader(input_pdf_path)
        writer = PdfWriter()
        stamp_reader = PdfReader(packet)
        stamp_page = stamp_reader.pages[0]

        # 4. Add all pages, and merge stamp on the last one
        for i, page in enumerate(reader.pages):
            if i == len(reader.pages) - 1:
                page.merge_page(stamp_page)
            writer.add_page(page)

        # 5. Save the result
        with open(output_pdf_path, "wb") as f:
            writer.write(f)

        return True
    except Exception as e:
        print(f"Error in stamp_last_page: {e}")
        return False
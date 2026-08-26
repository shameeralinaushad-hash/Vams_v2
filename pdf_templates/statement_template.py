import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm


def generate_statement_pdf(client, company_breakdown, combined_stats, orders, output_path):
    c = canvas.Canvas(output_path, pagesize=A4)
    width, height = A4
    y = height - 25 * mm

    c.setFont("Helvetica-Bold", 16)
    c.drawString(20 * mm, y, "Statement of Account")
    y -= 10 * mm

    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, y, f"Client: {client.name}")
    y -= 6 * mm
    if client.address:
        c.drawString(20 * mm, y, client.address)
        y -= 6 * mm
    from datetime import date
    c.drawString(20 * mm, y, f"Statement Date: {date.today().strftime('%d %B, %Y')}")
    y -= 12 * mm

    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y, "Summary (All Companies)")
    y -= 7 * mm
    c.setFont("Helvetica", 9.5)
    c.drawString(22 * mm, y, f"Total Revenue Generated: {combined_stats['revenue']:,.2f}")
    y -= 5.5 * mm
    c.drawString(22 * mm, y, f"Total Paid to Date: {combined_stats['paid']:,.2f}")
    y -= 5.5 * mm
    c.drawString(22 * mm, y, f"Outstanding Balance: {combined_stats['owed']:,.2f}")
    y -= 12 * mm

    if company_breakdown:
        c.setFont("Helvetica-Bold", 11)
        c.drawString(20 * mm, y, "Breakdown by Company")
        y -= 7 * mm
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(20 * mm, y, "Company")
        c.drawRightString(120 * mm, y, "Revenue")
        c.drawRightString(150 * mm, y, "Paid")
        c.drawRightString(190 * mm, y, "Owed")
        y -= 2 * mm
        c.line(20 * mm, y, 190 * mm, y)
        y -= 5 * mm
        c.setFont("Helvetica", 8.5)
        for entry in company_breakdown:
            c.drawString(20 * mm, y, entry["company"].name)
            c.drawRightString(120 * mm, y, f"{entry['revenue']:,.2f}")
            c.drawRightString(150 * mm, y, f"{entry['paid']:,.2f}")
            c.drawRightString(190 * mm, y, f"{entry['owed']:,.2f}")
            y -= 6 * mm
        y -= 8 * mm

    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y, "Order History")
    y -= 7 * mm
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(20 * mm, y, "Order #")
    c.drawString(50 * mm, y, "Company")
    c.drawString(90 * mm, y, "Status")
    c.drawString(130 * mm, y, "Date")
    c.drawRightString(190 * mm, y, "Invoice Total")
    y -= 2 * mm
    c.line(20 * mm, y, 190 * mm, y)
    y -= 5 * mm
    c.setFont("Helvetica", 8.5)

    for o in orders:
        if y < 30 * mm:
            c.showPage()
            y = height - 25 * mm
        c.drawString(20 * mm, y, f"#{o.id}")
        c.drawString(50 * mm, y, o.company.name[:20])
        c.drawString(90 * mm, y, o.status)
        c.drawString(130 * mm, y, str(o.inquiry_date))
        total = o.invoice.total_amount if o.invoice else 0
        c.drawRightString(190 * mm, y, f"{total:,.2f}")
        y -= 6 * mm

    c.save()
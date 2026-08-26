import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors

from pdf_templates.shared import sanitize_text, get_image_dimensions


SHEET_WIDTH, SHEET_HEIGHT = A4
MARGIN = 15 * mm
TOP = SHEET_HEIGHT - 15 * mm
LEFT = MARGIN
RIGHT = SHEET_WIDTH - MARGIN
BODY_WIDTH = RIGHT - LEFT


def generate_salary_slip_pdf(company, employee, payroll_record, output_path):
    c = canvas.Canvas(output_path, pagesize=A4)
    y = TOP

    # --- Header ---
    c.setFont("Helvetica-Bold", 16)
    c.drawString(LEFT, y, sanitize_text(company.name) if company else "Salary Slip")
    y -= 8 * mm

    c.setFont("Helvetica", 8)
    c.drawString(LEFT, y, f"Pay Period: {payroll_record.month}/{payroll_record.year}")
    c.drawRightString(RIGHT, y, "Salary Slip")
    y -= 12 * mm

    # --- Employee Info Block ---
    c.setFillColor(colors.Color(0.15, 0.15, 0.15))
    c.setFont("Helvetica-Bold", 9)
    c.drawString(LEFT, y, "Employee Details")
    y -= 2 * mm
    c.setStrokeColor(colors.Color(0.8, 0.8, 0.8))
    c.line(LEFT, y, RIGHT, y)
    y -= 7 * mm

    c.setFont("Helvetica", 9)
    c.setFillColor(colors.black)
    info_lines = [
        ("Name", employee.name),
        ("Code", employee.employee_code or "—"),
        ("Designation", employee.designation or "—"),
        ("Department", employee.department or "—"),
    ]
    for i, (label, val) in enumerate(info_lines):
        x_pos = LEFT + (i % 2) * (BODY_WIDTH // 2)
        y_pos = y - (i // 2) * 5 * mm
        c.setFont("Helvetica", 7.5)
        c.drawString(x_pos, y_pos, label.upper())
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x_pos, y_pos - 3.5 * mm, sanitize_text(str(val)))

    y -= 14 * mm

    # --- Salary Breakdown ---
    c.setFont("Helvetica-Bold", 9)
    c.drawString(LEFT, y, "Salary Breakdown")
    y -= 2 * mm
    c.line(LEFT, y, RIGHT, y)
    y -= 8 * mm

    half_days = payroll_record.half_days or 0
    daily_rate = payroll_record.base_salary / payroll_record.working_days_in_month if payroll_record.working_days_in_month else 0

    rows = [
        ("Basic Salary (Monthly)", f"{payroll_record.base_salary:,.0f}"),
        ("Working Days", str(payroll_record.working_days_in_month)),
        ("Days Present", str(payroll_record.days_present)),
    ]
    if half_days:
        rows.append(("Half Days", str(half_days)))
    rows.append(("Calculated Salary", f"{payroll_record.calculated_salary:,.0f}"))

    if payroll_record.adjustment_amount:
        rows.append(("Adjustment", f"{payroll_record.adjustment_amount:+,.0f}"))

    rows.append(("Net Pay", f"{payroll_record.final_salary:,.0f}"))

    for label, val in rows:
        c.setFont("Helvetica", 9)
        c.drawString(LEFT + 5 * mm, y, label)
        c.setFont("Helvetica-Bold", 9)
        c.drawRightString(RIGHT - 5 * mm, y, val)
        y -= 5.5 * mm

    y -= 10 * mm

    # --- Status & Footer ---
    c.setFont("Helvetica", 7.5)
    c.setFillColor(colors.Color(0.5, 0.5, 0.5))
    c.drawString(LEFT, y, f"Status: {payroll_record.status.upper()}")
    y -= 5 * mm

    c.setFont("Helvetica", 7)
    c.drawString(LEFT, y, "This is a computer-generated salary slip.")
    c.drawRightString(RIGHT, y, f"Generated: {__import__('datetime').date.today().isoformat()}")

    c.save()

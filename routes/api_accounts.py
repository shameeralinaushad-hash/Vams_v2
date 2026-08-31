from datetime import datetime
import os
import re
from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from werkzeug.utils import secure_filename
from models import db, Expense, ExpenseCategory, Budget

api_accounts_bp = Blueprint("api_accounts", __name__)


def _get_company_id():
    claims = get_jwt()
    return claims.get("company_id")


def _get_user_id():
    return int(get_jwt_identity())


@api_accounts_bp.route("/api/v1/accounts/expenses", methods=["GET"])
@jwt_required()
def list_expenses():
    company_id = _get_company_id()
    user_id = _get_user_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    scope = request.args.get("scope", "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)
    per_page = min(per_page, 100)

    query = Expense.query
    if scope == "company":
        query = query.filter_by(company_id=company_id)
    elif scope == "personal":
        query = query.filter_by(created_by=user_id, scope="personal")
    else:
        query = query.filter(
            (Expense.company_id == company_id) | (Expense.created_by == user_id)
        )

    pagination = query.order_by(Expense.expense_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    result = []
    for e in pagination.items:
        result.append({
            "id": e.id,
            "scope": e.scope,
            "category": e.category,
            "category_id": e.category_id,
            "amount": e.amount,
            "expense_date": e.expense_date.isoformat() if e.expense_date else None,
            "notes": e.notes,
            "payee": e.payee,
            "payment_method": e.payment_method,
            "receipt_filename": e.receipt_filename,
            "created_by": e.created_by,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        })

    return jsonify({
        "success": True,
        "expenses": result,
        "total": pagination.total,
        "pages": pagination.pages,
        "current_page": pagination.page,
    })


@api_accounts_bp.route("/api/v1/accounts/expenses", methods=["POST"])
@jwt_required()
def create_expense():
    company_id = _get_company_id()
    user_id = _get_user_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "invalid_json", "message": "Request body must be valid JSON."}), 400

    amount = data.get("amount")
    expense_date = data.get("expense_date")
    scope = data.get("scope", "company")

    if amount is None:
        return jsonify({"success": False, "error": "validation", "message": "amount is required."}), 400
    if not expense_date:
        return jsonify({"success": False, "error": "validation", "message": "expense_date is required."}), 400

    try:
        parsed_date = datetime.strptime(expense_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "validation", "message": "expense_date must be YYYY-MM-DD."}), 400

    expense = Expense(
        company_id=company_id if scope == "company" else None,
        scope=scope,
        category_id=data.get("category_id"),
        category=data.get("category"),
        amount=float(amount),
        expense_date=parsed_date,
        notes=data.get("notes"),
        payee=data.get("payee"),
        payment_method=data.get("payment_method"),
        receipt_filename=data.get("receipt_filename"),
        created_by=user_id,
        updated_by=user_id,
    )
    db.session.add(expense)
    db.session.commit()

    return jsonify({
        "success": True,
        "expense": {
            "id": expense.id,
            "scope": expense.scope,
            "category_id": expense.category_id,
            "amount": expense.amount,
            "expense_date": expense.expense_date.isoformat(),
            "notes": expense.notes,
            "payee": expense.payee,
            "payment_method": expense.payment_method,
        },
    }), 201


@api_accounts_bp.route("/api/v1/accounts/categories", methods=["GET"])
@jwt_required()
def list_categories():
    categories = ExpenseCategory.query.filter_by(is_active=True).order_by(ExpenseCategory.name.asc()).all()

    result = []
    for c in categories:
        result.append({
            "id": c.id,
            "name": c.name,
            "scope": c.scope,
        })

    return jsonify({"success": True, "categories": result})


@api_accounts_bp.route("/api/v1/accounts/categories", methods=["POST"])
@jwt_required()
def create_category():
    data = request.get_json(silent=True)
    if not data or not data.get("name", "").strip():
        return jsonify({"success": False, "error": "validation_error", "message": "Category name is required."}), 400

    name = data["name"].strip()
    scope = data.get("scope", "general")

    existing = ExpenseCategory.query.filter_by(name=name, scope=scope).first()
    if existing:
        return jsonify({"success": False, "error": "validation_error", "message": "Category already exists."}), 400

    category = ExpenseCategory(name=name, scope=scope, is_active=True)
    db.session.add(category)
    db.session.commit()

    return jsonify({
        "success": True,
        "category": {"id": category.id, "name": category.name, "scope": category.scope},
    }), 201


@api_accounts_bp.route("/api/v1/accounts/categories/<int:cat_id>/toggle", methods=["POST"])
@jwt_required()
def toggle_category(cat_id):
    category = db.session.get(ExpenseCategory, cat_id)
    if not category:
        return jsonify({"success": False, "error": "not_found", "message": "Category not found."}), 404

    category.is_active = not category.is_active
    db.session.commit()

    return jsonify({
        "success": True,
        "category": {"id": category.id, "name": category.name, "scope": category.scope, "is_active": category.is_active},
    })


@api_accounts_bp.route("/api/v1/accounts/budgets", methods=["GET"])
@jwt_required()
def list_budgets():
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    scope = request.args.get("scope", "").strip()

    query = Budget.query.filter(
        (Budget.company_id == company_id) | (Budget.scope == "personal")
    )
    if scope:
        query = query.filter_by(scope=scope)

    budgets = query.order_by(Budget.year.desc(), Budget.month.desc()).all()
    result = []
    for b in budgets:
        result.append({
            "id": b.id,
            "scope": b.scope,
            "category_id": b.category_id,
            "category_name": b.category.name if b.category else None,
            "month": b.month,
            "year": b.year,
            "period_type": b.period_type,
            "amount": b.amount,
            "recurring": b.recurring,
            "created_at": b.created_at.isoformat() if b.created_at else None,
        })

    return jsonify({"success": True, "budgets": result})


@api_accounts_bp.route("/api/v1/accounts/budgets", methods=["POST"])
@jwt_required()
def create_budget():
    company_id = _get_company_id()
    user_id = _get_user_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "invalid_json", "message": "Request body must be valid JSON."}), 400

    scope = data.get("scope", "company")
    month = data.get("month")
    year = data.get("year")
    amount = data.get("amount")

    if not all([month, year, amount]):
        return jsonify({"success": False, "error": "validation", "message": "month, year, and amount are required."}), 400

    budget = Budget(
        scope=scope,
        company_id=company_id if scope == "company" else None,
        category_id=data.get("category_id"),
        month=int(month),
        year=int(year),
        period_type="monthly",
        amount=float(amount),
        recurring=data.get("recurring", False),
        created_by=user_id,
    )
    db.session.add(budget)
    db.session.commit()

    return jsonify({
        "success": True,
        "budget": {
            "id": budget.id,
            "scope": budget.scope,
            "category_id": budget.category_id,
            "month": budget.month,
            "year": budget.year,
            "amount": budget.amount,
            "recurring": budget.recurring,
        },
    }), 201


@api_accounts_bp.route("/api/v1/accounts/receipt-ocr", methods=["POST"])
@jwt_required()
def receipt_ocr():
    if "file" not in request.files:
        return jsonify({"success": False, "error": "validation_error", "message": "No file uploaded."}), 400

    file = request.files["file"]
    allowed = ("png", "jpg", "jpeg", "gif", "webp", "bmp", "pdf")
    if not any(file.filename.lower().endswith(ext) for ext in allowed):
        return jsonify({"success": False, "error": "validation_error", "message": "Accepted formats: PNG, JPG, GIF, WebP, BMP, PDF."}), 400

    try:
        image_exts = {"png", "jpg", "jpeg", "gif", "webp", "bmp"}
        ext = file.filename.lower().rsplit(".", 1)[-1] if "." in file.filename else ""
        fname = secure_filename(file.filename or "receipt.jpg")
        save_path = os.path.join(current_app.root_path, "static", "uploads", f"ocr_{fname}")
        file.save(save_path)

        raw_text = ""
        if ext in image_exts:
            raw_text = _ocr_image_text(save_path)
        elif ext == "pdf":
            raw_text = _ocr_pdf_text(save_path)

        os.remove(save_path)

        if not raw_text.strip():
            return jsonify({"success": False, "error": "ocr_failed", "message": "No text could be extracted from the receipt."}), 422

        result = _parse_receipt_text(raw_text)
        result["raw_text"] = raw_text

        return jsonify({"success": True, "result": result})

    except Exception as e:
        return jsonify({"success": False, "error": "ocr_failed", "message": f"OCR failed: {str(e)}"}), 500


def _ocr_image_text(path):
    try:
        from PIL import Image
        import pytesseract
        img = Image.open(path)
        img = img.convert("L")
        win_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        if os.path.exists(win_path):
            pytesseract.pytesseract.tesseract_cmd = win_path
        return pytesseract.image_to_string(img)
    except Exception as e:
        raise RuntimeError(f"Tesseract OCR failed: {e}")


def _ocr_pdf_text(path):
    text_parts = []
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text_parts.append(t)
    except Exception:
        pass
    if text_parts and any(len(p.strip()) > 50 for p in text_parts):
        return "\n".join(text_parts)
    try:
        import fitz
        from PIL import Image
        import pytesseract
        doc = fitz.open(path)
        for page in doc:
            pix = page.get_pixmap(dpi=300)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            img = img.convert("L")
            win_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            if os.path.exists(win_path):
                pytesseract.pytesseract.tesseract_cmd = win_path
            t = pytesseract.image_to_string(img)
            if t.strip():
                text_parts.append(t)
        doc.close()
    except Exception as e:
        raise RuntimeError(f"Scanned PDF OCR failed: {e}")
    return "\n".join(text_parts)


_RECEIPT_TOTAL_RE = re.compile(
    r"(?:total|grand total|amount due|balance due|net|tender|sum)\s*:?\s*(?:rs|pk|usd|inr|)\s*:?\s*([0-9,]+\.\d{2})",
    re.IGNORECASE
)
_RECEIPT_DATE_RE = re.compile(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})")
_RECEIPT_ITEM_RE = re.compile(
    r"^(.+?)\s+(\d+(?:\.\d+)?)\s*(?:x\s*)?([0-9,]+\.?\d*)\s*(?:@\s*)?([0-9,]+\.\d{2})?\s*$"
)
_RECEIPT_ITEM_SIMPLE_RE = re.compile(r"^(.+?)\s+([0-9,]+\.\d{2})\s*$")


def _parse_receipt_text(text):
    lines = text.split("\n")
    clean = [l.strip() for l in lines if l.strip()]

    result = {"vendor": "", "date": "", "total": 0.0, "items": []}

    date_matches = []
    total_matches = []
    item_candidates = []

    for line in clean:
        m = _RECEIPT_TOTAL_RE.search(line)
        if m:
            try:
                total_matches.append(float(m.group(1).replace(",", "")))
            except ValueError:
                pass
            continue

        m = _RECEIPT_DATE_RE.search(line)
        if m:
            date_matches.append(m.group(1))
            continue

        m = _RECEIPT_ITEM_RE.match(line)
        if m:
            desc = m.group(1).strip()
            qty = float(m.group(2))
            price = float(m.group(3).replace(",", ""))
            item_candidates.append({"item": desc, "qty": qty, "unit_price": round(price / qty, 2) if qty else 0, "total": price})
            continue

        m = _RECEIPT_ITEM_SIMPLE_RE.match(line)
        if m:
            desc = m.group(1).strip()
            amt = float(m.group(2).replace(",", ""))
            if not any(kw in desc.lower() for kw in ("total", "subtotal", "tax", "change", "cash", "due", "balance")):
                item_candidates.append({"item": desc, "qty": 1, "unit_price": amt, "total": amt})
            continue

    if date_matches:
        result["date"] = date_matches[0]
    if total_matches:
        result["total"] = max(total_matches)

    result["items"] = item_candidates
    return result

@api_accounts_bp.route("/api/v1/accounts/expenses/export", methods=["GET"])
@jwt_required()
def export_expenses_csv():
    """Export expenses as CSV."""
    import io
    import csv
    from flask import Response

    company_id = _get_company_id()
    user_id = _get_user_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    scope = request.args.get("scope", "").strip()

    query = Expense.query
    if scope == "company":
        query = query.filter_by(company_id=company_id)
    elif scope == "personal":
        query = query.filter_by(created_by=user_id, scope="personal")
    else:
        query = query.filter(
            (Expense.company_id == company_id) | (Expense.created_by == user_id)
        )

    expenses = query.order_by(Expense.expense_date.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Scope", "Category", "Amount", "Payee", "Payment Method", "Notes"])

    for e in expenses:
        writer.writerow([
            e.expense_date.isoformat() if e.expense_date else "",
            e.scope or "",
            e.category or "",
            f"{e.amount:.2f}",
            e.payee or "",
            e.payment_method or "",
            e.notes or "",
        ])

    csv_content = output.getvalue()
    output.close()

    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=expenses.csv"},
    )

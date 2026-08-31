from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from models import db, Employee, AttendanceRecord, PayrollRecord, Holiday

api_hr_bp = Blueprint("api_hr", __name__)


def _get_company_id():
    claims = get_jwt()
    return claims.get("company_id")


def _get_user_id():
    return int(get_jwt_identity())


def _get_employee_for_user(user_id, company_id):
    emp = db.session.query(Employee).filter_by(user_id=user_id, company_id=company_id).first()
    return emp


@api_hr_bp.route("/api/v1/hr/employees", methods=["GET"])
@jwt_required()
def list_employees():
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    employees = Employee.query.filter_by(company_id=company_id, is_active=True).all()
    result = []
    for e in employees:
        result.append({
            "id": e.id,
            "name": e.name,
            "email": e.email,
            "phone": e.phone,
            "department": e.department,
            "designation": e.designation,
            "employee_code": e.employee_code,
            "base_monthly_salary": e.base_monthly_salary,
            "monthly_leave_accrual": e.monthly_leave_accrual,
            "date_joined": e.date_joined.isoformat() if e.date_joined else None,
            "is_active": e.is_active,
        })

    return jsonify({"success": True, "employees": result})


@api_hr_bp.route("/api/v1/hr/employees/<int:emp_id>", methods=["GET"])
@jwt_required()
def get_employee(emp_id):
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    employee = db.session.get(Employee, emp_id)
    if not employee or employee.company_id != company_id:
        return jsonify({"success": False, "error": "not_found", "message": "Employee not found."}), 404

    return jsonify({
        "success": True,
        "employee": {
            "id": employee.id,
            "name": employee.name,
            "email": employee.email,
            "phone": employee.phone,
            "department": employee.department,
            "designation": employee.designation,
            "employee_code": employee.employee_code,
            "base_monthly_salary": employee.base_monthly_salary,
            "monthly_leave_accrual": employee.monthly_leave_accrual,
            "date_joined": employee.date_joined.isoformat() if employee.date_joined else None,
            "date_left": employee.date_left.isoformat() if employee.date_left else None,
            "is_active": employee.is_active,
        },
    })


@api_hr_bp.route("/api/v1/hr/attendance/scan", methods=["POST"])
@jwt_required()
def scan_attendance():
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    user_id = _get_user_id()
    employee = _get_employee_for_user(user_id, company_id)
    if not employee:
        return jsonify({"success": False, "error": "not_found", "message": "No employee linked to your account."}), 404

    today = date.today()
    existing = AttendanceRecord.query.filter_by(employee_id=employee.id, date=today).first()
    if existing:
        return jsonify({"success": True, "already_marked": True, "status": existing.status})

    record = AttendanceRecord(
        employee_id=employee.id,
        date=today,
        status="present",
        marked_by=user_id,
    )
    db.session.add(record)
    db.session.commit()

    return jsonify({"success": True, "already_marked": False, "status": "present"})


@api_hr_bp.route("/api/v1/hr/attendance/today", methods=["GET"])
@jwt_required()
def get_today_attendance():
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    user_id = _get_user_id()
    employee = _get_employee_for_user(user_id, company_id)
    if not employee:
        return jsonify({"success": False, "error": "not_found", "message": "No employee linked to your account."}), 404

    today = date.today()
    record = AttendanceRecord.query.filter_by(employee_id=employee.id, date=today).first()
    if not record:
        return jsonify({"success": True, "marked": False, "status": None})

    return jsonify({"success": True, "marked": True, "status": record.status})


@api_hr_bp.route("/api/v1/hr/payroll", methods=["GET"])
@jwt_required()
def list_payroll():
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    month = request.args.get("month", type=int)
    year = request.args.get("year", type=int)

    employee_ids = [e.id for e in Employee.query.filter_by(company_id=company_id).all()]
    if not employee_ids:
        return jsonify({"success": True, "payroll": []})

    query = PayrollRecord.query.filter(PayrollRecord.employee_id.in_(employee_ids))
    if month:
        query = query.filter(PayrollRecord.month == month)
    if year:
        query = query.filter(PayrollRecord.year == year)

    records = query.order_by(PayrollRecord.year.desc(), PayrollRecord.month.desc()).all()
    result = []
    for r in records:
        result.append({
            "id": r.id,
            "employee_id": r.employee_id,
            "employee_name": r.employee.name if r.employee else None,
            "month": r.month,
            "year": r.year,
            "base_salary": r.base_salary,
            "days_present": r.days_present,
            "half_days": r.half_days,
            "paid_leaves_used": r.paid_leaves_used,
            "working_days_in_month": r.working_days_in_month,
            "calculated_salary": r.calculated_salary,
            "adjustment_amount": r.adjustment_amount,
            "adjustment_note": r.adjustment_note,
            "final_salary": r.final_salary,
            "status": r.status,
            "generated_at": r.generated_at.isoformat() if r.generated_at else None,
        })

    return jsonify({"success": True, "payroll": result})


@api_hr_bp.route("/api/v1/hr/holidays", methods=["GET"])
@jwt_required()
def list_holidays():
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    holidays = Holiday.query.filter(
        (Holiday.company_id == company_id) | (Holiday.company_id.is_(None))
    ).order_by(Holiday.date.asc()).all()

    result = []
    for h in holidays:
        result.append({
            "id": h.id,
            "date": h.date.isoformat(),
            "name": h.name,
            "is_recurring": h.is_recurring,
        })

    return jsonify({"success": True, "holidays": result})


@api_hr_bp.route("/api/v1/hr/employees", methods=["POST"])
@jwt_required()
def create_employee():
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"success": False, "error": "forbidden", "message": "Admin access required."}), 403

    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "validation_error", "message": "Request body must be JSON."}), 400

    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"success": False, "error": "validation_error", "message": "Employee name is required."}), 400

    employee = Employee(
        company_id=company_id,
        name=name,
        email=(data.get("email") or "").strip() or None,
        phone=(data.get("phone") or "").strip() or None,
        department=(data.get("department") or "").strip() or None,
        designation=(data.get("designation") or "").strip() or None,
        employee_code=(data.get("employee_code") or "").strip() or None,
        base_monthly_salary=float(data.get("base_monthly_salary", 0) or 0),
        monthly_leave_accrual=float(data.get("monthly_leave_accrual", 0) or 0),
        is_active=True,
    )
    db.session.add(employee)
    db.session.commit()

    return jsonify({
        "success": True,
        "employee": {
            "id": employee.id,
            "name": employee.name,
            "email": employee.email,
            "phone": employee.phone,
            "department": employee.department,
            "designation": employee.designation,
            "employee_code": employee.employee_code,
            "base_monthly_salary": employee.base_monthly_salary,
        },
    }), 201


@api_hr_bp.route("/api/v1/hr/employees/<int:emp_id>", methods=["PUT"])
@jwt_required()
def edit_employee(emp_id):
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"success": False, "error": "forbidden", "message": "Admin access required."}), 403

    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    employee = db.session.get(Employee, emp_id)
    if not employee or employee.company_id != company_id:
        return jsonify({"success": False, "error": "not_found", "message": "Employee not found."}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "validation_error", "message": "Request body must be JSON."}), 400

    if "name" in data:
        employee.name = data["name"].strip() if data["name"] else employee.name
    if "email" in data:
        employee.email = data["email"].strip() or None
    if "phone" in data:
        employee.phone = data["phone"].strip() or None
    if "department" in data:
        employee.department = data["department"].strip() or None
    if "designation" in data:
        employee.designation = data["designation"].strip() or None
    if "employee_code" in data:
        employee.employee_code = data["employee_code"].strip() or None
    if "base_monthly_salary" in data:
        employee.base_monthly_salary = float(data["base_monthly_salary"] or 0)
    if "monthly_leave_accrual" in data:
        employee.monthly_leave_accrual = float(data["monthly_leave_accrual"] or 0)
    if "is_active" in data:
        employee.is_active = bool(data["is_active"])

    db.session.commit()

    return jsonify({
        "success": True,
        "employee": {
            "id": employee.id,
            "name": employee.name,
            "email": employee.email,
            "phone": employee.phone,
            "department": employee.department,
            "designation": employee.designation,
            "employee_code": employee.employee_code,
            "base_monthly_salary": employee.base_monthly_salary,
            "is_active": employee.is_active,
        },
    })

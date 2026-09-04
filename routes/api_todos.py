from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from models import db, Todo

api_todos_bp = Blueprint("api_todos", __name__)


def _get_company_id():
    claims = get_jwt()
    return claims.get("company_id")


def _get_user_id():
    return int(get_jwt_identity())


def _serialize_todo(todo):
    return {
        "id": todo.id,
        "title": todo.text,
        "is_done": todo.is_done,
        "priority": todo.priority,
        "due_date": todo.due_date.isoformat() if todo.due_date else None,
        "assignee_id": todo.assignee_id,
        "created_at": todo.created_at.isoformat() if todo.created_at else None,
    }


@api_todos_bp.route("/api/v1/todos", methods=["GET"])
@jwt_required()
def list_todos():
    company_id = _get_company_id()
    user_id = _get_user_id()
    show_all = request.args.get("all", "false").lower() == "true"

    if show_all:
        query = Todo.query.filter_by(company_id=company_id)
    else:
        query = Todo.query.filter(
            Todo.company_id == company_id,
            (Todo.assignee_id == user_id) | (Todo.assignee_id.is_(None))
        )

    todos = query.order_by(Todo.created_at.desc()).all()
    return jsonify({"success": True, "todos": [_serialize_todo(t) for t in todos]})


@api_todos_bp.route("/api/v1/todos", methods=["POST"])
@jwt_required()
def create_todo():
    company_id = _get_company_id()
    user_id = _get_user_id()
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "validation_error", "message": "Request body must be JSON."}), 400

    text = (data.get("title") or data.get("text") or "").strip()
    if not text:
        return jsonify({"success": False, "error": "validation_error", "message": "Title is required."}), 400

    due_date = None
    if data.get("due_date"):
        try:
            due_date = datetime.strptime(data["due_date"], "%Y-%m-%d").date()
        except ValueError:
            pass

    todo = Todo(
        company_id=company_id,
        text=text,
        priority=data.get("priority", "medium"),
        due_date=due_date,
        assignee_id=data.get("assignee_id", user_id),
    )
    db.session.add(todo)
    db.session.commit()

    return jsonify({"success": True, "todo": _serialize_todo(todo)}), 201


@api_todos_bp.route("/api/v1/todos/<int:todo_id>", methods=["PUT"])
@jwt_required()
def edit_todo(todo_id):
    company_id = _get_company_id()
    todo = db.session.get(Todo, todo_id)
    if not todo or todo.company_id != company_id:
        return jsonify({"success": False, "error": "not_found", "message": "Todo not found."}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "validation_error", "message": "Request body must be JSON."}), 400

    if "title" in data or "text" in data:
        text = (data.get("title") or data.get("text") or "").strip()
        if text:
            todo.text = text
    if "priority" in data:
        todo.priority = data["priority"]
    if "due_date" in data:
        if data["due_date"]:
            try:
                todo.due_date = datetime.strptime(data["due_date"], "%Y-%m-%d").date()
            except ValueError:
                pass
        else:
            todo.due_date = None

    db.session.commit()
    return jsonify({"success": True, "todo": _serialize_todo(todo)})


@api_todos_bp.route("/api/v1/todos/<int:todo_id>", methods=["DELETE"])
@jwt_required()
def delete_todo(todo_id):
    company_id = _get_company_id()
    todo = db.session.get(Todo, todo_id)
    if not todo or todo.company_id != company_id:
        return jsonify({"success": False, "error": "not_found", "message": "Todo not found."}), 404

    db.session.delete(todo)
    db.session.commit()
    return jsonify({"success": True, "message": "Todo deleted."})


@api_todos_bp.route("/api/v1/todos/<int:todo_id>/toggle", methods=["POST"])
@jwt_required()
def toggle_todo(todo_id):
    company_id = _get_company_id()
    todo = db.session.get(Todo, todo_id)
    if not todo or todo.company_id != company_id:
        return jsonify({"success": False, "error": "not_found", "message": "Todo not found."}), 404

    todo.is_done = not todo.is_done
    db.session.commit()
    return jsonify({"success": True, "todo": _serialize_todo(todo)})

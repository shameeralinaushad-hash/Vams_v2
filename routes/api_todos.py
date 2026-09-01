from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import db, Todo

api_todos_bp = Blueprint("api_todos", __name__)


def _get_user_id():
    return int(get_jwt_identity())


def _serialize_todo(todo):
    return {
        "id": todo.id,
        "title": todo.title,
        "description": todo.description,
        "status": todo.status,
        "priority": todo.priority,
        "due_date": todo.due_date.isoformat() if todo.due_date else None,
        "created_at": todo.created_at.isoformat() if todo.created_at else None,
        "completed_at": todo.completed_at.isoformat() if todo.completed_at else None,
    }


@api_todos_bp.route("/api/v1/todos", methods=["GET"])
@jwt_required()
def list_todos():
    user_id = _get_user_id()
    status = request.args.get("status")

    query = Todo.query.filter_by(user_id=user_id)
    if status:
        query = query.filter_by(status=status)

    todos = query.order_by(Todo.created_at.desc()).all()
    return jsonify({"success": True, "todos": [_serialize_todo(t) for t in todos]})


@api_todos_bp.route("/api/v1/todos", methods=["POST"])
@jwt_required()
def create_todo():
    user_id = _get_user_id()
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "validation_error", "message": "Request body must be JSON."}), 400

    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"success": False, "error": "validation_error", "message": "Title is required."}), 400

    due_date = None
    if data.get("due_date"):
        try:
            due_date = datetime.strptime(data["due_date"], "%Y-%m-%d").date()
        except ValueError:
            pass

    todo = Todo(
        user_id=user_id,
        title=title,
        description=data.get("description", ""),
        priority=data.get("priority", "medium"),
        due_date=due_date,
    )
    db.session.add(todo)
    db.session.commit()

    return jsonify({"success": True, "todo": _serialize_todo(todo)}), 201


@api_todos_bp.route("/api/v1/todos/<int:todo_id>", methods=["PUT"])
@jwt_required()
def edit_todo(todo_id):
    user_id = _get_user_id()
    todo = db.session.get(Todo, todo_id)
    if not todo or todo.user_id != user_id:
        return jsonify({"success": False, "error": "not_found", "message": "Todo not found."}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "validation_error", "message": "Request body must be JSON."}), 400

    if "title" in data:
        todo.title = data["title"].strip() if data["title"] else todo.title
    if "description" in data:
        todo.description = data["description"]
    if "status" in data:
        todo.status = data["status"]
        if data["status"] == "done" and not todo.completed_at:
            todo.completed_at = datetime.utcnow()
        elif data["status"] != "done":
            todo.completed_at = None
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
    user_id = _get_user_id()
    todo = db.session.get(Todo, todo_id)
    if not todo or todo.user_id != user_id:
        return jsonify({"success": False, "error": "not_found", "message": "Todo not found."}), 404

    db.session.delete(todo)
    db.session.commit()
    return jsonify({"success": True, "message": "Todo deleted."})


@api_todos_bp.route("/api/v1/todos/<int:todo_id>/toggle", methods=["POST"])
@jwt_required()
def toggle_todo(todo_id):
    user_id = _get_user_id()
    todo = db.session.get(Todo, todo_id)
    if not todo or todo.user_id != user_id:
        return jsonify({"success": False, "error": "not_found", "message": "Todo not found."}), 404

    if todo.status == "done":
        todo.status = "pending"
        todo.completed_at = None
    else:
        todo.status = "done"
        todo.completed_at = datetime.utcnow()

    db.session.commit()
    return jsonify({"success": True, "todo": _serialize_todo(todo)})

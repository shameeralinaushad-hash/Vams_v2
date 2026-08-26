from datetime import datetime
from flask import Blueprint, request, redirect, url_for, session
from flask_login import login_required
from models import db, Todo

todos_bp = Blueprint("todos", __name__, url_prefix="/todos")


@todos_bp.route("/add", methods=["POST"])
@login_required
def add_todo():
    company_id = session.get("active_company_id")
    text = request.form.get("text", "").strip()
    priority = request.form.get("priority", "medium")
    due_date_str = request.form.get("due_date", "")
    assignee_id = request.form.get("assignee_id")

    due_date_val = datetime.strptime(due_date_str, "%Y-%m-%d").date() if due_date_str else None

    if company_id and text:
        new_todo = Todo(
            company_id=company_id,
            text=text,
            priority=priority,
            due_date=due_date_val,
            assignee_id=int(assignee_id) if assignee_id else None
        )
        db.session.add(new_todo)
        db.session.commit()
    return redirect(url_for("home"))


@todos_bp.route("/toggle/<int:todo_id>", methods=["POST"])
@login_required
def toggle_todo(todo_id):
    todo = Todo.query.get_or_404(todo_id)
    todo.is_done = not todo.is_done
    db.session.commit()
    return {"ok": True, "is_done": todo.is_done}


@todos_bp.route("/delete/<int:todo_id>", methods=["POST"])
@login_required
def delete_todo(todo_id):
    todo = Todo.query.get_or_404(todo_id)
    db.session.delete(todo)
    db.session.commit()
    return {"ok": True}
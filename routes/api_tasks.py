from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from models import db, TeamTask, TeamTaskSubItem, TeamTaskComment, PersonalItem, Employee

api_tasks_bp = Blueprint("api_tasks", __name__)


def _get_user_id():
    return int(get_jwt_identity())


def _get_company_id():
    claims = get_jwt()
    return claims.get("company_id")


def _serialize_team_task(task):
    assignee = task.assignee
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "acknowledged_at": task.acknowledged_at.isoformat() if task.acknowledged_at else None,
        "archived_at": task.archived_at.isoformat() if task.archived_at else None,
        "assignee": {
            "id": assignee.id,
            "name": assignee.name,
        } if assignee else None,
        "assigned_by": task.assigned_by,
        "order_id": task.order_id,
        "project_id": task.project_id,
    }


@api_tasks_bp.route("/api/v1/tasks/team", methods=["GET"])
@jwt_required()
def list_team_tasks():
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    status = request.args.get("status")
    assignee_id = request.args.get("assignee_id", type=int)

    query = (
        db.session.query(TeamTask)
        .join(Employee, TeamTask.assignee_id == Employee.id)
        .filter(Employee.company_id == company_id, TeamTask.archived_at.is_(None))
    )

    if status:
        query = query.filter(TeamTask.status == status)
    if assignee_id:
        query = query.filter(TeamTask.assignee_id == assignee_id)

    tasks = query.order_by(TeamTask.created_at.desc()).all()
    return jsonify({"success": True, "tasks": [_serialize_team_task(t) for t in tasks]})


@api_tasks_bp.route("/api/v1/tasks/team/<int:tid>", methods=["GET"])
@jwt_required()
def get_team_task(tid):
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    task = db.session.get(TeamTask, tid)
    if not task:
        return jsonify({"success": False, "error": "not_found", "message": "Task not found."}), 404

    assignee = task.assignee
    if not assignee or assignee.company_id != company_id:
        return jsonify({"success": False, "error": "not_found", "message": "Task not found."}), 404

    sub_items = [
        {"id": s.id, "title": s.title, "is_done": s.is_done, "order": s.order}
        for s in sorted(task.sub_items, key=lambda x: x.order)
    ]

    comments = []
    for c in task.comments:
        comments.append({
            "id": c.id,
            "body": c.body,
            "author_id": c.author_id,
            "parent_id": c.parent_id,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        })

    data = _serialize_team_task(task)
    data["sub_items"] = sub_items
    data["comments"] = comments
    return jsonify({"success": True, "task": data})


@api_tasks_bp.route("/api/v1/tasks/team", methods=["POST"])
@jwt_required()
def create_team_task():
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    user_id = _get_user_id()
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "invalid_request", "message": "Request body must be JSON."}), 400

    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"success": False, "error": "validation_error", "message": "Title is required."}), 400

    assignee_id = data.get("assignee_id")
    if not assignee_id:
        return jsonify({"success": False, "error": "validation_error", "message": "Assignee is required."}), 400

    employee = db.session.get(Employee, int(assignee_id))
    if not employee or employee.company_id != company_id:
        return jsonify({"success": False, "error": "validation_error", "message": "Invalid assignee."}), 400

    due_date = None
    if data.get("due_date"):
        try:
            due_date = datetime.strptime(data["due_date"], "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"success": False, "error": "validation_error", "message": "Invalid due_date format."}), 400

    task = TeamTask(
        title=title,
        description=data.get("description", ""),
        assignee_id=int(assignee_id),
        assigned_by=user_id,
        priority=data.get("priority", "medium"),
        status="to_do",
        due_date=due_date,
        order_id=data.get("order_id"),
        project_id=data.get("project_id"),
    )
    db.session.add(task)
    db.session.commit()

    return jsonify({"success": True, "task": _serialize_team_task(task)}), 201


@api_tasks_bp.route("/api/v1/tasks/team/<int:tid>", methods=["PUT"])
@jwt_required()
def update_team_task(tid):
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    task = db.session.get(TeamTask, tid)
    if not task:
        return jsonify({"success": False, "error": "not_found", "message": "Task not found."}), 404

    assignee = task.assignee
    if not assignee or assignee.company_id != company_id:
        return jsonify({"success": False, "error": "not_found", "message": "Task not found."}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "invalid_request", "message": "Request body must be JSON."}), 400

    if "status" in data:
        new_status = data["status"]
        valid_statuses = ["to_do", "in_progress", "done", "archived"]
        if new_status not in valid_statuses:
            return jsonify({"success": False, "error": "validation_error", "message": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"}), 400
        task.status = new_status
        if new_status == "done" and not task.completed_at:
            task.completed_at = datetime.utcnow()
        elif new_status != "done":
            task.completed_at = None

    if "priority" in data:
        task.priority = data["priority"]

    if "due_date" in data:
        if data["due_date"]:
            try:
                task.due_date = datetime.strptime(data["due_date"], "%Y-%m-%d").date()
            except ValueError:
                return jsonify({"success": False, "error": "validation_error", "message": "Invalid due_date format."}), 400
        else:
            task.due_date = None

    db.session.commit()
    return jsonify({"success": True, "task": _serialize_team_task(task)})


@api_tasks_bp.route("/api/v1/tasks/team/<int:tid>/acknowledge", methods=["POST"])
@jwt_required()
def acknowledge_team_task(tid):
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    task = db.session.get(TeamTask, tid)
    if not task:
        return jsonify({"success": False, "error": "not_found", "message": "Task not found."}), 404

    assignee = task.assignee
    if not assignee or assignee.company_id != company_id:
        return jsonify({"success": False, "error": "not_found", "message": "Task not found."}), 404

    task.acknowledged_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"success": True})


@api_tasks_bp.route("/api/v1/tasks/team/<int:tid>/subtask", methods=["POST"])
@jwt_required()
def add_subtask(tid):
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    task = db.session.get(TeamTask, tid)
    if not task:
        return jsonify({"success": False, "error": "not_found", "message": "Task not found."}), 404

    assignee = task.assignee
    if not assignee or assignee.company_id != company_id:
        return jsonify({"success": False, "error": "not_found", "message": "Task not found."}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "invalid_request", "message": "Request body must be JSON."}), 400

    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"success": False, "error": "validation_error", "message": "Title is required."}), 400

    max_order = max((s.order for s in task.sub_items), default=-1)
    sub = TeamTaskSubItem(team_task_id=task.id, title=title, order=max_order + 1)
    db.session.add(sub)
    db.session.commit()

    return jsonify({"success": True, "subtask": {"id": sub.id, "title": sub.title, "is_done": sub.is_done, "order": sub.order}}), 201


@api_tasks_bp.route("/api/v1/tasks/team/<int:tid>/comments", methods=["POST"])
@jwt_required()
def add_comment(tid):
    company_id = _get_company_id()
    if not company_id:
        return jsonify({"success": False, "error": "no_company", "message": "No active company."}), 400

    user_id = _get_user_id()
    task = db.session.get(TeamTask, tid)
    if not task:
        return jsonify({"success": False, "error": "not_found", "message": "Task not found."}), 404

    assignee = task.assignee
    if not assignee or assignee.company_id != company_id:
        return jsonify({"success": False, "error": "not_found", "message": "Task not found."}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "invalid_request", "message": "Request body must be JSON."}), 400

    body = (data.get("body") or "").strip()
    if not body:
        return jsonify({"success": False, "error": "validation_error", "message": "Comment body is required."}), 400

    comment = TeamTaskComment(
        team_task_id=task.id,
        author_id=user_id,
        body=body,
    )
    db.session.add(comment)
    db.session.commit()

    return jsonify({
        "success": True,
        "comment": {
            "id": comment.id,
            "body": comment.body,
            "author_id": comment.author_id,
            "created_at": comment.created_at.isoformat() if comment.created_at else None,
        },
    }), 201


@api_tasks_bp.route("/api/v1/tasks/subtask/<int:sid>/toggle", methods=["POST"])
@jwt_required()
def toggle_subtask(sid):
    sub = db.session.get(TeamTaskSubItem, sid)
    if not sub:
        return jsonify({"success": False, "error": "not_found", "message": "Subtask not found."}), 404

    sub.is_done = not sub.is_done
    db.session.commit()
    return jsonify({"success": True, "subtask": {"id": sub.id, "title": sub.title, "is_done": sub.is_done, "order": sub.order}})


@api_tasks_bp.route("/api/v1/tasks/personal", methods=["GET"])
@jwt_required()
def list_personal_items():
    user_id = _get_user_id()
    lane = request.args.get("lane")
    status = request.args.get("status")

    query = PersonalItem.query.filter_by(user_id=user_id)

    if lane:
        query = query.filter_by(lane=lane)
    if status:
        query = query.filter_by(status=status)

    items = query.order_by(PersonalItem.created_at.desc()).all()

    return jsonify({
        "success": True,
        "items": [
            {
                "id": i.id,
                "lane": i.lane,
                "title": i.title,
                "description": i.description,
                "status": i.status,
                "priority": i.priority,
                "due_date": i.due_date.isoformat() if i.due_date else None,
                "category": i.category,
                "estimated_minutes": i.estimated_minutes,
                "recurrence_rule": i.recurrence_rule,
                "created_at": i.created_at.isoformat() if i.created_at else None,
                "completed_at": i.completed_at.isoformat() if i.completed_at else None,
            }
            for i in items
        ],
    })


@api_tasks_bp.route("/api/v1/tasks/personal", methods=["POST"])
@jwt_required()
def create_personal_item():
    user_id = _get_user_id()
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "invalid_request", "message": "Request body must be JSON."}), 400

    title = (data.get("title") or "").strip()
    lane = (data.get("lane") or "").strip()
    if not title or not lane:
        return jsonify({"success": False, "error": "validation_error", "message": "Title and lane are required."}), 400

    valid_lanes = ["task", "goal", "future_plan"]
    if lane not in valid_lanes:
        return jsonify({"success": False, "error": "validation_error", "message": f"Invalid lane. Must be one of: {', '.join(valid_lanes)}"}), 400

    due_date = None
    if data.get("due_date"):
        try:
            due_date = datetime.strptime(data["due_date"], "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"success": False, "error": "validation_error", "message": "Invalid due_date format."}), 400

    item = PersonalItem(
        user_id=user_id,
        lane=lane,
        title=title,
        description=data.get("description", ""),
        priority=data.get("priority", "medium"),
        due_date=due_date,
        category=data.get("category"),
        estimated_minutes=data.get("estimated_minutes"),
        recurrence_rule=data.get("recurrence_rule"),
    )
    db.session.add(item)
    db.session.commit()

    return jsonify({
        "success": True,
        "item": {
            "id": item.id,
            "lane": item.lane,
            "title": item.title,
            "description": item.description,
            "status": item.status,
            "priority": item.priority,
            "due_date": item.due_date.isoformat() if item.due_date else None,
            "category": item.category,
            "estimated_minutes": item.estimated_minutes,
            "recurrence_rule": item.recurrence_rule,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "completed_at": item.completed_at.isoformat() if item.completed_at else None,
        },
    }), 201


@api_tasks_bp.route("/api/v1/tasks/personal/<int:pid>/toggle", methods=["POST"])
@jwt_required()
def toggle_personal_item(pid):
    user_id = _get_user_id()
    item = db.session.get(PersonalItem, pid)
    if not item or item.user_id != user_id:
        return jsonify({"success": False, "error": "not_found", "message": "Item not found."}), 404

    if item.status == "done":
        item.status = "not_started"
        item.completed_at = None
    else:
        item.status = "done"
        item.completed_at = datetime.utcnow()

    db.session.commit()
    return jsonify({
        "success": True,
        "item": {
            "id": item.id,
            "lane": item.lane,
            "title": item.title,
            "description": item.description,
            "status": item.status,
            "priority": item.priority,
            "due_date": item.due_date.isoformat() if item.due_date else None,
            "category": item.category,
            "estimated_minutes": item.estimated_minutes,
            "recurrence_rule": item.recurrence_rule,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "completed_at": item.completed_at.isoformat() if item.completed_at else None,
        },
    })


@api_tasks_bp.route("/api/v1/tasks/personal/<int:pid>", methods=["PUT"])
@jwt_required()
def update_personal_item(pid):
    user_id = _get_user_id()
    item = db.session.get(PersonalItem, pid)
    if not item or item.user_id != user_id:
        return jsonify({"success": False, "error": "not_found", "message": "Item not found."}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "invalid_request", "message": "Request body must be JSON."}), 400

    if "lane" in data:
        valid_lanes = ["task", "goal", "future_plan"]
        if data["lane"] not in valid_lanes:
            return jsonify({"success": False, "error": "validation_error", "message": f"Invalid lane. Must be one of: {', '.join(valid_lanes)}"}), 400
        item.lane = data["lane"]

    if "title" in data:
        item.title = data["title"]
    if "description" in data:
        item.description = data["description"]
    if "status" in data:
        item.status = data["status"]
    if "priority" in data:
        item.priority = data["priority"]
    if "category" in data:
        item.category = data["category"]
    if "estimated_minutes" in data:
        item.estimated_minutes = data["estimated_minutes"]
    if "recurrence_rule" in data:
        item.recurrence_rule = data["recurrence_rule"]

    if "due_date" in data:
        if data["due_date"]:
            try:
                item.due_date = datetime.strptime(data["due_date"], "%Y-%m-%d").date()
            except ValueError:
                return jsonify({"success": False, "error": "validation_error", "message": "Invalid due_date format."}), 400
        else:
            item.due_date = None

    db.session.commit()
    return jsonify({
        "success": True,
        "item": {
            "id": item.id,
            "lane": item.lane,
            "title": item.title,
            "description": item.description,
            "status": item.status,
            "priority": item.priority,
            "due_date": item.due_date.isoformat() if item.due_date else None,
            "category": item.category,
            "estimated_minutes": item.estimated_minutes,
            "recurrence_rule": item.recurrence_rule,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "completed_at": item.completed_at.isoformat() if item.completed_at else None,
        },
    })


@api_tasks_bp.route("/api/v1/tasks/personal/<int:pid>", methods=["DELETE"])
@jwt_required()
def delete_personal_item(pid):
    user_id = _get_user_id()
    item = db.session.get(PersonalItem, pid)
    if not item or item.user_id != user_id:
        return jsonify({"success": False, "error": "not_found", "message": "Item not found."}), 404

    db.session.delete(item)
    db.session.commit()
    return jsonify({"success": True})

from datetime import datetime, date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from models import db, Project, ProjectMember, TeamTask

api_projects_bp = Blueprint("api_projects", __name__)


def _get_company_id():
    claims = get_jwt()
    return claims.get("company_id")


def _get_user_id():
    return int(get_jwt_identity())


def _serialize_project(project):
    owner = project.owner
    task_counts = project.task_counts()
    return {
        "id": project.id,
        "title": project.title,
        "description": project.description,
        "status": project.status,
        "owner_id": project.owner_id,
        "owner_name": owner.name if owner else None,
        "start_date": project.start_date.isoformat() if project.start_date else None,
        "target_date": project.target_date.isoformat() if project.target_date else None,
        "completed_at": project.completed_at.isoformat() if project.completed_at else None,
        "color": project.color,
        "icon": project.icon,
        "progress_pct": project.progress_pct(),
        "task_counts": task_counts,
        "health": project.health(),
        "days_to_deadline": project.days_to_deadline(),
        "created_at": project.created_at.isoformat() if project.created_at else None,
    }


@api_projects_bp.route("/api/v1/projects", methods=["GET"])
@jwt_required()
def list_projects():
    user_id = _get_user_id()
    projects = Project.query.filter(
        Project.members.any(ProjectMember.user_id == user_id)
    ).order_by(Project.created_at.desc()).all()

    return jsonify({
        "success": True,
        "projects": [_serialize_project(p) for p in projects],
    })


@api_projects_bp.route("/api/v1/projects/<int:project_id>", methods=["GET"])
@jwt_required()
def get_project(project_id):
    project = db.session.get(Project, project_id)
    if not project:
        return jsonify({"success": False, "error": "not_found", "message": "Project not found."}), 404

    tasks = TeamTask.query.filter_by(project_id=project_id).order_by(TeamTask.created_at.desc()).all()
    task_list = []
    for t in tasks:
        assignee = t.assignee
        task_list.append({
            "id": t.id,
            "title": t.title,
            "status": t.status,
            "priority": t.priority,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "assignee": {"id": assignee.id, "name": assignee.name} if assignee else None,
        })

    data = _serialize_project(project)
    data["tasks"] = task_list
    return jsonify({"success": True, "project": data})


@api_projects_bp.route("/api/v1/projects", methods=["POST"])
@jwt_required()
def create_project():
    user_id = _get_user_id()
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "validation_error", "message": "Request body must be JSON."}), 400

    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"success": False, "error": "validation_error", "message": "Title is required."}), 400

    start_date = None
    if data.get("start_date"):
        try:
            start_date = datetime.strptime(data["start_date"], "%Y-%m-%d").date()
        except ValueError:
            pass

    target_date = None
    if data.get("target_date"):
        try:
            target_date = datetime.strptime(data["target_date"], "%Y-%m-%d").date()
        except ValueError:
            pass

    project = Project(
        title=title,
        description=data.get("description", ""),
        status=data.get("status", "planning"),
        owner_id=user_id,
        start_date=start_date,
        target_date=target_date,
        color=data.get("color", "#1e9e63"),
    )
    db.session.add(project)
    db.session.flush()

    member = ProjectMember(project_id=project.id, user_id=user_id, role="owner")
    db.session.add(member)
    db.session.commit()

    return jsonify({"success": True, "project": _serialize_project(project)}), 201


@api_projects_bp.route("/api/v1/projects/<int:project_id>", methods=["PUT"])
@jwt_required()
def edit_project(project_id):
    project = db.session.get(Project, project_id)
    if not project:
        return jsonify({"success": False, "error": "not_found", "message": "Project not found."}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "validation_error", "message": "Request body must be JSON."}), 400

    if "title" in data:
        project.title = data["title"].strip() if data["title"] else project.title
    if "description" in data:
        project.description = data["description"]
    if "status" in data:
        project.status = data["status"]
        if data["status"] == "completed" and not project.completed_at:
            project.completed_at = datetime.utcnow()
    if "color" in data:
        project.color = data["color"]
    if "start_date" in data:
        if data["start_date"]:
            try:
                project.start_date = datetime.strptime(data["start_date"], "%Y-%m-%d").date()
            except ValueError:
                pass
        else:
            project.start_date = None
    if "target_date" in data:
        if data["target_date"]:
            try:
                project.target_date = datetime.strptime(data["target_date"], "%Y-%m-%d").date()
            except ValueError:
                pass
        else:
            project.target_date = None

    db.session.commit()
    return jsonify({"success": True, "project": _serialize_project(project)})


@api_projects_bp.route("/api/v1/projects/<int:project_id>", methods=["DELETE"])
@jwt_required()
def delete_project(project_id):
    project = db.session.get(Project, project_id)
    if not project:
        return jsonify({"success": False, "error": "not_found", "message": "Project not found."}), 404

    db.session.delete(project)
    db.session.commit()
    return jsonify({"success": True, "message": "Project deleted."})


@api_projects_bp.route("/api/v1/projects/<int:project_id>/tasks", methods=["POST"])
@jwt_required()
def create_project_task(project_id):
    project = db.session.get(Project, project_id)
    if not project:
        return jsonify({"success": False, "error": "not_found", "message": "Project not found."}), 404

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

    user_id = _get_user_id()
    assignee_id = data.get("assignee_id", user_id)

    task = TeamTask(
        title=title,
        description=data.get("description", ""),
        project_id=project_id,
        status=data.get("status", "to_do"),
        priority=data.get("priority"),
        due_date=due_date,
        assignee_id=assignee_id,
        created_by=user_id,
    )
    db.session.add(task)
    db.session.commit()

    return jsonify({"success": True, "message": "Task added to project."}), 201

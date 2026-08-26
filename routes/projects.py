import json
from datetime import date, datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_required, current_user
from models import db, Project, ProjectMember, ProjectResource, ProjectUpdate, TeamTask, Employee, User
from audit import log_action

projects_bp = Blueprint("projects", __name__, url_prefix="/projects")

PROJECT_STATUSES = ["planning", "active", "on_hold", "completed"]
RESOURCE_TYPES = ["file", "link", "budget_line", "note"]


def _employee_for_user():
    return db.session.get(Employee, current_user.employee.id) if current_user.employee else None


def _is_admin():
    return current_user.role in ("admin", "hr")

def _is_ajax():
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


@projects_bp.route("")
@login_required
def list_projects():
    status_filter = request.args.get("status")
    owner_filter = request.args.get("owner_id", type=int)
    my_projects = request.args.get("my") == "1"

    q = Project.query
    if status_filter:
        q = q.filter(Project.status == status_filter)
    if owner_filter:
        q = q.filter(Project.owner_id == owner_filter)
    if my_projects:
        member_ids = db.session.query(ProjectMember.project_id).filter(
            ProjectMember.user_id == current_user.id
        ).subquery()
        q = q.filter(
            db.or_(Project.owner_id == current_user.id, Project.id.in_(member_ids))
        )

    projects = q.order_by(Project.created_at.desc()).all()

    now = datetime.utcnow()

    def time_ago(dt):
        diff = now - dt
        if diff.days > 30:
            return f"{diff.days // 30}mo ago"
        if diff.days > 0:
            return f"{diff.days}d ago"
        if diff.seconds > 3600:
            return f"{diff.seconds // 3600}h ago"
        if diff.seconds > 60:
            return f"{diff.seconds // 60}m ago"
        return "just now"

    quiet_projects = []
    for p in projects:
        if p.status != "active":
            continue
        latest = ProjectUpdate.query.filter_by(project_id=p.id).order_by(
            ProjectUpdate.created_at.desc()
        ).first()
        if latest:
            staleness = (datetime.utcnow() - latest.created_at).days
        else:
            staleness = 999
        if staleness >= 5:
            quiet_projects.append(p)

    return render_template("projects/list.html",
        projects=projects, statuses=PROJECT_STATUSES,
        quiet_projects=quiet_projects, now=now, time_ago=time_ago,
        date=date, is_admin=_is_admin(),
    )


@projects_bp.route("/create", methods=["POST"])
@login_required
def create_project():
    if not _is_admin():
        flash("Admin access required.")
        return redirect(url_for("projects.list_projects"))
    title = request.form.get("title", "").strip()
    if not title:
        flash("Project title is required.")
        return redirect(url_for("projects.list_projects"))
    p = Project(
        title=title,
        description=request.form.get("description", "").strip() or None,
        owner_id=current_user.id,
        status=request.form.get("status", "planning"),
        start_date=datetime.strptime(request.form["start_date"], "%Y-%m-%d").date()
        if request.form.get("start_date") else None,
        target_date=datetime.strptime(request.form["target_date"], "%Y-%m-%d").date()
        if request.form.get("target_date") else None,
        color=request.form.get("color", "#1e9e63"),
    )
    db.session.add(p)
    db.session.flush()
    # Auto-add creator as owner member
    pm = ProjectMember(project_id=p.id, user_id=current_user.id, role="owner")
    db.session.add(pm)
    db.session.commit()
    log_action("create_project", "Project", p.id, f"Created project: {title}")
    flash(f"Project '{title}' created.")
    return redirect(url_for("projects.view_project", project_id=p.id))


@projects_bp.route("/<int:project_id>")
@login_required
def view_project(project_id):
    p = db.session.get(Project, project_id)
    if not p:
        flash("Project not found.")
        return redirect(url_for("projects.list_projects"))
    tab = request.args.get("tab", "tasks")

    tasks = TeamTask.query.options(
        db.selectinload(TeamTask.assignee), db.selectinload(TeamTask.sub_items)
    ).filter(TeamTask.project_id == p.id).order_by(TeamTask.created_at.desc()).all()

    overdue = [t for t in tasks if t.status != "done" and t.due_date and t.due_date < date.today()]
    recent_done = [t for t in tasks if t.status == "done" and t.completed_at][:5]

    members = ProjectMember.query.options(
        db.selectinload(ProjectMember.user)
    ).filter(ProjectMember.project_id == p.id).all()

    resources = ProjectResource.query.options(
        db.selectinload(ProjectResource.adder)
    ).filter(ProjectResource.project_id == p.id).order_by(
        ProjectResource.created_at.desc()
    ).all()

    updates = ProjectUpdate.query.options(
        db.selectinload(ProjectUpdate.author)
    ).filter(ProjectUpdate.project_id == p.id).order_by(
        ProjectUpdate.created_at.desc()
    ).all()

    all_users = User.query.order_by(User.name).all() if _is_admin() else []
    member_ids = {m.user_id for m in members}
    available_users = [u for u in all_users if u.id not in member_ids]
    employees = Employee.query.filter(Employee.is_active == True).order_by(Employee.name).all()

    now = datetime.utcnow()

    def time_ago(dt):
        diff = now - dt
        if diff.days > 30:
            return f"{diff.days // 30}mo ago"
        if diff.days > 0:
            return f"{diff.days}d ago"
        if diff.seconds > 3600:
            return f"{diff.seconds // 3600}h ago"
        if diff.seconds > 60:
            return f"{diff.seconds // 60}m ago"
        return "just now"

    return render_template("projects/detail.html",
        project=p, tab=tab, tasks=tasks, overdue=overdue, recent_done=recent_done,
        members=members, resources=resources, updates=updates,
        available_users=available_users, employees=employees,
        statuses=PROJECT_STATUSES, date=date,
        time_ago=time_ago, now=now, is_admin=_is_admin(),
    )


@projects_bp.route("/<int:project_id>/status", methods=["POST"])
@login_required
def update_status(project_id):
    if not _is_admin():
        return jsonify({"ok": False, "error": "Not authorized"}), 403
    p = db.session.get(Project, project_id)
    if not p:
        return jsonify({"ok": False, "error": "Not found"}), 404
    new_status = request.form.get("status")
    if new_status not in PROJECT_STATUSES:
        return jsonify({"ok": False, "error": "Invalid status"}), 400
    p.status = new_status
    if new_status == "completed":
        p.completed_at = datetime.utcnow()
    db.session.commit()
    log_action("update_project_status", "Project", p.id, f"Status → {new_status}")
    return jsonify({"ok": True})


@projects_bp.route("/<int:project_id>/members", methods=["POST"])
@login_required
def add_member(project_id):
    if not _is_admin():
        if _is_ajax():
            return jsonify({"ok": False, "error": "Not authorized"}), 403
        flash("Admin access required.")
        return redirect(url_for("projects.list_projects"))
    p = db.session.get(Project, project_id)
    if not p:
        if _is_ajax():
            return jsonify({"ok": False, "error": "Not found"}), 404
        flash("Project not found.")
        return redirect(url_for("projects.list_projects"))
    user_id = request.form.get("user_id", type=int)
    role = request.form.get("role", "contributor")
    if not user_id:
        if _is_ajax():
            return jsonify({"ok": False, "error": "User required"}), 400
        flash("Please select a user.")
        return redirect(url_for("projects.view_project", project_id=p.id))
    existing = ProjectMember.query.filter_by(project_id=p.id, user_id=user_id).first()
    if existing:
        if _is_ajax():
            return jsonify({"ok": False, "error": "Already a member"}), 400
        flash("That user is already a member of this project.")
        return redirect(url_for("projects.view_project", project_id=p.id))
    pm = ProjectMember(project_id=p.id, user_id=user_id, role=role)
    db.session.add(pm)
    db.session.commit()
    log_action("add_project_member", "Project", p.id, f"Added user #{user_id} as {role}")
    if _is_ajax():
        return jsonify({"ok": True})
    flash("Member added.")
    return redirect(url_for("projects.view_project", project_id=p.id))


@projects_bp.route("/<int:project_id>/members/<int:member_id>/remove", methods=["POST"])
@login_required
def remove_member(project_id, member_id):
    if not _is_admin():
        return jsonify({"ok": False, "error": "Not authorized"}), 403
    pm = db.session.get(ProjectMember, member_id)
    if not pm or pm.project_id != project_id:
        return jsonify({"ok": False, "error": "Not found"}), 404
    db.session.delete(pm)
    db.session.commit()
    return jsonify({"ok": True})


@projects_bp.route("/<int:project_id>/resources", methods=["POST"])
@login_required
def add_resource(project_id):
    p = db.session.get(Project, project_id)
    if not p:
        return jsonify({"ok": False, "error": "Not found"}), 404
    rtype = request.form.get("type", "link")
    title = request.form.get("title", "").strip()
    if not title:
        return jsonify({"ok": False, "error": "Title required"}), 400
    r = ProjectResource(
        project_id=p.id, type=rtype, title=title,
        value=request.form.get("value", "").strip() or None,
        added_by=current_user.id,
    )
    db.session.add(r)
    db.session.commit()
    log_action("add_project_resource", "Project", p.id, f"Added resource: {title}")
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": True, "id": r.id})
    flash("Resource added.")
    return redirect(url_for("projects.view_project", project_id=p.id, tab="resources"))


@projects_bp.route("/<int:project_id>/resources/<int:resource_id>/delete", methods=["POST"])
@login_required
def delete_resource(project_id, resource_id):
    if not _is_admin():
        return jsonify({"ok": False, "error": "Not authorized"}), 403
    r = db.session.get(ProjectResource, resource_id)
    if not r or r.project_id != project_id:
        return jsonify({"ok": False, "error": "Not found"}), 404
    db.session.delete(r)
    db.session.commit()
    return jsonify({"ok": True})


@projects_bp.route("/<int:project_id>/activity", methods=["POST"])
@login_required
def post_update(project_id):
    p = db.session.get(Project, project_id)
    if not p:
        return jsonify({"ok": False, "error": "Not found"}), 404
    body = request.form.get("body", "").strip()
    if not body:
        return jsonify({"ok": False, "error": "Body required"}), 400
    u = ProjectUpdate(project_id=p.id, author_id=current_user.id, body=body)
    db.session.add(u)
    db.session.commit()
    log_action("project_update", "Project", p.id, f"Posted update: {body[:60]}")
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": True, "id": u.id,
            "author": current_user.name or "?",
            "created_at": u.created_at.isoformat() if u.created_at else "",
        })
    return redirect(url_for("projects.view_project", project_id=p.id, tab="activity"))


@projects_bp.route("/<int:project_id>/edit", methods=["POST"])
@login_required
def edit_project(project_id):
    if not _is_admin():
        return jsonify({"ok": False, "error": "Not authorized"}), 403
    p = db.session.get(Project, project_id)
    if not p:
        return jsonify({"ok": False, "error": "Not found"}), 404
    title = request.form.get("title", "").strip()
    if title:
        p.title = title
    p.description = request.form.get("description", p.description or "").strip() or None
    p.color = request.form.get("color", p.color)
    p.start_date = datetime.strptime(request.form["start_date"], "%Y-%m-%d").date() if request.form.get("start_date") else p.start_date
    p.target_date = datetime.strptime(request.form["target_date"], "%Y-%m-%d").date() if request.form.get("target_date") else p.target_date
    db.session.commit()
    log_action("edit_project", "Project", p.id, f"Edited project: {title or p.title}")
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": True})
    flash("Project updated.")
    return redirect(url_for("projects.view_project", project_id=p.id))


@projects_bp.route("/<int:project_id>/tasks", methods=["POST"])
@login_required
def add_task(project_id):
    if not _is_admin():
        if _is_ajax():
            return jsonify({"ok": False, "error": "Not authorized"}), 403
        flash("Admin access required.")
        return redirect(url_for("projects.list_projects"))
    p = db.session.get(Project, project_id)
    if not p:
        if _is_ajax():
            return jsonify({"ok": False, "error": "Not found"}), 404
        flash("Project not found.")
        return redirect(url_for("projects.list_projects"))
    title = request.form.get("title", "").strip()
    if not title:
        if _is_ajax():
            return jsonify({"ok": False, "error": "Title required"}), 400
        flash("Task title is required.")
        return redirect(url_for("projects.view_project", project_id=p.id))
    assignee_id = request.form.get("assignee_id", type=int)
    t = TeamTask(
        title=title,
        description=request.form.get("description", "").strip() or None,
        assignee_id=assignee_id,
        assigned_by=current_user.id,
        priority=request.form.get("priority", "medium"),
        due_date=datetime.strptime(request.form["due_date"], "%Y-%m-%d").date() if request.form.get("due_date") else None,
        project_id=p.id,
    )
    db.session.add(t)
    db.session.commit()
    log_action("add_project_task", "TeamTask", t.id, f"Task added to project {p.title}: {title}")
    if _is_ajax():
        return jsonify({"ok": True, "id": t.id})
    flash("Task added to project.")
    return redirect(url_for("projects.view_project", project_id=p.id, tab="tasks"))

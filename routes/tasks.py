import csv, io, json, re
from datetime import date, datetime, timedelta
from calendar import monthrange, month_name, day_name
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, Response, session, current_app
from flask_login import login_required, current_user
from rate_limiter import limiter
from sqlalchemy.orm import selectinload
from models import db, PersonalItem, PersonalItemMilestone, TeamTask, TeamTaskComment, TeamTaskSubItem, TeamTaskActivityLog, Discussion, DiscussionReply, Employee, Notification, User, Order
from audit import log_action

tasks_bp = Blueprint("tasks", __name__, url_prefix="/tasks")

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTH_NAMES_INV = {"january":1,"february":2,"march":3,"april":4,"may":5,"june":6,"july":7,"august":8,"september":9,"october":10,"november":11,"december":12}


def _parse_nl(raw):
    if not raw:
        return "", "medium", None, None, None
    raw = raw.strip()
    priority = "medium"
    due_str = category = recurrence = None

    # 1. Extract #category
    m = re.search(r'#(\w+)', raw)
    if m:
        category = m.group(1)
        raw = raw.replace(m.group(0), "", 1).strip()

    # 2. Extract recurrence
    rec_map = {
        r'\bevery\s+day\b': "daily", r'\bdaily\b': "daily",
        r'\bevery\s+other\s+day\b': "every_2_days",
        r'\bevery\s+week\b': "weekly", r'\bweekly\b': "weekly",
        r'\bevery\s+other\s+week\b': "every_2_weeks",
        r'\bevery\s+month\b': "monthly", r'\bmonthly\b': "monthly",
        r'\bevery\s+year\b': "yearly", r'\byearly\b': "yearly",
    }
    for pat, val in rec_map.items():
        m = re.search(pat, raw, re.IGNORECASE)
        if m:
            recurrence = val
            raw = raw.replace(m.group(0), "", 1).strip()
            break
    if not recurrence:
        m = re.search(r'\bevery\s+([\w,]+(?:\s*,\s*[\w.]+)*)\b', raw, re.IGNORECASE)
        if m:
            parts = [p.strip().lower().rstrip('.') for p in re.split(r'[,\s]+', m.group(1)) if p.strip()]
            valid = set(d[:3] for d in WEEKDAYS) | set(WEEKDAYS)
            if parts and all(p in valid for p in parts):
                recurrence = ",".join(sorted(set(parts), key=lambda x: list(valid).index(x) if x in valid else 99))
                raw = raw.replace(m.group(0), "", 1).strip()

    # 3. Extract priority
    prio_pats = [(r'\bp[1!]\b', "high"), (r'\burgent\b', "high"), (r'\bp[34]\b', "low"), (r'\bp[23]\b', "medium")]
    for pat, val in prio_pats:
        m = re.search(pat, raw, re.IGNORECASE)
        if m:
            priority = val
            raw = raw.replace(m.group(0), "", 1).strip()
            break

    # 4. Extract due date
    today = date.today()
    # tomorrow
    m = re.search(r'\btomorrow\b', raw, re.IGNORECASE)
    if m:
        due_str = (today + timedelta(days=1)).isoformat(); raw = raw.replace(m.group(0), "", 1).strip()
    # today
    if not due_str:
        m = re.search(r'\btoday\b', raw, re.IGNORECASE)
        if m:
            due_str = today.isoformat(); raw = raw.replace(m.group(0), "", 1).strip()
    # next {dayname}
    if not due_str:
        m = re.search(r'\bnext\s+(' + '|'.join(WEEKDAYS) + r')\b', raw, re.IGNORECASE)
        if m:
            diff = (WEEKDAYS.index(m.group(1).lower()) - today.weekday()) % 7
            due_str = (today + timedelta(days=diff or 7)).isoformat(); raw = raw.replace(m.group(0), "", 1).strip()
    # this|next week
    if not due_str:
        m = re.search(r'\b(?:this|next)\s+week\b', raw, re.IGNORECASE)
        if m:
            offset = 7 if m.group(0).lower().startswith("next") else 0
            due_str = (today + timedelta(days=offset - today.weekday())).isoformat()
            raw = raw.replace(m.group(0), "", 1).strip()
    # next month
    if not due_str:
        m = re.search(r'\bnext\s+month\b', raw, re.IGNORECASE)
        if m:
            m_num = today.month + 1; y = today.year
            if m_num > 12: m_num = 1; y += 1
            max_d = monthrange(y, m_num)[1]
            due_str = date(y, m_num, min(today.day, max_d)).isoformat()
            raw = raw.replace(m.group(0), "", 1).strip()
    # in N days/weeks
    if not due_str:
        m = re.search(r'\bin\s+(\d+)\s*(days?|weeks?)\b', raw, re.IGNORECASE)
        if m:
            mult = 7 if m.group(2).startswith("w") else 1
            due_str = (today + timedelta(days=int(m.group(1)) * mult)).isoformat()
            raw = raw.replace(m.group(0), "", 1).strip()
    # YYYY-MM-DD
    if not due_str:
        m = re.search(r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b', raw)
        if m:
            try: due_str = date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat(); raw = raw.replace(m.group(0), "", 1).strip()
            except ValueError: pass
    # {month} {day}
    if not due_str:
        m = re.search(r'\b(' + '|'.join(MONTH_NAMES_INV) + r')\s+(\d{1,2})\b', raw, re.IGNORECASE)
        if m:
            try:
                d = date(today.year, MONTH_NAMES_INV[m.group(1).lower()], int(m.group(2)))
                if d < today: d = d.replace(year=today.year + 1)
                due_str = d.isoformat(); raw = raw.replace(m.group(0), "", 1).strip()
            except ValueError: pass
    # DD/MM or DD/MM/YYYY
    if not due_str:
        m = re.search(r'\b(\d{1,2})/(\d{1,2})(?:/(\d{4}))?\b', raw)
        if m:
            y = int(m.group(3)) if m.group(3) else today.year
            try: due_str = date(y, int(m.group(2)), int(m.group(1))).isoformat(); raw = raw.replace(m.group(0), "", 1).strip()
            except ValueError: pass
    # this {dayname} or standalone {dayname}
    if not due_str:
        m = re.search(r'\b(?:this\s+)?(' + '|'.join(WEEKDAYS) + r')\b', raw, re.IGNORECASE)
        if m:
            diff = (WEEKDAYS.index(m.group(1).lower()) - today.weekday()) % 7
            due_str = (today + timedelta(days=diff or 7)).isoformat()
            raw = raw.replace(m.group(0), "", 1).strip()
    # Strip trailing by/due prefix
    raw = re.sub(r'^(by|due)\s+', '', raw, flags=re.IGNORECASE).strip()

    title = raw.strip() or text.strip()
    return title, priority, due_str, category, recurrence


def _next_recurring_date(rule, from_date):
    today = from_date or date.today()
    if rule == "daily":
        return today + timedelta(days=1)
    if rule == "every_2_days":
        return today + timedelta(days=2)
    if rule == "weekly":
        return today + timedelta(days=7)
    if rule == "every_2_weeks":
        return today + timedelta(days=14)
    if rule == "monthly":
        next_m = today.month + 1; y = today.year
        if next_m > 12: next_m = 1; y += 1
        max_d = monthrange(y, next_m)[1]
        return date(y, next_m, min(today.day, max_d))
    if rule == "yearly":
        try: return date(today.year + 1, today.month, today.day)
        except ValueError: return date(today.year + 1, 3, 1)
    # Comma-separated weekday recurrence: "mon,wed,fri"
    days_match = [d for d in rule.split(",") if d.strip()]
    if days_match:
        target_nums = []
        for d in days_match:
            d = d.strip().lower()[:3]
            for i, wd in enumerate(WEEKDAYS):
                if wd.startswith(d):
                    target_nums.append(i)
                    break
        if target_nums:
            today_num = today.weekday()
            for offset in range(1, 15):
                next_day = (today_num + offset) % 7
                if next_day in target_nums:
                    return today + timedelta(days=offset)
    return None


# --- My Space (§4a) ---

@tasks_bp.route("/mine")
@login_required
def my_space():
    lane = request.args.get("lane", "task")
    view = request.args.get("view", "list")
    q = request.args.get("q", "").strip()
    cal_month = request.args.get("cal_month", type=int) or date.today().month
    cal_year = request.args.get("cal_year", type=int) or date.today().year
    uid = current_user.id

    base_q = PersonalItem.query.filter_by(user_id=uid, lane=lane)
    if q:
        like = f"%{q}%"
        base_q = base_q.filter(db.or_(PersonalItem.title.ilike(like), PersonalItem.description.ilike(like)))
    all_lane_items = base_q.order_by(PersonalItem.created_at.desc()).all()
    items = all_lane_items
    if view == "board" and lane == "task":
        groups = {"to_do": [], "in_progress": [], "done": []}
        for it in all_lane_items:
            st = it.status if it.status in groups else "to_do"
            groups[st].append(it)
        items = groups

    today = date.today()
    this_week = PersonalItem.query.filter(
        PersonalItem.user_id == uid,
        PersonalItem.due_date.isnot(None),
        PersonalItem.due_date <= today,
        PersonalItem.status != "done",
    ).order_by(PersonalItem.due_date).all()

    due_today_count = PersonalItem.query.filter(
        PersonalItem.user_id == uid,
        PersonalItem.due_date == today,
        PersonalItem.status != "done",
    ).count()

    # Calendar data: tasks with due dates in the viewed month
    cal_start = date(cal_year, cal_month, 1)
    cal_end = date(cal_year, cal_month, monthrange(cal_year, cal_month)[1])
    cal_items = PersonalItem.query.filter(
        PersonalItem.user_id == uid,
        PersonalItem.due_date.isnot(None),
        PersonalItem.due_date >= cal_start,
        PersonalItem.due_date <= cal_end,
    ).order_by(PersonalItem.due_date).all()
    cal_map = {}
    for ci in cal_items:
        d = ci.due_date.day
        cal_map.setdefault(d, []).append(ci)

    total_tasks = PersonalItem.query.filter_by(user_id=uid, lane="task").count()
    done_tasks = PersonalItem.query.filter_by(user_id=uid, lane="task", status="done").count()
    overdue_tasks = PersonalItem.query.filter(
        PersonalItem.user_id == uid, PersonalItem.lane == "task",
        PersonalItem.status != "done", PersonalItem.due_date.isnot(None),
        PersonalItem.due_date < today,
    ).count()
    total_goals = PersonalItem.query.filter_by(user_id=uid, lane="goal").count()
    total_ideas = PersonalItem.query.filter_by(user_id=uid, lane="future_plan").count()
    done_goals = PersonalItem.query.filter_by(user_id=uid, lane="goal", status="done").count()
    stats = dict(
        total_tasks=total_tasks, done_tasks=done_tasks, overdue_tasks=overdue_tasks,
        total_goals=total_goals, done_goals=done_goals, total_ideas=total_ideas,
    )

    return render_template("tasks/mine.html",
        lane=lane, view=view, items=items, this_week=this_week, stats=stats, q=q,
        add_url=url_for("tasks.add_personal"),
        toggle_url=url_for("tasks.toggle_personal", item_id="__ID__"),
        update_base=url_for("tasks.update_personal", item_id="__ID__").replace("__ID__", ""),
        delete_base=url_for("tasks.delete_personal", item_id="__ID__").replace("__ID__", ""),
        milestone_toggle_url=url_for("tasks.toggle_milestone", ms_id="__ID__"),
        milestone_add_base=url_for("tasks.add_milestone", item_id="__ID__").replace("__ID__", ""),
        promote_base=url_for("tasks.promote_item", item_id="__ID__").replace("__ID__", ""),
        search_url=url_for("tasks.my_space", lane=lane),
        data_base=url_for("tasks.personal_item_data", item_id="__ID__").replace("__ID__", ""),
        due_today_count=due_today_count,
        cal_month=cal_month, cal_year=cal_year, cal_map=cal_map,
        monthrange=monthrange, month_name=month_name, day_name=day_name,
        date=date,
    )


@tasks_bp.route("/mine/add", methods=["POST"])
@login_required
def add_personal():
    lane = request.form.get("lane", "task")
    raw = request.form.get("q", "").strip()
    title = request.form.get("title", "").strip()
    priority = request.form.get("priority", "medium")
    due_date_str = request.form.get("due_date", "")
    category = request.form.get("category", "").strip() or None
    description = request.form.get("description", "").strip() or None
    estimated_minutes = request.form.get("estimated_minutes", type=int) or None
    recurrence = request.form.get("recurrence_rule", "").strip() or None

    # If the collapsed input (q) was used, parse it with NL
    if raw and not title:
        title, priority, due_date_str, category, recurrence = _parse_nl(raw)
        description = None  # NL input can't set description

    if not title:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"ok": False, "error": "Title required"}), 400
        flash("Title is required.")
        return redirect(url_for("tasks.my_space", lane=lane))

    due_date = None
    if due_date_str:
        try:
            due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            pass

    item = PersonalItem(
        user_id=current_user.id,
        lane=lane,
        title=title,
        description=description,
        priority=priority,
        category=category,
        estimated_minutes=estimated_minutes,
        due_date=due_date,
        recurrence_rule=recurrence,
    )
    db.session.add(item)
    db.session.commit()
    log_action("add_personal", "PersonalItem", item.id, f"Added {lane}: {title}")
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        card_html = render_template("tasks/_card.html", lane=lane, item=item, today=date.today())
        return jsonify({"ok": True, "id": item.id, "card_html": card_html})
    flash(f"{lane.replace('_',' ').title()} added.")
    return redirect(url_for("tasks.my_space", lane=lane))


@tasks_bp.route("/mine/toggle/<item_id>", methods=["POST"])
@login_required
def toggle_personal(item_id):
    item_id = _validate_id(item_id)
    if item_id is None:
        return jsonify({"ok": False}), 404
    item = db.session.get(PersonalItem, item_id)
    if not item or item.user_id != current_user.id:
        return jsonify({"ok": False}), 404
    if item.lane == "task":
        item.status = "done" if item.status != "done" else "not_started"
        item.completed_at = datetime.utcnow() if item.status == "done" else None
    else:
        item.status = "done" if item.status != "done" else "in_progress"
        item.completed_at = datetime.utcnow() if item.status == "done" else None

    # Generate next recurring instance if marked done and has recurrence rule
    new_id = None
    if item.status == "done" and item.recurrence_rule:
        next_due = _next_recurring_date(item.recurrence_rule, item.due_date)
        if next_due:
            new_item = PersonalItem(
                user_id=item.user_id, lane=item.lane, title=item.title,
                description=item.description, priority=item.priority,
                category=item.category, estimated_minutes=item.estimated_minutes,
                due_date=next_due, recurrence_rule=item.recurrence_rule,
            )
            db.session.add(new_item)
            db.session.flush()
            new_id = new_item.id

    db.session.commit()
    resp = {"ok": True, "status": item.status}
    if new_id:
        resp["new_id"] = new_id
        resp["new_title"] = item.title
        resp["new_due"] = next_due.isoformat()
    return jsonify(resp)


@tasks_bp.route("/mine/data/<item_id>")
@login_required
def personal_item_data(item_id):
    item_id = _validate_id(item_id)
    if item_id is None:
        return jsonify({"ok": False}), 404
    item = db.session.get(PersonalItem, item_id)
    if not item or item.user_id != current_user.id:
        return jsonify({"ok": False}), 404
    return jsonify({"ok": True, "task": {
        "id": item.id, "title": item.title, "description": item.description or "",
        "status": item.status, "priority": item.priority,
        "due_date": item.due_date.isoformat() if item.due_date else "",
        "category": item.category or "",
        "estimated_minutes": item.estimated_minutes or "",
        "recurrence_rule": item.recurrence_rule or "",
    }})


@tasks_bp.route("/mine/update/<item_id>", methods=["POST"])
@login_required
def update_personal(item_id):
    item_id = _validate_id(item_id)
    if item_id is None:
        flash("Invalid request.")
        return redirect(url_for("tasks.my_space"))
    item = db.session.get(PersonalItem, item_id)
    if not item or item.user_id != current_user.id:
        flash("Item not found.")
        return redirect(url_for("tasks.my_space"))
    item.title = request.form.get("title", item.title).strip()
    item.description = request.form.get("description", item.description or "").strip() or None
    item.priority = request.form.get("priority", item.priority)
    item.status = request.form.get("status", item.status)
    item.category = request.form.get("category", item.category or "").strip() or None
    item.estimated_minutes = request.form.get("estimated_minutes", type=int) or item.estimated_minutes
    if request.form.get("recurrence_rule") is not None:
        item.recurrence_rule = request.form.get("recurrence_rule", "").strip() or None
    if request.form.get("due_date"):
        item.due_date = datetime.strptime(request.form["due_date"], "%Y-%m-%d").date()
    elif request.form.get("due_date") == "":
        item.due_date = None
    if item.status == "done" and not item.completed_at:
        item.completed_at = datetime.utcnow()
    db.session.commit()
    log_action("update_personal", "PersonalItem", item.id, f"Updated {item.lane}: {item.title}")
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": True, "status": item.status})
    return redirect(url_for("tasks.my_space", lane=item.lane))


@tasks_bp.route("/mine/delete/<item_id>", methods=["POST"])
@login_required
def delete_personal(item_id):
    item_id = _validate_id(item_id)
    if item_id is None:
        return jsonify({"ok": False}), 404
    item = db.session.get(PersonalItem, item_id)
    if not item or item.user_id != current_user.id:
        return jsonify({"ok": False}), 404
    lane = item.lane
    db.session.delete(item)
    db.session.commit()
    return jsonify({"ok": True, "lane": lane})


@tasks_bp.route("/mine/milestone/toggle/<ms_id>", methods=["POST"])
@login_required
def toggle_milestone(ms_id):
    ms_id = _validate_id(ms_id)
    if ms_id is None:
        return jsonify({"ok": False}), 404
    ms = db.session.get(PersonalItemMilestone, ms_id)
    if not ms:
        return jsonify({"ok": False}), 404
    item = db.session.get(PersonalItem, ms.personal_item_id)
    if not item or item.user_id != current_user.id:
        return jsonify({"ok": False}), 404
    ms.is_done = not ms.is_done
    db.session.commit()
    total = len(item.milestones)
    done = sum(1 for m in item.milestones if m.is_done)
    return jsonify({"ok": True, "is_done": ms.is_done, "progress": round(done / total * 100) if total else 0})


@tasks_bp.route("/mine/milestone/add/<item_id>", methods=["POST"])
@login_required
def add_milestone(item_id):
    item_id = _validate_id(item_id)
    if item_id is None:
        flash("Invalid request.")
        return redirect(url_for("tasks.my_space"))
    item = db.session.get(PersonalItem, item_id)
    if not item or item.user_id != current_user.id:
        flash("Item not found.")
        return redirect(url_for("tasks.my_space"))
    title = request.form.get("title", "").strip()
    if title:
        max_order = db.session.query(db.func.coalesce(db.func.max(PersonalItemMilestone.order), 0)).filter(
            PersonalItemMilestone.personal_item_id == item_id
        ).scalar()
        ms = PersonalItemMilestone(personal_item_id=item_id, title=title, order=max_order + 1)
        db.session.add(ms)
        db.session.commit()
        total = len(item.milestones)
        done = sum(1 for m in item.milestones if m.is_done)
        progress = round(done / total * 100) if total else 0
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            ms_html = f'<div class="ms-row"><button class="msb" onclick="toggleMs({ms.id},this)"></button><span>{title}</span></div>'
            return jsonify({"ok": True, "id": ms.id, "ms_html": ms_html, "progress": progress, "total": total, "done": done})
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": False, "error": "Title required"}), 400
    return redirect(url_for("tasks.my_space", lane=item.lane))


@tasks_bp.route("/mine/promote/<item_id>", methods=["POST"])
@login_required
def promote_item(item_id):
    item_id = _validate_id(item_id)
    if item_id is None:
        flash("Invalid request.")
        return redirect(url_for("tasks.my_space"))
    item = db.session.get(PersonalItem, item_id)
    if not item or item.user_id != current_user.id:
        flash("Item not found.")
        return redirect(url_for("tasks.my_space"))
    target = request.form.get("target", "task")
    if target in ("task", "goal"):
        item.lane = target
        item.status = "not_started"
        db.session.commit()
        log_action("promote", "PersonalItem", item.id, f"Promoted future_plan to {target}")
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": True})
    return redirect(url_for("tasks.my_space", lane=target))


# --- Groq AI Assistant ---

@tasks_bp.route("/mine/ai-idea", methods=["POST"])
@login_required
@limiter.limit("10 per minute")
def idea_ai_assist():
    import os, json as j
    item_id = request.form.get("item_id", type=int)
    prompt = request.form.get("prompt", "").strip()
    mode = request.form.get("mode", "chat")
    if not prompt:
        return jsonify({"ok": False, "error": "Prompt required"}), 400
    idea = db.session.get(PersonalItem, item_id) if item_id else None
    if idea and idea.user_id != current_user.id:
        return jsonify({"ok": False, "error": "Not found"}), 404
    ctx = f"Idea title: {idea.title if idea else 'Untitled'}"
    if idea and idea.description:
        ctx += f"\nDescription: {idea.description}"
    ctx += f"\nPrompt: {prompt}"
    if mode == "diagram":
        ctx += "\n\nGenerate a Mermaid.js diagram that visualizes this idea. Return ONLY valid Mermaid code (no markdown fences, no explanation). Use a format like graph TD, flowchart LR, mindmap, or sequenceDiagram."
    elif mode == "flowchart":
        ctx += "\n\nGenerate a Mermaid.js flowchart that maps out the steps or components of this idea. Return ONLY valid Mermaid code (no markdown fences, no explanation). Use flowchart LR or flowchart TD."
    system = "You are a creative AI assistant that helps develop ideas. Respond in plain text. For diagram/flowchart requests, output ONLY valid Mermaid.js code with no surrounding text or markdown fences."
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return jsonify({"ok": False, "error": "GROQ_API_KEY not set"}), 400
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        resp = client.chat.completions.create(
            model=os.environ.get("GROQ_CHAT_MODEL", "llama-3.3-70b-versatile"),
            messages=[{"role": "system", "content": system}, {"role": "user", "content": ctx}],
            temperature=0.7, max_tokens=1200,
        )
        reply = resp.choices[0].message.content.strip()
        return jsonify({"ok": True, "reply": reply, "mode": mode})
    except Exception as e:
        current_app.logger.error("AI suggest error: %s", e)
        return jsonify({"ok": False, "error": "AI request failed. Please try again."}), 500


@tasks_bp.route("/mine/ai-chat", methods=["POST"])
@login_required
@limiter.limit("15 per minute")
def personal_ai_chat():
    import os, json as j
    message = request.form.get("message", "").strip()
    conversation_raw = request.form.get("conversation", "[]")
    if not message:
        return jsonify({"ok": False, "error": "Message required"}), 400

    uid = current_user.id
    try:
        conv = j.loads(conversation_raw) if isinstance(conversation_raw, str) else conversation_raw
    except (j.JSONDecodeError, TypeError):
        conv = []
    if not isinstance(conv, list):
        conv = []

    # Build context from user's items
    all_items = PersonalItem.query.filter(PersonalItem.user_id == uid).order_by(PersonalItem.created_at.desc()).limit(50).all()
    ctx_lines = []
    lanes = {"task": "Tasks", "goal": "Goals", "project": "Works", "future_plan": "Ideas"}
    for l, label in lanes.items():
        items = [i for i in all_items if i.lane == l]
        if items:
            ctx_lines.append(f"## {label}")
            for i in items:
                due = f" due:{i.due_date}" if i.due_date else ""
                done = " [DONE]" if i.status == "done" else ""
                pri = f" ({i.priority})" if i.priority != "medium" else ""
                cat = f" #{i.category}" if i.category else ""
                ctx_lines.append(f"  - {i.title}{pri}{due}{cat}{done}")

    # Count stats for context
    total = len(all_items)
    overdue = sum(1 for i in all_items if i.lane == "task" and i.status != "done" and i.due_date and i.due_date < today)
    done_today = sum(1 for i in all_items if i.status == "done" and i.completed_at and i.completed_at.date() == today)
    no_due = sum(1 for i in all_items if i.lane == "task" and i.status != "done" and not i.due_date)

    today_str = today.isoformat()
    system_prompt = (
        "You are a friendly AI productivity assistant. You help the user manage their personal tasks, "
        "goals, ideas, and projects. Be concise, practical, encouraging, and sometimes gently critical.\n\n"
        f"Today is {today_str}. User has {total} total items ({overdue} overdue, {done_today} done today, "
        f"{no_due} tasks without due dates).\n\n"
        "The user's current items:\n" + "\n".join(ctx_lines) + "\n\n"
        "=== COMMANDS ===\n"
        "/focus — Analyze all open tasks and suggest the top 3 to work on today (based on priority + due date)\n"
        "/breakdown [goal title] — Break a goal or project into concrete milestones/sub-tasks\n"
        "/plan — Create a weekly plan prioritizing overdue and due-soon items\n"
        "/balance — Check workload balance: priorities, categories, overdue vs done ratio\n"
        "/cleanup — Find stale, duplicated, or completed items that can be archived or deleted\n"
        "/prioritize — Review all tasks and suggest priority upgrades/downgrades\n"
        "/motivate — Give personalized encouragement based on recent progress and what's left\n"
        "/next — Suggest the single next best thing to work on right now\n"
        "/cluster — Group tasks by shared category/tag and suggest batch-work sessions\n"
        "/estimate [task title] — Suggest a time estimate for a specific task\n"
        "/review — Summarize what was accomplished recently and what's ahead\n"
        "/describe [item title] — Generate a description for a goal, project, or task\n\n"
        "If the user asks a general question (not a command), answer helpfully.\n"
        "If you notice a mistake (wrong priority, missing due date on high-prio task, duplicate titles), "
        "flag it politely.\n"
        "Respond in plain text (no markdown). Keep responses under 150 words unless providing a breakdown."
    )

    messages = [{"role": "system", "content": system_prompt}]
    # Add up to 10 turns of history
    for c in conv[-10:]:
        role = c.get("role", "user")
        messages.append({"role": role, "content": c.get("content", "")})
    messages.append({"role": "user", "content": message})

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return jsonify({"ok": False, "error": "GROQ_API_KEY not set"}), 400

    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=os.environ.get("GROQ_CHAT_MODEL", "llama-3.3-70b-versatile"),
            messages=messages,
            temperature=0.7,
            max_tokens=600,
        )
        reply = response.choices[0].message.content.strip()
        return jsonify({"ok": True, "reply": reply})
    except Exception as e:
        current_app.logger.error("AI chat error: %s", e)
        return jsonify({"ok": False, "error": "AI request failed. Please try again."}), 500


# --- Team Tasks (§4b/4c) — Upgraded ---

def _employee_for_user():
    return db.session.get(Employee, current_user.employee.id) if current_user.employee else None


def _validate_id(id_str):
    if not id_str or not id_str.isdigit():
        return None
    return int(id_str)


def _log_activity(task_id, action_text):
    log = TeamTaskActivityLog(team_task_id=task_id, actor_id=current_user.id, action_text=action_text)
    db.session.add(log)


def _notify_assignee(task, message, link=None):
    if not task.assignee_id:
        return
    emp = db.session.get(Employee, task.assignee_id)
    if emp and emp.user_id and emp.user_id != current_user.id:
        Notification.send(emp.user_id, message, link or url_for("tasks.team_tasks"))


def _parse_mentions(body):
    import re
    mentioned = set()
    for m in re.finditer(r'@(\w+(?:\s+\w+)?)', body):
        name = m.group(1).strip()
        emp = Employee.query.filter(Employee.name.ilike(name + "%")).first()
        if emp and emp.user_id:
            mentioned.add(emp)
    return mentioned


def _notify_mentions(body, task, excluded_user_id=None):
    for emp in _parse_mentions(body):
        if emp.user_id and emp.user_id != excluded_user_id:
            Notification.send(emp.user_id, f"You were mentioned in \"{task.title}\"", url_for("tasks.team_tasks"))


SORTABLE_FIELDS = {"title", "assignee", "priority", "status", "due_date", "created_at", "order"}

def auto_archive_purge():
    archive_before = datetime.utcnow() - timedelta(days=1)
    delete_before = datetime.utcnow() - timedelta(days=15)
    archived = TeamTask.query.filter(TeamTask.status == "done", TeamTask.completed_at.isnot(None), TeamTask.archived_at.is_(None), TeamTask.completed_at < archive_before).all()
    for t in archived:
        t.archived_at = datetime.utcnow()
    deleted = TeamTask.query.filter(TeamTask.archived_at.isnot(None), TeamTask.completed_at < delete_before).all()
    for t in deleted:
        db.session.delete(t)
    if archived or deleted:
        db.session.commit()
        return {"archived": len(archived), "deleted": len(deleted)}
    return {"archived": 0, "deleted": 0}

@tasks_bp.route("/team")
@login_required
def team_tasks():
    auto_archive_purge()
    is_admin = current_user.role in ("admin", "hr")
    emp = _employee_for_user()
    if not is_admin and not emp:
        flash("No employee record linked to your account.")
        return redirect(url_for("home"))

    view = request.args.get("view") or ("inbox" if (not is_admin and emp) else "board")
    status_filter = request.args.get("status")
    priority_filter = request.args.get("priority")
    employee_filter = request.args.get("employee_id", type=int)
    sort_field = request.args.get("sort", "")
    sort_dir = request.args.get("dir", "asc")
    q = request.args.get("q", "").strip()

    company_id = session.get("active_company_id")
    recent_orders = Order.query.filter(
        Order.company_id == company_id
    ).order_by(Order.created_at.desc()).limit(50).all() if company_id else []

    # Inbox / My Day — employee-scoped simple views
    if view in ("inbox", "my_day") and not is_admin and emp:
        base = TeamTask.query.options(selectinload(TeamTask.sub_items), selectinload(TeamTask.comments), selectinload(TeamTask.assignee)).filter(TeamTask.assignee_id == emp.id, TeamTask.archived_at.is_(None))
        if view == "inbox":
            tasks = base.filter(TeamTask.acknowledged_at.is_(None)).order_by(TeamTask.created_at.desc()).all()
        else:
            tasks = base.filter(TeamTask.due_date == date.today()).order_by(TeamTask.created_at.desc()).all()
        unacknowledged_count = TeamTask.query.filter(
            TeamTask.assignee_id == emp.id, TeamTask.acknowledged_at.is_(None), TeamTask.archived_at.is_(None)
        ).count()
        all_employees = []
        employees = []
        acknowledged = False

        now = datetime.utcnow()
        def time_ago(dt):
            diff = now - dt
            if diff.days > 30: return f"{diff.days//30}mo ago"
            if diff.days > 0: return f"{diff.days}d ago"
            if diff.seconds > 3600: return f"{diff.seconds//3600}h ago"
            if diff.seconds > 60: return f"{diff.seconds//60}m ago"
            return "just now"

        return render_template("tasks/team.html",
            tasks=tasks, is_admin=is_admin, employees=employees, all_employees=all_employees,
            overdue=[], recent_done=[], due_today=0, week_done=0,
            current_employee_id=emp.id if emp else None,
            add_url=url_for("tasks.add_team_task"),
            update_base=url_for("tasks.update_team_task", task_id="__ID__").replace("__ID__", ""),
            delete_base=url_for("tasks.delete_team_task", task_id="__ID__").replace("__ID__", ""),
            comment_base=url_for("tasks.add_comment", task_id="__ID__").replace("__ID__", ""),
            data_url=url_for("tasks.team_task_data", task_id="__ID__"),
            bulk_url=url_for("tasks.bulk_team_task_action"),
            sort_field=sort_field, sort_dir=sort_dir, q=q,
            time_ago=time_ago, now=now, date=date,
            view=view, unacknowledged_count=unacknowledged_count,
            recent_orders=recent_orders,
            matrix={}, months=[],
        )

    # Admin-capable views (board, table, by_employee) — full query
    query = TeamTask.query.options(selectinload(TeamTask.sub_items), selectinload(TeamTask.comments), selectinload(TeamTask.assignee)).filter(TeamTask.archived_at.is_(None))
    if not is_admin and emp:
        query = query.filter(TeamTask.assignee_id == emp.id)
    elif employee_filter:
        query = query.filter(TeamTask.assignee_id == employee_filter)
    if status_filter:
        query = query.filter(TeamTask.status == status_filter)
    if priority_filter:
        query = query.filter(TeamTask.priority == priority_filter)
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(TeamTask.title.ilike(like), TeamTask.description.ilike(like)))

    order_col = None
    if sort_field == "title":
        order_col = TeamTask.title
    elif sort_field == "priority":
        order_col = TeamTask.priority
    elif sort_field == "status":
        order_col = TeamTask.status
    elif sort_field == "due_date":
        order_col = TeamTask.due_date
    elif sort_field == "created_at":
        order_col = TeamTask.created_at
    elif sort_field == "assignee":
        order_col = TeamTask.assignee_id
    if order_col:
        order_col = order_col.asc() if sort_dir == "asc" else order_col.desc()
        query = query.order_by(order_col, TeamTask.created_at.desc())
    else:
        query = query.order_by(TeamTask.created_at.desc())

    tasks = query.all()
    all_employees = Employee.query.filter(Employee.is_active == True).order_by(Employee.name).all() if is_admin else []
    employees = all_employees

    if request.args.get("format") == "csv":
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["ID", "Title", "Assignee", "Priority", "Status", "Due Date", "Created", "Completed", "Order ID"])
        for t in tasks:
            w.writerow([
                t.id, t.title, t.assignee.name if t.assignee else "",
                t.priority, t.status,
                t.due_date.isoformat() if t.due_date else "",
                t.created_at.isoformat() if t.created_at else "",
                t.completed_at.isoformat() if t.completed_at else "",
                t.order_id or "",
            ])
        return Response(out.getvalue(), mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=team_tasks.csv"})

    overdue = [t for t in tasks if t.status != "done" and t.due_date and t.due_date < date.today()]
    recent_done = [t for t in tasks if t.status == "done" and t.completed_at][:5]
    due_today = [t for t in tasks if t.status != "done" and t.due_date == date.today()]
    week_done = [t for t in tasks if t.status == "done" and t.completed_at and (datetime.utcnow() - t.completed_at).days < 7]
    unacknowledged_count = 0

    # Priority Matrix (Eisenhower) — categorize all tasks
    urgent_threshold = date.today() + timedelta(days=3)
    matrix = {"do_first": [], "schedule": [], "delegate": [], "eliminate": []}
    for t in tasks:
        is_important = t.priority == "high"
        is_urgent = t.due_date and t.due_date <= urgent_threshold
        if t.status == "done":
            continue
        if is_important and is_urgent:
            matrix["do_first"].append(t)
        elif is_important and not is_urgent:
            matrix["schedule"].append(t)
        elif not is_important and is_urgent:
            matrix["delegate"].append(t)
        else:
            matrix["eliminate"].append(t)

    # Timeline — tasks with due dates grouped by month
    today = date.today()
    months = []
    month_groups = {}
    for t in tasks:
        if not t.due_date:
            continue
        key = (t.due_date.year, t.due_date.month)
        if key not in month_groups:
            month_groups[key] = {"year": key[0], "month": key[1], "tasks": []}
        month_groups[key]["tasks"].append(t)
    months = sorted(month_groups.values(), key=lambda m: (m["year"], m["month"]))

    now = datetime.utcnow()
    def time_ago(dt):
        diff = now - dt
        if diff.days > 30: return f"{diff.days//30}mo ago"
        if diff.days > 0: return f"{diff.days}d ago"
        if diff.seconds > 3600: return f"{diff.seconds//3600}h ago"
        if diff.seconds > 60: return f"{diff.seconds//60}m ago"
        return "just now"

    return render_template("tasks/team.html",
        tasks=tasks, is_admin=is_admin, employees=employees, all_employees=all_employees,
        overdue=overdue, recent_done=recent_done, due_today=len(due_today), week_done=len(week_done),
        current_employee_id=emp.id if emp else None,
        add_url=url_for("tasks.add_team_task"),
        update_base=url_for("tasks.update_team_task", task_id="__ID__").replace("__ID__", ""),
        delete_base=url_for("tasks.delete_team_task", task_id="__ID__").replace("__ID__", ""),
        comment_base=url_for("tasks.add_comment", task_id="__ID__").replace("__ID__", ""),
        data_url=url_for("tasks.team_task_data", task_id="__ID__"),
        bulk_url=url_for("tasks.bulk_team_task_action"),
        sort_field=sort_field, sort_dir=sort_dir, q=q,
        time_ago=time_ago, now=now, date=date,
        view=view, unacknowledged_count=unacknowledged_count,
        recent_orders=recent_orders, matrix=matrix, months=months,
    )


# --- Sub-task checklists ---

@tasks_bp.route("/team/<task_id>/subtask/add", methods=["POST"])
@login_required
def add_subtask(task_id):
    task_id = _validate_id(task_id)
    if task_id is None:
        return jsonify({"ok": False}), 404
    task = db.session.get(TeamTask, task_id)
    if not task:
        return jsonify({"ok": False, "error": "Task not found"}), 404
    is_admin = current_user.role in ("admin", "hr")
    emp = _employee_for_user()
    if not is_admin and (not emp or task.assignee_id != emp.id):
        return jsonify({"ok": False, "error": "Not your task"}), 403
    title = request.form.get("title", "").strip()
    if not title:
        return jsonify({"ok": False, "error": "Title required"}), 400
    max_order = db.session.query(db.func.coalesce(db.func.max(TeamTaskSubItem.order), 0)).filter(
        TeamTaskSubItem.team_task_id == task_id
    ).scalar()
    si = TeamTaskSubItem(team_task_id=task_id, title=title, order=max_order + 1)
    db.session.add(si)
    db.session.commit()
    _log_activity(task_id, f"Added sub-task: {title}")
    return jsonify({"ok": True, "subtask": {
        "id": si.id, "title": si.title, "is_done": si.is_done, "order": si.order,
    }})


@tasks_bp.route("/team/subtask/<subtask_id>/toggle", methods=["POST"])
@login_required
def toggle_subtask(subtask_id):
    subtask_id = _validate_id(subtask_id)
    if subtask_id is None:
        return jsonify({"ok": False}), 404
    si = db.session.get(TeamTaskSubItem, subtask_id)
    if not si:
        return jsonify({"ok": False, "error": "Sub-task not found"}), 404
    task = db.session.get(TeamTask, si.team_task_id)
    if not task:
        return jsonify({"ok": False, "error": "Parent task not found"}), 404
    is_admin = current_user.role in ("admin", "hr")
    emp = _employee_for_user()
    if not is_admin and (not emp or task.assignee_id != emp.id):
        return jsonify({"ok": False, "error": "Not your task"}), 403
    si.is_done = not si.is_done
    db.session.commit()
    total = db.session.query(db.func.count(TeamTaskSubItem.id)).filter(
        TeamTaskSubItem.team_task_id == si.team_task_id
    ).scalar()
    done = db.session.query(db.func.count(TeamTaskSubItem.id)).filter(
        TeamTaskSubItem.team_task_id == si.team_task_id, TeamTaskSubItem.is_done == True
    ).scalar()
    _log_activity(si.team_task_id, f"{'Done' if si.is_done else 'Undone'} sub-task: {si.title}")
    return jsonify({"ok": True, "is_done": si.is_done, "progress": round(done / total * 100) if total else 0})


@tasks_bp.route("/team/subtask/<subtask_id>/delete", methods=["POST"])
@login_required
def delete_subtask(subtask_id):
    subtask_id = _validate_id(subtask_id)
    if subtask_id is None:
        return jsonify({"ok": False}), 404
    si = db.session.get(TeamTaskSubItem, subtask_id)
    if not si:
        return jsonify({"ok": False, "error": "Sub-task not found"}), 404
    task = db.session.get(TeamTask, si.team_task_id)
    if not task:
        return jsonify({"ok": False, "error": "Parent task not found"}), 404
    is_admin = current_user.role in ("admin", "hr")
    emp = _employee_for_user()
    if not is_admin and (not emp or task.assignee_id != emp.id):
        return jsonify({"ok": False, "error": "Not your task"}), 403
    _log_activity(si.team_task_id, f"Deleted sub-task: {si.title}")
    db.session.delete(si)
    db.session.commit()
    return jsonify({"ok": True})


# --- Acknowledge ---

@tasks_bp.route("/team/<task_id>/acknowledge", methods=["POST"])
@login_required
def acknowledge_team_task(task_id):
    task_id = _validate_id(task_id)
    if task_id is None:
        return jsonify({"ok": False}), 404
    task = db.session.get(TeamTask, task_id)
    if not task:
        return jsonify({"ok": False}), 404
    emp = _employee_for_user()
    if not emp or task.assignee_id != emp.id:
        return jsonify({"ok": False, "error": "Not your task"}), 403
    if task.acknowledged_at is None:
        task.acknowledged_at = datetime.utcnow()
        db.session.commit()
        _log_activity(task_id, "Acknowledged")
    return jsonify({"ok": True})


@tasks_bp.route("/team/data/<task_id>")
@login_required
def team_task_data(task_id):
    task_id = _validate_id(task_id)
    if task_id is None:
        return jsonify({"ok": False}), 404
    task = db.session.get(TeamTask, task_id)
    if not task:
        return jsonify({"ok": False}), 404
    is_admin = current_user.role in ("admin", "hr")
    emp = _employee_for_user()
    if not is_admin and (not emp or task.assignee_id != emp.id):
        return jsonify({"ok": False}), 403

    comments = [{
        "id": c.id, "author": c.author.name if c.author else "?",
        "body": c.body, "created_at": c.created_at.isoformat() if c.created_at else "",
        "parent_id": c.parent_id,
        "is_system": False,
    } for c in task.comments]

    log_entries = [{
        "id": l.id, "author": l.actor.name if l.actor else "System",
        "body": l.action_text, "created_at": l.created_at.isoformat() if l.created_at else "",
        "is_system": True,
    } for l in task.activity_log]

    thread = sorted(comments + log_entries, key=lambda x: x["created_at"])

    sub_items = [{
        "id": s.id, "title": s.title, "is_done": s.is_done, "order": s.order,
    } for s in (task.sub_items or [])]

    return jsonify({
        "ok": True,
        "task": {
            "id": task.id, "title": task.title, "description": task.description or "",
            "status": task.status, "priority": task.priority,
            "assignee_id": task.assignee_id,
            "assignee_name": task.assignee.name if task.assignee else "",
            "due_date": task.due_date.isoformat() if task.due_date else "",
            "order_id": task.order_id,
            "order_url": url_for("orders.view_order", order_id=task.order_id) if task.order_id else "",
            "sub_items": sub_items,
        },
        "thread": thread,
    })


@tasks_bp.route("/team/add", methods=["POST"])
@login_required
def add_team_task():
    if current_user.role not in ("admin", "hr"):
        return jsonify({"ok": False, "error": "Not authorized"}), 403
    title = request.form.get("title", "").strip()
    if not title:
        return jsonify({"ok": False, "error": "Title required"}), 400
    assignee_id = request.form.get("assignee_id", type=int)
    if not assignee_id:
        return jsonify({"ok": False, "error": "Assignee required"}), 400

    copies = int(request.form.get("copies", 1))
    created = []
    for i in range(copies):
        t = TeamTask(
            title=title,
            description=request.form.get("description", "").strip() or None,
            assignee_id=assignee_id,
            assigned_by=current_user.id,
            priority=request.form.get("priority", "medium"),
            due_date=datetime.strptime(request.form["due_date"], "%Y-%m-%d").date() if request.form.get("due_date") else None,
            order_id=request.form.get("order_id", type=int) or None,
        )
        db.session.add(t)
        db.session.flush()
        _log_activity(t.id, f"Task created · {t.priority} priority")
        _notify_assignee(t, f"New task assigned: {t.title}")
        created.append(t.id)
    db.session.commit()
    log_action("assign_team_task", "TeamTask", 0, f"Assigned task(s) to employee #{assignee_id}")
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": True, "ids": created})
    flash("Team task(s) assigned.")
    return redirect(url_for("tasks.team_tasks"))


@tasks_bp.route("/team/orders/search")
@login_required
def search_team_orders():
    q = request.args.get("q", "").strip()
    company_id = session.get("active_company_id")
    filter_args = [Order.company_id == company_id] if company_id else []
    if q:
        filter_args.append(Order.order_number.ilike(f"%{q}%"))
    orders = Order.query.filter(*filter_args).order_by(Order.created_at.desc()).limit(50).all()
    return jsonify([{"id": o.id, "text": f"Order #{o.order_number or o.id}"} for o in orders])


@tasks_bp.route("/team/update/<task_id>", methods=["POST"])
@login_required
def update_team_task(task_id):
    task_id = _validate_id(task_id)
    if task_id is None:
        return jsonify({"ok": False, "error": "Not found"}), 404
    task = db.session.get(TeamTask, task_id)
    if not task:
        return jsonify({"ok": False, "error": "Not found"}), 404
    is_admin = current_user.role in ("admin", "hr")
    emp = _employee_for_user()
    if not is_admin and (not emp or task.assignee_id != emp.id):
        return jsonify({"ok": False, "error": "Not your task"}), 403

    changes = []
    new_status = request.form.get("status")
    if new_status and new_status in ("to_do", "in_progress", "done") and new_status != task.status:
        task.status = new_status
        task.completed_at = datetime.utcnow() if new_status == "done" else None
        changes.append(f"Status → {new_status.replace('_', ' ')}")

    if is_admin:
        new_priority = request.form.get("priority")
        if new_priority and new_priority != task.priority:
            task.priority = new_priority
            changes.append(f"Priority → {new_priority}")

        new_assignee = request.form.get("assignee_id", type=int)
        if new_assignee and new_assignee != task.assignee_id:
            task.assignee_id = new_assignee
            changes.append(f"Reassigned")

        nd = request.form.get("due_date")
        if nd:
            parsed = datetime.strptime(nd, "%Y-%m-%d").date()
            if parsed != task.due_date:
                task.due_date = parsed
                changes.append(f"Due → {nd}")
        elif nd == "" and task.due_date:
            task.due_date = None
            changes.append("Due date removed")

        new_title = request.form.get("title", "").strip()
        if new_title and new_title != task.title:
            task.title = new_title
            changes.append(f"Renamed")

        order_id = request.form.get("order_id", type=int)
        if order_id != task.order_id:
            task.order_id = order_id or None
            changes.append(f"Order linked")

    db.session.commit()

    if changes:
        _log_activity(task_id, " · ".join(changes))
        _notify_assignee(task, f"\"{task.title}\" updated: {' · '.join(changes)}")

    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if is_ajax:
        return jsonify({"ok": True, "status": task.status})
    return redirect(url_for("tasks.team_tasks"))


@tasks_bp.route("/team/delete/<task_id>", methods=["POST"])
@login_required
def delete_team_task(task_id):
    task_id = _validate_id(task_id)
    if task_id is None:
        return jsonify({"ok": False}), 404
    if current_user.role not in ("admin", "hr"):
        return jsonify({"ok": False}), 403
    task = db.session.get(TeamTask, task_id)
    if task:
        db.session.delete(task)
        db.session.commit()
    return jsonify({"ok": True})


@tasks_bp.route("/team/comment/<task_id>", methods=["POST"])
@login_required
def add_comment(task_id):
    task_id = _validate_id(task_id)
    if task_id is None:
        return jsonify({"ok": False, "error": "Not found"}), 404
    task = db.session.get(TeamTask, task_id)
    if not task:
        return jsonify({"ok": False, "error": "Not found"}), 404
    is_admin = current_user.role in ("admin", "hr")
    emp = _employee_for_user()
    if not is_admin and (not emp or task.assignee_id != emp.id):
        return jsonify({"ok": False, "error": "Not your task"}), 403

    body = request.form.get("body", "").strip()
    if not body:
        return jsonify({"ok": False, "error": "Empty comment"}), 400

    parent_id = request.form.get("parent_id", type=int)
    c = TeamTaskComment(team_task_id=task_id, author_id=current_user.id, body=body, parent_id=parent_id or None)
    db.session.add(c)
    db.session.commit()

    _notify_assignee(task, f"New comment on \"{task.title}\"")
    _notify_mentions(body, task, excluded_user_id=current_user.id)

    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if is_ajax:
        return jsonify({"ok": True, "comment": {
            "id": c.id, "author": current_user.name or "?", "body": body,
            "created_at": c.created_at.isoformat() if c.created_at else "",
            "parent_id": c.parent_id,
            "is_system": False,
        }})
    return redirect(url_for("tasks.team_tasks"))


@tasks_bp.route("/team/bulk", methods=["POST"])
@login_required
def bulk_team_task_action():
    is_admin = current_user.role in ("admin", "hr")
    task_ids = request.form.getlist("ids[]")
    action = request.form.get("action")
    value = request.form.get("value")

    if not task_ids or not action:
        return jsonify({"ok": False, "error": "Missing ids or action"}), 400

    valid_ids = []
    for tid in task_ids:
        vid = _validate_id(tid)
        if vid is not None:
            valid_ids.append(vid)

    if not valid_ids:
        return jsonify({"ok": False, "error": "No valid task IDs"}), 400

    emp = _employee_for_user()
    tasks = db.session.query(TeamTask).filter(TeamTask.id.in_(valid_ids)).all()

    # Non-admin can only act on their own tasks
    if not is_admin:
        if not emp:
            return jsonify({"ok": False, "error": "No employee record"}), 403
        tasks = [t for t in tasks if t.assignee_id == emp.id]
        if not tasks:
            return jsonify({"ok": False, "error": "No accessible tasks"}), 403

    if action == "mark_done":
        for t in tasks:
            t.status = "done"
            t.completed_at = datetime.utcnow()
            _log_activity(t.id, "Bulk marked done")
        db.session.commit()
        return jsonify({"ok": True, "count": len(tasks)})

    if action == "set_priority":
        if value not in ("high", "medium", "low"):
            return jsonify({"ok": False, "error": "Invalid priority"}), 400
        for t in tasks:
            t.priority = value
            _log_activity(t.id, f"Bulk priority → {value}")
        db.session.commit()
        return jsonify({"ok": True, "count": len(tasks)})

    if action == "reassign":
        if not is_admin:
            return jsonify({"ok": False, "error": "Admin required"}), 403
        new_assignee_id = _validate_id(value or "")
        if new_assignee_id is None:
            return jsonify({"ok": False, "error": "Invalid assignee"}), 400
        for t in tasks:
            t.assignee_id = new_assignee_id
            _log_activity(t.id, "Bulk reassigned")
            _notify_assignee(t, f"Task reassigned: {t.title}")
        db.session.commit()
        return jsonify({"ok": True, "count": len(tasks)})

    if action == "delete":
        if not is_admin:
            return jsonify({"ok": False, "error": "Admin required"}), 403
        for t in tasks:
            db.session.delete(t)
        db.session.commit()
        return jsonify({"ok": True, "count": len(tasks)})

    return jsonify({"ok": False, "error": "Unknown action"}), 400


# --- Phase 6: Task Templates ---

@tasks_bp.route("/team/templates", methods=["GET"])
@login_required
def list_templates():
    company_id = session.get("active_company_id")
    q = request.args.get("q", "").strip()
    filter_args = [TaskTemplate.company_id == company_id] if company_id else []
    if q:
        filter_args.append(TaskTemplate.title.ilike(f"%{q}%"))
    templates = TaskTemplate.query.filter(*filter_args).order_by(TaskTemplate.title).all()
    return jsonify([{
        "id": t.id, "title": t.title, "description": t.description,
        "default_priority": t.default_priority,
        "sub_tasks": json.loads(t.sub_tasks) if t.sub_tasks else [],
        "created_at": t.created_at.isoformat() if t.created_at else "",
        "day_of_month": t.day_of_month,
        "is_active": t.is_active,
        "last_generated_month": t.last_generated_month,
        "last_generated_year": t.last_generated_year,
    } for t in templates])


@tasks_bp.route("/team/templates", methods=["POST"])
@login_required
def create_template():
    if current_user.role not in ("admin", "hr"):
        return jsonify({"ok": False, "error": "Not authorized"}), 403
    company_id = session.get("active_company_id")
    if not company_id:
        return jsonify({"ok": False, "error": "No active company"}), 400
    title = request.form.get("title", "").strip()
    if not title:
        return jsonify({"ok": False, "error": "Title required"}), 400

    source_task_id = request.form.get("source_task_id", type=int)
    if source_task_id:
        task = db.session.get(TeamTask, source_task_id)
        if task:
            sub_titles = [s.title for s in (task.sub_items or [])]
            tpl = TaskTemplate(
                title=title, description=task.description,
                default_priority=task.priority,
                company_id=company_id, sub_tasks=json.dumps(sub_titles),
                scope="company",
                day_of_month=request.form.get("day_of_month", type=int) or None,
            )
            db.session.add(tpl)
            db.session.commit()
            return jsonify({"ok": True, "id": tpl.id})
    description = request.form.get("description", "").strip() or None
    default_priority = request.form.get("default_priority", "medium")
    sub_tasks_raw = request.form.get("sub_tasks", "[]")
    try:
        sub_tasks_list = json.loads(sub_tasks_raw)
    except json.JSONDecodeError:
        sub_tasks_list = []
    tpl = TaskTemplate(
        title=title, description=description,
        default_priority=default_priority,
        company_id=company_id, sub_tasks=json.dumps(sub_tasks_list),
        scope="company",
        day_of_month=request.form.get("day_of_month", type=int) or None,
    )
    db.session.add(tpl)
    db.session.commit()
    return jsonify({"ok": True, "id": tpl.id})


@tasks_bp.route("/team/templates/<template_id>/apply", methods=["POST"])
@login_required
def apply_template(template_id):
    template_id = _validate_id(template_id)
    if template_id is None:
        return jsonify({"ok": False}), 404
    tpl = db.session.get(TaskTemplate, template_id)
    if not tpl:
        return jsonify({"ok": False, "error": "Template not found"}), 404
    assignee_id = request.form.get("assignee_id", type=int)
    if not assignee_id:
        return jsonify({"ok": False, "error": "Assignee required"}), 400
    due_date = datetime.strptime(request.form["due_date"], "%Y-%m-%d").date() if request.form.get("due_date") else None
    t = TeamTask(
        title=tpl.title, description=tpl.description,
        assignee_id=assignee_id, assigned_by=current_user.id,
        priority=tpl.default_priority or "medium", due_date=due_date,
    )
    db.session.add(t)
    db.session.flush()
    sub_titles = []
    try:
        sub_titles = json.loads(tpl.sub_tasks) if tpl.sub_tasks else []
    except json.JSONDecodeError:
        pass
    for i, st in enumerate(sub_titles):
        db.session.add(TeamTaskSubItem(team_task_id=t.id, title=st, order=i))
    _log_activity(t.id, f"Created from template: {tpl.title}")
    _notify_assignee(t, f"New task from template: {t.title}")
    db.session.commit()
    return jsonify({"ok": True, "id": t.id})


@tasks_bp.route("/team/templates/<template_id>/delete", methods=["POST"])
@login_required
def delete_template(template_id):
    template_id = _validate_id(template_id)
    if template_id is None:
        return jsonify({"ok": False}), 404
    if current_user.role not in ("admin", "hr"):
        return jsonify({"ok": False}), 403
    tpl = db.session.get(TaskTemplate, template_id)
    if not tpl:
        return jsonify({"ok": False, "error": "Not found"}), 404
    db.session.delete(tpl)
    db.session.commit()
    return jsonify({"ok": True})


@tasks_bp.route("/team/templates/<template_id>/toggle-recurring", methods=["POST"])
@login_required
def toggle_recurring(template_id):
    template_id = _validate_id(template_id)
    if template_id is None:
        return jsonify({"ok": False}), 404
    if current_user.role not in ("admin", "hr"):
        return jsonify({"ok": False}), 403
    tpl = db.session.get(TaskTemplate, template_id)
    if not tpl:
        return jsonify({"ok": False, "error": "Not found"}), 404
    day = request.form.get("day_of_month", type=int)
    if day and 1 <= day <= 28:
        tpl.day_of_month = day
        tpl.is_active = True
    else:
        tpl.day_of_month = None
        tpl.is_active = False
    db.session.commit()
    return jsonify({"ok": True, "day_of_month": tpl.day_of_month, "is_active": tpl.is_active})


@tasks_bp.route("/team/templates/generate-recurring", methods=["POST"])
@login_required
def generate_recurring_tasks():
    if current_user.role not in ("admin", "hr"):
        return jsonify({"ok": False, "error": "Not authorized"}), 403
    company_id = session.get("active_company_id")
    now = date.today()
    templates = TaskTemplate.query.filter(
        TaskTemplate.company_id == company_id,
        TaskTemplate.is_active == True,
        TaskTemplate.day_of_month != None,
    ).all()
    generated = 0
    for tpl in templates:
        if tpl.last_generated_year == now.year and tpl.last_generated_month == now.month:
            continue
        if now.day < tpl.day_of_month:
            continue
        assignee_id = tpl.default_assignee_id
        if not assignee_id:
            continue
        t = TeamTask(
            title=tpl.title, description=tpl.description,
            assignee_id=assignee_id, assigned_by=current_user.id,
            priority=tpl.default_priority or "medium",
        )
        db.session.add(t)
        db.session.flush()
        if tpl.sub_tasks:
            try:
                for st in json.loads(tpl.sub_tasks):
                    db.session.add(TeamTaskSubItem(team_task_id=t.id, title=st, order=0))
            except Exception:
                pass
        tpl.last_generated_month = now.month
        tpl.last_generated_year = now.year
        _log_activity(t.id, f"Auto-generated from recurring template: {tpl.title}")
        _notify_assignee(t, f"New recurring task: {t.title}")
        generated += 1
    if generated:
        db.session.commit()
    return jsonify({"ok": True, "generated": generated})


# --- Discussion Board ---

@tasks_bp.route("/discussions")
@login_required
def discussion_list():
    company_id = session.get("active_company_id")
    is_admin = current_user.role in ("admin", "hr")
    q = request.args.get("q", "").strip()
    filter_args = [Discussion.company_id == company_id] if company_id else []
    if q:
        filter_args.append(Discussion.title.ilike(f"%{q}%"))
    discussions = Discussion.query.filter(*filter_args).order_by(Discussion.is_pinned.desc(), Discussion.updated_at.desc()).all()
    now = datetime.utcnow()
    def time_ago(dt):
        diff = now - dt
        if diff.days > 30: return f"{diff.days//30}mo ago"
        if diff.days > 0: return f"{diff.days}d ago"
        if diff.seconds > 3600: return f"{diff.seconds//3600}h ago"
        if diff.seconds > 60: return f"{diff.seconds//60}m ago"
        return "just now"
    return render_template("tasks/discussions.html",
        discussions=discussions, is_admin=is_admin, q=q, time_ago=time_ago,
    )


@tasks_bp.route("/discussions/<discussion_id>")
@login_required
def discussion_detail(discussion_id):
    discussion_id = _validate_id(discussion_id)
    if discussion_id is None:
        flash("Invalid discussion.")
        return redirect(url_for("tasks.discussion_list"))
    d = db.session.get(Discussion, discussion_id)
    if not d:
        flash("Discussion not found.")
        return redirect(url_for("tasks.discussion_list"))
    is_admin = current_user.role in ("admin", "hr")
    now = datetime.utcnow()
    def time_ago(dt):
        diff = now - dt
        if diff.days > 30: return f"{diff.days//30}mo ago"
        if diff.days > 0: return f"{diff.days}d ago"
        if diff.seconds > 3600: return f"{diff.seconds//3600}h ago"
        if diff.seconds > 60: return f"{diff.seconds//60}m ago"
        return "just now"
    return render_template("tasks/discussion_detail.html",
        discussion=d, is_admin=is_admin, time_ago=time_ago,
        reply_url=url_for("tasks.add_discussion_reply", discussion_id=d.id),
        close_url=url_for("tasks.toggle_discussion_close", discussion_id=d.id),
        pin_url=url_for("tasks.toggle_discussion_pin", discussion_id=d.id),
        list_url=url_for("tasks.discussion_list"),
    )


@tasks_bp.route("/discussions/data/<discussion_id>")
@login_required
def discussion_data(discussion_id):
    discussion_id = _validate_id(discussion_id)
    if discussion_id is None:
        return jsonify({"ok": False}), 404
    d = db.session.get(Discussion, discussion_id)
    if not d:
        return jsonify({"ok": False}), 404
    return jsonify({
        "ok": True,
        "discussion": {
            "id": d.id, "title": d.title, "body": d.body or "",
            "author": d.author.name if d.author else "?",
            "author_id": d.author_id,
            "is_pinned": d.is_pinned, "is_closed": d.is_closed,
            "created_at": d.created_at.isoformat() if d.created_at else "",
            "reply_count": d.replies.count(),
        },
        "replies": [{
            "id": r.id, "author": r.author.name if r.author else "?",
            "body": r.body, "created_at": r.created_at.isoformat() if r.created_at else "",
        } for r in d.replies],
    })


@tasks_bp.route("/discussions/create", methods=["POST"])
@login_required
def create_discussion():
    company_id = session.get("active_company_id")
    if not company_id:
        return jsonify({"ok": False, "error": "No active company"}), 400
    title = request.form.get("title", "").strip()
    if not title:
        return jsonify({"ok": False, "error": "Title required"}), 400
    d = Discussion(
        title=title, body=request.form.get("body", "").strip() or None,
        author_id=current_user.id, company_id=company_id,
    )
    db.session.add(d)
    db.session.commit()
    return jsonify({"ok": True, "id": d.id})


@tasks_bp.route("/discussions/<discussion_id>/reply", methods=["POST"])
@login_required
def add_discussion_reply(discussion_id):
    discussion_id = _validate_id(discussion_id)
    if discussion_id is None:
        return jsonify({"ok": False}), 404
    d = db.session.get(Discussion, discussion_id)
    if not d:
        return jsonify({"ok": False, "error": "Not found"}), 404
    body = request.form.get("body", "").strip()
    if not body:
        return jsonify({"ok": False, "error": "Body required"}), 400
    r = DiscussionReply(discussion_id=d.id, author_id=current_user.id, body=body)
    db.session.add(r)
    d.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True, "reply": {
        "id": r.id, "author": current_user.name or "?", "body": r.body,
        "created_at": r.created_at.isoformat() if r.created_at else "",
    }})


@tasks_bp.route("/discussions/<discussion_id>/toggle-close", methods=["POST"])
@login_required
def toggle_discussion_close(discussion_id):
    discussion_id = _validate_id(discussion_id)
    if discussion_id is None:
        return jsonify({"ok": False}), 404
    if current_user.role not in ("admin", "hr"):
        return jsonify({"ok": False}), 403
    d = db.session.get(Discussion, discussion_id)
    if not d:
        return jsonify({"ok": False, "error": "Not found"}), 404
    d.is_closed = not d.is_closed
    d.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True, "is_closed": d.is_closed})


@tasks_bp.route("/discussions/<discussion_id>/toggle-pin", methods=["POST"])
@login_required
def toggle_discussion_pin(discussion_id):
    discussion_id = _validate_id(discussion_id)
    if discussion_id is None:
        return jsonify({"ok": False}), 404
    if current_user.role not in ("admin", "hr"):
        return jsonify({"ok": False}), 403
    d = db.session.get(Discussion, discussion_id)
    if not d:
        return jsonify({"ok": False, "error": "Not found"}), 404
    d.is_pinned = not d.is_pinned
    db.session.commit()
    return jsonify({"ok": True, "is_pinned": d.is_pinned})


# --- Notifications (global, not HR-gated) ---

@tasks_bp.route("/notifications")
@login_required
def notification_list():
    page = request.args.get("page", 1, type=int)
    per_page = 20
    pagination = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    notifications = pagination.items
    return render_template("tasks/notifications.html",
        notifications=notifications, pagination=pagination,
        read_url=url_for("tasks.notification_read", notif_id="__ID__"),
        read_all_url=url_for("tasks.notification_read_all"),
    )


@tasks_bp.route("/notifications/data")
@login_required
def notification_data():
    notifications = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(8).all()
    now = datetime.utcnow()
    def time_ago(dt):
        diff = now - dt
        if diff.days > 30: return f"{diff.days//30}mo ago"
        if diff.days > 0: return f"{diff.days}d ago"
        if diff.seconds > 3600: return f"{diff.seconds//3600}h ago"
        if diff.seconds > 60: return f"{diff.seconds//60}m ago"
        return "just now"
    return jsonify([{
        "id": n.id, "message": n.message, "link": n.link or "",
        "is_read": n.is_read, "created_at": time_ago(n.created_at),
    } for n in notifications])


@tasks_bp.route("/notifications/unread-count")
@login_required
def notification_unread_count():
    count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    return jsonify({"count": count})


@tasks_bp.route("/notifications/read/<notif_id>", methods=["POST"])
@login_required
def notification_read(notif_id):
    if not notif_id.isdigit():
        return jsonify({"ok": False}), 404
    n = db.session.get(Notification, int(notif_id))
    if n and n.user_id == current_user.id:
        n.is_read = True
        db.session.commit()
    return jsonify({"ok": True})


@tasks_bp.route("/notifications/read-all", methods=["POST"])
@login_required
def notification_read_all():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({"is_read": True})
    db.session.commit()
    return jsonify({"ok": True})


@tasks_bp.route("/notifications/clear-all", methods=["POST"])
@login_required
def notification_clear_all():
    Notification.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({"ok": True})


@tasks_bp.route("/toggle/<task_id>", methods=["POST"])
@login_required
def toggle_task(task_id):
    emp = current_user.employee
    if not emp:
        return jsonify({"ok": False, "error": "No employee profile"}), 400
    task = db.session.get(TeamTask, int(task_id))
    if not task or task.assignee_id != emp.id:
        return jsonify({"ok": False, "error": "Not found"}), 404
    if task.status == "done":
        task.status = "to_do"
        task.completed_at = None
    else:
        task.status = "done"
        task.completed_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True, "status": task.status})

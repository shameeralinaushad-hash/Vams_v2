import os, json
from datetime import date, datetime
from flask import Blueprint, request, jsonify, session
from flask_login import login_required, current_user
from models import db, PersonalItem, Order, Client, ClientCompanyLink, Employee, Expense, Invoice, Company

ai_bp = Blueprint("ai", __name__, url_prefix="/ai")


def _build_context(page, uid):
    today = date.today()
    cid = session.get("active_company_id")

    # ---- Always include company overview ----
    company_name = "N/A"
    if cid:
        co = db.session.get(Company, cid)
        if co:
            company_name = co.name

    ctx = {
        "page": page,
        "today": today.isoformat(),
        "company": company_name,
    }

    # ---- Company-wide stats (always available) ----
    if cid:
        orders = Order.query.filter(Order.company_id == cid).all()
        ctx["total_orders"] = len(orders)
        ctx["won_orders"] = sum(1 for o in orders if o.status == "PO Received")
        ctx["pending_orders"] = sum(1 for o in orders if o.status == "Pending")
        ctx["not_received"] = sum(1 for o in orders if o.status == "Not Received")

        invoices = Invoice.query.join(Order).filter(Order.company_id == cid).all()
        active_invs = [inv for inv in invoices if inv.is_current and not inv.is_cancelled()]
        ctx["total_invoiced"] = round(sum(inv.net_revenue() for inv in active_invs), 2)
        ctx["outstanding"] = round(sum(inv.balance_due() for inv in active_invs), 2)
        ctx["overdue_30plus"] = len([inv for inv in invoices if not inv.is_fully_paid() and not inv.is_cancelled() and inv.days_overdue() > 30])

        ctx["total_expenses"] = round(sum(e.amount for e in Expense.query.filter_by(company_id=cid).all()), 2)
        ctx["estimated_profit"] = round(ctx["total_invoiced"] - ctx["total_expenses"], 2)

        ctx["total_clients"] = ClientCompanyLink.query.filter(ClientCompanyLink.company_id == cid).count()
        ctx["total_employees"] = Employee.query.filter(Employee.company_id == cid, Employee.is_active == True).count()

        recent = sorted(orders, key=lambda o: o.created_at, reverse=True)[:5]
        ctx["recent_orders"] = [f"{o.order_number} ({o.status})" for o in recent]

    # ---- Page-specific context ----
    if page == "tasks/mine":
        all_items = PersonalItem.query.filter(PersonalItem.user_id == uid).order_by(PersonalItem.created_at.desc()).limit(50).all()
        lines = []
        lanes = {"task": "Tasks", "goal": "Goals", "project": "Works", "future_plan": "Ideas"}
        for lane_label, heading in lanes.items():
            items = [i for i in all_items if i.lane == lane_label]
            if items:
                lines.append(f"## {heading}")
                for i in items:
                    due = f" due:{i.due_date}" if i.due_date else ""
                    done = " [DONE]" if i.status == "done" else ""
                    pri = f" ({i.priority})" if i.priority != "medium" else ""
                    cat = f" #{i.category}" if i.category else ""
                    lines.append(f"  - {i.title}{pri}{due}{cat}{done}")
        ctx["overdue"] = sum(1 for i in all_items if i.lane == "task" and i.status != "done" and i.due_date and i.due_date < today)
        ctx["done_today"] = sum(1 for i in all_items if i.status == "done" and i.completed_at and i.completed_at.date() == today)
        ctx["items"] = "\n".join(lines) if lines else "No items yet."
        ctx["total_items"] = len(all_items)
        ctx["no_due"] = sum(1 for i in all_items if i.lane == "task" and i.status != "done" and not i.due_date)
        ctx["page_label"] = "your personal tasks, goals, works, and ideas"

    elif page == "dashboard":
        ctx["page_label"] = "the dashboard (business overview)"

    elif page in ("orders",):
        ctx["page_label"] = "the orders page"

    elif page in ("clients",):
        ctx["page_label"] = "the clients page"

    elif page in ("hr",):
        ctx["page_label"] = "the human resources page"

    elif page in ("accounts", "expenses"):
        ctx["page_label"] = "the accounts & expenses page"

    elif page in ("catalog",):
        ctx["page_label"] = "the item catalog page"

    elif page in ("reports",):
        ctx["page_label"] = "the reports page"

    elif page in ("documents", "quotations", "invoices"):
        ctx["page_label"] = "the documents page"

    elif page in ("projects",):
        ctx["page_label"] = "the projects page"

    elif page in ("search",):
        ctx["page_label"] = "the search page"

    else:
        ctx["page_label"] = "the system"

    return ctx


def _build_system_prompt(ctx):
    today = ctx["today"]

    prompt = (
        f"You are a versatile AI assistant for '{ctx['company']}'. "
        f"Today is {today}. The user is on {ctx['page_label']}.\n\n"
        f"You can answer ANY question — business-related or general knowledge "
        f"(e.g. current affairs, history, definitions, calculations, explanations). "
        f"You also have access to the user's live business data below.\n\n"
        f"=== CURRENT BUSINESS SNAPSHOT ===\n"
        f"Orders: {ctx.get('total_orders',0)} total ({ctx.get('won_orders',0)} won, "
        f"{ctx.get('pending_orders',0)} pending, {ctx.get('not_received',0)} not received)\n"
        f"Invoiced: ${ctx.get('total_invoiced',0):,}  |  Outstanding: ${ctx.get('outstanding',0):,}\n"
        f"Overdue 30+ days: {ctx.get('overdue_30plus',0)}\n"
        f"Expenses: ${ctx.get('total_expenses',0):,}  |  Est. Profit: ${ctx.get('estimated_profit',0):,}\n"
        f"Clients: {ctx.get('total_clients',0)}  |  Active Employees: {ctx.get('total_employees',0)}\n"
    )

    if ctx.get("recent_orders"):
        prompt += "Recent orders:\n" + "\n".join(f"  - {o}" for o in ctx["recent_orders"][:5]) + "\n"

    if ctx.get("items"):
        prompt += (
            f"\n=== YOUR PERSONAL ITEMS ===\n"
            f"Total: {ctx.get('total_items',0)} ({ctx.get('overdue',0)} overdue, "
            f"{ctx.get('done_today',0)} done today, {ctx.get('no_due',0)} without due dates)\n"
            + ctx["items"]
        )

    prompt += (
        "\n\n=== COMMANDS ===\n"
        "/focus  /next  /breakdown  /plan  /balance  /prioritize\n"
        "/cleanup  /motivate  /cluster  /review  /estimate  /describe\n"
        "Use business data above when relevant. For general questions, answer from your own knowledge. "
        "Respond in plain text (no markdown). Be concise and helpful."
    )

    return prompt


@ai_bp.route("/chat", methods=["POST"])
@login_required
def ai_chat():
    message = request.form.get("message", "").strip()
    conversation_raw = request.form.get("conversation", "[]")
    page = request.form.get("page", "general")
    page_title = request.form.get("page_title", "")

    if not message:
        return jsonify({"ok": False, "error": "Message required"}), 400

    try:
        conv = json.loads(conversation_raw) if isinstance(conversation_raw, str) else conversation_raw
    except (json.JSONDecodeError, TypeError):
        conv = []
    if not isinstance(conv, list):
        conv = []

    ctx = _build_context(page, current_user.id)
    system_prompt = _build_system_prompt(ctx)

    messages = [{"role": "system", "content": system_prompt}]
    for c in conv[-15:]:
        messages.append({"role": c.get("role", "user"), "content": c.get("content", "")})
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
            max_tokens=800,
        )
        reply = response.choices[0].message.content.strip()
        return jsonify({"ok": True, "reply": reply})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

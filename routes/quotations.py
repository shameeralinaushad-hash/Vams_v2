import os
import json
from datetime import date, datetime
from flask import Blueprint, render_template, request, redirect, url_for, current_app, flash, session, jsonify
from werkzeug.utils import secure_filename
from models import db, Quotation, QuotationLineItem, QuotationAnnexure, CatalogItem, Order, ClientDocSequence, PriceHistory, CustomField
from utils import get_order_folder, validate_upload, delete_file_if_exists
from pdf_templates.quotation_template import generate_quotation_pdf
from audit import log_action
from numbering import build_quotation_number, build_technical_offer_number
from permissions import permission_required
from ml.tender_extractor import extract_items_from_file
from socket_events import emit_company, emit_dashboard_update

quotations_bp = Blueprint("quotations", __name__, url_prefix="/quotations")

DEFAULT_TERMS = "1. Delivery within 5 days after order confirmation.\n2. This quotation is valid for 30 days from the date of issuance."

TECHNICAL_COLUMN_PRESET = ["sr", "part_no", "nomenclature", "unit", "qty", "specs", "photo", "coo", "quoted", "remark"]


def get_or_create_catalog_item(description):
    description = description.strip()
    item = CatalogItem.query.filter(db.func.lower(CatalogItem.description) == description.lower()).first()
    if not item:
        item = CatalogItem(description=description)
        db.session.add(item)
        db.session.commit()
    return item


def _process_item_photos(file_list, expected_count):
    """Saves uploaded line-item photos to static/uploads/quotation_photos and
    returns a list aligned with the item rows ('' when nothing uploaded)."""
    allowed = {"png", "jpg", "jpeg", "gif", "webp"}
    results = [""] * expected_count
    for i, f in enumerate(file_list[:expected_count]):
        if f and f.filename and validate_upload(f, allowed):
            folder = os.path.join(current_app.root_path, "static", "uploads", "quotation_photos")
            os.makedirs(folder, exist_ok=True)
            safe = secure_filename(f.filename)
            name = f"q_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{i}_{safe}"
            rel = os.path.join("uploads", "quotation_photos", name)
            f.save(os.path.join(folder, name))
            results[i] = rel.replace("\\", "/")
    return results


def _parse_quotation_form(order):
    doc_type = "commercial" if request.form.get("doc_type") != "technical" else "technical"
    part_nos = request.form.getlist("item_part_no")
    descriptions = request.form.getlist("item_description")
    units = request.form.getlist("item_unit")
    qtys = request.form.getlist("item_qty")
    prices = request.form.getlist("item_price")
    taxes = request.form.getlist("item_tax")
    specs = request.form.getlist("item_specs")
    coos = request.form.getlist("item_coo")
    quoted = request.form.getlist("item_quoted")
    remarks = request.form.getlist("item_remark")
    existing_photos = request.form.getlist("item_photo_path")
    tax_amount = float(request.form.get("tax_amount", "0") or 0)
    discount_amount = float(request.form.get("discount_amount", "0") or 0)
    installation_charges = float(request.form.get("installation_charges", "0") or 0)
    transportation_charges = float(request.form.get("transportation_charges", "0") or 0)
    skip_letterhead = request.form.get("skip_letterhead") == "on"

    try:
        photo_size_mm = int(float(request.form.get("photo_size_mm", "0") or 0))
    except (TypeError, ValueError):
        photo_size_mm = 0
    photo_size_mm = 18 if photo_size_mm < 6 or photo_size_mm > 150 else photo_size_mm

    photos = _process_item_photos(request.files.getlist("item_photo"), len(part_nos))
    photo_paths = [photos[i] if photos[i] else (existing_photos[i].strip() if i < len(existing_photos) else "") for i in range(len(part_nos))]

    col_keys = ["sr", "part_no", "nomenclature", "unit", "qty", "price", "gst", "total"]

    custom_fields = CustomField.query.filter_by(
        company_id=order.company_id, doc_type="quotation", is_active=True
    ).order_by(CustomField.sort_order.asc(), CustomField.id.asc()).all()
    show_cf = set(request.form.getlist("show_custom_field"))

    field_by_id = {f.id: f for f in custom_fields}
    field_by_key = {str(f.id): f for f in custom_fields}

    new_field_defs = []
    new_fields_raw = request.form.get("new_fields_json", "")
    if new_fields_raw:
        try:
            new_field_defs = json.loads(new_fields_raw)
        except ValueError:
            new_field_defs = []
    for d in new_field_defs:
        if not isinstance(d, dict) or not (d.get("key") or "").strip() or not (d.get("name") or "").strip():
            continue
        name = d["name"].strip()
        ftype = "number" if d.get("type") == "number" else "text"
        field = CustomField.query.filter_by(
            company_id=order.company_id, doc_type="quotation", name=name
        ).first()
        if not field:
            field = CustomField(
                company_id=order.company_id, doc_type="quotation",
                name=name, field_type=ftype, is_active=True,
            )
            db.session.add(field)
            db.session.flush()
        field_by_key[d["key"]] = field
        field_by_id[field.id] = field

    column_order = request.form.get("column_order", "")
    enabled_cf = []
    if column_order:
        col_keys = []
        for k in column_order.split("|"):
            k = k.strip()
            if not k:
                continue
            if k.startswith("custom_"):
                f = field_by_key.get(k[len("custom_"):])
                if f:
                    if f.id not in enabled_cf:
                        enabled_cf.append(f.id)
                    k = f"custom_{f.id}"
            col_keys.append(k)
    else:
        col_keys = TECHNICAL_COLUMN_PRESET if doc_type == "technical" else ["sr", "part_no", "nomenclature", "unit", "qty", "price", "gst", "total"]
        enabled_cf = [f.id for f in custom_fields if str(f.id) in show_cf]
        for d in new_field_defs:
            f = field_by_key.get(d["key"])
            if f and d["key"] in show_cf and f.id not in enabled_cf:
                enabled_cf.append(f.id)

    for d in new_field_defs:
        f = field_by_key.get(d["key"])
        if f and d["key"] in show_cf and f.id not in enabled_cf:
            enabled_cf.append(f.id)

    custom_field_map = {str(fid): field_by_id[fid].name for fid in enabled_cf if fid in field_by_id}
    custom_values_lists = {}
    for ckey, f in field_by_key.items():
        if f.id in enabled_cf:
            custom_values_lists[str(f.id)] = request.form.getlist(f"item_custom_{ckey}")

    if not column_order:
        for fid in enabled_cf:
            col_keys.append(f"custom_{fid}")

    visible_columns = None
    column_widths = {}
    widths_raw = request.form.get("column_widths_json", "")
    if widths_raw:
        try:
            parsed_widths = json.loads(widths_raw)
        except ValueError:
            parsed_widths = {}
        if isinstance(parsed_widths, dict):
            known_builtin = {"sr", "part_no", "nomenclature", "unit", "qty", "price", "gst", "total", "specs", "photo", "coo", "quoted", "remark"}
            for k, v in parsed_widths.items():
                if not isinstance(k, str):
                    continue
                if not (k.startswith("custom_") or k in known_builtin):
                    continue
                try:
                    val = int(round(float(v)))
                except (TypeError, ValueError):
                    continue
                if 20 <= val <= 2000:
                    column_widths[k] = val

    default_keys = ["sr", "part_no", "nomenclature", "unit", "qty", "price", "gst", "total"]
    technical_cols = ["sr", "part_no", "nomenclature", "unit", "qty", "specs", "photo", "coo", "quoted", "remark"]
    if enabled_cf or column_widths or (col_keys and col_keys != default_keys) or photo_size_mm:
        visible_columns = {"columns": col_keys}
        if custom_field_map:
            visible_columns["custom_fields"] = custom_field_map
        if column_widths:
            visible_columns["column_widths"] = column_widths
        if photo_size_mm:
            visible_columns["photo_size_mm"] = photo_size_mm

    default_cf_ids = []
    for cid in request.form.getlist("cf_default"):
        cid = cid.strip()
        f = field_by_key.get(cid)
        if f and f.id not in default_cf_ids:
            default_cf_ids.append(f.id)
    if default_cf_ids:
        config = order.company.pdf_columns or {}
        existing = config.get("custom_fields_default") or []
        merged = list(dict.fromkeys([int(i) for i in existing] + default_cf_ids))
        config["custom_fields_default"] = merged
        order.company.pdf_columns = config

    quote_number = request.form.get("quote_number", "").strip()
    quote_date_str = request.form.get("quote_date", "")
    quote_date_val = datetime.strptime(quote_date_str, "%Y-%m-%d").date() if quote_date_str else date.today()

    recipient = request.form.get("recipient", "").strip()
    subject = request.form.get("subject", "").strip()
    client_ref_number = request.form.get("client_ref_number", "").strip()
    terms_conditions = request.form.get("terms_conditions", "").strip()

    # Annexure data
    annexure_count = int(request.form.get("annexure_count", "0") or 0)
    annexure_names = request.form.getlist("annexure_name")
    annexure_page_breaks = request.form.getlist("annexure_page_break")
    annexure_show_totals = request.form.getlist("annexure_show_totals")
    item_annexure_raw = request.form.get("item_annexure", "")
    item_annexure_map = [x.strip() for x in item_annexure_raw.split(",") if x.strip()] if item_annexure_raw else []
    main_show_totals = request.form.get("main_show_totals", "on") == "on"

    annexures = []
    for i in range(annexure_count):
        name = annexure_names[i].strip() if i < len(annexure_names) else f"Annexure {i}"
        page_break = annexure_page_breaks[i] == "on" if i < len(annexure_page_breaks) else False
        show_totals = annexure_show_totals[i] == "on" if i < len(annexure_show_totals) else True
        annexures.append({"name": name, "page_break_before": page_break, "show_totals": show_totals, "sort_order": i})

    return {
        "doc_type": doc_type,
        "part_nos": part_nos, "descriptions": descriptions, "units": units,
        "qtys": qtys, "prices": prices, "taxes": taxes,
        "specs": specs, "coos": coos, "quoted": quoted, "remarks": remarks,
        "photo_paths": photo_paths,
        "tax_amount": tax_amount, "discount_amount": discount_amount,
        "installation_charges": installation_charges, "transportation_charges": transportation_charges,
        "skip_letterhead": skip_letterhead,
        "photo_size_mm": photo_size_mm,
        "col_keys": col_keys, "custom_field_map": custom_field_map,
        "custom_values_lists": custom_values_lists,
        "visible_columns": visible_columns, "column_widths": column_widths,
        "default_cf_ids": default_cf_ids,
        "quote_number": quote_number, "quote_date": quote_date_val,
        "recipient": recipient, "subject": subject,
        "client_ref_number": client_ref_number, "terms_conditions": terms_conditions,
        "annexures": annexures, "item_annexure_map": item_annexure_map,
        "show_totals": main_show_totals,
    }


def _build_quotation_line_items(quotation, data, order):
    line_items = []

    # Create annexure records
    annexure_records = {}
    for i, ann_data in enumerate(data.get("annexures", [])):
        ann = QuotationAnnexure(
            quotation_id=quotation.id,
            name=ann_data["name"],
            sort_order=ann_data["sort_order"],
            page_break_before=ann_data.get("page_break_before", False),
            show_totals=ann_data.get("show_totals", True),
        )
        db.session.add(ann)
        db.session.flush()
        annexure_records[i + 1] = ann

    item_map = data.get("item_annexure_map") or []

    for idx, (part_no, desc, unit, qty, price, tax) in enumerate(
            zip(data["part_nos"], data["descriptions"], data["units"],
                data["qtys"], data["prices"], data["taxes"])):
        if not desc.strip():
            continue
        catalog_item = get_or_create_catalog_item(desc)
        unit_price = float(price or 0)
        is_technical = data.get("doc_type") == "technical"

        custom_values = {}
        for cf_id, values in data["custom_values_lists"].items():
            value = values[idx].strip() if idx < len(values) else ""
            if value:
                custom_values[cf_id] = value

        specs = data.get("specs") or []
        coos = data.get("coos") or []
        quoted = data.get("quoted") or []
        remarks = data.get("remarks") or []
        photos = data.get("photo_paths") or []

        # Determine annexure for this item
        annexure_id = None
        if idx < len(item_map):
            ann_idx = int(item_map[idx] or 0)
            if ann_idx > 0 and ann_idx in annexure_records:
                annexure_id = annexure_records[ann_idx].id

        li = QuotationLineItem(
            quotation_id=quotation.id,
            catalog_item_id=catalog_item.id,
            annexure_id=annexure_id,
            part_no=part_no.strip() if part_no else "",
            description=desc.strip(),
            unit=unit.strip() if unit else "Nos",
            qty=float(qty or 0),
            unit_price=unit_price,
            tax_percent=float(tax or 0),
            custom_values=custom_values or None,
            specs=specs[idx].strip() if idx < len(specs) and specs[idx] else None,
            coo=coos[idx].strip() if idx < len(coos) and coos[idx] else None,
            quoted=quoted[idx].strip() if idx < len(quoted) and quoted[idx] else None,
            remark=remarks[idx].strip() if idx < len(remarks) and remarks[idx] else None,
            photo_path=photos[idx] if idx < len(photos) and photos[idx] else None,
        )
        db.session.add(li)
        line_items.append(li)

        if not is_technical:
            db.session.add(PriceHistory(
                catalog_item_id=catalog_item.id,
                client_id=order.client_id,
                company_id=order.company_id,
                price=unit_price,
                quoted_date=data["quote_date"],
                source_doc="quotation",
            ))
    return line_items


def _write_quotation_pdf(order, quotation, line_items):
    version_suffix = f"_v{quotation.pdf_version}" if (quotation.pdf_version or 1) > 1 else ""
    folder = get_order_folder(current_app, order)
    filename = f"Quotation_{quotation.quote_number.replace('/', '-')}{version_suffix}.pdf"
    output_path = os.path.join(folder, filename)

    generate_quotation_pdf(
        order.company, order.client, quotation, line_items, output_path,
        skip_letterhead=bool(quotation.skip_letterhead)
    )

    safe_title = secure_filename(order.title) if order.title else "untitled"
    folder_name = f"{order.id}_{safe_title}"
    quotation.pdf_path = f"documents/company_{order.company_id}/{folder_name}/{filename}"
    db.session.commit()


@quotations_bp.route("/")
def list_quotations():
    company_id = session.get("active_company_id")
    if not company_id:
        flash("Select an active company first.")
        return redirect(url_for("companies.list_companies"))

    page = request.args.get("page", 1, type=int)
    pagination = (
        Quotation.query.join(Order)
        .filter(Order.company_id == company_id)
        .options(db.contains_eager(Quotation.order).joinedload(Order.client))
        .order_by(Quotation.id.desc())
        .paginate(page=page, per_page=25, error_out=False)
    )
    return render_template("quotations/list.html", quotations=pagination.items, pagination=pagination)


@quotations_bp.route("/order/<int:order_id>/create", methods=["GET", "POST"])
def create_quotation(order_id):
    order = Order.query.get_or_404(order_id)
    doc_type = "commercial" if request.args.get("doc_type", "commercial") != "technical" else "technical"
    seq_doc_type = "technical" if doc_type == "technical" else "quotation"
    seq = ClientDocSequence.get_or_create(order.company_id, order.client_id, seq_doc_type)

    if request.method == "POST":
        data = _parse_quotation_form(order)
        doc_type = data["doc_type"]

        quote_number = data["quote_number"]
        if quote_number:
            if seq:
                seq.get_next_raw_number()
        else:
            raw = seq.get_next_raw_number() if seq else order.id
            if doc_type == "technical":
                quote_number = build_technical_offer_number(order.company, order.client, raw)
            else:
                quote_number = build_quotation_number(order.company, order.client, raw)

        # Mark existing quotations of the SAME type as revisions, so a
        # commercial and a technical current quotation can coexist.
        existing = Quotation.query.filter_by(order_id=order.id, doc_type=doc_type).all()
        for old_q in existing:
            old_q.is_current = False
        db.session.commit()

        quotation = Quotation(
            order_id=order.id, quote_number=quote_number, quote_date=data["quote_date"],
            recipient=data["recipient"], subject=data["subject"], client_ref_number=data["client_ref_number"],
            terms_conditions=data["terms_conditions"],
            is_current=True, pdf_version=1,
            doc_type=doc_type,
            tax_amount=data["tax_amount"],
            discount_amount=data["discount_amount"], installation_charges=data["installation_charges"],
            transportation_charges=data["transportation_charges"],
            skip_letterhead=data["skip_letterhead"],
            show_totals=data.get("show_totals", True),
            visible_columns=data["visible_columns"],
        )
        db.session.add(quotation)
        db.session.commit()

        line_items = _build_quotation_line_items(quotation, data, order)
        db.session.commit()

        _write_quotation_pdf(order, quotation, line_items)

        log_action("create_quotation", "Quotation", quotation.id, f"Created quotation {quote_number} for {order.client.name}")

        emit_company("list_refresh", {"section": "quotations"}, order.company_id)
        emit_dashboard_update(order.company_id)
        return redirect(url_for("orders.view_order", order_id=order.id))

    raw = seq.peek_next_raw_number() if seq else order.id
    if doc_type == "technical":
        suggested_number = build_technical_offer_number(order.company, order.client, raw)
    else:
        suggested_number = build_quotation_number(order.company, order.client, raw)

    default_recipient = order.client.name
    if getattr(order.client, 'address', None):
        default_recipient += f"\n{order.client.address}"

    custom_fields = CustomField.query.filter_by(
        company_id=order.company_id, doc_type="quotation", is_active=True
    ).order_by(CustomField.sort_order.asc(), CustomField.id.asc()).all()

    company_cols = getattr(order.company, "pdf_columns", None) or {}
    if doc_type == "technical":
        default_col_keys = TECHNICAL_COLUMN_PRESET
    else:
        default_col_keys = company_cols.get("quotation")
    default_cf_ids = set(company_cols.get("custom_fields_default") or [])
    custom_fields_json = [
        {"id": f.id, "name": f.name, "field_type": f.field_type, "default": f.id in default_cf_ids}
        for f in custom_fields
    ]

    return render_template(
        "quotations/create.html", order=order, doc_type=doc_type,
        suggested_number=suggested_number, today=date.today().isoformat(),
        default_terms=DEFAULT_TERMS, default_recipient=default_recipient,
        custom_fields=custom_fields, custom_fields_json=custom_fields_json,
        default_col_keys=default_col_keys, default_cf_ids=default_cf_ids,
        photo_size_mm=18,
    )


@quotations_bp.route("/edit/<int:quotation_id>", methods=["GET", "POST"])
def edit_quotation(quotation_id):
    quotation = Quotation.query.get_or_404(quotation_id)
    order = quotation.order

    if request.method == "POST":
        data = _parse_quotation_form(order)

        quotation.quote_number = data["quote_number"] or quotation.quote_number
        quotation.quote_date = data["quote_date"]
        quotation.doc_type = data["doc_type"]
        quotation.recipient = data["recipient"]
        quotation.subject = data["subject"]
        quotation.client_ref_number = data["client_ref_number"]
        quotation.terms_conditions = data["terms_conditions"]
        quotation.tax_amount = data["tax_amount"]
        quotation.discount_amount = data["discount_amount"]
        quotation.installation_charges = data["installation_charges"]
        quotation.transportation_charges = data["transportation_charges"]
        quotation.skip_letterhead = data["skip_letterhead"]
        quotation.show_totals = data.get("show_totals", True)
        quotation.visible_columns = data["visible_columns"]
        quotation.pdf_version = (quotation.pdf_version or 1) + 1

        old_photo_paths = {li.photo_path for li in quotation.line_items if li.photo_path}

        # Delete old annexures (cascade deletes line_items)
        for ann in list(quotation.annexures):
            db.session.delete(ann)
        db.session.flush()

        for li in list(quotation.line_items):
            db.session.delete(li)
        db.session.flush()

        line_items = _build_quotation_line_items(quotation, data, order)
        db.session.commit()

        kept_photo_paths = {li.photo_path for li in line_items if li.photo_path}
        for path in old_photo_paths - kept_photo_paths:
            delete_file_if_exists(os.path.join(current_app.root_path, "static", path.lstrip("/")))

        _write_quotation_pdf(order, quotation, line_items)

        log_action("edit_quotation", "Quotation", quotation.id,
                   f"Edited quotation {quotation.quote_number} for {order.client.name}")

        flash("Quotation updated.")
        emit_company("list_refresh", {"section": "quotations"}, order.company_id)
        emit_dashboard_update(order.company_id)
        return redirect(url_for("orders.view_order", order_id=order.id))

    custom_fields = CustomField.query.filter_by(
        company_id=order.company_id, doc_type="quotation", is_active=True
    ).order_by(CustomField.sort_order.asc(), CustomField.id.asc()).all()

    vc = quotation.visible_columns or {}
    col_keys = vc.get("columns") or ["sr", "part_no", "nomenclature", "unit", "qty", "price", "gst", "total"]
    cf_map = vc.get("custom_fields") or {}
    custom_fields_json = [
        {"id": f.id, "name": f.name, "field_type": f.field_type, "default": str(f.id) in cf_map}
        for f in custom_fields
    ]
    column_widths = vc.get("column_widths") or {}

    default_recipient = order.client.name
    if getattr(order.client, "address", None):
        default_recipient += f"\n{order.client.address}"

    return render_template(
        "quotations/create.html", order=order, quotation=quotation,
        doc_type=quotation.doc_type or "commercial",
        suggested_number=quotation.quote_number, today=quotation.quote_date.isoformat(),
        default_recipient=quotation.recipient or default_recipient,
        default_terms=quotation.terms_conditions or DEFAULT_TERMS,
        custom_fields=custom_fields, custom_fields_json=custom_fields_json,
        default_col_keys=col_keys, default_cf_ids=set(cf_map.keys()),
        column_widths=column_widths,
        photo_size_mm=vc.get("photo_size_mm") or 18,
        annexures=quotation.annexures,
    )


@quotations_bp.route("/delete/<int:quotation_id>", methods=["POST"])
@permission_required("delete_documents")
def delete_quotation(quotation_id):
    quotation = Quotation.query.get_or_404(quotation_id)
    order_id = quotation.order_id
    was_current = quotation.is_current
    quote_number = quotation.quote_number
    company_id = quotation.order.company_id

    if quotation.pdf_path:
        full_path = os.path.join(current_app.root_path, "static", quotation.pdf_path)
        if os.path.exists(full_path):
            os.remove(full_path)

    db.session.delete(quotation)
    db.session.commit()

    if was_current:
        remaining = Quotation.query.filter_by(order_id=order_id, doc_type=quotation.doc_type).order_by(Quotation.id.desc()).first()
        if remaining:
            remaining.is_current = True
            db.session.commit()

    log_action("delete_quotation", "Quotation", quotation_id, f"Deleted quotation {quote_number}")

    flash("Quotation deleted.")
    emit_company("list_refresh", {"section": "quotations"}, company_id)
    emit_dashboard_update(company_id)
    return redirect(url_for("orders.view_order", order_id=order_id))


@quotations_bp.route("/regenerate/<int:quotation_id>", methods=["POST"])
def regenerate_quotation(quotation_id):
    quotation = Quotation.query.get_or_404(quotation_id)
    order = quotation.order
    quotation_id = quotation.id

    def _generate():
        with current_app.app_context():
            q = db.session.get(Quotation, quotation_id)
            if not q:
                return
            o = q.order
            q.pdf_version = (q.pdf_version or 1) + 1
            version_suffix = f"_v{q.pdf_version}" if q.pdf_version > 1 else ""
            folder = get_order_folder(current_app, o)
            filename = f"Quotation_{q.quote_number.replace('/', '-')}{version_suffix}.pdf"
            output_path = os.path.join(folder, filename)
            generate_quotation_pdf(
                o.company, o.client, q, q.line_items, output_path,
                skip_letterhead=bool(q.skip_letterhead)
            )
            safe_title = secure_filename(o.title) if o.title else "untitled"
            folder_name = f"{o.id}_{safe_title}"
            q.pdf_path = f"documents/company_{o.company_id}/{folder_name}/{filename}"
            db.session.commit()

    from background import run_in_background
    run_in_background(_generate, _app=current_app._get_current_object())

    flash("Quotation PDF generating in background. It will be ready shortly.")
    return redirect(url_for("orders.view_order", order_id=order.id))


# =========================================================================
# EXTRACTION ROUTES
# =========================================================================

def _save_extracted_photos(items):
    """Writes any photo_bytes the extractor attached to items onto disk
    under static/uploads/quotation_photos (same folder _process_item_photos
    uses for manual uploads), and swaps the raw bytes for a servable
    relative path. Raw bytes are never sent to jsonify() — they aren't
    JSON-serializable and the client only needs a URL it can preview."""
    folder = os.path.join(current_app.root_path, "static", "uploads", "quotation_photos")
    for i, item in enumerate(items):
        photo_bytes = item.pop("photo_bytes", None)
        photo_ext = item.pop("photo_ext", None)
        if not photo_bytes:
            continue
        os.makedirs(folder, exist_ok=True)
        name = f"extract_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{i}.{photo_ext or 'jpg'}"
        with open(os.path.join(folder, name), "wb") as f:
            f.write(photo_bytes)
        item["photo_path"] = os.path.join("uploads", "quotation_photos", name).replace("\\", "/")


@quotations_bp.route("/extract-from-pdf", methods=["POST"])
def extract_from_pdf():
    """Standard Rule-Based Extraction with Groq AI Fallback."""
    file = request.files.get("tender_file")
    doc_type = "commercial" if request.form.get("doc_type", "commercial") != "technical" else "technical"
    if not file or not file.filename:
        return jsonify({"items": [], "error": "Please select a file to upload."})

    allowed_exts = {"pdf", "png", "jpg", "jpeg", "webp", "xlsx", "xls", "docx", "doc"}
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""

    if ext not in allowed_exts:
        return jsonify({
            "items": [],
            "error": "Supported file types: PDF, Images (PNG/JPG), Excel (.xlsx/.xls), Word (.docx/.doc)"
        })

    # Photos are only worth pairing for technical offers (that's the only
    # doc type with a Photo column), and only make sense for PDFs, which is
    # what _attach_photos_to_items's heading-number matching assumes.
    want_photos = doc_type == "technical" and ext == "pdf"
    items = extract_items_from_file(file, file.filename, use_groq_fallback=True, force_groq=False,
                                     include_photos=want_photos)
    if doc_type == "technical" and items:
        for item in items:
            item["unit_price"] = 0.0
    if want_photos and items:
        _save_extracted_photos(items)

    if not items:
        return jsonify({
            "items": [],
            "error": "Couldn't extract items from this file. You may need to enter items manually."
        })

    # Collect unique annexure names from extracted items
    annexure_names = list(dict.fromkeys(
        item.get("annexure", "") for item in items if item.get("annexure")
    ))

    return jsonify({"items": items, "error": None, "annexures": annexure_names})


@quotations_bp.route("/extract-with-groq", methods=["POST"])
def extract_with_groq():
    """Explicit Groq AI Extraction (chunked/token-safe backup provider)."""
    file = request.files.get("tender_file")
    doc_type = "commercial" if request.form.get("doc_type", "commercial") != "technical" else "technical"
    if not file or not file.filename:
        return jsonify({"items": [], "error": "Please select a file to upload."})

    allowed_exts = {"pdf", "png", "jpg", "jpeg", "webp", "xlsx", "xls", "docx", "doc"}
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""

    if ext not in allowed_exts:
        return jsonify({
            "items": [],
            "error": "Supported file types: PDF, Images (PNG/JPG), Excel (.xlsx/.xls), Word (.docx/.doc)"
        })

    items = extract_items_from_file(file, file.filename, force_groq=True)
    if doc_type == "technical" and items:
        for item in items:
            item["unit_price"] = 0.0

    # Same reasoning as the Gemini route: Groq's vision model reads the
    # PDF/image directly and doesn't touch embedded photo objects, so
    # pair photos separately.
    want_photos = doc_type == "technical" and ext == "pdf"
    if want_photos and items:
        try:
            from ml.tender_extractor import (
                _attach_photos_by_position, _extract_images_from_pdf,
                _attach_photos_to_items, _MIN_IMG_DIM,
            )
            file.stream.seek(0)
            _attach_photos_by_position(items, file.stream)
            if any(not it.get("photo_bytes") for it in items):
                file.stream.seek(0)
                photos = _extract_images_from_pdf(file.stream, _MIN_IMG_DIM, None, True)
                _attach_photos_to_items(items, photos)
            _save_extracted_photos(items)
        except Exception as e:
            current_app.logger.warning(f"Photo pairing skipped for Groq extraction: {e}")

    if not items:
        from ml.tender_extractor import _last_extraction_error
        error_msg = _last_extraction_error or "Groq AI was unable to extract items or no valid line items were found."
        return jsonify({
            "items": [],
            "error": error_msg
        })

    annexure_names = list(dict.fromkeys(
        item.get("annexure", "") for item in items if item.get("annexure")
    ))

    return jsonify({"items": items, "error": None, "annexures": annexure_names})


@quotations_bp.route("/extract-with-gemini", methods=["POST"])
def extract_with_gemini():
    """Direct Multimodal Gemini AI Extraction."""
    file = request.files.get("tender_file")
    doc_type = "commercial" if request.form.get("doc_type", "commercial") != "technical" else "technical"
    if not file or not file.filename:
        return jsonify({"items": [], "error": "Please select a file to upload."})

    allowed_exts = {"pdf", "png", "jpg", "jpeg", "webp", "xlsx", "xls", "docx", "doc"}
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""

    if ext not in allowed_exts:
        return jsonify({
            "items": [],
            "error": "Supported file types: PDF, Images (PNG/JPG), Excel (.xlsx/.xls), Word (.docx/.doc)"
        })

    items = extract_items_from_file(file, file.filename, force_gemini=True)
    if doc_type == "technical" and items:
        for item in items:
            item["unit_price"] = 0.0

    # Same reasoning as the Groq route: Gemini reads the PDF natively and
    # doesn't touch embedded photo objects, so pair photos separately.
    want_photos = doc_type == "technical" and ext == "pdf"
    if want_photos and items:
        try:
            from ml.tender_extractor import (
                _attach_photos_by_position, _extract_images_from_pdf,
                _attach_photos_to_items, _MIN_IMG_DIM,
            )
            file.stream.seek(0)
            _attach_photos_by_position(items, file.stream)
            if any(not it.get("photo_bytes") for it in items):
                file.stream.seek(0)
                photos = _extract_images_from_pdf(file.stream, _MIN_IMG_DIM, None, True)
                _attach_photos_to_items(items, photos)
            _save_extracted_photos(items)
        except Exception as e:
            current_app.logger.warning(f"Photo pairing skipped for Gemini extraction: {e}")

    if not items:
        from ml.tender_extractor import _last_extraction_error
        error_msg = _last_extraction_error or "Gemini AI was unable to extract items or no valid line items were found."
        return jsonify({
            "items": [],
            "error": error_msg
        })

    annexure_names = list(dict.fromkeys(
        item.get("annexure", "") for item in items if item.get("annexure")
    ))

    return jsonify({"items": items, "error": None, "annexures": annexure_names})
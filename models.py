from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date

db = SQLAlchemy()


class Company(db.Model):
    __tablename__ = "companies"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    address = db.Column(db.String(300))
    phone = db.Column(db.String(50))
    email = db.Column(db.String(150))
    tax_number = db.Column(db.String(100))
    bank_details = db.Column(db.Text)
    letterhead_filename = db.Column(db.String(200))
    letterhead_footer_filename = db.Column(db.String(200))
    logo_filename = db.Column(db.String(200))
    authorized_name = db.Column(db.String(150))
    designation = db.Column(db.String(150))
    signature_filename = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    short_name = db.Column(db.String(50))
    location_code = db.Column(db.String(20))
    pdf_theme = db.Column(db.String(50), default="default")
    pdf_columns = db.Column(db.JSON, nullable=True)
    entity_type = db.Column(db.String(50))
    status = db.Column(db.String(30))
    formation_date = db.Column(db.Date)
    ein = db.Column(db.String(50))
    registered_agent = db.Column(db.String(150))

    def __repr__(self):
        return f"<Company {self.name}>"


class DocSequence(db.Model):
    __tablename__ = "doc_sequences"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)
    doc_type = db.Column(db.String(20), nullable=False)
    last_number = db.Column(db.Integer, default=0)
    last_reset_year = db.Column(db.Integer, default=lambda: datetime.utcnow().year)
    format_pattern = db.Column(db.String(50), default="{prefix}-{year}-{number:03d}")

    company = db.relationship("Company", backref="doc_sequences")

    def get_next_raw_number(self):
        current_year = datetime.utcnow().year
        if self.last_reset_year != current_year:
            db.session.execute(
                db.update(DocSequence)
                .where(DocSequence.id == self.id)
                .values(last_number=0, last_reset_year=current_year)
            )
            db.session.commit()

        result = db.session.execute(
            db.update(DocSequence)
            .where(DocSequence.id == self.id)
            .values(last_number=DocSequence.last_number + 1)
            .returning(DocSequence.last_number)
        )
        new_number = result.scalar_one()
        db.session.commit()
        db.session.refresh(self)
        return new_number

    def peek_next_raw_number(self):
        current_year = datetime.utcnow().year
        return 1 if self.last_reset_year != current_year else self.last_number + 1

class ClientDocSequence(db.Model):
    """Same idea as DocSequence, but scoped to one client within one company
    -- so each client's quotation/invoice/challan numbers count on their own,
    separate from every other client's numbers for that same company. A
    client linked to multiple companies gets a separate counter per company,
    matching how DocSequence already keeps each company's numbering apart."""
    __tablename__ = "client_doc_sequences"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False, index=True)
    doc_type = db.Column(db.String(20), nullable=False)
    last_number = db.Column(db.Integer, default=0)
    last_reset_year = db.Column(db.Integer, default=lambda: datetime.utcnow().year)

    company = db.relationship("Company")
    client = db.relationship("Client")

    def get_next_raw_number(self):
        current_year = datetime.utcnow().year
        if self.last_reset_year != current_year:
            db.session.execute(
                db.update(ClientDocSequence)
                .where(ClientDocSequence.id == self.id)
                .values(last_number=0, last_reset_year=current_year)
            )
            db.session.commit()

        result = db.session.execute(
            db.update(ClientDocSequence)
            .where(ClientDocSequence.id == self.id)
            .values(last_number=ClientDocSequence.last_number + 1)
            .returning(ClientDocSequence.last_number)
        )
        new_number = result.scalar_one()
        db.session.commit()
        db.session.refresh(self)
        return new_number

    def peek_next_raw_number(self):
        current_year = datetime.utcnow().year
        return 1 if self.last_reset_year != current_year else self.last_number + 1

    @staticmethod
    def get_or_create(company_id, client_id, doc_type):
        seq = ClientDocSequence.query.filter_by(
            company_id=company_id, client_id=client_id, doc_type=doc_type
        ).first()
        if not seq:
            seq = ClientDocSequence(company_id=company_id, client_id=client_id, doc_type=doc_type)
            db.session.add(seq)
            db.session.commit()
        return seq




class Client(db.Model):
    __tablename__ = "clients"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    address = db.Column(db.String(300))
    contact_info = db.Column(db.String(200))
    tax_number = db.Column(db.String(100))
    logo_filename = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    client_code = db.Column(db.String(20))
    gst_registration = db.Column(db.Boolean, default=False)
    gst_registration_number = db.Column(db.String(100))
    belongs_to_gst = db.Column(db.Boolean, default=False)

    company_links = db.relationship("ClientCompanyLink", backref="client", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Client {self.name}>"


class ClientCompanyLink(db.Model):
    __tablename__ = "client_company_links"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False, index=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)

    company = db.relationship("Company")


class Order(db.Model):
    __tablename__ = "orders"

    title = db.Column(db.String(200))
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(50), nullable=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False, index=True)
    subsidiary_id = db.Column(db.Integer, db.ForeignKey("client_subsidiaries.id"), nullable=True, index=True)
    status = db.Column(db.String(20), default="Pending")
    inquiry_date = db.Column(db.Date, default=datetime.utcnow)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    company = db.relationship("Company")
    client = db.relationship("Client")
    subsidiary = db.relationship("ClientSubsidiary")
    purchase_order = db.relationship("PurchaseOrder", backref="order", uselist=False, cascade="all, delete-orphan")

    quotations = db.relationship(
        "Quotation", backref="order", cascade="all, delete-orphan",
        order_by="Quotation.id.desc()"
    )
    invoices = db.relationship(
        "Invoice", backref="order", cascade="all, delete-orphan",
        order_by="Invoice.id.desc()"
    )
    delivery_challans = db.relationship(
        "DeliveryChallan", backref="order", cascade="all, delete-orphan",
        order_by="DeliveryChallan.id.desc()"
    )
    documents = db.relationship(
        "OrderDocument", backref="order", cascade="all, delete-orphan",
        order_by="OrderDocument.doc_date.desc()"
    )

    # --- Helper Properties for Reports ---
    @property
    def is_dispatched(self):
        return len(self.delivery_challans) > 0

    @property
    def revenue(self):
        if self.invoice and not self.invoice.is_cancelled():
            return self.invoice.net_revenue()
        return 0

    @property
    def total_expenses(self):
        return sum(e.amount for e in self.expenses)

    @property
    def profit(self):
        return self.revenue - self.total_expenses

    @property
    def quotation(self):
        return self.quotations[0] if self.quotations else None

    def quotations_of_type(self, doc_type):
        return [q for q in self.quotations if q.doc_type == doc_type]

    @property
    def commercial_quotation(self):
        current = [q for q in self.quotations_of_type("commercial") if q.is_current]
        if current:
            return current[0]
        return self.quotations_of_type("commercial")[0] if self.quotations_of_type("commercial") else None

    @property
    def technical_quotation(self):
        current = [q for q in self.quotations_of_type("technical") if q.is_current]
        if current:
            return current[0]
        technical = self.quotations_of_type("technical")
        return technical[0] if technical else None

    @property
    def invoice(self):
        return self.invoices[0] if self.invoices else None

    @property
    def delivery_challan(self):
        return self.delivery_challans[0] if self.delivery_challans else None

    def __repr__(self):
        return f"<Order #{self.id} - {self.status}>"


class PurchaseOrder(db.Model):
    __tablename__ = "purchase_orders"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True)
    po_number = db.Column(db.String(100))
    po_date = db.Column(db.Date)
    attachment_path = db.Column(db.String(300))
    status = db.Column(db.String(20), default="Pending")
    total_amount = db.Column(db.Float, default=0)

    line_items = db.relationship("PurchaseOrderLineItem", backref="purchase_order", cascade="all, delete-orphan")


class PurchaseOrderLineItem(db.Model):
    __tablename__ = "purchase_order_line_items"

    id = db.Column(db.Integer, primary_key=True)
    purchase_order_id = db.Column(db.Integer, db.ForeignKey("purchase_orders.id"), nullable=False, index=True)
    description = db.Column(db.String(300))
    part_no = db.Column(db.String(100))
    unit = db.Column(db.String(50))
    qty = db.Column(db.Float, default=1)
    unit_price = db.Column(db.Float, default=0)


class CatalogItem(db.Model):
    __tablename__ = "catalog_items"

    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(300), nullable=False)
    unit = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    price_history = db.relationship("PriceHistory", backref="catalog_item", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<CatalogItem {self.description}>"


class PriceHistory(db.Model):
    __tablename__ = "price_history"

    id = db.Column(db.Integer, primary_key=True)
    catalog_item_id = db.Column(db.Integer, db.ForeignKey("catalog_items.id"), nullable=False, index=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=True, index=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=True, index=True)
    price = db.Column(db.Float, nullable=False)
    quoted_date = db.Column(db.Date, default=datetime.utcnow)
    source_doc = db.Column(db.String(20))

    client = db.relationship("Client")
    company = db.relationship("Company")


class Quotation(db.Model):
    __tablename__ = "quotations"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True)
    quote_number = db.Column(db.String(50))
    quote_date = db.Column(db.Date)
    pdf_path = db.Column(db.String(300))
    pdf_version = db.Column(db.Integer, default=1)
    is_current = db.Column(db.Boolean, default=True)
    doc_type = db.Column(db.String(16), default="commercial", nullable=False)
    subject = db.Column(db.String(300))
    client_ref_number = db.Column(db.String(100))
    terms_conditions = db.Column(db.Text)
    tax_amount = db.Column(db.Float, default=0)
    discount_amount = db.Column(db.Float, default=0)
    installation_charges = db.Column(db.Float, default=0)
    transportation_charges = db.Column(db.Float, default=0)
    skip_letterhead = db.Column(db.Boolean, default=False)
    recipient = db.Column(db.Text, nullable=True)
    visible_columns = db.Column(db.JSON, nullable=True)

    line_items = db.relationship("QuotationLineItem", backref="quotation", cascade="all, delete-orphan")


class QuotationLineItem(db.Model):
    __tablename__ = "quotation_line_items"

    id = db.Column(db.Integer, primary_key=True)
    quotation_id = db.Column(db.Integer, db.ForeignKey("quotations.id"), nullable=False, index=True)
    catalog_item_id = db.Column(db.Integer, db.ForeignKey("catalog_items.id"), nullable=False, index=True)
    part_no = db.Column(db.String(100))
    description = db.Column(db.String(300))
    unit = db.Column(db.String(50))
    qty = db.Column(db.Float, default=1)
    unit_price = db.Column(db.Float, default=0)
    tax_percent = db.Column(db.Float, default=0)
    custom_values = db.Column(db.JSON, nullable=True)
    specs = db.Column(db.Text, nullable=True)
    coo = db.Column(db.String(100), nullable=True)
    quoted = db.Column(db.String(8), nullable=True)
    remark = db.Column(db.Text, nullable=True)
    photo_path = db.Column(db.String(300), nullable=True)

    catalog_item = db.relationship("CatalogItem")


class CustomField(db.Model):
    __tablename__ = "custom_fields"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)
    doc_type = db.Column(db.String(20), default="quotation")
    name = db.Column(db.String(100), nullable=False)
    field_type = db.Column(db.String(20), default="text")
    is_active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)

    company = db.relationship("Company", backref="custom_fields")


class Invoice(db.Model):
    __tablename__ = "invoices"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True)
    invoice_number = db.Column(db.String(50))
    invoice_date = db.Column(db.Date)
    total_amount = db.Column(db.Float, default=0)
    pdf_path = db.Column(db.String(300))
    pdf_version = db.Column(db.Integer, default=1)
    is_current = db.Column(db.Boolean, default=True)
    status = db.Column(db.String(20), default="issued")
    discount_amount = db.Column(db.Float, default=0)
    installation_charges = db.Column(db.Float, default=0)
    transportation_charges = db.Column(db.Float, default=0)
    tax_amount = db.Column(db.Float, default=0)
    skip_letterhead = db.Column(db.Boolean, default=False)
    recipient = db.Column(db.Text, nullable=True)
    line_items = db.relationship("InvoiceLineItem", backref="invoice", cascade="all, delete-orphan")
    payments = db.relationship("Payment", backref="invoice", cascade="all, delete-orphan")
    credit_notes = db.relationship("CreditNote", backref="invoice", cascade="all, delete-orphan")

    def total_paid(self):
        return sum(p.amount for p in self.payments)

    def total_credited(self):
        return sum(c.amount for c in self.credit_notes)

    def balance_due(self):
        return self.total_amount - self.total_paid() - self.total_credited()

    def is_fully_paid(self):
        return self.balance_due() <= 0.01

    def is_cancelled(self):
        return self.status == "cancelled"

    def days_overdue(self):
        if self.is_fully_paid() or self.is_cancelled():
            return 0
        delta = datetime.utcnow().date() - self.invoice_date
        return max(delta.days, 0)

    def net_revenue(self):
        if self.is_cancelled():
            return 0
        return self.total_amount - self.total_credited()


class InvoiceLineItem(db.Model):
    __tablename__ = "invoice_line_items"

    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id"), nullable=False, index=True)
    catalog_item_id = db.Column(db.Integer, db.ForeignKey("catalog_items.id"), nullable=False, index=True)
    part_no = db.Column(db.String(100))
    description = db.Column(db.String(300))
    unit = db.Column(db.String(50))
    qty = db.Column(db.Float, default=1)
    unit_price = db.Column(db.Float, default=0)
    tax_percent = db.Column(db.Float, default=0)

    catalog_item = db.relationship("CatalogItem")


class DeliveryChallan(db.Model):
    __tablename__ = "delivery_challans"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True)
    challan_number = db.Column(db.String(50))
    dispatch_date = db.Column(db.Date)
    transport_mode = db.Column(db.String(100))
    vehicle_number = db.Column(db.String(100))
    place = db.Column(db.String(300))
    skip_letterhead = db.Column(db.Boolean, default=False)
    pdf_path = db.Column(db.String(300))
    pdf_version = db.Column(db.Integer, default=1)
    is_current = db.Column(db.Boolean, default=True)
    recipient = db.Column(db.Text, nullable=True)

    line_items = db.relationship("DeliveryChallanLineItem", backref="challan", cascade="all, delete-orphan")


class DeliveryChallanLineItem(db.Model):
    __tablename__ = "delivery_challan_line_items"

    id = db.Column(db.Integer, primary_key=True)
    challan_id = db.Column(db.Integer, db.ForeignKey("delivery_challans.id"), nullable=False, index=True)
    catalog_item_id = db.Column(db.Integer, db.ForeignKey("catalog_items.id"), nullable=False, index=True)
    description = db.Column(db.String(300))
    unit = db.Column(db.String(50))
    qty = db.Column(db.Float, default=1)

    catalog_item = db.relationship("CatalogItem")


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id"), nullable=False, index=True)
    amount = db.Column(db.Float, nullable=False)
    paid_date = db.Column(db.Date, default=datetime.utcnow)
    method = db.Column(db.String(50))
    notes = db.Column(db.String(300))


class Todo(db.Model):
    __tablename__ = "todos"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)
    text = db.Column(db.String(300), nullable=False)
    is_done = db.Column(db.Boolean, default=False)
    due_date = db.Column(db.Date, nullable=True)
    priority = db.Column(db.String(10), default="medium")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    assignee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    assignee = db.relationship("User", foreign_keys=[assignee_id])

    def is_overdue(self):
        from datetime import date
        return bool(self.due_date and not self.is_done and self.due_date < date.today())


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=True, index=True)
    action = db.Column(db.String(50))
    entity_type = db.Column(db.String(50))
    entity_id = db.Column(db.Integer)
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User")
    company = db.relationship("Company")


from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin


class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(150))
    role = db.Column(db.String(20), default="staff")
    is_active_user = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    permissions = db.Column(db.Text, default="")
    hidden_widgets = db.Column(db.Text, default="")
    email_notifications = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        return str(self.id)

    @property
    def is_active(self):
        return self.is_active_user

    def has_permission(self, perm_key):
        """Admins implicitly have every permission. Staff only have whatever
        an admin has explicitly granted them."""
        if self.role == "admin":
            return True
        return perm_key in (self.permissions or "").split(",")

    def permission_list(self):
        return [p for p in (self.permissions or "").split(",") if p]

    def is_widget_hidden(self, widget_key):
        return widget_key in (self.hidden_widgets or "").split(",")

    employee = db.relationship("Employee", back_populates="user", uselist=False)


class CreditNote(db.Model):
    __tablename__ = "credit_notes"

    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id"), nullable=False, index=True)
    credit_number = db.Column(db.String(50))
    credit_date = db.Column(db.Date, default=datetime.utcnow)
    amount = db.Column(db.Float, nullable=False)
    reason = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# --- Accounts Module Models ---

class ExpenseCategory(db.Model):
    __tablename__ = "expense_categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    scope = db.Column(db.String(20), default="general")
    is_active = db.Column(db.Boolean, default=True)

    expenses = db.relationship("Expense", backref="category_ref", foreign_keys="Expense.category_id")


class CategoryBudget(db.Model):
    __tablename__ = "category_budgets"

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey("expense_categories.id"), nullable=False, index=True)
    scope = db.Column(db.String(20), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    amount = db.Column(db.Float, nullable=False)
    period = db.Column(db.String(20), nullable=False, default="monthly")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    category_ref = db.relationship("ExpenseCategory", backref="budgets")
    company = db.relationship("Company")
    user = db.relationship("User")

    __table_args__ = (
        db.UniqueConstraint("category_id", "scope", "company_id", "user_id", name="uq_category_budget_scope"),
    )


class Expense(db.Model):
    __tablename__ = "expenses"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=True, index=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=True, index=True)
    category = db.Column(db.String(100))
    category_id = db.Column(db.Integer, db.ForeignKey("expense_categories.id"), nullable=True, index=True)
    scope = db.Column(db.String(20), default="company")
    amount = db.Column(db.Float, nullable=False)
    expense_date = db.Column(db.Date, default=datetime.utcnow)
    notes = db.Column(db.String(300))
    payee = db.Column(db.String(200))
    payment_method = db.Column(db.String(20))
    receipt_filename = db.Column(db.String(200))
    payroll_record_id = db.Column(db.Integer, db.ForeignKey("payroll_records.id"), nullable=True, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    company = db.relationship("Company")
    order = db.relationship("Order", backref="expenses")
    creator = db.relationship("User", foreign_keys=[created_by])
    updater = db.relationship("User", foreign_keys=[updated_by])
    payroll_record = db.relationship("PayrollRecord", foreign_keys=[payroll_record_id])


class PettyCashTransaction(db.Model):
    __tablename__ = "petty_cash_transactions"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, default=datetime.utcnow, nullable=False)
    type = db.Column(db.String(10), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    note = db.Column(db.String(300))
    linked_expense_id = db.Column(db.Integer, db.ForeignKey("expenses.id"), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    linked_expense = db.relationship("Expense", foreign_keys=[linked_expense_id])
    creator = db.relationship("User", foreign_keys=[created_by])


class Budget(db.Model):
    __tablename__ = "budgets"

    id = db.Column(db.Integer, primary_key=True)
    scope = db.Column(db.String(30), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=True, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("expense_categories.id"), nullable=True, index=True)
    month = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    period_type = db.Column(db.String(10), default="monthly")
    period_start = db.Column(db.Date, nullable=True)
    period_end = db.Column(db.Date, nullable=True)
    amount = db.Column(db.Float, nullable=False)
    recurring = db.Column(db.Boolean, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    company = db.relationship("Company")
    category = db.relationship("ExpenseCategory", foreign_keys=[category_id])
    creator = db.relationship("User", foreign_keys=[created_by])

    __table_args__ = (db.UniqueConstraint("scope", "company_id", "category_id", "month", "year", name="_budget_scope_uc"),)


class Employee(db.Model):
    __tablename__ = "employees"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150))
    phone = db.Column(db.String(30))
    department = db.Column(db.String(100))
    designation = db.Column(db.String(100))
    employee_code = db.Column(db.String(50))
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    base_monthly_salary = db.Column(db.Float, default=0)
    monthly_leave_accrual = db.Column(db.Float, default=4)
    date_joined = db.Column(db.Date)
    date_left = db.Column(db.Date)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    company = db.relationship("Company")
    user = db.relationship("User", foreign_keys=[user_id], back_populates="employee")

    def get_paid_leave_stats(self, as_of_date=None):
        if as_of_date is None:
            as_of_date = date.today()
        if self.date_joined:
            start = self.date_joined
        elif self.created_at:
            start = self.created_at.date() if hasattr(self.created_at, "date") else self.created_at
        else:
            start = as_of_date
        if start > as_of_date:
            months_active = 0
        else:
            months_active = max(0, (as_of_date.year - start.year) * 12 + (as_of_date.month - start.month) + 1)
        accrual = self.monthly_leave_accrual or 4
        earned = months_active * accrual
        used = AttendanceRecord.query.filter_by(employee_id=self.id, status="leave").filter(
            AttendanceRecord.date <= as_of_date
        ).count()
        balance = max(0, earned - used)
        return {
            "earned": earned,
            "used": used,
            "balance": balance,
            "months_active": months_active,
            "monthly_accrual": accrual,
            "as_of": as_of_date,
        }


class AttendanceRecord(db.Model):
    __tablename__ = "attendance_records"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(10), nullable=False)
    marked_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    employee = db.relationship("Employee")
    marker = db.relationship("User", foreign_keys=[marked_by])

    __table_args__ = (db.UniqueConstraint("employee_id", "date", name="_emp_date_uc"),)


class PayrollRecord(db.Model):
    __tablename__ = "payroll_records"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False, index=True)
    month = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    base_salary = db.Column(db.Float, default=0)
    days_present = db.Column(db.Integer, default=0)
    half_days = db.Column(db.Integer, default=0)
    paid_leaves_used = db.Column(db.Float, default=0)
    working_days_in_month = db.Column(db.Integer, default=30)
    calculated_salary = db.Column(db.Float, default=0)
    adjustment_amount = db.Column(db.Float, default=0)
    adjustment_note = db.Column(db.String(300))
    final_salary = db.Column(db.Float, default=0)
    status = db.Column(db.String(10), default="draft")
    generated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)

    employee = db.relationship("Employee")
    generator = db.relationship("User", foreign_keys=[generated_by])

    __table_args__ = (db.UniqueConstraint("employee_id", "month", "year", name="_emp_month_uc"),)


class Payable(db.Model):
    __tablename__ = "payables"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)
    owed_to = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    due_date = db.Column(db.Date, nullable=True)
    method = db.Column(db.String(50))
    is_paid = db.Column(db.Boolean, default=False)
    paid_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def is_overdue(self):
        from datetime import date
        return bool(self.due_date and not self.is_paid and self.due_date < date.today())


class CompanyDocument(db.Model):
    __tablename__ = "company_documents"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    filename = db.Column(db.String(300), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    company = db.relationship("Company")


class ClientSubsidiary(db.Model):
    __tablename__ = "client_subsidiaries"

    id = db.Column(db.Integer, primary_key=True)
    parent_client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False, index=True)
    name = db.Column(db.String(150), nullable=False)
    address = db.Column(db.String(300))
    contact_info = db.Column(db.String(200))
    tax_number = db.Column(db.String(100))
    client_code = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    parent_client = db.relationship("Client", backref=db.backref("subsidiaries", cascade="all, delete-orphan"))

class OrderDocument(db.Model):
    __tablename__ = "order_documents"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    doc_date = db.Column(db.Date, nullable=True)
    filename = db.Column(db.String(300), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<OrderDocument {self.name} for Order #{self.order_id}>"


class RecurringExpenseTemplate(db.Model):
    __tablename__ = "recurring_expense_templates"

    id = db.Column(db.Integer, primary_key=True)
    scope = db.Column(db.String(20), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=True, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("expense_categories.id"), nullable=True, index=True)
    amount = db.Column(db.Float, nullable=False)
    notes = db.Column(db.String(300))
    payee = db.Column(db.String(200))
    payment_method = db.Column(db.String(20))
    day_of_month = db.Column(db.Integer, default=1)
    is_active = db.Column(db.Boolean, default=True)
    last_generated_month = db.Column(db.Integer)
    last_generated_year = db.Column(db.Integer)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    company = db.relationship("Company")
    category = db.relationship("ExpenseCategory")


class Holiday(db.Model):
    __tablename__ = "holidays"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    is_recurring = db.Column(db.Boolean, default=False)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    company = db.relationship("Company")

    __table_args__ = (db.UniqueConstraint("date", "company_id", name="_holiday_date_company_uc"),)


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    message = db.Column(db.String(300), nullable=False)
    link = db.Column(db.String(300))
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", foreign_keys=[user_id])

    @classmethod
    def send(cls, user_id, message, link=None):
        n = cls(user_id=user_id, message=message, link=link)
        db.session.add(n)
        db.session.commit()
        cls._try_email(user_id, message, link)
        return n

    @classmethod
    def _try_email(cls, user_id, message, link=None):
        try:
            from email_utils import send_notification_email
            user = db.session.get(User, user_id)
            if user and user.email and user.email_notifications:
                send_notification_email(user.email, user.name or user.email, message, link)
        except Exception:
            pass

    @classmethod
    def send_all_employees(cls, message, link=None):
        employees = Employee.query.filter(Employee.user_id != None).all()
        for emp in employees:
            cls.send(emp.user_id, message, link)


class PersonalItem(db.Model):
    __tablename__ = "personal_items"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    lane = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default="not_started")
    priority = db.Column(db.String(10), default="medium")
    due_date = db.Column(db.Date)
    category = db.Column(db.String(50))
    estimated_minutes = db.Column(db.Integer)
    recurrence_rule = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)

    user = db.relationship("User")


class PersonalItemMilestone(db.Model):
    __tablename__ = "personal_item_milestones"

    id = db.Column(db.Integer, primary_key=True)
    personal_item_id = db.Column(db.Integer, db.ForeignKey("personal_items.id"), nullable=False, index=True)
    title = db.Column(db.String(300), nullable=False)
    is_done = db.Column(db.Boolean, default=False)
    order = db.Column(db.Integer, default=0)

    item = db.relationship("PersonalItem", backref=db.backref("milestones", cascade="all, delete-orphan", order_by="PersonalItemMilestone.order"))


class Project(db.Model):
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default="planning")
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    start_date = db.Column(db.Date)
    target_date = db.Column(db.Date)
    completed_at = db.Column(db.DateTime)
    color = db.Column(db.String(7), default="#1e9e63")
    icon = db.Column(db.String(50), default="bi-kanban")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    owner = db.relationship("User", foreign_keys=[owner_id])

    def progress_pct(self):
        total = db.session.query(db.func.count(TeamTask.id)).filter(
            TeamTask.project_id == self.id
        ).scalar() or 0
        if total == 0:
            return 0
        done = db.session.query(db.func.count(TeamTask.id)).filter(
            TeamTask.project_id == self.id,
            TeamTask.status == "done",
        ).scalar() or 0
        return round(done / total * 100)

    def task_counts(self):
        rows = db.session.query(
            TeamTask.status,
            db.func.count(TeamTask.id)
        ).filter(TeamTask.project_id == self.id).group_by(TeamTask.status).all()
        counts = {"to_do": 0, "in_progress": 0, "done": 0}
        for status, cnt in rows:
            counts[status] = cnt
        return counts

    def health(self):
        from datetime import date
        today = date.today()
        overdue = TeamTask.query.filter(
            TeamTask.project_id == self.id,
            TeamTask.status != "done",
            TeamTask.due_date.isnot(None),
            TeamTask.due_date < today,
        ).count()
        total = TeamTask.query.filter(TeamTask.project_id == self.id).count()
        overdue_ratio = overdue / total if total else 0
        if overdue_ratio > 0.3 or (self.target_date and self.target_date < today):
            return "red"
        if overdue_ratio > 0.1 or (self.target_date and (self.target_date - today).days < 7):
            return "yellow"
        return "green"

    def days_to_deadline(self):
        if not self.target_date:
            return None
        return (self.target_date - date.today()).days


class ProjectMember(db.Model):
    __tablename__ = "project_members"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    role = db.Column(db.String(20), default="contributor")

    project = db.relationship("Project", backref=db.backref("members", cascade="all, delete-orphan"))
    user = db.relationship("User", foreign_keys=[user_id])


class ProjectResource(db.Model):
    __tablename__ = "project_resources"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    type = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    value = db.Column(db.Text)
    added_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    project = db.relationship("Project", backref=db.backref("resources", cascade="all, delete-orphan"))
    adder = db.relationship("User", foreign_keys=[added_by])


class ProjectUpdate(db.Model):
    __tablename__ = "project_updates"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    project = db.relationship("Project", backref=db.backref("updates", cascade="all, delete-orphan", order_by="ProjectUpdate.created_at.desc()"))
    author = db.relationship("User", foreign_keys=[author_id])


class TeamTask(db.Model):
    __tablename__ = "team_tasks"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text)
    assignee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False, index=True)
    assigned_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    priority = db.Column(db.String(10), default="medium")
    status = db.Column(db.String(20), default="to_do")
    due_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    acknowledged_at = db.Column(db.DateTime)
    archived_at = db.Column(db.DateTime)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=True, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=True, index=True)

    assignee = db.relationship("Employee", foreign_keys=[assignee_id])
    assigner = db.relationship("User", foreign_keys=[assigned_by])
    order = db.relationship("Order", foreign_keys=[order_id])
    project = db.relationship("Project", backref=db.backref("tasks", lazy="dynamic"))


class TeamTaskComment(db.Model):
    __tablename__ = "team_task_comments"

    id = db.Column(db.Integer, primary_key=True)
    team_task_id = db.Column(db.Integer, db.ForeignKey("team_tasks.id"), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    body = db.Column(db.Text, nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("team_task_comments.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    task = db.relationship("TeamTask", backref=db.backref("comments", cascade="all, delete-orphan", order_by="TeamTaskComment.created_at"))
    author = db.relationship("User", foreign_keys=[author_id])
    replies = db.relationship("TeamTaskComment", backref=db.backref("parent", remote_side=[id]), lazy="dynamic")


class TeamTaskSubItem(db.Model):
    __tablename__ = "team_task_sub_items"

    id = db.Column(db.Integer, primary_key=True)
    team_task_id = db.Column(db.Integer, db.ForeignKey("team_tasks.id"), nullable=False, index=True)
    title = db.Column(db.String(300), nullable=False)
    is_done = db.Column(db.Boolean, default=False)
    order = db.Column(db.Integer, default=0)

    task = db.relationship("TeamTask", backref=db.backref("sub_items", cascade="all, delete-orphan", order_by="TeamTaskSubItem.order"))


class Discussion(db.Model):
    __tablename__ = "discussions"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    body = db.Column(db.Text)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)
    is_pinned = db.Column(db.Boolean, default=False)
    is_closed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    author = db.relationship("User", foreign_keys=[author_id])
    company = db.relationship("Company")


class DiscussionReply(db.Model):
    __tablename__ = "discussion_replies"

    id = db.Column(db.Integer, primary_key=True)
    discussion_id = db.Column(db.Integer, db.ForeignKey("discussions.id"), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    discussion = db.relationship("Discussion", backref=db.backref("replies", cascade="all, delete-orphan", order_by="DiscussionReply.created_at"))
    author = db.relationship("User", foreign_keys=[author_id])


class TaskTemplate(db.Model):
    __tablename__ = "task_templates"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text)
    default_priority = db.Column(db.String(10), default="medium")
    default_assignee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=True)
    scope = db.Column(db.String(20), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)
    sub_tasks = db.Column(db.Text, nullable=True, default="[]")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    day_of_month = db.Column(db.Integer, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    last_generated_month = db.Column(db.Integer, nullable=True)
    last_generated_year = db.Column(db.Integer, nullable=True)

    default_assignee = db.relationship("Employee", foreign_keys=[default_assignee_id])
    company = db.relationship("Company")


class TeamTaskActivityLog(db.Model):
    __tablename__ = "team_task_activity_log"

    id = db.Column(db.Integer, primary_key=True)
    team_task_id = db.Column(db.Integer, db.ForeignKey("team_tasks.id"), nullable=False, index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action_text = db.Column(db.String(300), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    task = db.relationship("TeamTask", backref=db.backref("activity_log", cascade="all, delete-orphan", order_by="TeamTaskActivityLog.created_at"))
    actor = db.relationship("User", foreign_keys=[actor_id])


class MailConfig(db.Model):
    __tablename__ = "mail_config"

    id = db.Column(db.Integer, primary_key=True)
    smtp_server = db.Column(db.String(200), nullable=False, default="")
    smtp_port = db.Column(db.Integer, nullable=False, default=587)
    smtp_username = db.Column(db.String(200), nullable=False, default="")
    smtp_password = db.Column(db.String(300), nullable=False, default="")
    use_tls = db.Column(db.Boolean, default=True)
    from_email = db.Column(db.String(200), nullable=False, default="")
    from_name = db.Column(db.String(200), nullable=False, default="")
    is_enabled = db.Column(db.Boolean, default=False)


class ActionSnooze(db.Model):
    __tablename__ = "action_snoozes"
    __table_args__ = (
        db.UniqueConstraint("company_id", "source", "source_id", name="uq_action_snooze_source"),
    )

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False, index=True)
    source = db.Column(db.String(50), nullable=False)
    source_id = db.Column(db.Integer, nullable=True)
    snoozed_until = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    company = db.relationship("Company", backref="action_snoozes", lazy=True)
"""Remove bank reconciliation and GST tax features

Revision ID: e9f2d4c6a8b0
Revises: 7d3a1c4e9f02
Create Date: 2026-08-16

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision = 'e9f2d4c6a8b0'
down_revision = '7d3a1c4e9f02'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    tables = set(inspector.get_table_names())

    # Drop the bank reconciliation table (BankTransaction model)
    if "bank_transactions" in tables:
        op.drop_table("bank_transactions")

    def _drop_col_if_exists(table, col):
        if table in tables and col in {c["name"] for c in inspector.get_columns(table)}:
            with op.batch_alter_table(table, schema=None) as batch_op:
                batch_op.drop_column(col)

    # Expenses: GST fields
    _drop_col_if_exists("expenses", "is_gst_applicable")
    _drop_col_if_exists("expenses", "gst_amount")

    # Invoices: GST fields (only used by the removed GST reports)
    _drop_col_if_exists("invoices", "gst_entitled")
    _drop_col_if_exists("invoices", "is_gst_registered")
    _drop_col_if_exists("invoices", "gst_amount")
    _drop_col_if_exists("invoices", "gst_percentage")

    # Companies: GST rate
    _drop_col_if_exists("companies", "gst_rate")


def downgrade():
    # Best-effort restore of the removed columns/table (data is not restored).
    with op.batch_alter_table("expenses", schema=None) as batch_op:
        batch_op.add_column(sa.Column("gst_amount", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("is_gst_applicable", sa.Boolean(), nullable=True))

    with op.batch_alter_table("invoices", schema=None) as batch_op:
        batch_op.add_column(sa.Column("gst_percentage", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("gst_amount", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("is_gst_registered", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("gst_entitled", sa.Boolean(), nullable=True))

    with op.batch_alter_table("companies", schema=None) as batch_op:
        batch_op.add_column(sa.Column("gst_rate", sa.Float(), nullable=True))

    op.create_table(
        'bank_transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('type', sa.String(length=10), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=True),
        sa.Column('reference', sa.String(length=200), nullable=True),
        sa.Column('reconciled', sa.Boolean(), nullable=True),
        sa.Column('matched_expense_id', sa.Integer(), nullable=True),
        sa.Column('source', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ),
        sa.ForeignKeyConstraint(['matched_expense_id'], ['expenses.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
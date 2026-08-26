"""Remove freight_charges from quotations, add tax_amount to invoices

Revision ID: d1e2f3a4b5c6
Revises: 9f6ecd3d58f0
Create Date: 2026-07-24 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision = 'd1e2f3a4b5c6'
down_revision = '9f6ecd3d58f0'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)

    with op.batch_alter_table('quotations', schema=None) as batch_op:
        batch_op.drop_column('freight_charges')

    # Guard: only add tax_amount to invoices if it doesn't already exist
    # (may have been added manually in development).
    invoice_cols = {c['name'] for c in inspector.get_columns('invoices')}
    if 'tax_amount' not in invoice_cols:
        with op.batch_alter_table('invoices', schema=None) as batch_op:
            batch_op.add_column(sa.Column('tax_amount', sa.Float(), nullable=True))


def downgrade():
    with op.batch_alter_table('quotations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('freight_charges', sa.Float(), nullable=True))

    with op.batch_alter_table('invoices', schema=None) as batch_op:
        batch_op.drop_column('tax_amount')


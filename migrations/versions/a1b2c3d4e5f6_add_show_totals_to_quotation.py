"""Add show_totals to quotations and quotation_annexures

Revision ID: a1b2c3d4e5f6
Revises: f1f90f23dd50
Create Date: 2026-08-31
"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = '03c656521d29'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('quotations', sa.Column('show_totals', sa.Boolean(), nullable=True))
    op.execute("UPDATE quotations SET show_totals = TRUE WHERE show_totals IS NULL")
    op.alter_column('quotations', 'show_totals', nullable=False, server_default='true')

    op.add_column('quotation_annexures', sa.Column('show_totals', sa.Boolean(), nullable=True))
    op.execute("UPDATE quotation_annexures SET show_totals = TRUE WHERE show_totals IS NULL")
    op.alter_column('quotation_annexures', 'show_totals', nullable=False, server_default='true')


def downgrade():
    op.drop_column('quotation_annexures', 'show_totals')
    op.drop_column('quotations', 'show_totals')

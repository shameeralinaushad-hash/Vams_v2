"""add terms_conditions and show_on_profile

Revision ID: a245c60b1a2c
Revises: a2b3c4d5e6f7
Create Date: 2026-08-26 16:44:36.881354

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a245c60b1a2c'
down_revision = 'a2b3c4d5e6f7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('companies', schema=None) as batch_op:
        batch_op.add_column(sa.Column('terms_conditions', sa.Text(), nullable=True))

    with op.batch_alter_table('company_documents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('show_on_profile', sa.Boolean(), nullable=True))


def downgrade():
    with op.batch_alter_table('company_documents', schema=None) as batch_op:
        batch_op.drop_column('show_on_profile')

    with op.batch_alter_table('companies', schema=None) as batch_op:
        batch_op.drop_column('terms_conditions')

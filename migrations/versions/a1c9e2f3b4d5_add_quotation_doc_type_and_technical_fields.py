"""Add quotation doc_type and technical line-item fields

Revision ID: a1c9e2f3b4d5
Revises: b7f3a9c1e2d4
Create Date: 2026-08-08 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1c9e2f3b4d5'
down_revision = 'b7f3a9c1e2d4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('quotations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('doc_type', sa.String(length=16), nullable=False, server_default='commercial'))

    with op.batch_alter_table('quotation_line_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('specs', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('coo', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('quoted', sa.String(length=8), nullable=True))
        batch_op.add_column(sa.Column('remark', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('photo_path', sa.String(length=300), nullable=True))


def downgrade():
    with op.batch_alter_table('quotation_line_items', schema=None) as batch_op:
        batch_op.drop_column('photo_path')
        batch_op.drop_column('remark')
        batch_op.drop_column('quoted')
        batch_op.drop_column('coo')
        batch_op.drop_column('specs')

    with op.batch_alter_table('quotations', schema=None) as batch_op:
        batch_op.drop_column('doc_type')

"""add PO line items and status

Revision ID: a2b3c4d5e6f7
Revises: e9f2d4c6a8b0
Create Date: 2026-08-24 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a2b3c4d5e6f7'
down_revision = 'e9f2d4c6a8b0'
branch_labels = None
depends_on = None


def upgrade():
    # Add status and total_amount to purchase_orders
    with op.batch_alter_table('purchase_orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('status', sa.String(20), server_default='Pending'))
        batch_op.add_column(sa.Column('total_amount', sa.Float(), server_default='0'))

    # Create purchase_order_line_items table
    op.create_table(
        'purchase_order_line_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('purchase_order_id', sa.Integer(), nullable=False),
        sa.Column('description', sa.String(300), nullable=True),
        sa.Column('part_no', sa.String(100), nullable=True),
        sa.Column('unit', sa.String(50), nullable=True),
        sa.Column('qty', sa.Float(), server_default='1'),
        sa.Column('unit_price', sa.Float(), server_default='0'),
        sa.ForeignKeyConstraint(['purchase_order_id'], ['purchase_orders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_purchase_order_line_items_purchase_order_id', 'purchase_order_line_items', ['purchase_order_id'])


def downgrade():
    op.drop_index('ix_purchase_order_line_items_purchase_order_id', table_name='purchase_order_line_items')
    op.drop_table('purchase_order_line_items')

    with op.batch_alter_table('purchase_orders', schema=None) as batch_op:
        batch_op.drop_column('total_amount')
        batch_op.drop_column('status')

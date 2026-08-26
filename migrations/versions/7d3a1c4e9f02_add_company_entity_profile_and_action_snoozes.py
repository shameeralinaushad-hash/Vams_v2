"""add company entity profile fields and action snoozes

Revision ID: 7d3a1c4e9f02
Revises: 4c2ae11995d8
Create Date: 2026-08-13

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7d3a1c4e9f02'
down_revision = '4c2ae11995d8'
branch_labels = None
depends_on = None


def upgrade():
    # NOTE: db.create_all() at app startup creates missing tables but never
    # alters existing ones, so we defensively add only missing columns and
    # skip the table if it already exists.
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    # Company entity-profile fields (all nullable so existing rows are fine)
    if "companies" in existing_tables:
        existing_cols = {c["name"] for c in insp.get_columns("companies")}
        for col_name, col_type in [
            ("entity_type", sa.String(length=50)),
            ("status", sa.String(length=30)),
            ("formation_date", sa.Date()),
            ("ein", sa.String(length=50)),
            ("registered_agent", sa.String(length=150)),
        ]:
            if col_name not in existing_cols:
                op.add_column("companies", sa.Column(col_name, col_type, nullable=True))

    # Dashboard Important Actions snooze table
    if "action_snoozes" not in existing_tables:
        op.create_table(
            'action_snoozes',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('company_id', sa.Integer(), nullable=False),
            sa.Column('source', sa.String(length=50), nullable=False),
            sa.Column('source_id', sa.Integer(), nullable=True),
            sa.Column('snoozed_until', sa.DateTime(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('company_id', 'source', 'source_id', name='uq_action_snooze_source'),
        )
        op.create_index(op.f('ix_action_snoozes_company_id'), 'action_snoozes', ['company_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_action_snoozes_company_id'), table_name='action_snoozes')
    op.drop_table('action_snoozes')

    with op.batch_alter_table('companies', schema=None) as batch_op:
        batch_op.drop_column('registered_agent')
        batch_op.drop_column('ein')
        batch_op.drop_column('formation_date')
        batch_op.drop_column('status')
        batch_op.drop_column('entity_type')

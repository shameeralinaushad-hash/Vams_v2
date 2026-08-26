"""task system phase 1: acknowledged_at order_id TeamTaskSubItem TaskTemplate

Revision ID: 81a2fe7f1ca0
Revises: f1f90f23dd50
Create Date: 2026-07-27 14:01:10.368480

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '81a2fe7f1ca0'
down_revision = 'f1f90f23dd50'
branch_labels = None
depends_on = None


def upgrade():
    # Schema already applied by db.create_all() on startup — stamp only
    pass


def downgrade():
    pass

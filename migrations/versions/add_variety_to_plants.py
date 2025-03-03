"""add variety to plants

Revision ID: add_variety_to_plants
Revises: e3e3dce7551b
Create Date: 2024-01-15 14:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_variety_to_plants'
down_revision = 'e3e3dce7551b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('plants', sa.Column('variety', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('plants', 'variety')
"""add variety to seed packets
Revision ID: add_variety_to_seed_packets
Revises: add_variety_to_plants
Create Date: 2024-01-15 14:45:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_variety_to_seed_packets'
down_revision = 'add_variety_to_plants'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('seed_packets', sa.Column('variety', sa.String(), nullable=True))

def downgrade() -> None:
    op.drop_column('seed_packets', 'variety')
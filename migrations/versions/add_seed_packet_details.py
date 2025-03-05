"""add detailed fields to seed packets
Revision ID: add_seed_packet_details
Revises: add_variety_to_seed_packets
Create Date: 2024-01-15 15:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_seed_packet_details'
down_revision = 'add_variety_to_seed_packets'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('seed_packets', sa.Column('description', sa.String(), nullable=True))
    op.add_column('seed_packets', sa.Column('planting_instructions', sa.String(), nullable=True))
    op.add_column('seed_packets', sa.Column('days_to_germination', sa.Integer(), nullable=True))
    op.add_column('seed_packets', sa.Column('spacing', sa.String(), nullable=True))
    op.add_column('seed_packets', sa.Column('sun_exposure', sa.String(), nullable=True))
    op.add_column('seed_packets', sa.Column('soil_type', sa.String(), nullable=True))
    op.add_column('seed_packets', sa.Column('watering', sa.String(), nullable=True))
    op.add_column('seed_packets', sa.Column('fertilizer', sa.String(), nullable=True))
    op.add_column('seed_packets', sa.Column('package_weight', sa.Float(), nullable=True))
    op.add_column('seed_packets', sa.Column('expiration_date', sa.Date(), nullable=True))

def downgrade() -> None:
    op.drop_column('seed_packets', 'expiration_date')
    op.drop_column('seed_packets', 'package_weight')
    op.drop_column('seed_packets', 'fertilizer')
    op.drop_column('seed_packets', 'watering')
    op.drop_column('seed_packets', 'soil_type')
    op.drop_column('seed_packets', 'sun_exposure')
    op.drop_column('seed_packets', 'spacing')
    op.drop_column('seed_packets', 'days_to_germination')
    op.drop_column('seed_packets', 'planting_instructions')
    op.drop_column('seed_packets', 'description')
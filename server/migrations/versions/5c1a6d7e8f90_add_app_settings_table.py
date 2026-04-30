"""add app settings table

Revision ID: 5c1a6d7e8f90
Revises: dda0ad0a94b2, f2c3d9a4b6e1
Create Date: 2026-04-30 11:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5c1a6d7e8f90'
down_revision = ('dda0ad0a94b2', 'f2c3d9a4b6e1')
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'app_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('value', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_app_settings')),
        sa.UniqueConstraint('key', name=op.f('uq_app_settings_key')),
    )


def downgrade():
    op.drop_table('app_settings')

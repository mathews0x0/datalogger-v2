"""default processed sessions to public

Revision ID: 7b9d4e2c1a11
Revises: 5c1a6d7e8f90
Create Date: 2026-05-31 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7b9d4e2c1a11'
down_revision = '5c1a6d7e8f90'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        'sessions',
        'is_public',
        existing_type=sa.Boolean(),
        server_default=sa.true(),
        existing_nullable=True,
    )


def downgrade():
    op.alter_column(
        'sessions',
        'is_public',
        existing_type=sa.Boolean(),
        server_default=sa.false(),
        existing_nullable=True,
    )

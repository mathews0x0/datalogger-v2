"""add revoked_at to device tokens

Revision ID: 3a1bf78310b2
Revises: f07e0346bf7c
Create Date: 2026-03-19 11:35:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3a1bf78310b2'
down_revision = 'f07e0346bf7c'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('device_tokens', schema=None) as batch_op:
        batch_op.add_column(sa.Column('revoked_at', sa.DateTime(), nullable=True))

    op.execute(
        """
        UPDATE device_tokens
        SET revoked_at = created_at
        WHERE revoked = 1 AND revoked_at IS NULL
        """
    )


def downgrade():
    with op.batch_alter_table('device_tokens', schema=None) as batch_op:
        batch_op.drop_column('revoked_at')

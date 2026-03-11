"""Added active_track_id to users

Revision ID: 1d9450fbf1f3
Revises: e719279ca5a3
Create Date: 2026-03-11 02:46:43.186656

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1d9450fbf1f3'
down_revision = 'e719279ca5a3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('active_track_id', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('active_track_id')

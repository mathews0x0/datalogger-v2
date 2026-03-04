"""add_device_tokens_table

Revision ID: e719279ca5a3
Revises: faaaa4857ac1
Create Date: 2026-03-05 01:25:30.607477

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e719279ca5a3'
down_revision = 'faaaa4857ac1'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'device_tokens' not in inspector.get_table_names():
        op.create_table('device_tokens',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('token', sa.String(length=100), nullable=False),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('device_name', sa.String(length=100), nullable=True),
            sa.Column('revoked', sa.Boolean(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('expires_at', sa.DateTime(), nullable=True),
            sa.Column('last_sync', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('token')
        )
    # ### end Alembic commands ###


def downgrade():
    pass

    op.drop_table('device_tokens')
    # ### end Alembic commands ###

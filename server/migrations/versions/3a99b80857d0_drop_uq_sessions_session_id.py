"""Drop uq_sessions_session_id

Revision ID: 3a99b80857d0
Revises: a3dc88229df0
Create Date: 2026-03-28 01:11:53.155868

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3a99b80857d0'
down_revision = 'a3dc88229df0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('annotations', schema=None) as batch_op:
        batch_op.drop_constraint('fk_annotations_session_id_sessions', type_='foreignkey')
        batch_op.drop_column('session_id')
        batch_op.add_column(sa.Column('session_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_annotations_session_id_sessions', 'sessions', ['session_id'], ['id'])

    with op.batch_alter_table('sessions', schema=None) as batch_op:
        batch_op.drop_constraint('uq_sessions_session_id', type_='unique')


def downgrade():
    with op.batch_alter_table('sessions', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_sessions_session_id', ['session_id'])

    with op.batch_alter_table('annotations', schema=None) as batch_op:
        batch_op.drop_constraint('fk_annotations_session_id_sessions', type_='foreignkey')
        batch_op.drop_column('session_id')
        batch_op.add_column(sa.Column('session_id', sa.String(length=100), nullable=True))
        batch_op.create_foreign_key('fk_annotations_session_id_sessions', 'sessions', ['session_id'], ['session_id'])

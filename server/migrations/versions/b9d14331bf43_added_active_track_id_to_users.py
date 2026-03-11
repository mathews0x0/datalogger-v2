"""Added active_track_id to users

Revision ID: b9d14331bf43
Revises: 1d9450fbf1f3
Create Date: 2026-03-11 02:47:29.644917

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b9d14331bf43'
down_revision = '1d9450fbf1f3'
branch_labels = None
depends_on = None


def upgrade():
    # Clean up orphaned temp table from any prior aborted migration
    try:
        op.drop_table('_alembic_tmp_annotations')
    except Exception:
        pass

    with op.batch_alter_table('annotations', schema=None) as batch_op:
        batch_op.alter_column('id',
               existing_type=sa.INTEGER(),
               nullable=False,
               autoincrement=True)

    with op.batch_alter_table('device_tokens', schema=None) as batch_op:
        batch_op.create_unique_constraint(batch_op.f('uq_device_tokens_token'), ['token'])

    with op.batch_alter_table('sessions', schema=None) as batch_op:
        batch_op.alter_column('id',
               existing_type=sa.INTEGER(),
               nullable=False,
               autoincrement=True)
        batch_op.create_unique_constraint('_session_user_uc', ['session_id', 'user_id'])
        batch_op.create_unique_constraint(batch_op.f('uq_sessions_share_token'), ['share_token'])

    with op.batch_alter_table('team_invites', schema=None) as batch_op:
        batch_op.create_unique_constraint(batch_op.f('uq_team_invites_token'), ['token'])

    with op.batch_alter_table('trackdays', schema=None) as batch_op:
        batch_op.create_unique_constraint(batch_op.f('uq_trackdays_trackday_id'), ['trackday_id'])

    with op.batch_alter_table('tracks', schema=None) as batch_op:
        batch_op.alter_column('id',
               existing_type=sa.INTEGER(),
               nullable=False,
               autoincrement=True)
        batch_op.create_unique_constraint('_track_user_uc', ['track_id', 'user_id'])

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_unique_constraint(batch_op.f('uq_users_email'), ['email'])


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('uq_users_email'), type_='unique')

    with op.batch_alter_table('tracks', schema=None) as batch_op:
        batch_op.drop_constraint('_track_user_uc', type_='unique')
        batch_op.alter_column('id',
               existing_type=sa.INTEGER(),
               nullable=True,
               autoincrement=True)

    with op.batch_alter_table('trackdays', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('uq_trackdays_trackday_id'), type_='unique')

    with op.batch_alter_table('team_invites', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('uq_team_invites_token'), type_='unique')

    with op.batch_alter_table('sessions', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('uq_sessions_share_token'), type_='unique')
        batch_op.drop_constraint('_session_user_uc', type_='unique')
        batch_op.alter_column('id',
               existing_type=sa.INTEGER(),
               nullable=True,
               autoincrement=True)

    with op.batch_alter_table('device_tokens', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('uq_device_tokens_token'), type_='unique')

    with op.batch_alter_table('annotations', schema=None) as batch_op:
        batch_op.alter_column('id',
               existing_type=sa.INTEGER(),
               nullable=True,
               autoincrement=True)

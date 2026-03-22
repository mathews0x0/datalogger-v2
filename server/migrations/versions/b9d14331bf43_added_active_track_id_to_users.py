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


def _existing_unique_constraints(inspector, table_name):
    return {constraint['name'] for constraint in inspector.get_unique_constraints(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Clean up orphaned temp table from any prior aborted migration.
    op.execute(sa.text('DROP TABLE IF EXISTS _alembic_tmp_annotations'))

    existing = {
        'device_tokens': _existing_unique_constraints(inspector, 'device_tokens'),
        'sessions': _existing_unique_constraints(inspector, 'sessions'),
        'team_invites': _existing_unique_constraints(inspector, 'team_invites'),
        'trackdays': _existing_unique_constraints(inspector, 'trackdays'),
        'tracks': _existing_unique_constraints(inspector, 'tracks'),
        'users': _existing_unique_constraints(inspector, 'users'),
    }

    device_tokens_token = op.f('uq_device_tokens_token')
    if device_tokens_token not in existing['device_tokens']:
        with op.batch_alter_table('device_tokens', schema=None) as batch_op:
            batch_op.create_unique_constraint(device_tokens_token, ['token'])

    session_share_token = op.f('uq_sessions_share_token')
    missing_session_constraints = []
    if '_session_user_uc' not in existing['sessions']:
        missing_session_constraints.append(('_session_user_uc', ['session_id', 'user_id']))
    if session_share_token not in existing['sessions']:
        missing_session_constraints.append((session_share_token, ['share_token']))
    if missing_session_constraints:
        with op.batch_alter_table('sessions', schema=None) as batch_op:
            for constraint_name, columns in missing_session_constraints:
                batch_op.create_unique_constraint(constraint_name, columns)

    team_invites_token = op.f('uq_team_invites_token')
    if team_invites_token not in existing['team_invites']:
        with op.batch_alter_table('team_invites', schema=None) as batch_op:
            batch_op.create_unique_constraint(team_invites_token, ['token'])

    trackdays_trackday_id = op.f('uq_trackdays_trackday_id')
    if trackdays_trackday_id not in existing['trackdays']:
        with op.batch_alter_table('trackdays', schema=None) as batch_op:
            batch_op.create_unique_constraint(trackdays_trackday_id, ['trackday_id'])

    if '_track_user_uc' not in existing['tracks']:
        with op.batch_alter_table('tracks', schema=None) as batch_op:
            batch_op.create_unique_constraint('_track_user_uc', ['track_id', 'user_id'])

    users_email = op.f('uq_users_email')
    if users_email not in existing['users']:
        with op.batch_alter_table('users', schema=None) as batch_op:
            batch_op.create_unique_constraint(users_email, ['email'])


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

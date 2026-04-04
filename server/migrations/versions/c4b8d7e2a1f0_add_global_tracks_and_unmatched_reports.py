"""add global tracks and unmatched reports

Revision ID: c4b8d7e2a1f0
Revises: dda0ad0a94b2
Create Date: 2026-04-03 18:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4b8d7e2a1f0'
down_revision = 'dda0ad0a94b2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'global_tracks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('track_id', sa.Integer(), nullable=False),
        sa.Column('slug', sa.String(length=255), nullable=False),
        sa.Column('track_name', sa.String(length=255), nullable=False),
        sa.Column('folder_name', sa.String(length=255), nullable=False),
        sa.Column('package_version', sa.Integer(), nullable=True),
        sa.Column('layout_width', sa.Integer(), nullable=True),
        sa.Column('layout_height', sa.Integer(), nullable=True),
        sa.Column('has_canonical_layout', sa.Boolean(), nullable=True),
        sa.Column('match_metadata', sa.Text(), nullable=True),
        sa.Column('location', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_global_tracks')),
        sa.UniqueConstraint('slug', name=op.f('uq_global_tracks_slug')),
        sa.UniqueConstraint('track_id', name=op.f('uq_global_tracks_track_id')),
    )

    op.create_table(
        'unmatched_track_reports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.String(length=100), nullable=False),
        sa.Column('fallback_track_id', sa.Integer(), nullable=False),
        sa.Column('fallback_track_name', sa.String(length=255), nullable=False),
        sa.Column('resolved_global_track_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('payload', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_unmatched_track_reports_user_id_users')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_unmatched_track_reports')),
    )


def downgrade():
    op.drop_table('unmatched_track_reports')
    op.drop_table('global_tracks')

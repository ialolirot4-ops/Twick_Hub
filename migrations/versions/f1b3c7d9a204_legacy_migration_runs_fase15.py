"""legacy migration runs fase 15: persisted record of TwitchLink 3.5.x import cycles

Revision ID: f1b3c7d9a204
Revises: e7a2b8c4f610
Create Date: 2026-09-25 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f1b3c7d9a204'
down_revision: str | Sequence[str] | None = 'e7a2b8c4f610'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'legacy_migration_runs',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('source_path', sa.String(length=2048), nullable=False),
        sa.Column('source_sha256', sa.String(length=64), nullable=False),
        sa.Column('backup_path', sa.String(length=2048), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('settings_migrated', sa.Boolean(), nullable=False),
        sa.Column('previous_settings_json', sa.Text(), nullable=True),
        sa.Column('account_token_migrated', sa.Boolean(), nullable=False),
        sa.Column('created_favorite_ids', sa.Text(), nullable=False),
        sa.Column('created_scheduled_download_ids', sa.Text(), nullable=False),
        sa.Column('created_download_ids', sa.Text(), nullable=False),
        sa.Column('skipped_bookmark_logins', sa.Text(), nullable=False),
        sa.Column('skipped_scheduled_download_logins', sa.Text(), nullable=False),
        sa.Column('warnings', sa.Text(), nullable=False),
        sa.Column('error_message', sa.String(length=2048), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_legacy_migration_runs_source_sha256',
        'legacy_migration_runs',
        ['source_sha256'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_legacy_migration_runs_source_sha256', table_name='legacy_migration_runs')
    op.drop_table('legacy_migration_runs')

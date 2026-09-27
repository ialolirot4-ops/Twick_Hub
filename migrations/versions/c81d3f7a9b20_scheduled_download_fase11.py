"""scheduled download fase 11: triggers, window, priority, retries, recovery state

Revision ID: c81d3f7a9b20
Revises: b34855f71713
Create Date: 2026-09-21 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c81d3f7a9b20'
down_revision: str | Sequence[str] | None = 'b34855f71713'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = 'scheduled_downloads'


def upgrade() -> None:
    """Upgrade schema."""
    # Every NOT NULL column carries a server_default: SQLite's
    # ALTER TABLE ADD COLUMN ... NOT NULL fails without one as soon as the
    # table already has rows (same lesson as the favorites migration).
    op.add_column(_TABLE, sa.Column('run_at', sa.DateTime(), nullable=True))
    op.add_column(_TABLE, sa.Column('weekdays', sa.String(length=16), nullable=False, server_default=''))
    op.add_column(_TABLE, sa.Column('window_seconds', sa.Integer(), nullable=False, server_default='14400'))
    op.add_column(_TABLE, sa.Column('priority', sa.Integer(), nullable=False, server_default='0'))
    op.add_column(_TABLE, sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='3'))
    op.add_column(_TABLE, sa.Column('download_directory', sa.String(length=2048), nullable=True))
    op.add_column(_TABLE, sa.Column('preferred_format', sa.String(length=16), nullable=True))
    op.add_column(_TABLE, sa.Column('next_due_at', sa.DateTime(), nullable=True))
    op.add_column(_TABLE, sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'))
    op.add_column(_TABLE, sa.Column('download_id', sa.String(length=32), nullable=True))
    op.add_column(_TABLE, sa.Column('last_outcome', sa.String(length=16), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table(_TABLE) as batch:
        for column in (
            'last_outcome', 'download_id', 'attempts', 'next_due_at', 'preferred_format',
            'download_directory', 'max_attempts', 'priority', 'window_seconds', 'weekdays', 'run_at',
        ):
            batch.drop_column(column)

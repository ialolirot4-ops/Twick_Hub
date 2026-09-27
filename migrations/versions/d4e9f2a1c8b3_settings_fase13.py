"""settings fase 13: one-row table for user-editable application settings

Revision ID: d4e9f2a1c8b3
Revises: c81d3f7a9b20
Create Date: 2026-09-23 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e9f2a1c8b3"
down_revision: str | Sequence[str] | None = "c81d3f7a9b20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # A brand-new table, so — unlike the favorites/scheduled_downloads
    # migrations — there's no pre-existing-rows concern requiring a
    # server_default on every NOT NULL column; SqlSettingsRepository.get()
    # never even needs this table to have a row (it falls back to
    # Settings() in Python when one is missing).
    op.create_table(
        "settings",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("minimize_to_tray", sa.Boolean(), nullable=False),
        sa.Column("default_directory", sa.String(length=2048), nullable=True),
        sa.Column("default_quality_preference", sa.String(length=32), nullable=False),
        sa.Column("default_format", sa.String(length=16), nullable=True),
        sa.Column("max_concurrent_downloads", sa.Integer(), nullable=False),
        sa.Column("retry_max_attempts", sa.Integer(), nullable=False),
        sa.Column("retry_base_delay_seconds", sa.Float(), nullable=False),
        sa.Column("retry_max_delay_seconds", sa.Float(), nullable=False),
        sa.Column("notifications_enabled", sa.Boolean(), nullable=False),
        sa.Column("theme", sa.String(length=16), nullable=False),
        sa.Column("temp_directory", sa.String(length=2048), nullable=True),
        sa.Column("live_monitor_poll_interval_seconds", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("settings")

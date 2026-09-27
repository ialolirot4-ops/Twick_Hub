"""update attempts fase 14: persisted record of check-download-install cycles

Revision ID: e7a2b8c4f610
Revises: d4e9f2a1c8b3
Create Date: 2026-09-24 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e7a2b8c4f610'
down_revision: str | Sequence[str] | None = 'd4e9f2a1c8b3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'update_attempts',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('from_version', sa.String(length=32), nullable=False),
        sa.Column('to_version', sa.String(length=32), nullable=False),
        sa.Column('download_url', sa.String(length=2048), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('artifact_path', sa.String(length=2048), nullable=True),
        sa.Column('backup_path', sa.String(length=2048), nullable=True),
        sa.Column('error_message', sa.String(length=2048), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_update_attempts_started_at', 'update_attempts', ['started_at'], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_update_attempts_started_at', table_name='update_attempts')
    op.drop_table('update_attempts')

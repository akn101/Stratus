"""Add sync state tracking table

Revision ID: 0007_add_sync_state
Revises: 0006
Create Date: 2025-08-31 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0007_add_sync_state'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add sync state tracking table."""
    
    # Sync state table
    op.create_table('sync_state',
        sa.Column('domain', sa.String(), nullable=False),
        sa.Column('last_synced_at', sa.DateTime(timezone=True)),
        sa.Column('last_sync_key', sa.String()),
        sa.Column('status', sa.String(), server_default='success'),
        sa.Column('error_count', sa.Integer(), server_default='0'),
        sa.Column('error_message', sa.Text()),
        sa.Column('sync_metadata', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('domain')
    )
    
    # Indexes for sync state
    op.create_index('ix_sync_state_last_synced_at', 'sync_state', ['last_synced_at'])
    op.create_index('ix_sync_state_status', 'sync_state', ['status'])


def downgrade() -> None:
    """Drop sync state tracking table."""
    op.drop_table('sync_state')
"""add_shopify_internal_id_to_orders

Revision ID: 0009
Revises: 0007
Create Date: 2025-08-31 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0009'
down_revision: Union[str, None] = '0007_add_sync_state'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add shopify_internal_id column to orders table
    op.add_column('orders', sa.Column('shopify_internal_id', sa.Text(), nullable=True))
    
    # Create index for quick lookups by Shopify internal ID
    op.create_index('ix_orders_shopify_internal_id', 'orders', ['shopify_internal_id'])


def downgrade() -> None:
    # Drop index and column in reverse order
    op.drop_index('ix_orders_shopify_internal_id', table_name='orders')
    op.drop_column('orders', 'shopify_internal_id')
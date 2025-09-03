"""add_storefront_column_simple

Revision ID: c6dfe41e8ea1
Revises: 99bf6edba699
Create Date: 2025-09-01 00:52:34.749593

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c6dfe41e8ea1'
down_revision = '99bf6edba699'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add storefront column to shopify_orders table
    op.add_column('shopify_orders', sa.Column('storefront', sa.Text(), nullable=True))
    
    # Set default value for existing records
    op.execute("UPDATE shopify_orders SET storefront = 'shopify' WHERE storefront IS NULL")
    
    # Add default constraint
    op.alter_column('shopify_orders', 'storefront', server_default='shopify')


def downgrade() -> None:
    # Remove storefront column
    op.drop_column('shopify_orders', 'storefront')
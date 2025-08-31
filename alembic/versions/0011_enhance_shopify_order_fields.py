"""enhance shopify order fields

Revision ID: 0011
Revises: 0010
Create Date: 2025-08-31 21:47:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add financial details to shopify_orders
    op.add_column('shopify_orders', sa.Column('subtotal_price', sa.Numeric(12, 2)))
    op.add_column('shopify_orders', sa.Column('total_tax', sa.Numeric(12, 2)))
    op.add_column('shopify_orders', sa.Column('total_discounts', sa.Numeric(12, 2)))
    op.add_column('shopify_orders', sa.Column('total_weight', sa.Integer()))  # grams
    
    # Add order metadata
    op.add_column('shopify_orders', sa.Column('email', sa.Text()))
    op.add_column('shopify_orders', sa.Column('phone', sa.Text()))
    op.add_column('shopify_orders', sa.Column('tags', sa.Text()))  # comma-separated or JSON
    op.add_column('shopify_orders', sa.Column('note', sa.Text()))
    op.add_column('shopify_orders', sa.Column('confirmation_number', sa.Text()))
    op.add_column('shopify_orders', sa.Column('order_number', sa.Integer()))  # Shopify's internal order number
    
    # Add marketing attribution
    op.add_column('shopify_orders', sa.Column('referring_site', sa.Text()))
    op.add_column('shopify_orders', sa.Column('landing_site', sa.Text()))
    op.add_column('shopify_orders', sa.Column('source_name', sa.Text()))
    
    # Add important timestamps
    op.add_column('shopify_orders', sa.Column('processed_at', sa.DateTime(timezone=True)))
    op.add_column('shopify_orders', sa.Column('closed_at', sa.DateTime(timezone=True)))
    op.add_column('shopify_orders', sa.Column('cancelled_at', sa.DateTime(timezone=True)))
    op.add_column('shopify_orders', sa.Column('updated_at_shopify', sa.DateTime(timezone=True)))
    
    # Add fulfillment status (separate from financial status)
    op.add_column('shopify_orders', sa.Column('fulfillment_status', sa.Text()))
    
    # Add billing and shipping addresses as JSON
    op.add_column('shopify_orders', sa.Column('billing_address', postgresql.JSONB()))
    op.add_column('shopify_orders', sa.Column('shipping_address', postgresql.JSONB()))


def downgrade() -> None:
    # Remove all the added columns
    op.drop_column('shopify_orders', 'shipping_address')
    op.drop_column('shopify_orders', 'billing_address')
    op.drop_column('shopify_orders', 'fulfillment_status')
    op.drop_column('shopify_orders', 'updated_at_shopify')
    op.drop_column('shopify_orders', 'cancelled_at')
    op.drop_column('shopify_orders', 'closed_at')
    op.drop_column('shopify_orders', 'processed_at')
    op.drop_column('shopify_orders', 'source_name')
    op.drop_column('shopify_orders', 'landing_site')
    op.drop_column('shopify_orders', 'referring_site')
    op.drop_column('shopify_orders', 'order_number')
    op.drop_column('shopify_orders', 'confirmation_number')
    op.drop_column('shopify_orders', 'note')
    op.drop_column('shopify_orders', 'tags')
    op.drop_column('shopify_orders', 'phone')
    op.drop_column('shopify_orders', 'email')
    op.drop_column('shopify_orders', 'total_weight')
    op.drop_column('shopify_orders', 'total_discounts')
    op.drop_column('shopify_orders', 'total_tax')
    op.drop_column('shopify_orders', 'subtotal_price')
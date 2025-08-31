"""restructure_to_source_specific_tables

Revision ID: 0010
Revises: 0009
Create Date: 2025-08-31 20:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0010'
down_revision: Union[str, None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # First, migrate existing data to source-specific tables
    
    # 1. Create Shopify-specific tables
    op.create_table(
        'shopify_orders',
        sa.Column('order_id', sa.Text(), nullable=False),
        sa.Column('shopify_internal_id', sa.Text(), nullable=True),
        sa.Column('purchase_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.Text(), nullable=True),
        sa.Column('customer_id', sa.Text(), nullable=True),
        sa.Column('total', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('currency', sa.Text(), nullable=True),
        sa.Column('tracking_number', sa.Text(), nullable=True),
        sa.Column('carrier', sa.Text(), nullable=True),
        sa.Column('tracking_url', sa.Text(), nullable=True),
        sa.Column('tracking_updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('order_id')
    )
    op.create_index('ix_shopify_orders_purchase_date', 'shopify_orders', ['purchase_date'])
    op.create_index('ix_shopify_orders_shopify_internal_id', 'shopify_orders', ['shopify_internal_id'])

    op.create_table(
        'shopify_order_items',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('order_id', sa.Text(), nullable=False),
        sa.Column('sku', sa.Text(), nullable=False),
        sa.Column('qty', sa.Integer(), nullable=False),
        sa.Column('price', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['order_id'], ['shopify_orders.order_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('order_id', 'sku', name='uq_shopify_order_items_order_sku')
    )
    op.create_index('ix_shopify_order_items_order_id', 'shopify_order_items', ['order_id'])
    op.create_index('ix_shopify_order_items_sku', 'shopify_order_items', ['sku'])

    # 2. Create ShipBob-specific tables
    op.create_table(
        'shipbob_inventory',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('sku', sa.Text(), nullable=False),
        sa.Column('quantity_on_hand', sa.Integer(), nullable=True),
        sa.Column('quantity_available', sa.Integer(), nullable=True),
        sa.Column('quantity_reserved', sa.Integer(), nullable=True),
        sa.Column('quantity_incoming', sa.Integer(), nullable=True),
        sa.Column('fulfillable_quantity', sa.Integer(), nullable=True),
        sa.Column('backordered_quantity', sa.Integer(), nullable=True),
        sa.Column('exception_quantity', sa.Integer(), nullable=True),
        sa.Column('internal_transfer_quantity', sa.Integer(), nullable=True),
        sa.Column('last_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sku', name='uq_shipbob_inventory_sku')
    )
    op.create_index('ix_shipbob_inventory_sku', 'shipbob_inventory', ['sku'])
    op.create_index('ix_shipbob_inventory_last_updated', 'shipbob_inventory', ['last_updated'])

    # 3. Rename Amazon tables to be properly prefixed
    op.execute('ALTER TABLE settlements RENAME TO amazon_settlements')
    op.execute('ALTER TABLE settlement_lines RENAME TO amazon_settlement_lines')

    # 4. Migrate existing data
    # Migrate Shopify orders
    op.execute("""
        INSERT INTO shopify_orders (order_id, shopify_internal_id, purchase_date, status, customer_id, total, currency, tracking_number, carrier, tracking_url, tracking_updated_at, created_at)
        SELECT order_id, shopify_internal_id, purchase_date, status, customer_id, total, currency, tracking_number, carrier, tracking_url, tracking_updated_at, created_at
        FROM orders WHERE source = 'shopify'
    """)
    
    # Migrate Shopify order items  
    op.execute("""
        INSERT INTO shopify_order_items (order_id, sku, qty, price, created_at)
        SELECT oi.order_id, oi.sku, oi.qty, oi.price, oi.created_at
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.order_id
        WHERE o.source = 'shopify'
    """)

    # Migrate ShipBob inventory
    op.execute("""
        INSERT INTO shipbob_inventory (sku, quantity_on_hand, quantity_available, quantity_reserved, quantity_incoming, fulfillable_quantity, backordered_quantity, exception_quantity, internal_transfer_quantity, last_updated, created_at)
        SELECT sku, quantity_on_hand, quantity_available, quantity_reserved, quantity_incoming, fulfillable_quantity, backordered_quantity, exception_quantity, internal_transfer_quantity, last_updated, created_at
        FROM inventory WHERE source = 'shipbob'
    """)

    # 5. Drop old generic tables (keep invoices for now as it might be used by FreeAgent)
    op.drop_table('order_items')
    op.drop_table('orders') 
    op.drop_table('inventory')


def downgrade() -> None:
    # Recreate original tables
    op.create_table(
        'orders',
        sa.Column('order_id', sa.Text(), nullable=False),
        sa.Column('source', sa.Text(), nullable=False),
        sa.Column('purchase_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.Text(), nullable=True),
        sa.Column('customer_id', sa.Text(), nullable=True),
        sa.Column('total', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('currency', sa.Text(), nullable=True),
        sa.Column('marketplace_id', sa.Text(), nullable=True),
        sa.Column('shopify_internal_id', sa.Text(), nullable=True),
        sa.Column('tracking_number', sa.Text(), nullable=True),
        sa.Column('carrier', sa.Text(), nullable=True),
        sa.Column('tracking_url', sa.Text(), nullable=True),
        sa.Column('tracking_updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('order_id')
    )
    
    op.create_table(
        'order_items',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('order_id', sa.Text(), nullable=False),
        sa.Column('sku', sa.Text(), nullable=False),
        sa.Column('asin', sa.Text(), nullable=True),
        sa.Column('qty', sa.Integer(), nullable=False),
        sa.Column('price', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('tax', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('fee_estimate', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['order_id'], ['orders.order_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('order_id', 'sku', name='uq_order_items_order_sku')
    )
    
    op.create_table(
        'inventory',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('sku', sa.Text(), nullable=False),
        sa.Column('source', sa.Text(), nullable=False),
        sa.Column('quantity_on_hand', sa.Integer(), nullable=True),
        sa.Column('quantity_available', sa.Integer(), nullable=True),
        sa.Column('quantity_reserved', sa.Integer(), nullable=True),
        sa.Column('quantity_incoming', sa.Integer(), nullable=True),
        sa.Column('fulfillable_quantity', sa.Integer(), nullable=True),
        sa.Column('backordered_quantity', sa.Integer(), nullable=True),
        sa.Column('exception_quantity', sa.Integer(), nullable=True),
        sa.Column('internal_transfer_quantity', sa.Integer(), nullable=True),
        sa.Column('last_updated', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sku', 'source', name='uq_inventory_sku_source')
    )

    # Migrate data back
    op.execute("""
        INSERT INTO orders (order_id, source, purchase_date, status, customer_id, total, currency, shopify_internal_id, tracking_number, carrier, tracking_url, tracking_updated_at, created_at)
        SELECT order_id, 'shopify', purchase_date, status, customer_id, total, currency, shopify_internal_id, tracking_number, carrier, tracking_url, tracking_updated_at, created_at
        FROM shopify_orders
    """)
    
    op.execute("""
        INSERT INTO order_items (order_id, sku, qty, price, created_at)
        SELECT order_id, sku, qty, price, created_at
        FROM shopify_order_items
    """)
    
    op.execute("""
        INSERT INTO inventory (sku, source, quantity_on_hand, quantity_available, quantity_reserved, quantity_incoming, fulfillable_quantity, backordered_quantity, exception_quantity, internal_transfer_quantity, last_updated, created_at)
        SELECT sku, 'shipbob', quantity_on_hand, quantity_available, quantity_reserved, quantity_incoming, fulfillable_quantity, backordered_quantity, exception_quantity, internal_transfer_quantity, last_updated, created_at
        FROM shipbob_inventory
    """)

    # Rename Amazon tables back
    op.execute('ALTER TABLE amazon_settlements RENAME TO settlements')
    op.execute('ALTER TABLE amazon_settlement_lines RENAME TO settlement_lines')

    # Drop source-specific tables
    op.drop_table('shopify_order_items')
    op.drop_table('shopify_orders')
    op.drop_table('shipbob_inventory')
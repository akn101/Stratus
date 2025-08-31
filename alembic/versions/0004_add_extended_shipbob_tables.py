"""Add extended ShipBob tables

Revision ID: 0004
Revises: 0003
Create Date: 2025-08-31 01:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ShipBob Returns table
    op.create_table(
        'shipbob_returns',
        sa.Column('return_id', sa.Text(), nullable=False),
        sa.Column('source', sa.Text(), nullable=False),
        sa.Column('original_shipment_id', sa.Text(), nullable=True),
        sa.Column('reference_id', sa.Text(), nullable=True),
        sa.Column('store_order_id', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), nullable=True),
        sa.Column('return_type', sa.Text(), nullable=True),
        sa.Column('customer_name', sa.Text(), nullable=True),
        sa.Column('tracking_number', sa.Text(), nullable=True),
        sa.Column('total_cost', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('fulfillment_center_id', sa.Text(), nullable=True),
        sa.Column('fulfillment_center_name', sa.Text(), nullable=True),
        sa.Column('items', sa.Text(), nullable=True),
        sa.Column('transactions', sa.Text(), nullable=True),
        sa.Column('insert_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('return_id')
    )
    
    # ShipBob Returns indexes
    op.create_index('ix_shipbob_returns_reference_id', 'shipbob_returns', ['reference_id'])
    op.create_index('ix_shipbob_returns_status', 'shipbob_returns', ['status'])
    op.create_index('ix_shipbob_returns_fulfillment_center', 'shipbob_returns', ['fulfillment_center_id'])
    op.create_index('ix_shipbob_returns_insert_date', 'shipbob_returns', ['insert_date'])
    
    # ShipBob Receiving Orders table
    op.create_table(
        'shipbob_receiving_orders',
        sa.Column('wro_id', sa.Text(), nullable=False),
        sa.Column('source', sa.Text(), nullable=False),
        sa.Column('purchase_order_number', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), nullable=True),
        sa.Column('package_type', sa.Text(), nullable=True),
        sa.Column('box_packaging_type', sa.Text(), nullable=True),
        sa.Column('fulfillment_center_id', sa.Text(), nullable=True),
        sa.Column('fulfillment_center_name', sa.Text(), nullable=True),
        sa.Column('inventory_quantities', sa.Text(), nullable=True),
        sa.Column('status_history', sa.Text(), nullable=True),
        sa.Column('expected_arrival_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('insert_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_updated_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('wro_id')
    )
    
    # ShipBob Receiving Orders indexes
    op.create_index('ix_shipbob_wro_po_number', 'shipbob_receiving_orders', ['purchase_order_number'])
    op.create_index('ix_shipbob_wro_status', 'shipbob_receiving_orders', ['status'])
    op.create_index('ix_shipbob_wro_fulfillment_center', 'shipbob_receiving_orders', ['fulfillment_center_id'])
    op.create_index('ix_shipbob_wro_insert_date', 'shipbob_receiving_orders', ['insert_date'])
    op.create_index('ix_shipbob_wro_expected_arrival', 'shipbob_receiving_orders', ['expected_arrival_date'])
    
    # ShipBob Products table
    op.create_table(
        'shipbob_products',
        sa.Column('product_id', sa.Text(), nullable=False),
        sa.Column('source', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=True),
        sa.Column('sku', sa.Text(), nullable=True),
        sa.Column('barcode', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.Text(), nullable=True),
        sa.Column('is_case', sa.Text(), nullable=True),
        sa.Column('is_lot', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Text(), nullable=True),
        sa.Column('is_bundle', sa.Text(), nullable=True),
        sa.Column('is_digital', sa.Text(), nullable=True),
        sa.Column('is_hazmat', sa.Text(), nullable=True),
        sa.Column('dimensions', sa.Text(), nullable=True),
        sa.Column('weight', sa.Text(), nullable=True),
        sa.Column('value', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('product_id')
    )
    
    # ShipBob Products indexes
    op.create_index('ix_shipbob_products_sku', 'shipbob_products', ['sku'])
    op.create_index('ix_shipbob_products_category', 'shipbob_products', ['category'])
    op.create_index('ix_shipbob_products_is_active', 'shipbob_products', ['is_active'])
    
    # ShipBob Variants table
    op.create_table(
        'shipbob_variants',
        sa.Column('variant_id', sa.Text(), nullable=False),
        sa.Column('product_id', sa.Text(), nullable=False),
        sa.Column('source', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=True),
        sa.Column('sku', sa.Text(), nullable=True),
        sa.Column('barcode', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Text(), nullable=True),
        sa.Column('dimensions', sa.Text(), nullable=True),
        sa.Column('weight', sa.Text(), nullable=True),
        sa.Column('value', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['product_id'], ['shipbob_products.product_id']),
        sa.PrimaryKeyConstraint('variant_id')
    )
    
    # ShipBob Variants indexes
    op.create_index('ix_shipbob_variants_product_id', 'shipbob_variants', ['product_id'])
    op.create_index('ix_shipbob_variants_sku', 'shipbob_variants', ['sku'])
    op.create_index('ix_shipbob_variants_is_active', 'shipbob_variants', ['is_active'])
    
    # ShipBob Fulfillment Centers table
    op.create_table(
        'shipbob_fulfillment_centers',
        sa.Column('center_id', sa.Text(), nullable=False),
        sa.Column('source', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=True),
        sa.Column('address1', sa.Text(), nullable=True),
        sa.Column('address2', sa.Text(), nullable=True),
        sa.Column('city', sa.Text(), nullable=True),
        sa.Column('state', sa.Text(), nullable=True),
        sa.Column('zip_code', sa.Text(), nullable=True),
        sa.Column('country', sa.Text(), nullable=True),
        sa.Column('phone_number', sa.Text(), nullable=True),
        sa.Column('email', sa.Text(), nullable=True),
        sa.Column('timezone', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('center_id')
    )
    
    # ShipBob Fulfillment Centers indexes
    op.create_index('ix_shipbob_centers_state', 'shipbob_fulfillment_centers', ['state'])
    op.create_index('ix_shipbob_centers_country', 'shipbob_fulfillment_centers', ['country'])
    op.create_index('ix_shipbob_centers_name', 'shipbob_fulfillment_centers', ['name'])


def downgrade() -> None:
    # Drop tables in reverse order (respecting foreign key dependencies)
    op.drop_table('shipbob_variants')
    op.drop_table('shipbob_products')
    op.drop_table('shipbob_fulfillment_centers')
    op.drop_table('shipbob_receiving_orders')
    op.drop_table('shipbob_returns')

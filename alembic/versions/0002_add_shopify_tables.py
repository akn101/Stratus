"""Add Shopify tables

Revision ID: 0002
Revises: 0001
Create Date: 2024-01-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create shopify_customers table
    op.create_table(
        'shopify_customers',
        sa.Column('customer_id', sa.Text(), nullable=False),
        sa.Column('email', sa.Text(), nullable=True),
        sa.Column('first_name', sa.Text(), nullable=True),
        sa.Column('last_name', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('total_spent', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('orders_count', sa.Integer(), nullable=True),
        sa.Column('state', sa.Text(), nullable=True),
        sa.Column('tags', sa.Text(), nullable=True),
        sa.Column('last_order_id', sa.Text(), nullable=True),
        sa.Column('last_order_date', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('customer_id')
    )
    
    # Create indexes for shopify_customers
    op.create_index('ix_shopify_customers_email', 'shopify_customers', ['email'])
    op.create_index('ix_shopify_customers_updated_at', 'shopify_customers', ['updated_at'])
    
    # Create shopify_products table
    op.create_table(
        'shopify_products',
        sa.Column('product_id', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('vendor', sa.Text(), nullable=True),
        sa.Column('product_type', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('product_id')
    )
    
    # Create indexes for shopify_products
    op.create_index('ix_shopify_products_vendor', 'shopify_products', ['vendor'])
    op.create_index('ix_shopify_products_product_type', 'shopify_products', ['product_type'])
    op.create_index('ix_shopify_products_updated_at', 'shopify_products', ['updated_at'])
    
    # Create shopify_variants table
    op.create_table(
        'shopify_variants',
        sa.Column('variant_id', sa.Text(), nullable=False),
        sa.Column('product_id', sa.Text(), nullable=False),
        sa.Column('sku', sa.Text(), nullable=True),
        sa.Column('price', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('inventory_item_id', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['product_id'], ['shopify_products.product_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('variant_id')
    )
    
    # Create indexes for shopify_variants
    op.create_index('ix_shopify_variants_product_id', 'shopify_variants', ['product_id'])
    op.create_index('ix_shopify_variants_sku', 'shopify_variants', ['sku'])
    op.create_index('ix_shopify_variants_inventory_item_id', 'shopify_variants', ['inventory_item_id'])


def downgrade() -> None:
    # Drop tables in reverse order (respecting foreign key constraints)
    op.drop_table('shopify_variants')
    op.drop_table('shopify_products')
    op.drop_table('shopify_customers')
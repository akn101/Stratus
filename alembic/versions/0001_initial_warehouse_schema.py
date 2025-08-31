"""Initial warehouse schema

Revision ID: 0001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create orders table
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
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('order_id')
    )
    
    # Create indexes for orders
    op.create_index('ix_orders_purchase_date', 'orders', ['purchase_date'])
    op.create_index('ix_orders_source_purchase_date', 'orders', ['source', sa.text('purchase_date DESC')])
    
    # Create order_items table
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
    
    # Create indexes for order_items
    op.create_index('ix_order_items_order_id', 'order_items', ['order_id'])
    op.create_index('ix_order_items_sku', 'order_items', ['sku'])
    
    # Create inventory table
    op.create_table(
        'inventory',
        sa.Column('sku', sa.Text(), nullable=False),
        sa.Column('asin', sa.Text(), nullable=True),
        sa.Column('fnsku', sa.Text(), nullable=True),
        sa.Column('fc', sa.Text(), nullable=True),
        sa.Column('on_hand', sa.Integer(), nullable=True),
        sa.Column('reserved', sa.Integer(), nullable=True),
        sa.Column('inbound', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('sku')
    )
    
    # Create settlements table
    op.create_table(
        'settlements',
        sa.Column('settlement_id', sa.Text(), nullable=False),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('gross', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('fees', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('refunds', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('net', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('currency', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('settlement_id')
    )
    
    # Create indexes for settlements
    op.create_index('ix_settlements_period_start', 'settlements', ['period_start'])
    op.create_index('ix_settlements_period_end', 'settlements', ['period_end'])
    
    # Create settlement_lines table
    op.create_table(
        'settlement_lines',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('settlement_id', sa.Text(), nullable=False),
        sa.Column('order_id', sa.Text(), nullable=True),
        sa.Column('type', sa.Text(), nullable=True),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('fee_type', sa.Text(), nullable=True),
        sa.Column('posted_date', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['settlement_id'], ['settlements.settlement_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('settlement_id', 'order_id', 'type', 'posted_date', name='uq_settlement_lines_unique')
    )
    
    # Create indexes for settlement_lines
    op.create_index('ix_settlement_lines_settlement_id', 'settlement_lines', ['settlement_id'])
    op.create_index('ix_settlement_lines_order_id', 'settlement_lines', ['order_id'])
    op.create_index('ix_settlement_lines_posted_date', 'settlement_lines', ['posted_date'])
    
    # Create invoices table
    op.create_table(
        'invoices',
        sa.Column('invoice_id', sa.Text(), nullable=False),
        sa.Column('source', sa.Text(), nullable=True),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('currency', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('fa_status', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('invoice_id')
    )


def downgrade() -> None:
    # Drop tables in reverse order (respecting foreign key constraints)
    op.drop_table('invoices')
    op.drop_table('settlement_lines')
    op.drop_table('settlements')
    op.drop_table('inventory')
    op.drop_table('order_items')
    op.drop_table('orders')
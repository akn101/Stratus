"""Update inventory and orders for ShipBob integration

Revision ID: 0003
Revises: 0002
Create Date: 2025-08-31 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # First, rename existing inventory columns to match new schema
    with op.batch_alter_table('inventory', schema=None) as batch_op:
        # Add source column as part of primary key
        batch_op.add_column(sa.Column('source', sa.Text(), nullable=False, server_default='amazon'))
        
        # Rename existing columns to new names
        batch_op.alter_column('on_hand', new_column_name='quantity_on_hand')
        batch_op.alter_column('reserved', new_column_name='quantity_reserved') 
        batch_op.alter_column('inbound', new_column_name='quantity_incoming')
        batch_op.alter_column('fc', new_column_name='fulfillment_center')
        batch_op.alter_column('updated_at', new_column_name='last_updated')
        
        # Add new columns
        batch_op.add_column(sa.Column('quantity_available', sa.Integer(), nullable=True, default=0))
        batch_op.add_column(sa.Column('inventory_id', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('inventory_name', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('fulfillable_quantity', sa.Integer(), nullable=True, default=0))
        batch_op.add_column(sa.Column('backordered_quantity', sa.Integer(), nullable=True, default=0))
        batch_op.add_column(sa.Column('exception_quantity', sa.Integer(), nullable=True, default=0))
        batch_op.add_column(sa.Column('internal_transfer_quantity', sa.Integer(), nullable=True, default=0))
        batch_op.add_column(sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()))
    
    # Drop old primary key and create new composite primary key
    with op.batch_alter_table('inventory', schema=None) as batch_op:
        batch_op.drop_constraint('inventory_pkey', type_='primary')
        batch_op.create_primary_key('inventory_pkey', ['sku', 'source'])
    
    # Create new indexes
    op.create_index('ix_inventory_sku_source', 'inventory', ['sku', 'source'])
    op.create_index('ix_inventory_source', 'inventory', ['source'])
    op.create_index('ix_inventory_last_updated', 'inventory', ['last_updated'])
    
    # Update orders table with tracking fields
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tracking_number', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('carrier', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('tracking_url', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('tracking_updated_at', sa.DateTime(timezone=True), nullable=True))
    
    # Create new indexes for orders
    op.create_index('ix_orders_status', 'orders', ['status'])
    op.create_index('ix_orders_tracking_updated', 'orders', ['tracking_updated_at'])


def downgrade() -> None:
    # Drop new indexes
    op.drop_index('ix_orders_tracking_updated', table_name='orders')
    op.drop_index('ix_orders_status', table_name='orders')
    op.drop_index('ix_inventory_last_updated', table_name='inventory')
    op.drop_index('ix_inventory_source', table_name='inventory')
    op.drop_index('ix_inventory_sku_source', table_name='inventory')
    
    # Remove tracking columns from orders
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.drop_column('tracking_updated_at')
        batch_op.drop_column('tracking_url')
        batch_op.drop_column('carrier')
        batch_op.drop_column('tracking_number')
    
    # Restore inventory table to original structure
    with op.batch_alter_table('inventory', schema=None) as batch_op:
        batch_op.drop_constraint('inventory_pkey', type_='primary')
        batch_op.create_primary_key('inventory_pkey', ['sku'])
        
        # Drop new columns
        batch_op.drop_column('created_at')
        batch_op.drop_column('internal_transfer_quantity')
        batch_op.drop_column('exception_quantity') 
        batch_op.drop_column('backordered_quantity')
        batch_op.drop_column('fulfillable_quantity')
        batch_op.drop_column('inventory_name')
        batch_op.drop_column('inventory_id')
        batch_op.drop_column('quantity_available')
        batch_op.drop_column('source')
        
        # Rename columns back to original names
        batch_op.alter_column('last_updated', new_column_name='updated_at')
        batch_op.alter_column('fulfillment_center', new_column_name='fc')
        batch_op.alter_column('quantity_incoming', new_column_name='inbound')
        batch_op.alter_column('quantity_reserved', new_column_name='reserved')
        batch_op.alter_column('quantity_on_hand', new_column_name='on_hand')

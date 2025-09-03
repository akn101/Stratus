"""add missing shopify fields

Revision ID: 0012
Revises: 0011
Create Date: 2025-08-31 23:20:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add missing phone field to shopify_customers
    op.add_column('shopify_customers', sa.Column('phone', sa.Text()))
    
    # Add missing handle field to shopify_products  
    op.add_column('shopify_products', sa.Column('handle', sa.Text()))


def downgrade() -> None:
    op.drop_column('shopify_products', 'handle')
    op.drop_column('shopify_customers', 'phone')
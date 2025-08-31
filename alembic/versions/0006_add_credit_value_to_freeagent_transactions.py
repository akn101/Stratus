"""Add credit_value to FreeAgent transactions

Revision ID: 0006
Revises: 0005
Create Date: 2025-08-31 00:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('freeagent_transactions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('credit_value', sa.Numeric(15, 2), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('freeagent_transactions', schema=None) as batch_op:
        batch_op.drop_column('credit_value')


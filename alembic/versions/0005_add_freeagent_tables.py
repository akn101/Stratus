"""Add FreeAgent tables for Phase FA-1 accounting data

Revision ID: 0005
Revises: 0004
Create Date: 2025-08-31 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add FreeAgent tables for Phase FA-1 core accounting functionality."""
    
    # FreeAgent Contacts
    op.create_table('freeagent_contacts',
        sa.Column('contact_id', sa.Text(), nullable=False),
        sa.Column('source', sa.Text(), nullable=False, default='freeagent'),
        sa.Column('organisation_name', sa.Text()),
        sa.Column('first_name', sa.Text()),
        sa.Column('last_name', sa.Text()),
        sa.Column('contact_name_on_invoices', sa.Text()),
        sa.Column('email', sa.Text()),
        sa.Column('phone_number', sa.Text()),
        sa.Column('mobile', sa.Text()),
        sa.Column('fax', sa.Text()),
        sa.Column('address1', sa.Text()),
        sa.Column('address2', sa.Text()),
        sa.Column('address3', sa.Text()),
        sa.Column('town', sa.Text()),
        sa.Column('region', sa.Text()),
        sa.Column('postcode', sa.Text()),
        sa.Column('country', sa.Text()),
        sa.Column('contact_type', sa.Text()),
        sa.Column('default_payment_terms_in_days', sa.Integer()),
        sa.Column('charge_sales_tax', sa.Text()),
        sa.Column('sales_tax_registration_number', sa.Text()),
        sa.Column('active_projects_count', sa.Integer()),
        sa.Column('account_balance', sa.Numeric(15, 2)),
        sa.Column('uses_contact_invoice_sequence', sa.Text()),
        sa.Column('status', sa.Text()),
        sa.Column('created_at_api', sa.DateTime(timezone=True)),
        sa.Column('updated_at_api', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('contact_id')
    )
    
    # Indexes for contacts
    op.create_index('ix_freeagent_contacts_email', 'freeagent_contacts', ['email'])
    op.create_index('ix_freeagent_contacts_type', 'freeagent_contacts', ['contact_type'])
    op.create_index('ix_freeagent_contacts_organisation', 'freeagent_contacts', ['organisation_name'])
    op.create_index('ix_freeagent_contacts_status', 'freeagent_contacts', ['status'])
    op.create_index('ix_freeagent_contacts_updated', 'freeagent_contacts', ['updated_at_api'])
    
    # FreeAgent Invoices
    op.create_table('freeagent_invoices',
        sa.Column('invoice_id', sa.Text(), nullable=False),
        sa.Column('source', sa.Text(), nullable=False, default='freeagent'),
        sa.Column('reference', sa.Text()),
        sa.Column('dated_on', sa.DateTime(timezone=True)),
        sa.Column('due_on', sa.DateTime(timezone=True)),
        sa.Column('contact_id', sa.Text()),
        sa.Column('contact_name', sa.Text()),
        sa.Column('net_value', sa.Numeric(15, 2)),
        sa.Column('sales_tax_value', sa.Numeric(15, 2)),
        sa.Column('total_value', sa.Numeric(15, 2)),
        sa.Column('paid_value', sa.Numeric(15, 2)),
        sa.Column('due_value', sa.Numeric(15, 2)),
        sa.Column('currency', sa.Text()),
        sa.Column('exchange_rate', sa.Numeric(15, 6)),
        sa.Column('net_value_in_base_currency', sa.Numeric(15, 2)),
        sa.Column('status', sa.Text()),
        sa.Column('payment_terms_in_days', sa.Integer()),
        sa.Column('sales_tax_status', sa.Text()),
        sa.Column('outside_of_sales_tax_scope', sa.Text()),
        sa.Column('initial_sales_tax_rate', sa.Numeric(5, 2)),
        sa.Column('comments', sa.Text()),
        sa.Column('project_id', sa.Text()),
        sa.Column('created_at_api', sa.DateTime(timezone=True)),
        sa.Column('updated_at_api', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('invoice_id')
    )
    
    # Indexes for invoices
    op.create_index('ix_freeagent_invoices_reference', 'freeagent_invoices', ['reference'])
    op.create_index('ix_freeagent_invoices_contact', 'freeagent_invoices', ['contact_id'])
    op.create_index('ix_freeagent_invoices_status', 'freeagent_invoices', ['status'])
    op.create_index('ix_freeagent_invoices_dated_on', 'freeagent_invoices', ['dated_on'])
    op.create_index('ix_freeagent_invoices_due_on', 'freeagent_invoices', ['due_on'])
    op.create_index('ix_freeagent_invoices_updated', 'freeagent_invoices', ['updated_at_api'])
    
    # FreeAgent Bills
    op.create_table('freeagent_bills',
        sa.Column('bill_id', sa.Text(), nullable=False),
        sa.Column('source', sa.Text(), nullable=False, default='freeagent'),
        sa.Column('reference', sa.Text()),
        sa.Column('dated_on', sa.DateTime(timezone=True)),
        sa.Column('due_on', sa.DateTime(timezone=True)),
        sa.Column('contact_id', sa.Text()),
        sa.Column('contact_name', sa.Text()),
        sa.Column('net_value', sa.Numeric(15, 2)),
        sa.Column('sales_tax_value', sa.Numeric(15, 2)),
        sa.Column('total_value', sa.Numeric(15, 2)),
        sa.Column('paid_value', sa.Numeric(15, 2)),
        sa.Column('due_value', sa.Numeric(15, 2)),
        sa.Column('status', sa.Text()),
        sa.Column('sales_tax_status', sa.Text()),
        sa.Column('comments', sa.Text()),
        sa.Column('project_id', sa.Text()),
        sa.Column('created_at_api', sa.DateTime(timezone=True)),
        sa.Column('updated_at_api', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('bill_id')
    )
    
    # Indexes for bills
    op.create_index('ix_freeagent_bills_reference', 'freeagent_bills', ['reference'])
    op.create_index('ix_freeagent_bills_contact', 'freeagent_bills', ['contact_id'])
    op.create_index('ix_freeagent_bills_status', 'freeagent_bills', ['status'])
    op.create_index('ix_freeagent_bills_dated_on', 'freeagent_bills', ['dated_on'])
    op.create_index('ix_freeagent_bills_due_on', 'freeagent_bills', ['due_on'])
    op.create_index('ix_freeagent_bills_updated', 'freeagent_bills', ['updated_at_api'])
    
    # FreeAgent Categories
    op.create_table('freeagent_categories',
        sa.Column('category_id', sa.Text(), nullable=False),
        sa.Column('source', sa.Text(), nullable=False, default='freeagent'),
        sa.Column('description', sa.Text()),
        sa.Column('nominal_code', sa.Text()),
        sa.Column('category_type', sa.Text()),
        sa.Column('parent_category_id', sa.Text()),
        sa.Column('auto_sales_tax_rate', sa.Numeric(5, 2)),
        sa.Column('allowable_for_tax', sa.Text()),
        sa.Column('is_visible', sa.Text()),
        sa.Column('group_description', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('category_id')
    )
    
    # Indexes for categories
    op.create_index('ix_freeagent_categories_nominal_code', 'freeagent_categories', ['nominal_code'])
    op.create_index('ix_freeagent_categories_type', 'freeagent_categories', ['category_type'])
    op.create_index('ix_freeagent_categories_parent', 'freeagent_categories', ['parent_category_id'])
    op.create_index('ix_freeagent_categories_description', 'freeagent_categories', ['description'])
    
    # FreeAgent Bank Accounts
    op.create_table('freeagent_bank_accounts',
        sa.Column('bank_account_id', sa.Text(), nullable=False),
        sa.Column('source', sa.Text(), nullable=False, default='freeagent'),
        sa.Column('name', sa.Text()),
        sa.Column('bank_name', sa.Text()),
        sa.Column('type', sa.Text()),
        sa.Column('account_number', sa.Text()),
        sa.Column('sort_code', sa.Text()),
        sa.Column('iban', sa.Text()),
        sa.Column('bic', sa.Text()),
        sa.Column('current_balance', sa.Numeric(15, 2)),
        sa.Column('currency', sa.Text()),
        sa.Column('is_primary', sa.Text()),
        sa.Column('is_personal', sa.Text()),
        sa.Column('email_new_transactions', sa.Text()),
        sa.Column('default_bill_category_id', sa.Text()),
        sa.Column('opening_balance_date', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('bank_account_id')
    )
    
    # Indexes for bank accounts
    op.create_index('ix_freeagent_bank_accounts_name', 'freeagent_bank_accounts', ['name'])
    op.create_index('ix_freeagent_bank_accounts_type', 'freeagent_bank_accounts', ['type'])
    op.create_index('ix_freeagent_bank_accounts_bank_name', 'freeagent_bank_accounts', ['bank_name'])
    op.create_index('ix_freeagent_bank_accounts_currency', 'freeagent_bank_accounts', ['currency'])
    
    # FreeAgent Bank Transactions
    op.create_table('freeagent_bank_transactions',
        sa.Column('transaction_id', sa.Text(), nullable=False),
        sa.Column('source', sa.Text(), nullable=False, default='freeagent'),
        sa.Column('bank_account_id', sa.Text()),
        sa.Column('dated_on', sa.DateTime(timezone=True)),
        sa.Column('amount', sa.Numeric(15, 2)),
        sa.Column('description', sa.Text()),
        sa.Column('bank_reference', sa.Text()),
        sa.Column('transaction_type', sa.Text()),
        sa.Column('running_balance', sa.Numeric(15, 2)),
        sa.Column('is_manual', sa.Text()),
        sa.Column('created_at_api', sa.DateTime(timezone=True)),
        sa.Column('updated_at_api', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('transaction_id')
    )
    
    # Indexes for bank transactions
    op.create_index('ix_freeagent_bank_transactions_account', 'freeagent_bank_transactions', ['bank_account_id'])
    op.create_index('ix_freeagent_bank_transactions_dated_on', 'freeagent_bank_transactions', ['dated_on'])
    op.create_index('ix_freeagent_bank_transactions_amount', 'freeagent_bank_transactions', ['amount'])
    op.create_index('ix_freeagent_bank_transactions_type', 'freeagent_bank_transactions', ['transaction_type'])
    op.create_index('ix_freeagent_bank_transactions_updated', 'freeagent_bank_transactions', ['updated_at_api'])
    
    # FreeAgent Bank Transaction Explanations
    op.create_table('freeagent_bank_transaction_explanations',
        sa.Column('explanation_id', sa.Text(), nullable=False),
        sa.Column('source', sa.Text(), nullable=False, default='freeagent'),
        sa.Column('bank_transaction_id', sa.Text()),
        sa.Column('bank_account_id', sa.Text()),
        sa.Column('dated_on', sa.DateTime(timezone=True)),
        sa.Column('amount', sa.Numeric(15, 2)),
        sa.Column('description', sa.Text()),
        sa.Column('category_id', sa.Text()),
        sa.Column('category_name', sa.Text()),
        sa.Column('foreign_currency_amount', sa.Numeric(15, 2)),
        sa.Column('foreign_currency_type', sa.Text()),
        sa.Column('gross_value', sa.Numeric(15, 2)),
        sa.Column('sales_tax_rate', sa.Numeric(5, 2)),
        sa.Column('sales_tax_value', sa.Numeric(15, 2)),
        sa.Column('invoice_id', sa.Text()),
        sa.Column('bill_id', sa.Text()),
        sa.Column('created_at_api', sa.DateTime(timezone=True)),
        sa.Column('updated_at_api', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('explanation_id')
    )
    
    # Indexes for bank transaction explanations
    op.create_index('ix_freeagent_bank_explanations_transaction', 'freeagent_bank_transaction_explanations', ['bank_transaction_id'])
    op.create_index('ix_freeagent_bank_explanations_account', 'freeagent_bank_transaction_explanations', ['bank_account_id'])
    op.create_index('ix_freeagent_bank_explanations_category', 'freeagent_bank_transaction_explanations', ['category_id'])
    op.create_index('ix_freeagent_bank_explanations_dated_on', 'freeagent_bank_transaction_explanations', ['dated_on'])
    op.create_index('ix_freeagent_bank_explanations_updated', 'freeagent_bank_transaction_explanations', ['updated_at_api'])
    
    # FreeAgent Accounting Transactions
    op.create_table('freeagent_transactions',
        sa.Column('transaction_id', sa.Text(), nullable=False),
        sa.Column('source', sa.Text(), nullable=False, default='freeagent'),
        sa.Column('dated_on', sa.DateTime(timezone=True)),
        sa.Column('description', sa.Text()),
        sa.Column('category_id', sa.Text()),
        sa.Column('category_name', sa.Text()),
        sa.Column('nominal_code', sa.Text()),
        sa.Column('debit_value', sa.Numeric(15, 2)),
        sa.Column('source_item_url', sa.Text()),
        sa.Column('foreign_currency_data', sa.Text()),
        sa.Column('created_at_api', sa.DateTime(timezone=True)),
        sa.Column('updated_at_api', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('transaction_id')
    )
    
    # Indexes for accounting transactions
    op.create_index('ix_freeagent_transactions_dated_on', 'freeagent_transactions', ['dated_on'])
    op.create_index('ix_freeagent_transactions_category', 'freeagent_transactions', ['category_id'])
    op.create_index('ix_freeagent_transactions_nominal_code', 'freeagent_transactions', ['nominal_code'])
    op.create_index('ix_freeagent_transactions_debit_value', 'freeagent_transactions', ['debit_value'])
    op.create_index('ix_freeagent_transactions_updated', 'freeagent_transactions', ['updated_at_api'])
    
    # FreeAgent Users
    op.create_table('freeagent_users',
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('source', sa.Text(), nullable=False, default='freeagent'),
        sa.Column('email', sa.Text()),
        sa.Column('first_name', sa.Text()),
        sa.Column('last_name', sa.Text()),
        sa.Column('ni_number', sa.Text()),
        sa.Column('unique_tax_reference', sa.Text()),
        sa.Column('role', sa.Text()),
        sa.Column('permission_level', sa.Integer()),
        sa.Column('opening_mileage', sa.Numeric(10, 2)),
        sa.Column('current_payroll_profile', sa.Text()),
        sa.Column('created_at_api', sa.DateTime(timezone=True)),
        sa.Column('updated_at_api', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('user_id')
    )
    
    # Indexes for users
    op.create_index('ix_freeagent_users_email', 'freeagent_users', ['email'])
    op.create_index('ix_freeagent_users_role', 'freeagent_users', ['role'])
    op.create_index('ix_freeagent_users_permission_level', 'freeagent_users', ['permission_level'])
    op.create_index('ix_freeagent_users_updated', 'freeagent_users', ['updated_at_api'])


def downgrade() -> None:
    """Drop FreeAgent tables."""
    
    # Drop all FreeAgent tables (in reverse order of dependencies)
    op.drop_table('freeagent_users')
    op.drop_table('freeagent_transactions')
    op.drop_table('freeagent_bank_transaction_explanations')
    op.drop_table('freeagent_bank_transactions')
    op.drop_table('freeagent_bank_accounts')
    op.drop_table('freeagent_categories')
    op.drop_table('freeagent_bills')
    op.drop_table('freeagent_invoices')
    op.drop_table('freeagent_contacts')

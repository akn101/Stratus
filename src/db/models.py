"""
SQLAlchemy models for the Stratus data warehouse.

Defines the normalized schema for storing data from multiple sources:
- Amazon SP-API
- Shopify
- ShipBob
- FreeAgent
"""

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base()


class Order(Base):
    """
    Normalized order data from multiple sources.

    Sources: Amazon SP-API, Shopify, etc.
    """

    __tablename__ = "orders"

    order_id = Column(Text, primary_key=True)
    source = Column(Text, nullable=False)  # 'amazon' | 'shopify' | 'shipbob' | 'freeagent'
    purchase_date = Column(DateTime(timezone=True), nullable=False)
    status = Column(Text)
    customer_id = Column(Text)
    total = Column(Numeric(12, 2))
    currency = Column(Text)
    marketplace_id = Column(Text)
    
    # Source-specific IDs for reference
    shopify_internal_id = Column(Text)  # Shopify's internal numeric ID (e.g., "6913240793415")

    # Fulfillment tracking information (updated by fulfillment services)
    tracking_number = Column(Text)
    carrier = Column(Text)
    tracking_url = Column(Text)
    tracking_updated_at = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship to order items
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index("ix_orders_purchase_date", "purchase_date"),
        Index("ix_orders_source_purchase_date", "source", purchase_date.desc()),
        Index("ix_orders_status", "status"),
        Index("ix_orders_tracking_updated", "tracking_updated_at"),
    )


class OrderItem(Base):
    """
    Individual line items within orders.
    """

    __tablename__ = "order_items"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    order_id = Column(Text, ForeignKey("orders.order_id", ondelete="CASCADE"), nullable=False)
    sku = Column(Text, nullable=False)
    asin = Column(Text)
    qty = Column(Integer, nullable=False)
    price = Column(Numeric(12, 2))
    tax = Column(Numeric(12, 2))
    fee_estimate = Column(Numeric(12, 2))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship back to order
    order = relationship("Order", back_populates="items")

    # Indexes and constraints
    __table_args__ = (
        Index("ix_order_items_order_id", "order_id"),
        Index("ix_order_items_sku", "sku"),
        UniqueConstraint("order_id", "sku", name="uq_order_items_order_sku"),
    )


class Inventory(Base):
    """
    Current inventory levels from fulfillment centers.

    Sources: Amazon FBA, ShipBob, etc.
    """

    __tablename__ = "inventory"

    sku = Column(Text, primary_key=True)
    source = Column(Text, primary_key=True)  # 'amazon', 'shipbob'

    # Generic inventory fields
    quantity_on_hand = Column(Integer, default=0)
    quantity_available = Column(Integer, default=0)
    quantity_reserved = Column(Integer, default=0)
    quantity_incoming = Column(Integer, default=0)

    # Amazon-specific fields
    asin = Column(Text)
    fnsku = Column(Text)  # Fulfillment Network SKU
    fulfillment_center = Column(Text)  # Fulfillment center

    # ShipBob-specific fields
    inventory_id = Column(Text)  # ShipBob inventory ID
    inventory_name = Column(Text)
    fulfillable_quantity = Column(Integer, default=0)
    backordered_quantity = Column(Integer, default=0)
    exception_quantity = Column(Integer, default=0)
    internal_transfer_quantity = Column(Integer, default=0)

    last_updated = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Indexes
    __table_args__ = (
        Index("ix_inventory_sku_source", "sku", "source"),
        Index("ix_inventory_source", "source"),
        Index("ix_inventory_last_updated", "last_updated"),
    )


class Settlement(Base):
    """
    Financial settlement periods from marketplaces.

    Sources: Amazon SP-API settlements, Shopify payouts, etc.
    """

    __tablename__ = "settlements"

    settlement_id = Column(Text, primary_key=True)
    period_start = Column(DateTime(timezone=True))
    period_end = Column(DateTime(timezone=True))
    gross = Column(Numeric(12, 2))
    fees = Column(Numeric(12, 2))
    refunds = Column(Numeric(12, 2))
    net = Column(Numeric(12, 2))
    currency = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship to settlement lines
    lines = relationship(
        "SettlementLine", back_populates="settlement", cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index("ix_settlements_period_start", "period_start"),
        Index("ix_settlements_period_end", "period_end"),
    )


class SettlementLine(Base):
    """
    Individual line items within financial settlements.
    """

    __tablename__ = "settlement_lines"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    settlement_id = Column(
        Text, ForeignKey("settlements.settlement_id", ondelete="CASCADE"), nullable=False
    )
    order_id = Column(Text)
    type = Column(Text)  # 'FBA Fee', 'Commission', 'Refund', etc.
    amount = Column(Numeric(12, 2))
    fee_type = Column(Text)
    posted_date = Column(DateTime(timezone=True))

    # Relationship back to settlement
    settlement = relationship("Settlement", back_populates="lines")

    # Indexes and constraints
    __table_args__ = (
        Index("ix_settlement_lines_settlement_id", "settlement_id"),
        Index("ix_settlement_lines_order_id", "order_id"),
        Index("ix_settlement_lines_posted_date", "posted_date"),
        UniqueConstraint(
            "settlement_id", "order_id", "type", "posted_date", name="uq_settlement_lines_unique"
        ),
    )


class Invoice(Base):
    """
    Invoice records for accounting integration.

    Sources: Amazon orders → FreeAgent invoices, manual entries, etc.
    """

    __tablename__ = "invoices"

    invoice_id = Column(Text, primary_key=True)
    source = Column(Text)  # 'amazon' | 'shopify' | 'manual'
    amount = Column(Numeric(12, 2))
    currency = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    fa_status = Column(Text)  # 'pending' | 'sent' | 'paid'


class ShopifyCustomer(Base):
    """
    Shopify customer data for CRM and analytics.
    """

    __tablename__ = "shopify_customers"

    customer_id = Column(Text, primary_key=True)
    email = Column(Text)
    first_name = Column(Text)
    last_name = Column(Text)
    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))
    total_spent = Column(Numeric(12, 2))
    orders_count = Column(Integer)
    state = Column(Text)
    tags = Column(Text)  # JSON array stored as text
    last_order_id = Column(Text)
    last_order_date = Column(DateTime(timezone=True))

    # Indexes
    __table_args__ = (
        Index("ix_shopify_customers_email", "email"),
        Index("ix_shopify_customers_updated_at", "updated_at"),
    )


class ShopifyProduct(Base):
    """
    Shopify product data for catalog management.
    """

    __tablename__ = "shopify_products"

    product_id = Column(Text, primary_key=True)
    title = Column(Text)
    vendor = Column(Text)
    product_type = Column(Text)
    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))

    # Relationship to variants
    variants = relationship(
        "ShopifyVariant", back_populates="product", cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index("ix_shopify_products_vendor", "vendor"),
        Index("ix_shopify_products_product_type", "product_type"),
        Index("ix_shopify_products_updated_at", "updated_at"),
    )


class ShopifyVariant(Base):
    """
    Shopify product variants for inventory and pricing.
    """

    __tablename__ = "shopify_variants"

    variant_id = Column(Text, primary_key=True)
    product_id = Column(
        Text, ForeignKey("shopify_products.product_id", ondelete="CASCADE"), nullable=False
    )
    sku = Column(Text)
    price = Column(Numeric(12, 2))
    inventory_item_id = Column(Text)
    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))

    # Relationship back to product
    product = relationship("ShopifyProduct", back_populates="variants")

    # Indexes
    __table_args__ = (
        Index("ix_shopify_variants_product_id", "product_id"),
        Index("ix_shopify_variants_sku", "sku"),
        Index("ix_shopify_variants_inventory_item_id", "inventory_item_id"),
    )


class ShipBobReturn(Base):
    """
    ShipBob return orders for analytics and cost tracking.

    Tracks returns processed through ShipBob fulfillment centers.
    """

    __tablename__ = "shipbob_returns"

    return_id = Column(Text, primary_key=True)
    source = Column(Text, nullable=False, default="shipbob")
    original_shipment_id = Column(Text)
    reference_id = Column(Text)  # External order ID
    store_order_id = Column(Text)
    status = Column(Text)
    return_type = Column(Text)
    customer_name = Column(Text)
    tracking_number = Column(Text)
    total_cost = Column(Numeric(12, 2))

    # Fulfillment center information
    fulfillment_center_id = Column(Text)
    fulfillment_center_name = Column(Text)

    # JSON fields for complex data
    items = Column(Text)  # JSON array of return items
    transactions = Column(Text)  # JSON array of cost transactions

    # Timestamps
    insert_date = Column(DateTime(timezone=True))
    completed_date = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Indexes
    __table_args__ = (
        Index("ix_shipbob_returns_reference_id", "reference_id"),
        Index("ix_shipbob_returns_status", "status"),
        Index("ix_shipbob_returns_fulfillment_center", "fulfillment_center_id"),
        Index("ix_shipbob_returns_insert_date", "insert_date"),
    )


class ShipBobReceivingOrder(Base):
    """
    ShipBob warehouse receiving orders (WROs) for inbound logistics tracking.

    Tracks inbound inventory shipments to ShipBob fulfillment centers.
    """

    __tablename__ = "shipbob_receiving_orders"

    wro_id = Column(Text, primary_key=True)
    source = Column(Text, nullable=False, default="shipbob")
    purchase_order_number = Column(Text)
    status = Column(Text)
    package_type = Column(Text)
    box_packaging_type = Column(Text)

    # Fulfillment center information
    fulfillment_center_id = Column(Text)
    fulfillment_center_name = Column(Text)

    # JSON fields for complex data
    inventory_quantities = Column(Text)  # JSON array of expected/received quantities
    status_history = Column(Text)  # JSON array of status changes

    # Timestamps
    expected_arrival_date = Column(DateTime(timezone=True))
    insert_date = Column(DateTime(timezone=True))
    last_updated_date = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Indexes
    __table_args__ = (
        Index("ix_shipbob_wro_po_number", "purchase_order_number"),
        Index("ix_shipbob_wro_status", "status"),
        Index("ix_shipbob_wro_fulfillment_center", "fulfillment_center_id"),
        Index("ix_shipbob_wro_insert_date", "insert_date"),
        Index("ix_shipbob_wro_expected_arrival", "expected_arrival_date"),
    )


class ShipBobProduct(Base):
    """
    ShipBob product catalog for product management and analytics.

    Tracks products managed in ShipBob fulfillment system.
    """

    __tablename__ = "shipbob_products"

    product_id = Column(Text, primary_key=True)
    source = Column(Text, nullable=False, default="shipbob")
    name = Column(Text)
    sku = Column(Text)
    barcode = Column(Text)
    description = Column(Text)
    category = Column(Text)

    # Product attributes
    is_case = Column(Text)  # Boolean stored as text for flexibility
    is_lot = Column(Text)
    is_active = Column(Text)
    is_bundle = Column(Text)
    is_digital = Column(Text)
    is_hazmat = Column(Text)

    # JSON fields for complex data
    dimensions = Column(Text)  # JSON object with length, width, height, unit
    weight = Column(Text)  # JSON object with value, unit
    value = Column(Text)  # JSON object with amount, currency

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship to variants
    variants = relationship(
        "ShipBobVariant", back_populates="product", cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index("ix_shipbob_products_sku", "sku"),
        Index("ix_shipbob_products_category", "category"),
        Index("ix_shipbob_products_is_active", "is_active"),
    )


class ShipBobVariant(Base):
    """
    ShipBob product variants for detailed product catalog management.

    Tracks individual product variations within ShipBob products.
    """

    __tablename__ = "shipbob_variants"

    variant_id = Column(Text, primary_key=True)
    product_id = Column(Text, ForeignKey("shipbob_products.product_id"), nullable=False)
    source = Column(Text, nullable=False, default="shipbob")
    name = Column(Text)
    sku = Column(Text)
    barcode = Column(Text)
    is_active = Column(Text)

    # JSON fields for complex data
    dimensions = Column(Text)  # JSON object with dimensions
    weight = Column(Text)  # JSON object with weight
    value = Column(Text)  # JSON object with value

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship back to product
    product = relationship("ShipBobProduct", back_populates="variants")

    # Indexes
    __table_args__ = (
        Index("ix_shipbob_variants_product_id", "product_id"),
        Index("ix_shipbob_variants_sku", "sku"),
        Index("ix_shipbob_variants_is_active", "is_active"),
    )


class ShipBobFulfillmentCenter(Base):
    """
    ShipBob fulfillment centers for geographic and operational analytics.

    Tracks ShipBob warehouse locations and capabilities.
    """

    __tablename__ = "shipbob_fulfillment_centers"

    center_id = Column(Text, primary_key=True)
    source = Column(Text, nullable=False, default="shipbob")
    name = Column(Text)

    # Address information
    address1 = Column(Text)
    address2 = Column(Text)
    city = Column(Text)
    state = Column(Text)
    zip_code = Column(Text)
    country = Column(Text)

    # Contact information
    phone_number = Column(Text)
    email = Column(Text)
    timezone = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Indexes
    __table_args__ = (
        Index("ix_shipbob_centers_state", "state"),
        Index("ix_shipbob_centers_country", "country"),
        Index("ix_shipbob_centers_name", "name"),
    )


# FreeAgent Models for Phase FA-1


class FreeAgentContact(Base):
    """
    FreeAgent contacts for customer/supplier relationship management.

    Tracks business contacts including customers and suppliers.
    """

    __tablename__ = "freeagent_contacts"

    contact_id = Column(Text, primary_key=True)  # Extract from URL
    source = Column(Text, nullable=False, default="freeagent")

    # Basic information
    organisation_name = Column(Text)
    first_name = Column(Text)
    last_name = Column(Text)
    contact_name_on_invoices = Column(Text)

    # Contact details
    email = Column(Text)
    phone_number = Column(Text)
    mobile = Column(Text)
    fax = Column(Text)

    # Address information
    address1 = Column(Text)
    address2 = Column(Text)
    address3 = Column(Text)
    town = Column(Text)
    region = Column(Text)
    postcode = Column(Text)
    country = Column(Text)

    # Business details
    contact_type = Column(Text)  # 'Client', 'Supplier', 'Both'
    default_payment_terms_in_days = Column(Integer)
    charge_sales_tax = Column(Text)  # 'Auto', 'Never', 'Always'
    sales_tax_registration_number = Column(Text)
    active_projects_count = Column(Integer)

    # Financial information
    account_balance = Column(Numeric(15, 2))
    uses_contact_invoice_sequence = Column(Text)  # Boolean as string

    # Status flags
    status = Column(Text)

    # Timestamps
    created_at_api = Column(DateTime(timezone=True))
    updated_at_api = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Indexes
    __table_args__ = (
        Index("ix_freeagent_contacts_email", "email"),
        Index("ix_freeagent_contacts_type", "contact_type"),
        Index("ix_freeagent_contacts_organisation", "organisation_name"),
        Index("ix_freeagent_contacts_status", "status"),
        Index("ix_freeagent_contacts_updated", "updated_at_api"),
    )


class FreeAgentInvoice(Base):
    """
    FreeAgent invoices for revenue tracking and accounts receivable.

    Tracks sales invoices and related financial data.
    """

    __tablename__ = "freeagent_invoices"

    invoice_id = Column(Text, primary_key=True)  # Extract from URL
    source = Column(Text, nullable=False, default="freeagent")

    # Invoice identification
    reference = Column(Text)
    dated_on = Column(DateTime(timezone=True))
    due_on = Column(DateTime(timezone=True))

    # Contact relationship
    contact_id = Column(Text)  # Extract from contact URL
    contact_name = Column(Text)

    # Financial information
    net_value = Column(Numeric(15, 2))
    sales_tax_value = Column(Numeric(15, 2))
    total_value = Column(Numeric(15, 2))
    paid_value = Column(Numeric(15, 2))
    due_value = Column(Numeric(15, 2))

    # Currency and exchange
    currency = Column(Text)
    exchange_rate = Column(Numeric(15, 6))
    net_value_in_base_currency = Column(Numeric(15, 2))

    # Status and payment
    status = Column(Text)  # 'Draft', 'Sent', 'Scheduled', 'Paid', etc.
    payment_terms_in_days = Column(Integer)

    # Sales tax details
    sales_tax_status = Column(Text)
    outside_of_sales_tax_scope = Column(Text)  # Boolean as string
    initial_sales_tax_rate = Column(Numeric(5, 2))

    # Comments and notes
    comments = Column(Text)

    # Project association
    project_id = Column(Text)  # Extract from project URL

    # Timestamps
    created_at_api = Column(DateTime(timezone=True))
    updated_at_api = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Indexes
    __table_args__ = (
        Index("ix_freeagent_invoices_reference", "reference"),
        Index("ix_freeagent_invoices_contact", "contact_id"),
        Index("ix_freeagent_invoices_status", "status"),
        Index("ix_freeagent_invoices_dated_on", "dated_on"),
        Index("ix_freeagent_invoices_due_on", "due_on"),
        Index("ix_freeagent_invoices_updated", "updated_at_api"),
    )


class FreeAgentBill(Base):
    """
    FreeAgent bills for expense tracking and accounts payable.

    Tracks purchase invoices and supplier bills.
    """

    __tablename__ = "freeagent_bills"

    bill_id = Column(Text, primary_key=True)  # Extract from URL
    source = Column(Text, nullable=False, default="freeagent")

    # Bill identification
    reference = Column(Text)
    dated_on = Column(DateTime(timezone=True))
    due_on = Column(DateTime(timezone=True))

    # Contact relationship
    contact_id = Column(Text)  # Extract from contact URL
    contact_name = Column(Text)

    # Financial information
    net_value = Column(Numeric(15, 2))
    sales_tax_value = Column(Numeric(15, 2))
    total_value = Column(Numeric(15, 2))
    paid_value = Column(Numeric(15, 2))
    due_value = Column(Numeric(15, 2))

    # Status and payment
    status = Column(Text)  # 'Open', 'Scheduled', 'Paid', etc.

    # Sales tax details
    sales_tax_status = Column(Text)

    # Comments and notes
    comments = Column(Text)

    # Project association
    project_id = Column(Text)  # Extract from project URL

    # Timestamps
    created_at_api = Column(DateTime(timezone=True))
    updated_at_api = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Indexes
    __table_args__ = (
        Index("ix_freeagent_bills_reference", "reference"),
        Index("ix_freeagent_bills_contact", "contact_id"),
        Index("ix_freeagent_bills_status", "status"),
        Index("ix_freeagent_bills_dated_on", "dated_on"),
        Index("ix_freeagent_bills_due_on", "due_on"),
        Index("ix_freeagent_bills_updated", "updated_at_api"),
    )


class FreeAgentCategory(Base):
    """
    FreeAgent categories for chart of accounts and transaction classification.

    Tracks accounting categories and nominal codes.
    """

    __tablename__ = "freeagent_categories"

    category_id = Column(Text, primary_key=True)  # Extract from URL
    source = Column(Text, nullable=False, default="freeagent")

    # Category details
    description = Column(Text)
    nominal_code = Column(Text)
    category_type = Column(Text)

    # Hierarchy
    parent_category_id = Column(Text)  # Extract from parent URL

    # Tax configuration
    auto_sales_tax_rate = Column(Numeric(5, 2))
    allowable_for_tax = Column(Text)  # Boolean as string

    # Flags
    is_visible = Column(Text)  # Boolean as string
    group_description = Column(Text)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Indexes
    __table_args__ = (
        Index("ix_freeagent_categories_nominal_code", "nominal_code"),
        Index("ix_freeagent_categories_type", "category_type"),
        Index("ix_freeagent_categories_parent", "parent_category_id"),
        Index("ix_freeagent_categories_description", "description"),
    )


class FreeAgentBankAccount(Base):
    """
    FreeAgent bank accounts for cash management and reconciliation.

    Tracks business bank accounts and their details.
    """

    __tablename__ = "freeagent_bank_accounts"

    bank_account_id = Column(Text, primary_key=True)  # Extract from URL
    source = Column(Text, nullable=False, default="freeagent")

    # Account identification
    name = Column(Text)
    bank_name = Column(Text)
    type = Column(Text)  # 'CurrentAccount', 'SavingsAccount', 'CreditCardAccount', etc.
    account_number = Column(Text)
    sort_code = Column(Text)
    iban = Column(Text)
    bic = Column(Text)

    # Balances
    current_balance = Column(Numeric(15, 2))

    # Currency
    currency = Column(Text)

    # Status
    is_primary = Column(Text)  # Boolean as string
    is_personal = Column(Text)  # Boolean as string

    # Email settings
    email_new_transactions = Column(Text)  # Boolean as string

    # Default category
    default_bill_category_id = Column(Text)

    # Timestamps
    opening_balance_date = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Indexes
    __table_args__ = (
        Index("ix_freeagent_bank_accounts_name", "name"),
        Index("ix_freeagent_bank_accounts_type", "type"),
        Index("ix_freeagent_bank_accounts_bank_name", "bank_name"),
        Index("ix_freeagent_bank_accounts_currency", "currency"),
    )


class FreeAgentBankTransaction(Base):
    """
    FreeAgent bank transactions for cash flow tracking.

    Tracks individual transactions in bank accounts.
    """

    __tablename__ = "freeagent_bank_transactions"

    transaction_id = Column(Text, primary_key=True)  # Extract from URL
    source = Column(Text, nullable=False, default="freeagent")

    # Bank account relationship
    bank_account_id = Column(Text)  # Extract from bank_account URL

    # Transaction details
    dated_on = Column(DateTime(timezone=True))
    amount = Column(Numeric(15, 2))
    description = Column(Text)

    # Transaction identification
    bank_reference = Column(Text)
    transaction_type = Column(Text)

    # Balance information
    running_balance = Column(Numeric(15, 2))

    # Processing status
    is_manual = Column(Text)  # Boolean as string

    # Timestamps
    created_at_api = Column(DateTime(timezone=True))
    updated_at_api = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Indexes
    __table_args__ = (
        Index("ix_freeagent_bank_transactions_account", "bank_account_id"),
        Index("ix_freeagent_bank_transactions_dated_on", "dated_on"),
        Index("ix_freeagent_bank_transactions_amount", "amount"),
        Index("ix_freeagent_bank_transactions_type", "transaction_type"),
        Index("ix_freeagent_bank_transactions_updated", "updated_at_api"),
    )


class FreeAgentBankTransactionExplanation(Base):
    """
    FreeAgent bank transaction explanations for transaction categorization.

    Tracks how bank transactions are explained/categorized for accounting.
    """

    __tablename__ = "freeagent_bank_transaction_explanations"

    explanation_id = Column(Text, primary_key=True)  # Extract from URL
    source = Column(Text, nullable=False, default="freeagent")

    # Bank transaction relationship
    bank_transaction_id = Column(Text)  # Extract from bank_transaction URL
    bank_account_id = Column(Text)  # Extract from bank_account URL

    # Transaction details
    dated_on = Column(DateTime(timezone=True))
    amount = Column(Numeric(15, 2))
    description = Column(Text)

    # Categorization
    category_id = Column(Text)  # Extract from category URL
    category_name = Column(Text)

    # Foreign currency
    foreign_currency_amount = Column(Numeric(15, 2))
    foreign_currency_type = Column(Text)

    # Sales tax
    gross_value = Column(Numeric(15, 2))
    sales_tax_rate = Column(Numeric(5, 2))
    sales_tax_value = Column(Numeric(15, 2))

    # Associated items
    invoice_id = Column(Text)  # Extract from invoice URL if present
    bill_id = Column(Text)  # Extract from bill URL if present

    # Timestamps
    created_at_api = Column(DateTime(timezone=True))
    updated_at_api = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Indexes
    __table_args__ = (
        Index("ix_freeagent_bank_explanations_transaction", "bank_transaction_id"),
        Index("ix_freeagent_bank_explanations_account", "bank_account_id"),
        Index("ix_freeagent_bank_explanations_category", "category_id"),
        Index("ix_freeagent_bank_explanations_dated_on", "dated_on"),
        Index("ix_freeagent_bank_explanations_updated", "updated_at_api"),
    )


class FreeAgentTransaction(Base):
    """
    FreeAgent accounting transactions for double-entry bookkeeping.

    Tracks individual accounting entries in the general ledger.
    """

    __tablename__ = "freeagent_transactions"

    transaction_id = Column(Text, primary_key=True)  # Extract from URL
    source = Column(Text, nullable=False, default="freeagent")

    # Transaction details
    dated_on = Column(DateTime(timezone=True))
    description = Column(Text)

    # Category classification
    category_id = Column(Text)  # Extract from category URL
    category_name = Column(Text)
    nominal_code = Column(Text)

    # Amounts (debit and credit); FreeAgent returns one or both per entry
    debit_value = Column(Numeric(15, 2))
    credit_value = Column(Numeric(15, 2))

    # Source document
    source_item_url = Column(Text)  # URL to source document (invoice, bill, etc.)

    # Foreign currency data (stored as JSON text)
    foreign_currency_data = Column(Text)

    # Timestamps
    created_at_api = Column(DateTime(timezone=True))
    updated_at_api = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Indexes
    __table_args__ = (
        Index("ix_freeagent_transactions_dated_on", "dated_on"),
        Index("ix_freeagent_transactions_category", "category_id"),
        Index("ix_freeagent_transactions_nominal_code", "nominal_code"),
        Index("ix_freeagent_transactions_debit_value", "debit_value"),
        Index("ix_freeagent_transactions_updated", "updated_at_api"),
    )


class FreeAgentUser(Base):
    """
    FreeAgent users for access control and team management.

    Tracks users who have access to the FreeAgent account.
    """

    __tablename__ = "freeagent_users"

    user_id = Column(Text, primary_key=True)  # Extract from URL
    source = Column(Text, nullable=False, default="freeagent")

    # User identification
    email = Column(Text)
    first_name = Column(Text)
    last_name = Column(Text)

    # UK tax information
    ni_number = Column(Text)  # National Insurance Number
    unique_tax_reference = Column(Text)

    # Role and permissions
    role = Column(Text)  # 'Owner', 'Director', 'Employee', etc.
    permission_level = Column(Integer)

    # Business details
    opening_mileage = Column(Numeric(10, 2))

    # Payroll information (JSON stored as text)
    current_payroll_profile = Column(Text)

    # Timestamps
    created_at_api = Column(DateTime(timezone=True))
    updated_at_api = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Indexes
    __table_args__ = (
        Index("ix_freeagent_users_email", "email"),
        Index("ix_freeagent_users_role", "role"),
        Index("ix_freeagent_users_permission_level", "permission_level"),
        Index("ix_freeagent_users_updated", "updated_at_api"),
    )

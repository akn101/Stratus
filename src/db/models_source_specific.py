"""
Source-specific database models for the Stratus ERP Integration Service.

This module contains SQLAlchemy models representing data tables organized by source.
Each integration (Shopify, ShipBob, Amazon, FreeAgent) has its own set of tables.
"""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import declarative_base, relationship

# Create base class for all models
Base = declarative_base()


# =============================================================================
# SHOPIFY MODELS
# =============================================================================

class ShopifyOrder(Base):
    """Shopify order data with human-readable order IDs."""
    
    __tablename__ = "shopify_orders"

    order_id = Column(Text, primary_key=True)  # Human-readable ID like "2124"
    shopify_internal_id = Column(Text, nullable=True)  # Internal Shopify ID like "6913240793415"
    purchase_date = Column(DateTime(timezone=True), nullable=False)
    status = Column(Text)
    customer_id = Column(Text)
    total = Column(Numeric(12, 2))
    currency = Column(Text)
    
    # Fulfillment tracking
    tracking_number = Column(Text)
    carrier = Column(Text)
    tracking_url = Column(Text)
    tracking_updated_at = Column(DateTime(timezone=True))
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship to order items
    items = relationship("ShopifyOrderItem", back_populates="order", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_shopify_orders_purchase_date", "purchase_date"),
        Index("ix_shopify_orders_shopify_internal_id", "shopify_internal_id"),
    )


class ShopifyOrderItem(Base):
    """Individual line items within Shopify orders."""
    
    __tablename__ = "shopify_order_items"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    order_id = Column(Text, ForeignKey("shopify_orders.order_id", ondelete="CASCADE"), nullable=False)
    sku = Column(Text, nullable=False)
    qty = Column(Integer, nullable=False)
    price = Column(Numeric(12, 2))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship back to order
    order = relationship("ShopifyOrder", back_populates="items")

    __table_args__ = (
        Index("ix_shopify_order_items_order_id", "order_id"),
        Index("ix_shopify_order_items_sku", "sku"),
        UniqueConstraint("order_id", "sku", name="uq_shopify_order_items_order_sku"),
    )


class ShopifyCustomer(Base):
    """Shopify customer data."""
    
    __tablename__ = "shopify_customers"

    customer_id = Column(Text, primary_key=True)
    first_name = Column(Text)
    last_name = Column(Text)
    email = Column(Text)
    phone = Column(Text)
    total_spent = Column(Numeric(12, 2))
    orders_count = Column(Integer, default=0)
    state = Column(Text)  # enabled/disabled
    created_at_shopify = Column(DateTime(timezone=True))
    updated_at_shopify = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_shopify_customers_email", "email"),
        Index("ix_shopify_customers_state", "state"),
    )


class ShopifyProduct(Base):
    """Shopify product data."""
    
    __tablename__ = "shopify_products"

    product_id = Column(Text, primary_key=True)
    title = Column(Text, nullable=False)
    handle = Column(Text)
    status = Column(Text)  # active, archived, draft
    product_type = Column(Text)
    vendor = Column(Text)
    created_at_shopify = Column(DateTime(timezone=True))
    updated_at_shopify = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship to variants
    variants = relationship("ShopifyVariant", back_populates="product", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_shopify_products_status", "status"),
        Index("ix_shopify_products_vendor", "vendor"),
    )


class ShopifyVariant(Base):
    """Shopify product variants."""
    
    __tablename__ = "shopify_variants"

    variant_id = Column(Text, primary_key=True)
    product_id = Column(Text, ForeignKey("shopify_products.product_id", ondelete="CASCADE"), nullable=False)
    title = Column(Text)
    sku = Column(Text)
    price = Column(Numeric(12, 2))
    inventory_quantity = Column(Integer, default=0)
    weight = Column(Numeric(8, 3))  # in grams
    created_at_shopify = Column(DateTime(timezone=True))
    updated_at_shopify = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship back to product
    product = relationship("ShopifyProduct", back_populates="variants")

    __table_args__ = (
        Index("ix_shopify_variants_sku", "sku"),
        Index("ix_shopify_variants_product_id", "product_id"),
    )


# =============================================================================
# SHIPBOB MODELS  
# =============================================================================

class ShipBobInventory(Base):
    """ShipBob inventory levels."""
    
    __tablename__ = "shipbob_inventory"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    sku = Column(Text, nullable=False)
    quantity_on_hand = Column(Integer, default=0)
    quantity_available = Column(Integer, default=0)
    quantity_reserved = Column(Integer, default=0)
    quantity_incoming = Column(Integer, default=0)
    fulfillable_quantity = Column(Integer, default=0)
    backordered_quantity = Column(Integer, default=0)
    exception_quantity = Column(Integer, default=0)
    internal_transfer_quantity = Column(Integer, default=0)
    last_updated = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_shipbob_inventory_sku", "sku"),
        Index("ix_shipbob_inventory_last_updated", "last_updated"),
        UniqueConstraint("sku", name="uq_shipbob_inventory_sku"),
    )


class ShipBobProduct(Base):
    """ShipBob product master data."""
    
    __tablename__ = "shipbob_products"

    product_id = Column(Text, primary_key=True)
    reference_id = Column(Text)  # Client's product ID
    name = Column(Text, nullable=False)
    created_date = Column(DateTime(timezone=True))
    last_modified_date = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship to variants
    variants = relationship("ShipBobVariant", back_populates="product", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_shipbob_products_reference_id", "reference_id"),
    )


class ShipBobVariant(Base):
    """ShipBob product variants (inventory items)."""
    
    __tablename__ = "shipbob_variants"

    inventory_id = Column(Text, primary_key=True)
    product_id = Column(Text, ForeignKey("shipbob_products.product_id", ondelete="CASCADE"), nullable=False)
    sku = Column(Text, nullable=False)
    name = Column(Text)
    quantity_on_hand = Column(Integer, default=0)
    quantity_available = Column(Integer, default=0)
    quantity_committed = Column(Integer, default=0)
    quantity_backordered = Column(Integer, default=0)
    created_date = Column(DateTime(timezone=True))
    last_modified_date = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship back to product
    product = relationship("ShipBobProduct", back_populates="variants")

    __table_args__ = (
        Index("ix_shipbob_variants_sku", "sku"),
        Index("ix_shipbob_variants_product_id", "product_id"),
        UniqueConstraint("sku", name="uq_shipbob_variants_sku"),
    )


class ShipBobFulfillmentCenter(Base):
    """ShipBob fulfillment centers."""
    
    __tablename__ = "shipbob_fulfillment_centers"

    fulfillment_center_id = Column(Text, primary_key=True)
    name = Column(Text, nullable=False)
    company_name = Column(Text)
    email = Column(Text)
    phone = Column(Text)
    address_line_1 = Column(Text)
    address_line_2 = Column(Text)
    city = Column(Text)
    state = Column(Text)
    country = Column(Text)
    zip_code = Column(Text)
    is_active = Column(Boolean, default=True)
    timezone = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# =============================================================================
# AMAZON MODELS
# =============================================================================

class AmazonSettlement(Base):
    """Amazon settlements (renamed from settlements)."""
    
    __tablename__ = "amazon_settlements"

    settlement_id = Column(Text, primary_key=True)
    settlement_start_date = Column(DateTime(timezone=True))
    settlement_end_date = Column(DateTime(timezone=True))
    deposit_date = Column(DateTime(timezone=True))
    total_amount = Column(Numeric(12, 2))
    currency = Column(Text)
    marketplace_id = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship to settlement lines
    lines = relationship("AmazonSettlementLine", back_populates="settlement", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_amazon_settlements_deposit_date", "deposit_date"),
        Index("ix_amazon_settlements_marketplace_id", "marketplace_id"),
    )


class AmazonSettlementLine(Base):
    """Amazon settlement line items (renamed from settlement_lines)."""
    
    __tablename__ = "amazon_settlement_lines"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    settlement_id = Column(Text, ForeignKey("amazon_settlements.settlement_id", ondelete="CASCADE"), nullable=False)
    posted_date = Column(DateTime(timezone=True))
    order_id = Column(Text)
    sku = Column(Text)
    description = Column(Text)
    quantity = Column(Integer)
    amount = Column(Numeric(12, 2))
    type = Column(Text)  # Order, Refund, etc.
    fee_type = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship back to settlement
    settlement = relationship("AmazonSettlement", back_populates="lines")

    __table_args__ = (
        Index("ix_amazon_settlement_lines_settlement_id", "settlement_id"),
        Index("ix_amazon_settlement_lines_order_id", "order_id"),
        Index("ix_amazon_settlement_lines_sku", "sku"),
    )


# =============================================================================
# FREEAGENT MODELS (keep existing)
# =============================================================================

class FreeAgentContact(Base):
    """FreeAgent contacts (customers/suppliers)."""
    
    __tablename__ = "freeagent_contacts"

    contact_id = Column(Text, primary_key=True)
    contact_type = Column(Text)  # Company, Person
    organisation_name = Column(Text)
    first_name = Column(Text)
    last_name = Column(Text)
    email = Column(Text)
    phone_number = Column(Text)
    address1 = Column(Text)
    address2 = Column(Text) 
    address3 = Column(Text)
    town = Column(Text)
    region = Column(Text)
    country = Column(Text)
    postcode = Column(Text)
    contact_name_on_invoices = Column(Boolean, default=False)
    default_payment_terms_in_days = Column(Integer)
    locale = Column(Text)
    account_balance = Column(Numeric(12, 2))
    uses_contact_invoice_sequence = Column(Boolean, default=False)
    charge_sales_tax = Column(Text)  # Always, Never, Automatic
    sales_tax_registration_number = Column(Text)
    active_projects_count = Column(Integer, default=0)
    status = Column(Text)  # Active, Hidden
    created_at_api = Column(DateTime(timezone=True))
    updated_at_api = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_freeagent_contacts_email", "email"),
        Index("ix_freeagent_contacts_contact_type", "contact_type"),
        Index("ix_freeagent_contacts_status", "status"),
    )


class FreeAgentInvoice(Base):
    """FreeAgent invoices (sales)."""
    
    __tablename__ = "freeagent_invoices"

    invoice_id = Column(Text, primary_key=True)
    reference = Column(Text)
    dated_on = Column(DateTime(timezone=True))
    due_on = Column(DateTime(timezone=True))
    contact_id = Column(Text)
    contact_name = Column(Text)
    net_value = Column(Numeric(12, 2))
    sales_tax_value = Column(Numeric(12, 2))
    total_value = Column(Numeric(12, 2))
    paid_value = Column(Numeric(12, 2))
    due_value = Column(Numeric(12, 2))
    currency = Column(Text)
    exchange_rate = Column(Numeric(10, 6))
    net_value_in_base_currency = Column(Numeric(12, 2))
    status = Column(Text)  # Draft, Sent, etc.
    payment_terms_in_days = Column(Integer)
    sales_tax_status = Column(Text)
    outside_of_sales_tax_scope = Column(Text)
    initial_sales_tax_rate = Column(Numeric(5, 4))
    comments = Column(Text)
    project_id = Column(Text)
    created_at_api = Column(DateTime(timezone=True))
    updated_at_api = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_freeagent_invoices_contact_id", "contact_id"),
        Index("ix_freeagent_invoices_dated_on", "dated_on"),
        Index("ix_freeagent_invoices_status", "status"),
    )


# =============================================================================
# SYSTEM MODELS
# =============================================================================

class SyncState(Base):
    """Track ETL sync state for incremental processing."""
    
    __tablename__ = "sync_state"

    domain = Column(Text, primary_key=True)  # e.g., "shopify_orders", "shipbob_inventory"
    status = Column(Text, nullable=False, default="idle")  # idle, running, success, failed
    last_synced_at = Column(DateTime(timezone=True))
    last_success_at = Column(DateTime(timezone=True)) 
    next_sync_at = Column(DateTime(timezone=True))
    high_water_mark = Column(Text)  # Last processed ID/timestamp
    sync_metadata = Column(Text)  # JSON metadata for sync state
    error_count = Column(Integer, default=0)
    last_error = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_sync_state_status", "status"),
        Index("ix_sync_state_last_synced_at", "last_synced_at"),
    )
"""
Source-specific UPSERT helpers for Stratus data warehouse.

Implements conflict resolution using SQLAlchemy's PostgreSQL insert().on_conflict_do_update
for idempotent data loading from external APIs into source-specific tables.
"""

from collections.abc import Sequence

from sqlalchemy import literal_column
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from .deps import get_session
from .models_source_specific import (
    ShopifyOrder,
    ShopifyOrderItem,
    ShopifyCustomer, 
    ShopifyProduct,
    ShopifyVariant,
    ShipBobInventory,
    ShipBobProduct,
    ShipBobVariant,
    ShipBobFulfillmentCenter,
    AmazonSettlement,
    AmazonSettlementLine,
    FreeAgentContact,
    FreeAgentInvoice,
)


def _exec_upsert(
    session: Session,
    table,
    rows: Sequence[dict],
    conflict_cols: Sequence[str],
    update_cols: Sequence[str],
) -> tuple[int, int]:
    """Execute a bulk upsert and return (inserted_count, updated_count).

    Uses RETURNING xmax to distinguish inserts (xmax=0) from updates.
    """
    if not rows:
        return 0, 0

    stmt = pg_insert(table).values(rows)
    update_values = {c: getattr(stmt.excluded, c) for c in update_cols}
    stmt = stmt.on_conflict_do_update(index_elements=list(conflict_cols), set_=update_values)

    result = session.execute(stmt.returning(literal_column("xmax")))
    xmax_values = [row[0] for row in result.fetchall()]
    updated_count = sum(1 for x in xmax_values if x != 0)
    inserted_count = len(xmax_values) - updated_count
    return inserted_count, updated_count


# =============================================================================
# SHOPIFY UPSERTS
# =============================================================================

def upsert_shopify_orders(rows: list[dict], session: Session | None = None) -> tuple[int, int]:
    """
    Upsert Shopify orders with conflict resolution on order_id.
    Returns (inserted_count, updated_count).
    """

    def _run(sess: Session) -> tuple[int, int]:
        return _exec_upsert(
            sess,
            ShopifyOrder.__table__,
            rows,
            conflict_cols=["order_id"],
            update_cols=[
                "shopify_internal_id",
                "purchase_date",
                "status",
                "fulfillment_status",
                "customer_id",
                "total",
                "currency",
                
                # Financial details
                "subtotal_price",
                "total_tax", 
                "total_discounts",
                "total_weight",
                
                # Contact information
                "email",
                "phone",
                
                # Order metadata
                "tags",
                "note",
                "confirmation_number",
                "order_number",
                
                # Marketing attribution
                "referring_site",
                "landing_site",
                "source_name",
                
                # Timestamps
                "processed_at",
                "closed_at",
                "cancelled_at",
                "updated_at_shopify",
                
                # Fulfillment tracking
                "tracking_number",
                "carrier",
                "tracking_url",
                "tracking_updated_at",
                
                # Addresses
                "billing_address",
                "shipping_address",
            ],
        )

    if session is not None:
        return _run(session)
    
    with get_session() as sess:
        result = _run(sess)
        sess.commit()
        return result


def upsert_shopify_order_items(rows: list[dict], session: Session | None = None) -> tuple[int, int]:
    """
    Upsert Shopify order items with conflict resolution on (order_id, sku).
    Returns (inserted_count, updated_count).
    """

    def _run(sess: Session) -> tuple[int, int]:
        return _exec_upsert(
            sess,
            ShopifyOrderItem.__table__,
            rows,
            conflict_cols=["order_id", "sku"],
            update_cols=["qty", "price"],
        )

    if session is not None:
        return _run(session)
    
    with get_session() as sess:
        result = _run(sess)
        sess.commit()
        return result


def upsert_shopify_customers(rows: list[dict], session: Session | None = None) -> tuple[int, int]:
    """
    Upsert Shopify customers with conflict resolution on customer_id.
    Returns (inserted_count, updated_count).
    """

    def _run(sess: Session) -> tuple[int, int]:
        return _exec_upsert(
            sess,
            ShopifyCustomer.__table__,
            rows,
            conflict_cols=["customer_id"],
            update_cols=[
                "first_name",
                "last_name", 
                "email",
                "phone",
                "total_spent",
                "orders_count",
                "state",
                "updated_at_shopify",
            ],
        )

    if session is not None:
        return _run(session)
    
    with get_session() as sess:
        result = _run(sess)
        sess.commit()
        return result


def upsert_shopify_products(rows: list[dict], session: Session | None = None) -> tuple[int, int]:
    """
    Upsert Shopify products with conflict resolution on product_id.
    Returns (inserted_count, updated_count).
    """

    def _run(sess: Session) -> tuple[int, int]:
        return _exec_upsert(
            sess,
            ShopifyProduct.__table__,
            rows,
            conflict_cols=["product_id"],
            update_cols=[
                "title",
                "handle",
                "status",
                "product_type",
                "vendor",
                "updated_at_shopify",
            ],
        )

    if session is not None:
        return _run(session)
    
    with get_session() as sess:
        result = _run(sess)
        sess.commit()
        return result


def upsert_shopify_variants(rows: list[dict], session: Session | None = None) -> tuple[int, int]:
    """
    Upsert Shopify variants with conflict resolution on variant_id.
    Returns (inserted_count, updated_count).
    """

    def _run(sess: Session) -> tuple[int, int]:
        return _exec_upsert(
            sess,
            ShopifyVariant.__table__,
            rows,
            conflict_cols=["variant_id"],
            update_cols=[
                "title",
                "sku",
                "price",
                "inventory_quantity",
                "weight",
                "updated_at_shopify",
            ],
        )

    if session is not None:
        return _run(session)
    
    with get_session() as sess:
        result = _run(sess)
        sess.commit()
        return result


# =============================================================================
# SHIPBOB UPSERTS
# =============================================================================

def upsert_shipbob_inventory(rows: list[dict], session: Session | None = None) -> tuple[int, int]:
    """
    Upsert ShipBob inventory with conflict resolution on sku.
    Returns (inserted_count, updated_count).
    """

    def _run(sess: Session) -> tuple[int, int]:
        return _exec_upsert(
            sess,
            ShipBobInventory.__table__,
            rows,
            conflict_cols=["sku"],
            update_cols=[
                "quantity_on_hand",
                "quantity_available",
                "quantity_reserved",
                "quantity_incoming",
                "fulfillable_quantity",
                "backordered_quantity",
                "exception_quantity",
                "internal_transfer_quantity",
                "last_updated",
            ],
        )

    if session is not None:
        return _run(session)
    
    with get_session() as sess:
        result = _run(sess)
        sess.commit()
        return result


def upsert_shipbob_products(rows: list[dict], session: Session | None = None) -> tuple[int, int]:
    """
    Upsert ShipBob products with conflict resolution on product_id.
    Returns (inserted_count, updated_count).
    """

    def _run(sess: Session) -> tuple[int, int]:
        return _exec_upsert(
            sess,
            ShipBobProduct.__table__,
            rows,
            conflict_cols=["product_id"],
            update_cols=[
                "reference_id",
                "name",
                "last_modified_date",
            ],
        )

    if session is not None:
        return _run(session)
    
    with get_session() as sess:
        result = _run(sess)
        sess.commit()
        return result


def upsert_shipbob_variants(rows: list[dict], session: Session | None = None) -> tuple[int, int]:
    """
    Upsert ShipBob variants with conflict resolution on inventory_id.
    Returns (inserted_count, updated_count).
    """

    def _run(sess: Session) -> tuple[int, int]:
        return _exec_upsert(
            sess,
            ShipBobVariant.__table__,
            rows,
            conflict_cols=["inventory_id"],
            update_cols=[
                "sku",
                "name",
                "quantity_on_hand",
                "quantity_available",
                "quantity_committed",
                "quantity_backordered",
                "last_modified_date",
            ],
        )

    if session is not None:
        return _run(session)
    
    with get_session() as sess:
        result = _run(sess)
        sess.commit()
        return result


def upsert_shipbob_fulfillment_centers(rows: list[dict], session: Session | None = None) -> tuple[int, int]:
    """
    Upsert ShipBob fulfillment centers with conflict resolution on fulfillment_center_id.
    Returns (inserted_count, updated_count).
    """

    def _run(sess: Session) -> tuple[int, int]:
        return _exec_upsert(
            sess,
            ShipBobFulfillmentCenter.__table__,
            rows,
            conflict_cols=["fulfillment_center_id"],
            update_cols=[
                "name",
                "company_name",
                "email",
                "phone",
                "address_line_1",
                "address_line_2",
                "city",
                "state",
                "country",
                "zip_code",
                "is_active",
                "timezone",
            ],
        )

    if session is not None:
        return _run(session)
    
    with get_session() as sess:
        result = _run(sess)
        sess.commit()
        return result


# =============================================================================
# AMAZON UPSERTS
# =============================================================================

def upsert_amazon_settlements(rows: list[dict], session: Session | None = None) -> tuple[int, int]:
    """
    Upsert Amazon settlements with conflict resolution on settlement_id.
    Returns (inserted_count, updated_count).
    """

    def _run(sess: Session) -> tuple[int, int]:
        return _exec_upsert(
            sess,
            AmazonSettlement.__table__,
            rows,
            conflict_cols=["settlement_id"],
            update_cols=[
                "settlement_start_date",
                "settlement_end_date",
                "deposit_date",
                "total_amount",
                "currency",
                "marketplace_id",
            ],
        )

    if session is not None:
        return _run(session)
    
    with get_session() as sess:
        result = _run(sess)
        sess.commit()
        return result


def upsert_amazon_settlement_lines(rows: list[dict], session: Session | None = None) -> tuple[int, int]:
    """
    Upsert Amazon settlement lines with conflict resolution on id.
    Returns (inserted_count, updated_count).
    """

    def _run(sess: Session) -> tuple[int, int]:
        return _exec_upsert(
            sess,
            AmazonSettlementLine.__table__,
            rows,
            conflict_cols=["id"],
            update_cols=[
                "posted_date",
                "order_id",
                "sku",
                "description",
                "quantity",
                "amount",
                "type",
                "fee_type",
            ],
        )

    if session is not None:
        return _run(session)
    
    with get_session() as sess:
        result = _run(sess)
        sess.commit()
        return result


# =============================================================================
# FREEAGENT UPSERTS
# =============================================================================

def upsert_freeagent_contacts(rows: list[dict], session: Session | None = None) -> tuple[int, int]:
    """
    Upsert FreeAgent contacts with conflict resolution on contact_id.
    Returns (inserted_count, updated_count).
    """

    def _run(sess: Session) -> tuple[int, int]:
        return _exec_upsert(
            sess,
            FreeAgentContact.__table__,
            rows,
            conflict_cols=["contact_id"],
            update_cols=[
                "contact_type",
                "organisation_name",
                "first_name",
                "last_name",
                "email",
                "phone_number",
                "address1",
                "address2", 
                "address3",
                "town",
                "region",
                "country",
                "postcode",
                "contact_name_on_invoices",
                "default_payment_terms_in_days",
                "locale",
                "account_balance",
                "uses_contact_invoice_sequence",
                "charge_sales_tax",
                "sales_tax_registration_number",
                "active_projects_count",
                "status",
                "updated_at_api",
            ],
        )

    if session is not None:
        return _run(session)
    
    with get_session() as sess:
        result = _run(sess)
        sess.commit()
        return result


def upsert_freeagent_invoices(rows: list[dict], session: Session | None = None) -> tuple[int, int]:
    """
    Upsert FreeAgent invoices with conflict resolution on invoice_id.
    Returns (inserted_count, updated_count).
    """

    def _run(sess: Session) -> tuple[int, int]:
        return _exec_upsert(
            sess,
            FreeAgentInvoice.__table__,
            rows,
            conflict_cols=["invoice_id"],
            update_cols=[
                "reference",
                "dated_on",
                "due_on",
                "contact_id",
                "contact_name",
                "net_value",
                "sales_tax_value",
                "total_value",
                "paid_value",
                "due_value",
                "currency",
                "exchange_rate",
                "net_value_in_base_currency",
                "status",
                "payment_terms_in_days",
                "sales_tax_status",
                "outside_of_sales_tax_scope",
                "initial_sales_tax_rate",
                "comments",
                "project_id",
                "updated_at_api",
            ],
        )

    if session is not None:
        return _run(session)
    
    with get_session() as sess:
        result = _run(sess)
        sess.commit()
        return result
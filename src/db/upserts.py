"""
Generic UPSERT helpers for Stratus data warehouse.

Implements conflict resolution using SQLAlchemy's PostgreSQL insert().on_conflict_do_update
for idempotent data loading from external APIs.
"""

from collections.abc import Sequence

from sqlalchemy import literal_column
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from .deps import get_session
from .models import (
    FreeAgentBankAccount,
    FreeAgentBankTransaction,
    FreeAgentBankTransactionExplanation,
    FreeAgentBill,
    FreeAgentCategory,
    FreeAgentContact,
    FreeAgentInvoice,
    FreeAgentTransaction,
    FreeAgentUser,
    Inventory,
    Invoice,
    Order,
    OrderItem,
    Settlement,
    SettlementLine,
    ShopifyCustomer,
    ShopifyProduct,
    ShopifyVariant,
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


def upsert_orders(rows: list[dict], session: Session | None = None) -> tuple[int, int]:
    """
    Upsert orders with conflict resolution on order_id.
    Returns (inserted_count, updated_count).
    """

    def _run(sess: Session) -> tuple[int, int]:
        return _exec_upsert(
            sess,
            Order.__table__,
            rows,
            conflict_cols=["order_id"],
            update_cols=[
                "source",
                "purchase_date",
                "status",
                "customer_id",
                "total",
                "currency",
                "marketplace_id",
                "shopify_internal_id",
            ],
        )

    if session is not None:
        return _run(session)
    with get_session() as sess:
        return _run(sess)


def upsert_order_items(rows: list[dict], session: Session | None = None) -> tuple[int, int]:
    """
    Upsert order items with conflict on (order_id, sku).
    Returns (inserted_count, updated_count).
    """

    def _run(sess: Session) -> tuple[int, int]:
        return _exec_upsert(
            sess,
            OrderItem.__table__,
            rows,
            conflict_cols=["order_id", "sku"],
            update_cols=[
                "asin",
                "qty",
                "price",
                "tax",
                "fee_estimate",
            ],
        )

    if session is not None:
        return _run(session)
    with get_session() as sess:
        return _run(sess)


def upsert_inventory(rows: list[dict], session: Session | None = None) -> tuple[int, int]:
    """
    Upsert inventory with conflict on (sku, source).
    Returns (inserted_count, updated_count).
    """

    def _run(sess: Session) -> tuple[int, int]:
        # Backward-compatible field mapping: accept legacy Amazon keys
        transformed: list[dict] = []
        for r in rows:
            m = dict(r)
            # Default source to 'amazon' if missing
            m.setdefault("source", "amazon")
            if "fc" in m and "fulfillment_center" not in m:
                m["fulfillment_center"] = m.get("fc")
            if "on_hand" in m and "quantity_on_hand" not in m:
                m["quantity_on_hand"] = m.get("on_hand")
            if "reserved" in m and "quantity_reserved" not in m:
                m["quantity_reserved"] = m.get("reserved")
            if "inbound" in m and "quantity_incoming" not in m:
                m["quantity_incoming"] = m.get("inbound")
            if "updated_at" in m and "last_updated" not in m:
                m["last_updated"] = m.get("updated_at")
            transformed.append(m)

        return _exec_upsert(
            sess,
            Inventory.__table__,
            transformed,
            conflict_cols=["sku", "source"],
            update_cols=[
                "quantity_on_hand",
                "quantity_available",
                "quantity_reserved",
                "quantity_incoming",
                "asin",
                "fnsku",
                "fulfillment_center",
                "inventory_id",
                "inventory_name",
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
        return _run(sess)


def upsert_settlements(rows: list[dict], session: Session | None = None) -> tuple[int, int]:
    """
    Upsert settlements with conflict on settlement_id.
    Returns (inserted_count, updated_count).
    """

    def _run(sess: Session) -> tuple[int, int]:
        return _exec_upsert(
            sess,
            Settlement.__table__,
            rows,
            conflict_cols=["settlement_id"],
            update_cols=[
                "period_start",
                "period_end",
                "gross",
                "fees",
                "refunds",
                "net",
                "currency",
            ],
        )

    if session is not None:
        return _run(session)
    with get_session() as sess:
        return _run(sess)


def upsert_settlement_lines(rows: list[dict], session: Session | None = None) -> tuple[int, int]:
    """
    Upsert settlement lines with conflict on (settlement_id, order_id, type, posted_date).
    Returns (inserted_count, updated_count).
    """

    def _run(sess: Session) -> tuple[int, int]:
        return _exec_upsert(
            sess,
            SettlementLine.__table__,
            rows,
            conflict_cols=["settlement_id", "order_id", "type", "posted_date"],
            update_cols=[
                "amount",
                "fee_type",
            ],
        )

    if session is not None:
        return _run(session)
    with get_session() as sess:
        return _run(sess)


def upsert_invoices(rows: list[dict], session: Session | None = None) -> tuple[int, int]:
    """
    Upsert invoices with conflict on invoice_id.
    Returns (inserted_count, updated_count).
    """

    def _run(sess: Session) -> tuple[int, int]:
        return _exec_upsert(
            sess,
            Invoice.__table__,
            rows,
            conflict_cols=["invoice_id"],
            update_cols=[
                "source",
                "amount",
                "currency",
                "fa_status",
            ],
        )

    if session is not None:
        return _run(session)
    with get_session() as sess:
        return _run(sess)


def upsert_shopify_customers(rows: list[dict], session: Session | None = None) -> tuple[int, int]:
    """
    Upsert Shopify customers with conflict on customer_id.
    Returns (inserted_count, updated_count).
    """

    def _run(sess: Session) -> tuple[int, int]:
        return _exec_upsert(
            sess,
            ShopifyCustomer.__table__,
            rows,
            conflict_cols=["customer_id"],
            update_cols=[
                "email",
                "first_name",
                "last_name",
                "created_at",
                "updated_at",
                "total_spent",
                "orders_count",
                "state",
                "tags",
                "last_order_id",
                "last_order_date",
            ],
        )

    if session is not None:
        return _run(session)
    with get_session() as sess:
        return _run(sess)


def upsert_shopify_products(rows: list[dict], session: Session | None = None) -> tuple[int, int]:
    """
    Upsert Shopify products with conflict on product_id.
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
                "vendor",
                "product_type",
                "created_at",
                "updated_at",
            ],
        )

    if session is not None:
        return _run(session)
    with get_session() as sess:
        return _run(sess)


def upsert_shopify_variants(rows: list[dict], session: Session | None = None) -> tuple[int, int]:
    """
    Upsert Shopify variants with conflict on variant_id.
    Returns (inserted_count, updated_count).
    """

    def _run(sess: Session) -> tuple[int, int]:
        return _exec_upsert(
            sess,
            ShopifyVariant.__table__,
            rows,
            conflict_cols=["variant_id"],
            update_cols=[
                "product_id",
                "sku",
                "price",
                "inventory_item_id",
                "created_at",
                "updated_at",
            ],
        )

    if session is not None:
        return _run(session)
    with get_session() as sess:
        return _run(sess)


# FreeAgent Upsert Functions


def upsert_freeagent_contacts(rows: list[dict], session: Session | None = None) -> tuple[int, int]:
    """
    Upsert FreeAgent contacts with conflict on contact_id.
    Returns (inserted_count, updated_count).
    """

    def _run(sess: Session) -> tuple[int, int]:
        return _exec_upsert(
            sess,
            FreeAgentContact.__table__,
            rows,
            conflict_cols=["contact_id"],
            update_cols=[
                "organisation_name",
                "first_name",
                "last_name",
                "contact_name_on_invoices",
                "email",
                "phone_number",
                "mobile",
                "fax",
                "address1",
                "address2",
                "address3",
                "town",
                "region",
                "postcode",
                "country",
                "contact_type",
                "default_payment_terms_in_days",
                "charge_sales_tax",
                "sales_tax_registration_number",
                "active_projects_count",
                "account_balance",
                "uses_contact_invoice_sequence",
                "status",
                "updated_at_api",
            ],
        )

    if session is not None:
        return _run(session)
    with get_session() as sess:
        return _run(sess)


def upsert_freeagent_invoices(rows: list[dict], session: Session | None = None) -> tuple[int, int]:
    """
    Upsert FreeAgent invoices with conflict on invoice_id.
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
        return _run(sess)


def upsert_freeagent_bills(rows: list[dict], session: Session | None = None) -> tuple[int, int]:
    """
    Upsert FreeAgent bills with conflict on bill_id.
    Returns (inserted_count, updated_count).
    """

    def _run(sess: Session) -> tuple[int, int]:
        return _exec_upsert(
            sess,
            FreeAgentBill.__table__,
            rows,
            conflict_cols=["bill_id"],
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
                "status",
                "sales_tax_status",
                "comments",
                "project_id",
                "updated_at_api",
            ],
        )

    if session is not None:
        return _run(session)
    with get_session() as sess:
        return _run(sess)


def upsert_freeagent_categories(
    rows: list[dict], session: Session | None = None
) -> tuple[int, int]:
    """
    Upsert FreeAgent categories with conflict on category_id.
    Returns (inserted_count, updated_count).
    """

    def _run(sess: Session) -> tuple[int, int]:
        return _exec_upsert(
            sess,
            FreeAgentCategory.__table__,
            rows,
            conflict_cols=["category_id"],
            update_cols=[
                "description",
                "nominal_code",
                "category_type",
                "parent_category_id",
                "auto_sales_tax_rate",
                "allowable_for_tax",
                "is_visible",
                "group_description",
            ],
        )

    if session is not None:
        return _run(session)
    with get_session() as sess:
        return _run(sess)


def upsert_freeagent_bank_accounts(
    rows: list[dict], session: Session | None = None
) -> tuple[int, int]:
    """
    Upsert FreeAgent bank accounts with conflict on bank_account_id.
    Returns (inserted_count, updated_count).
    """

    def _run(sess: Session) -> tuple[int, int]:
        return _exec_upsert(
            sess,
            FreeAgentBankAccount.__table__,
            rows,
            conflict_cols=["bank_account_id"],
            update_cols=[
                "name",
                "bank_name",
                "type",
                "account_number",
                "sort_code",
                "iban",
                "bic",
                "current_balance",
                "currency",
                "is_primary",
                "is_personal",
                "email_new_transactions",
                "default_bill_category_id",
                "opening_balance_date",
            ],
        )

    if session is not None:
        return _run(session)
    with get_session() as sess:
        return _run(sess)


def upsert_freeagent_bank_transactions(
    rows: list[dict], session: Session | None = None
) -> tuple[int, int]:
    """
    Upsert FreeAgent bank transactions with conflict on transaction_id.
    Returns (inserted_count, updated_count).
    """

    def _run(sess: Session) -> tuple[int, int]:
        return _exec_upsert(
            sess,
            FreeAgentBankTransaction.__table__,
            rows,
            conflict_cols=["transaction_id"],
            update_cols=[
                "bank_account_id",
                "dated_on",
                "amount",
                "description",
                "bank_reference",
                "transaction_type",
                "running_balance",
                "is_manual",
                "updated_at_api",
            ],
        )

    if session is not None:
        return _run(session)
    with get_session() as sess:
        return _run(sess)


def upsert_freeagent_bank_transaction_explanations(
    rows: list[dict], session: Session | None = None
) -> tuple[int, int]:
    """
    Upsert FreeAgent bank transaction explanations with conflict on explanation_id.
    Returns (inserted_count, updated_count).
    """

    def _run(sess: Session) -> tuple[int, int]:
        return _exec_upsert(
            sess,
            FreeAgentBankTransactionExplanation.__table__,
            rows,
            conflict_cols=["explanation_id"],
            update_cols=[
                "bank_transaction_id",
                "bank_account_id",
                "dated_on",
                "amount",
                "description",
                "category_id",
                "category_name",
                "foreign_currency_amount",
                "foreign_currency_type",
                "gross_value",
                "sales_tax_rate",
                "sales_tax_value",
                "invoice_id",
                "bill_id",
                "updated_at_api",
            ],
        )

    if session is not None:
        return _run(session)
    with get_session() as sess:
        return _run(sess)


def upsert_freeagent_transactions(
    rows: list[dict], session: Session | None = None
) -> tuple[int, int]:
    """
    Upsert FreeAgent accounting transactions with conflict on transaction_id.
    Returns (inserted_count, updated_count).
    """

    def _run(sess: Session) -> tuple[int, int]:
        return _exec_upsert(
            sess,
            FreeAgentTransaction.__table__,
            rows,
            conflict_cols=["transaction_id"],
            update_cols=[
                "dated_on",
                "description",
                "category_id",
                "category_name",
                "nominal_code",
                "debit_value",
                "credit_value",
                "source_item_url",
                "foreign_currency_data",
                "updated_at_api",
            ],
        )

    if session is not None:
        return _run(session)
    with get_session() as sess:
        return _run(sess)


def upsert_freeagent_users(rows: list[dict], session: Session | None = None) -> tuple[int, int]:
    """
    Upsert FreeAgent users with conflict on user_id.
    Returns (inserted_count, updated_count).
    """

    def _run(sess: Session) -> tuple[int, int]:
        return _exec_upsert(
            sess,
            FreeAgentUser.__table__,
            rows,
            conflict_cols=["user_id"],
            update_cols=[
                "email",
                "first_name",
                "last_name",
                "ni_number",
                "unique_tax_reference",
                "role",
                "permission_level",
                "opening_mileage",
                "current_payroll_profile",
                "updated_at_api",
            ],
        )

    if session is not None:
        return _run(session)
    with get_session() as sess:
        return _run(sess)

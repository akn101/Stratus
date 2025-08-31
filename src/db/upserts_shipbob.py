"""
ShipBob-specific upsert functions for order tracking updates.
"""

from typing import Optional

from .deps import get_session
from .models import (
    Order,
    ShipBobFulfillmentCenter,
    ShipBobProduct,
    ShipBobReceivingOrder,
    ShipBobReturn,
    ShipBobVariant,
)
from .upserts import _exec_upsert


def update_order_tracking(rows: list[dict], session: Optional = None) -> tuple[int, int]:
    """
    Update order tracking information (status, tracking_number, carrier, etc.).
    Only updates orders that exist in the database.
    Returns (inserted_count, updated_count) - inserted_count will be 0.
    """

    def _run(sess) -> tuple[int, int]:
        return _exec_upsert(
            sess,
            Order.__table__,
            rows,
            conflict_cols=["order_id"],
            update_cols=[
                "status",
                "tracking_number",
                "carrier",
                "tracking_url",
                "tracking_updated_at",
            ],
        )

    if session is not None:
        return _run(session)
    with get_session() as sess:
        return _run(sess)


def upsert_shipbob_returns(rows: list[dict], session: Optional = None) -> tuple[int, int]:
    """
    Upsert ShipBob return orders with conflict resolution on return_id.
    Returns (inserted_count, updated_count).
    """

    def _run(sess) -> tuple[int, int]:
        return _exec_upsert(
            sess,
            ShipBobReturn.__table__,
            rows,
            conflict_cols=["return_id"],
            update_cols=[
                "original_shipment_id",
                "reference_id",
                "store_order_id",
                "status",
                "return_type",
                "customer_name",
                "tracking_number",
                "total_cost",
                "fulfillment_center_id",
                "fulfillment_center_name",
                "items",
                "transactions",
                "insert_date",
                "completed_date",
            ],
        )

    if session is not None:
        return _run(session)
    with get_session() as sess:
        return _run(sess)


def upsert_shipbob_receiving_orders(rows: list[dict], session: Optional = None) -> tuple[int, int]:
    """
    Upsert ShipBob warehouse receiving orders with conflict resolution on wro_id.
    Returns (inserted_count, updated_count).
    """

    def _run(sess) -> tuple[int, int]:
        return _exec_upsert(
            sess,
            ShipBobReceivingOrder.__table__,
            rows,
            conflict_cols=["wro_id"],
            update_cols=[
                "purchase_order_number",
                "status",
                "package_type",
                "box_packaging_type",
                "fulfillment_center_id",
                "fulfillment_center_name",
                "inventory_quantities",
                "status_history",
                "expected_arrival_date",
                "insert_date",
                "last_updated_date",
            ],
        )

    if session is not None:
        return _run(session)
    with get_session() as sess:
        return _run(sess)


def upsert_shipbob_products(rows: list[dict], session: Optional = None) -> tuple[int, int]:
    """
    Upsert ShipBob products with conflict resolution on product_id.
    Returns (inserted_count, updated_count).
    """

    def _run(sess) -> tuple[int, int]:
        return _exec_upsert(
            sess,
            ShipBobProduct.__table__,
            rows,
            conflict_cols=["product_id"],
            update_cols=[
                "name",
                "sku",
                "barcode",
                "description",
                "category",
                "is_case",
                "is_lot",
                "is_active",
                "is_bundle",
                "is_digital",
                "is_hazmat",
                "dimensions",
                "weight",
                "value",
            ],
        )

    if session is not None:
        return _run(session)
    with get_session() as sess:
        return _run(sess)


def upsert_shipbob_variants(rows: list[dict], session: Optional = None) -> tuple[int, int]:
    """
    Upsert ShipBob product variants with conflict resolution on variant_id.
    Returns (inserted_count, updated_count).
    """

    def _run(sess) -> tuple[int, int]:
        return _exec_upsert(
            sess,
            ShipBobVariant.__table__,
            rows,
            conflict_cols=["variant_id"],
            update_cols=[
                "product_id",
                "name",
                "sku",
                "barcode",
                "is_active",
                "dimensions",
                "weight",
                "value",
            ],
        )

    if session is not None:
        return _run(session)
    with get_session() as sess:
        return _run(sess)


def upsert_shipbob_fulfillment_centers(
    rows: list[dict], session: Optional = None
) -> tuple[int, int]:
    """
    Upsert ShipBob fulfillment centers with conflict resolution on center_id.
    Returns (inserted_count, updated_count).
    """

    def _run(sess) -> tuple[int, int]:
        return _exec_upsert(
            sess,
            ShipBobFulfillmentCenter.__table__,
            rows,
            conflict_cols=["center_id"],
            update_cols=[
                "name",
                "address1",
                "address2",
                "city",
                "state",
                "zip_code",
                "country",
                "phone_number",
                "email",
                "timezone",
            ],
        )

    if session is not None:
        return _run(session)
    with get_session() as sess:
        return _run(sess)

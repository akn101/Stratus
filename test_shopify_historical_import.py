#!/usr/bin/env python3
"""
Test script for Shopify historical order import with fixed pagination.
"""

import logging
import os
import sys
from datetime import datetime, UTC
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add src to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.adapters.shopify import ShopifyClient, ShopifyConfig
from src.db.deps import get_session
from src.db.upserts_source_specific import upsert_shopify_orders, upsert_shopify_order_items

# Configure logging with INFO level now that pagination is working
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def test_shopify_historical_import():
    """Test the historical import with fixed pagination."""
    logger.info("Starting Shopify historical import test")
    
    # Read credentials from environment
    shop = os.getenv("SHOPIFY_SHOP")
    access_token = os.getenv("SHOPIFY_ACCESS_TOKEN")
    
    if not shop or not access_token:
        logger.error("Missing SHOPIFY_SHOP or SHOPIFY_ACCESS_TOKEN environment variables")
        return False
        
    try:
        # Initialize client
        config = ShopifyConfig(shop=shop, access_token=access_token, api_version="2024-07")
        client = ShopifyClient(config=config)
        
        # Test the fixed get_all_orders method
        logger.info("Fetching all orders with fixed pagination...")
        
        # First, let's check how many total orders exist
        logger.info("Checking total order count...")
        try:
            response_data = client._make_request("GET", "orders/count.json", {"status": "any"})
            total_count = response_data.get("count", 0)
            logger.info(f"Total orders in store: {total_count}")
        except Exception as e:
            logger.warning(f"Could not get order count: {e}")
            
        orders, order_items = client.get_all_orders()
        
        logger.info(f"Retrieved {len(orders)} orders and {len(order_items)} order items")
        
        if orders:
            # Show order range
            order_names = [o.get("order_id", "N/A") for o in orders]
            try:
                # Extract numeric order IDs for range calculation
                numeric_orders = []
                for name in order_names:
                    if name and name != "N/A" and name.startswith("#"):
                        numeric_orders.append(int(name[1:]))
                    elif name and name.isdigit():
                        numeric_orders.append(int(name))
                        
                if numeric_orders:
                    min_order = min(numeric_orders)
                    max_order = max(numeric_orders)
                    logger.info(f"Order range: #{min_order} to #{max_order}")
                else:
                    logger.info(f"First order: {order_names[0]}, Last order: {order_names[-1]}")
            except Exception as e:
                logger.info(f"Could not determine order range: {e}")
                logger.info(f"First order: {order_names[0]}, Last order: {order_names[-1]}")
                
            # Show sample of tracking data
            tracking_orders = [o for o in orders if o.get("tracking_number")]
            logger.info(f"Orders with tracking: {len(tracking_orders)}/{len(orders)}")
            
            if tracking_orders:
                sample = tracking_orders[0]
                logger.info(f"Sample tracking data: Order {sample['order_id']} - {sample.get('carrier')} - {sample.get('tracking_number')}")
                
            # Show sample of available fields and data quality
            if orders:
                sample_order = orders[0]
                logger.info(f"Available fields in sample order: {list(sample_order.keys())}")
                
                # Show sample financial data
                sample_financial = {
                    'total': sample_order.get('total'),
                    'subtotal_price': sample_order.get('subtotal_price'),
                    'total_tax': sample_order.get('total_tax'),
                    'total_discounts': sample_order.get('total_discounts'),
                    'total_weight': sample_order.get('total_weight')
                }
                logger.info(f"Sample financial data: {sample_financial}")
                
                # Show address data quality
                has_billing = bool(sample_order.get('billing_address'))
                has_shipping = bool(sample_order.get('shipping_address'))
                logger.info(f"Address data: billing={has_billing}, shipping={has_shipping}")
                
                # Show metadata quality
                metadata_fields = ['tags', 'note', 'email', 'phone', 'source_name']
                metadata_present = {field: bool(sample_order.get(field)) for field in metadata_fields}
                logger.info(f"Metadata present: {metadata_present}")
        
        if not orders:
            logger.warning("No orders retrieved - this might indicate an issue")
            return False
            
        # Test database upsert in batches to avoid parameter limits
        logger.info("Testing database upsert in batches...")
        
        # Process in batches of 500 records
        batch_size = 500
        total_orders_inserted = total_orders_updated = 0
        total_items_inserted = total_items_updated = 0
        
        # Process orders in batches
        for i in range(0, len(orders), batch_size):
            batch_orders = orders[i:i + batch_size]
            logger.info(f"Processing orders batch {i//batch_size + 1}: {len(batch_orders)} orders")
            
            with get_session() as session:
                inserted, updated = upsert_shopify_orders(batch_orders, session)
                total_orders_inserted += inserted
                total_orders_updated += updated
                
        # Process order items in batches, deduplicating within each batch
        def deduplicate_items(items_batch):
            """Remove duplicates within batch, keeping last occurrence of each (order_id, sku)."""
            seen = {}
            for item in items_batch:
                key = (item['order_id'], item['sku'])
                seen[key] = item  # Keep last occurrence
            return list(seen.values())
        
        for i in range(0, len(order_items), batch_size):
            batch_items = order_items[i:i + batch_size]
            deduplicated_items = deduplicate_items(batch_items)
            
            logger.info(f"Processing items batch {i//batch_size + 1}: {len(batch_items)} items -> {len(deduplicated_items)} after dedup")
            
            with get_session() as session:
                inserted, updated = upsert_shopify_order_items(deduplicated_items, session)
                total_items_inserted += inserted
                total_items_updated += updated
        
        logger.info(f"Database results:")
        logger.info(f"  Orders: {total_orders_inserted} inserted, {total_orders_updated} updated")
        logger.info(f"  Items: {total_items_inserted} inserted, {total_items_updated} updated")
        
        return True
        
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    success = test_shopify_historical_import()
    sys.exit(0 if success else 1)
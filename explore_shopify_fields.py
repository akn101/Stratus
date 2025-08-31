#!/usr/bin/env python3
"""
Explore what fields are available in Shopify API responses.
"""

import logging
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add src to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.adapters.shopify import ShopifyClient, ShopifyConfig

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def explore_shopify_fields():
    """Explore available fields in Shopify API response."""
    
    shop = os.getenv("SHOPIFY_SHOP")
    access_token = os.getenv("SHOPIFY_ACCESS_TOKEN")
    
    if not shop or not access_token:
        logger.error("Missing SHOPIFY_SHOP or SHOPIFY_ACCESS_TOKEN environment variables")
        return
        
    try:
        config = ShopifyConfig(shop=shop, access_token=access_token, api_version="2024-07")
        client = ShopifyClient(config=config)
        
        # Get a single order with ALL fields (no fields parameter)
        logger.info("Fetching a single order with ALL fields...")
        response_data = client._make_request("GET", "orders.json", {"limit": 1, "status": "any"})
        
        orders = response_data.get("orders", [])
        if not orders:
            logger.error("No orders found")
            return
            
        order = orders[0]
        logger.info(f"Raw order fields: {list(order.keys())}")
        
        # Show some interesting nested fields
        if "customer" in order and order["customer"]:
            logger.info(f"Customer fields: {list(order['customer'].keys())}")
            
        if "line_items" in order and order["line_items"]:
            logger.info(f"Line item fields: {list(order['line_items'][0].keys())}")
            
        if "fulfillments" in order and order["fulfillments"]:
            logger.info(f"Fulfillment fields: {list(order['fulfillments'][0].keys())}")
        else:
            logger.info("No fulfillments in this order")
            
        # Show billing address if available
        if "billing_address" in order and order["billing_address"]:
            logger.info(f"Billing address fields: {list(order['billing_address'].keys())}")
            
        # Show shipping address if available  
        if "shipping_address" in order and order["shipping_address"]:
            logger.info(f"Shipping address fields: {list(order['shipping_address'].keys())}")

    except Exception as e:
        logger.error(f"Error: {e}")

if __name__ == "__main__":
    explore_shopify_fields()
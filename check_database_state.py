#!/usr/bin/env python3
"""
Check the current state of all Shopify tables and relationships.
"""

import logging
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add src to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.db.deps import get_session
from sqlalchemy import text

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def check_table_counts():
    """Check record counts in all Shopify tables."""
    
    tables = [
        'shopify_orders',
        'shopify_order_items', 
        'shopify_customers',
        'shopify_products',
        'shopify_variants'
    ]
    
    with get_session() as session:
        logger.info("=== TABLE RECORD COUNTS ===")
        for table in tables:
            try:
                result = session.execute(text(f"SELECT COUNT(*) FROM {table}"))
                count = result.scalar()
                logger.info(f"{table}: {count} records")
            except Exception as e:
                logger.error(f"Error checking {table}: {e}")
                
        logger.info("\n=== RELATIONSHIP ANALYSIS ===")
        
        # Check customer relationships
        try:
            result = session.execute(text("""
                SELECT 
                    COUNT(DISTINCT customer_id) as unique_customers_in_orders,
                    COUNT(*) as total_orders_with_customer_id
                FROM shopify_orders 
                WHERE customer_id IS NOT NULL AND customer_id != ''
            """))
            row = result.fetchone()
            logger.info(f"Orders reference {row.unique_customers_in_orders} unique customers ({row.total_orders_with_customer_id} orders have customer_id)")
        except Exception as e:
            logger.error(f"Error checking customer relationships: {e}")
            
        # Check if any customers exist
        try:
            result = session.execute(text("SELECT COUNT(*) FROM shopify_customers"))
            count = result.scalar()
            logger.info(f"But only {count} customers exist in shopify_customers table")
        except Exception as e:
            logger.error(f"Error checking customers table: {e}")
            
        # Check order items
        try:
            result = session.execute(text("""
                SELECT 
                    COUNT(*) as total_items,
                    COUNT(DISTINCT order_id) as orders_with_items,
                    COUNT(DISTINCT sku) as unique_skus
                FROM shopify_order_items
            """))
            row = result.fetchone()
            logger.info(f"Order items: {row.total_items} items across {row.orders_with_items} orders, {row.unique_skus} unique SKUs")
        except Exception as e:
            logger.error(f"Error checking order items: {e}")
        
        # Sample some data
        logger.info("\n=== SAMPLE DATA ===")
        try:
            result = session.execute(text("""
                SELECT order_id, customer_id, email, total, tracking_number
                FROM shopify_orders 
                LIMIT 3
            """))
            for row in result:
                logger.info(f"Order {row.order_id}: customer={row.customer_id}, email={row.email}, total={row.total}, tracking={row.tracking_number}")
        except Exception as e:
            logger.error(f"Error sampling orders: {e}")

if __name__ == "__main__":
    check_table_counts()
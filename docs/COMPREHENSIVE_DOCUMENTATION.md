# Stratus ERP Integration Service - Comprehensive Documentation

**Version:** 0.1.0
**Last Updated:** October 26, 2025
**Author:** Stratus Development Team

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [System Architecture](#system-architecture)
3. [Technology Stack](#technology-stack)
4. [Database Schema](#database-schema)
5. [Integration Adapters](#integration-adapters)
6. [ETL Jobs](#etl-jobs)
7. [Web Dashboard & API](#web-dashboard--api)
8. [Analytics & Alerting](#analytics--alerting)
9. [Configuration Management](#configuration-management)
10. [Development Setup](#development-setup)
11. [Deployment Guide](#deployment-guide)
12. [Troubleshooting](#troubleshooting)
13. [API Reference](#api-reference)
14. [Best Practices](#best-practices)

---

## Executive Summary

### What is Stratus?

Stratus is a **data warehouse and ERP integration service** that consolidates data from multiple e-commerce, fulfillment, and accounting platforms into a single normalized PostgreSQL database. It provides:

- **Real-time data synchronization** from Amazon, Shopify, ShipBob, and FreeAgent
- **Business intelligence alerts** for delivery exceptions, inventory issues, and revenue trends
- **Web dashboard** for monitoring ETL jobs and viewing analytics
- **Extensible architecture** designed to evolve from read-only ETL to full ERP with write operations

### Core Value Proposition

1. **Unified Data Model**: Single source of truth for orders, inventory, customers, and financial data
2. **Cross-Platform Analytics**: Link Shopify orders to ShipBob fulfillment and FreeAgent invoices
3. **Operational Alerts**: Proactive notification of business problems requiring attention
4. **Audit Trail**: Complete history of all data changes with timestamps
5. **API-First Design**: REST API for integration with external systems

### Key Metrics

- **4 Platform Integrations**: Amazon SP-API, Shopify Admin API, ShipBob API, FreeAgent API
- **26 ETL Jobs**: Automated data pipelines for orders, inventory, customers, products, accounting
- **20+ Database Tables**: Normalized schema with proper foreign keys and indexes
- **Business Alerts**: 12+ automated checks for operational issues
- **Idempotent Operations**: Safe to re-run any job without data duplication

---

## System Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        External APIs                            │
├──────────────┬──────────────┬──────────────┬───────────────────┤
│   Amazon     │   Shopify    │   ShipBob    │   FreeAgent       │
│   SP-API     │   Admin API  │   REST API   │   OAuth API       │
└──────┬───────┴──────┬───────┴──────┬───────┴──────┬────────────┘
       │              │              │              │
       ▼              ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Adapters Layer                          │
│  • Authentication   • Rate Limiting   • Pagination              │
│  • Data Normalization   • Error Handling   • Retry Logic        │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                          ETL Jobs Layer                         │
│  • Job Orchestration   • Validation   • Logging                │
│  • Statistics Tracking   • Error Reporting                      │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Database Layer (Upserts)                   │
│  • Idempotent Operations   • Transaction Management             │
│  • Insert/Update Tracking   • Cascade Deletes                   │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                  PostgreSQL Database (Supabase)                 │
│  • Normalized Schema   • Indexes   • Foreign Keys               │
│  • JSONB for Complex Data   • Timezone Support                  │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Analytics & Reporting                        │
│  • Business Alerts   • Revenue Analytics   • Inventory Reports  │
│  • Web Dashboard   • REST API   • Email Notifications           │
└─────────────────────────────────────────────────────────────────┘
```

### Design Patterns

#### 1. Adapter Pattern
Each external API has a dedicated adapter that:
- Handles authentication (OAuth, bearer tokens, etc.)
- Implements rate limiting and retry logic
- Manages pagination automatically
- Normalizes API responses to internal format
- Provides clean Python interfaces

#### 2. ETL Job Pattern
Each job follows a consistent pattern:
1. **Extract**: Fetch data from external API via adapter
2. **Transform**: Validate and normalize data
3. **Load**: Upsert data to database with statistics tracking

#### 3. Idempotent Upserts
All database operations use PostgreSQL's `ON CONFLICT DO UPDATE`:
```python
INSERT INTO orders (order_id, source, ...)
VALUES (...)
ON CONFLICT (order_id)
DO UPDATE SET ...
RETURNING (xmax = 0) AS inserted
```
This returns exact counts of inserted vs updated records.

#### 4. Cross-Platform Linking
Orders, inventory, and products link across platforms via:
- **SKU**: Links inventory across Amazon, ShipBob, Shopify
- **tracking_number**: Links Shopify orders to ShipBob returns
- **reference_id**: Links e-commerce orders to fulfillment orders
- **customer_id**: Links orders to customer records

---

## Technology Stack

### Core Technologies

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| **Language** | Python | 3.11+ | Primary programming language |
| **Database** | PostgreSQL | 14+ | Data warehouse (Supabase hosted) |
| **ORM** | SQLAlchemy | 2.0+ | Database models and queries |
| **Validation** | Pydantic | 2.4+ | Data validation and config management |
| **HTTP Client** | Requests | 2.31+ | API communication |
| **Job Scheduler** | APScheduler | 3.10+ | Cron-based job scheduling |
| **Retry Logic** | Tenacity | 8.2+ | Exponential backoff retries |
| **Web Framework** | Flask | 3.0+ | Dashboard and REST API |
| **Migrations** | Alembic | 1.12+ | Database schema versioning |

### Development Tools

| Tool | Purpose |
|------|---------|
| **Poetry** | Dependency management and packaging |
| **Black** | Code formatting (line length: 100) |
| **Ruff** | Fast linting (replaces flake8) |
| **MyPy** | Static type checking |
| **Pytest** | Unit and integration testing |
| **Pre-commit** | Git hooks for code quality |

### External Services

| Service | Purpose | Hosting |
|---------|---------|---------|
| **Supabase** | PostgreSQL database | Cloud (gedjqnemtrufmmonptef.supabase.co) |
| **Amazon SP-API** | Orders, inventory, settlements | AWS |
| **Shopify Admin API** | Orders, customers, products | Shopify Cloud |
| **ShipBob API** | Fulfillment, returns, inventory | ShipBob Cloud |
| **FreeAgent API** | Accounting, invoices, transactions | FreeAgent Cloud |

---

## Database Schema

### Core Tables (Multi-Platform)

#### `orders`
Primary order table supporting all platforms.

```sql
CREATE TABLE orders (
    order_id TEXT PRIMARY KEY,                    -- Platform order ID
    source TEXT NOT NULL,                         -- 'amazon' | 'shopify' | 'shipbob'
    purchase_date TIMESTAMP WITH TIME ZONE NOT NULL,
    status TEXT,                                  -- Order status
    customer_id TEXT,                             -- Customer reference
    total NUMERIC(12,2),                          -- Order total amount
    currency TEXT,                                -- Currency code (USD, GBP, EUR)
    marketplace_id TEXT,                          -- Platform marketplace ID
    shopify_internal_id TEXT,                     -- Shopify numeric ID

    -- Fulfillment tracking
    tracking_number TEXT,
    carrier TEXT,
    tracking_url TEXT,
    tracking_updated_at TIMESTAMP WITH TIME ZONE,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX ix_orders_purchase_date ON orders(purchase_date);
CREATE INDEX ix_orders_source_purchase_date ON orders(source, purchase_date DESC);
CREATE INDEX ix_orders_status ON orders(status);
CREATE INDEX ix_orders_tracking_updated ON orders(tracking_updated_at);
```

**Relationships:**
- `order_items` (one-to-many): Line items for each order
- `shipbob_orders` (via reference_id): Fulfillment tracking
- `shipbob_returns` (via tracking_number): Return tracking

#### `order_items`
Line items within orders.

```sql
CREATE TABLE order_items (
    id BIGSERIAL PRIMARY KEY,
    order_id TEXT REFERENCES orders(order_id) ON DELETE CASCADE NOT NULL,
    sku TEXT NOT NULL,                            -- Stock keeping unit
    asin TEXT,                                    -- Amazon ASIN
    qty INTEGER NOT NULL,                         -- Quantity ordered
    price NUMERIC(12,2),                          -- Unit price
    tax NUMERIC(12,2),                            -- Tax amount
    fee_estimate NUMERIC(12,2),                   -- Estimated fees
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Unique constraint: one item per SKU per order
CREATE UNIQUE INDEX uq_order_items_order_sku ON order_items(order_id, sku);
CREATE INDEX ix_order_items_sku ON order_items(sku);
```

#### `inventory`
Current inventory levels from all fulfillment centers.

```sql
CREATE TABLE inventory (
    sku TEXT,
    source TEXT,                                  -- 'amazon' | 'shipbob'
    PRIMARY KEY (sku, source),                    -- Composite key

    -- Generic inventory fields
    quantity_on_hand INTEGER DEFAULT 0,
    quantity_available INTEGER DEFAULT 0,
    quantity_reserved INTEGER DEFAULT 0,
    quantity_incoming INTEGER DEFAULT 0,

    -- Amazon-specific fields
    asin TEXT,
    fnsku TEXT,                                   -- Fulfillment Network SKU
    fulfillment_center TEXT,

    -- ShipBob-specific fields
    inventory_id TEXT,
    inventory_name TEXT,
    fulfillable_quantity INTEGER DEFAULT 0,
    backordered_quantity INTEGER DEFAULT 0,
    exception_quantity INTEGER DEFAULT 0,
    internal_transfer_quantity INTEGER DEFAULT 0,

    last_updated TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX ix_inventory_source ON inventory(source);
CREATE INDEX ix_inventory_last_updated ON inventory(last_updated);
```

**Cross-Platform Linking:**
```python
# Find the same SKU across platforms
inventory_records = session.query(Inventory).filter(Inventory.sku == "SKU123").all()

# Link to Shopify variants
shopify_variants = session.query(ShopifyVariant).filter(ShopifyVariant.sku == "SKU123").all()
```

#### `settlements`
Financial settlement periods from marketplaces.

```sql
CREATE TABLE settlements (
    settlement_id TEXT PRIMARY KEY,
    period_start TIMESTAMP WITH TIME ZONE,
    period_end TIMESTAMP WITH TIME ZONE,
    gross NUMERIC(12,2),                          -- Gross sales
    fees NUMERIC(12,2),                           -- Platform fees
    refunds NUMERIC(12,2),                        -- Total refunds
    net NUMERIC(12,2),                            -- Net amount
    currency TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX ix_settlements_period_start ON settlements(period_start);
CREATE INDEX ix_settlements_period_end ON settlements(period_end);
```

#### `settlement_lines`
Individual transactions within settlements.

```sql
CREATE TABLE settlement_lines (
    id BIGSERIAL PRIMARY KEY,
    settlement_id TEXT REFERENCES settlements(settlement_id) ON DELETE CASCADE NOT NULL,
    order_id TEXT,                                -- Associated order
    type TEXT,                                    -- 'FBA Fee', 'Commission', 'Refund'
    amount NUMERIC(12,2),
    fee_type TEXT,
    posted_date TIMESTAMP WITH TIME ZONE
);

CREATE UNIQUE INDEX uq_settlement_lines_unique
    ON settlement_lines(settlement_id, order_id, type, posted_date);
CREATE INDEX ix_settlement_lines_order_id ON settlement_lines(order_id);
```

### Shopify Tables

#### `shopify_customers`
Customer relationship management data.

```sql
CREATE TABLE shopify_customers (
    customer_id TEXT PRIMARY KEY,                 -- Shopify customer ID
    email TEXT,
    first_name TEXT,
    last_name TEXT,
    created_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE,
    total_spent NUMERIC(12,2),                    -- Lifetime value
    orders_count INTEGER,
    state TEXT,                                   -- 'enabled' | 'disabled'
    tags TEXT,                                    -- JSON array as text
    last_order_id TEXT,
    last_order_date TIMESTAMP WITH TIME ZONE
);

CREATE INDEX ix_shopify_customers_email ON shopify_customers(email);
CREATE INDEX ix_shopify_customers_updated_at ON shopify_customers(updated_at);
```

#### `shopify_products` & `shopify_variants`
Product catalog management.

```sql
CREATE TABLE shopify_products (
    product_id TEXT PRIMARY KEY,
    title TEXT,
    vendor TEXT,
    product_type TEXT,
    created_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE shopify_variants (
    variant_id TEXT PRIMARY KEY,
    product_id TEXT REFERENCES shopify_products(product_id) ON DELETE CASCADE NOT NULL,
    sku TEXT,                                     -- Links to inventory
    price NUMERIC(12,2),
    inventory_item_id TEXT,
    created_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX ix_shopify_variants_sku ON shopify_variants(sku);
CREATE INDEX ix_shopify_variants_product_id ON shopify_variants(product_id);
```

### ShipBob Tables

#### `shipbob_orders`
Fulfillment order tracking.

```sql
CREATE TABLE shipbob_orders (
    shipbob_order_id TEXT PRIMARY KEY,
    reference_id TEXT,                            -- Links to orders.order_id
    status TEXT,                                  -- Fulfillment status
    created_date TIMESTAMP WITH TIME ZONE,
    last_updated_date TIMESTAMP WITH TIME ZONE,
    shipped_date TIMESTAMP WITH TIME ZONE,
    delivered_date TIMESTAMP WITH TIME ZONE,
    tracking_number TEXT,                         -- Links to orders.tracking_number
    carrier TEXT,
    recipient_name TEXT,
    recipient_email TEXT,
    fulfillment_center_id TEXT,
    total_weight NUMERIC(10,3),
    total_cost NUMERIC(12,2),
    currency TEXT DEFAULT 'USD',
    shipping_method TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX ix_shipbob_orders_reference_id ON shipbob_orders(reference_id);
CREATE INDEX ix_shipbob_orders_tracking_number ON shipbob_orders(tracking_number);
CREATE INDEX ix_shipbob_orders_status ON shipbob_orders(status);
```

#### `shipbob_returns`
Return order tracking and cost analysis.

```sql
CREATE TABLE shipbob_returns (
    return_id TEXT PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'shipbob',
    original_shipment_id TEXT,
    reference_id TEXT,                            -- Links to orders.order_id
    store_order_id TEXT,
    status TEXT,
    return_type TEXT,
    customer_name TEXT,
    tracking_number TEXT,
    total_cost NUMERIC(12,2),
    fulfillment_center_id TEXT,
    fulfillment_center_name TEXT,
    items TEXT,                                   -- JSON array of return items
    transactions TEXT,                            -- JSON array of cost transactions
    insert_date TIMESTAMP WITH TIME ZONE,
    completed_date TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX ix_shipbob_returns_reference_id ON shipbob_returns(reference_id);
CREATE INDEX ix_shipbob_returns_status ON shipbob_returns(status);
CREATE INDEX ix_shipbob_returns_fulfillment_center ON shipbob_returns(fulfillment_center_id);
```

#### `shipbob_products` & `shipbob_variants`
ShipBob product catalog with dimensions and weight.

```sql
CREATE TABLE shipbob_products (
    product_id TEXT PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'shipbob',
    name TEXT,
    sku TEXT,
    barcode TEXT,
    description TEXT,
    category TEXT,
    is_case TEXT,                                 -- Boolean as text
    is_lot TEXT,
    is_active TEXT,
    is_bundle TEXT,
    is_digital TEXT,
    is_hazmat TEXT,
    dimensions TEXT,                              -- JSON: {length, width, height, unit}
    weight TEXT,                                  -- JSON: {value, unit}
    value TEXT,                                   -- JSON: {amount, currency}
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX ix_shipbob_products_sku ON shipbob_products(sku);
CREATE INDEX ix_shipbob_products_category ON shipbob_products(category);
```

#### `shipbob_fulfillment_centers`
Warehouse location and contact information.

```sql
CREATE TABLE shipbob_fulfillment_centers (
    center_id TEXT PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'shipbob',
    name TEXT,
    address1 TEXT,
    address2 TEXT,
    city TEXT,
    state TEXT,
    zip_code TEXT,
    country TEXT,
    phone_number TEXT,
    email TEXT,
    timezone TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX ix_shipbob_centers_state ON shipbob_fulfillment_centers(state);
CREATE INDEX ix_shipbob_centers_country ON shipbob_fulfillment_centers(country);
```

#### `shipbob_receiving_orders`
Inbound logistics tracking (Warehouse Receiving Orders).

```sql
CREATE TABLE shipbob_receiving_orders (
    wro_id TEXT PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'shipbob',
    purchase_order_number TEXT,
    status TEXT,
    package_type TEXT,
    box_packaging_type TEXT,
    fulfillment_center_id TEXT,
    fulfillment_center_name TEXT,
    inventory_quantities TEXT,                    -- JSON: expected vs received
    status_history TEXT,                          -- JSON: status change log
    expected_arrival_date TIMESTAMP WITH TIME ZONE,
    insert_date TIMESTAMP WITH TIME ZONE,
    last_updated_date TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX ix_shipbob_wro_po_number ON shipbob_receiving_orders(purchase_order_number);
CREATE INDEX ix_shipbob_wro_status ON shipbob_receiving_orders(status);
CREATE INDEX ix_shipbob_wro_expected_arrival ON shipbob_receiving_orders(expected_arrival_date);
```

### FreeAgent Tables (Accounting Integration)

#### `freeagent_contacts`
Customer and supplier relationship management.

```sql
CREATE TABLE freeagent_contacts (
    contact_id TEXT PRIMARY KEY,                  -- Extracted from FreeAgent URL
    source TEXT NOT NULL DEFAULT 'freeagent',
    organisation_name TEXT,
    first_name TEXT,
    last_name TEXT,
    contact_name_on_invoices TEXT,
    email TEXT,
    phone_number TEXT,
    mobile TEXT,
    fax TEXT,
    address1 TEXT,
    address2 TEXT,
    address3 TEXT,
    town TEXT,
    region TEXT,
    postcode TEXT,
    country TEXT,
    contact_type TEXT,                            -- 'Client' | 'Supplier' | 'Both'
    default_payment_terms_in_days INTEGER,
    charge_sales_tax TEXT,                        -- 'Auto' | 'Never' | 'Always'
    sales_tax_registration_number TEXT,
    active_projects_count INTEGER,
    account_balance NUMERIC(15,2),
    uses_contact_invoice_sequence TEXT,
    status TEXT,
    created_at_api TIMESTAMP WITH TIME ZONE,
    updated_at_api TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX ix_freeagent_contacts_email ON freeagent_contacts(email);
CREATE INDEX ix_freeagent_contacts_type ON freeagent_contacts(contact_type);
CREATE INDEX ix_freeagent_contacts_organisation ON freeagent_contacts(organisation_name);
```

#### `freeagent_invoices`
Sales invoices and accounts receivable.

```sql
CREATE TABLE freeagent_invoices (
    invoice_id TEXT PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'freeagent',
    reference TEXT,                               -- Invoice number
    dated_on TIMESTAMP WITH TIME ZONE,
    due_on TIMESTAMP WITH TIME ZONE,
    contact_id TEXT,                              -- Links to freeagent_contacts
    contact_name TEXT,
    net_value NUMERIC(15,2),
    sales_tax_value NUMERIC(15,2),
    total_value NUMERIC(15,2),
    paid_value NUMERIC(15,2),
    due_value NUMERIC(15,2),
    currency TEXT,
    exchange_rate NUMERIC(15,6),
    net_value_in_base_currency NUMERIC(15,2),
    status TEXT,                                  -- 'Draft' | 'Sent' | 'Paid'
    payment_terms_in_days INTEGER,
    sales_tax_status TEXT,
    outside_of_sales_tax_scope TEXT,
    initial_sales_tax_rate NUMERIC(5,2),
    comments TEXT,
    project_id TEXT,
    created_at_api TIMESTAMP WITH TIME ZONE,
    updated_at_api TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX ix_freeagent_invoices_reference ON freeagent_invoices(reference);
CREATE INDEX ix_freeagent_invoices_contact ON freeagent_invoices(contact_id);
CREATE INDEX ix_freeagent_invoices_status ON freeagent_invoices(status);
CREATE INDEX ix_freeagent_invoices_dated_on ON freeagent_invoices(dated_on);
CREATE INDEX ix_freeagent_invoices_due_on ON freeagent_invoices(due_on);
```

#### `freeagent_bills`
Purchase invoices and accounts payable.

```sql
CREATE TABLE freeagent_bills (
    bill_id TEXT PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'freeagent',
    reference TEXT,
    dated_on TIMESTAMP WITH TIME ZONE,
    due_on TIMESTAMP WITH TIME ZONE,
    contact_id TEXT,
    contact_name TEXT,
    net_value NUMERIC(15,2),
    sales_tax_value NUMERIC(15,2),
    total_value NUMERIC(15,2),
    paid_value NUMERIC(15,2),
    due_value NUMERIC(15,2),
    status TEXT,                                  -- 'Open' | 'Scheduled' | 'Paid'
    sales_tax_status TEXT,
    comments TEXT,
    project_id TEXT,
    created_at_api TIMESTAMP WITH TIME ZONE,
    updated_at_api TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX ix_freeagent_bills_reference ON freeagent_bills(reference);
CREATE INDEX ix_freeagent_bills_contact ON freeagent_bills(contact_id);
CREATE INDEX ix_freeagent_bills_status ON freeagent_bills(status);
```

#### `freeagent_categories`
Chart of accounts and transaction classification.

```sql
CREATE TABLE freeagent_categories (
    category_id TEXT PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'freeagent',
    description TEXT,
    nominal_code TEXT,                            -- Account code
    category_type TEXT,                           -- Account type
    parent_category_id TEXT,                      -- Hierarchy
    auto_sales_tax_rate NUMERIC(5,2),
    allowable_for_tax TEXT,
    is_visible TEXT,
    group_description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX ix_freeagent_categories_nominal_code ON freeagent_categories(nominal_code);
CREATE INDEX ix_freeagent_categories_type ON freeagent_categories(category_type);
CREATE INDEX ix_freeagent_categories_parent ON freeagent_categories(parent_category_id);
```

#### `freeagent_bank_accounts`
Business bank account configuration.

```sql
CREATE TABLE freeagent_bank_accounts (
    bank_account_id TEXT PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'freeagent',
    name TEXT,
    bank_name TEXT,
    type TEXT,                                    -- 'CurrentAccount' | 'SavingsAccount' | 'CreditCardAccount'
    account_number TEXT,
    sort_code TEXT,
    iban TEXT,
    bic TEXT,
    current_balance NUMERIC(15,2),
    currency TEXT,
    is_primary TEXT,
    is_personal TEXT,
    email_new_transactions TEXT,
    default_bill_category_id TEXT,
    opening_balance_date TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX ix_freeagent_bank_accounts_name ON freeagent_bank_accounts(name);
CREATE INDEX ix_freeagent_bank_accounts_type ON freeagent_bank_accounts(type);
```

#### `freeagent_bank_transactions`
Individual bank transactions for cash flow tracking.

```sql
CREATE TABLE freeagent_bank_transactions (
    transaction_id TEXT PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'freeagent',
    bank_account_id TEXT,
    dated_on TIMESTAMP WITH TIME ZONE,
    amount NUMERIC(15,2),
    description TEXT,
    bank_reference TEXT,
    transaction_type TEXT,
    running_balance NUMERIC(15,2),
    is_manual TEXT,
    created_at_api TIMESTAMP WITH TIME ZONE,
    updated_at_api TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX ix_freeagent_bank_transactions_account ON freeagent_bank_transactions(bank_account_id);
CREATE INDEX ix_freeagent_bank_transactions_dated_on ON freeagent_bank_transactions(dated_on);
CREATE INDEX ix_freeagent_bank_transactions_amount ON freeagent_bank_transactions(amount);
```

#### `freeagent_bank_transaction_explanations`
Transaction categorization and explanations.

```sql
CREATE TABLE freeagent_bank_transaction_explanations (
    explanation_id TEXT PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'freeagent',
    bank_transaction_id TEXT,
    bank_account_id TEXT,
    dated_on TIMESTAMP WITH TIME ZONE,
    amount NUMERIC(15,2),
    description TEXT,
    category_id TEXT,
    category_name TEXT,
    foreign_currency_amount NUMERIC(15,2),
    foreign_currency_type TEXT,
    gross_value NUMERIC(15,2),
    sales_tax_rate NUMERIC(5,2),
    sales_tax_value NUMERIC(15,2),
    invoice_id TEXT,                              -- Links to freeagent_invoices
    bill_id TEXT,                                 -- Links to freeagent_bills
    created_at_api TIMESTAMP WITH TIME ZONE,
    updated_at_api TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX ix_freeagent_bank_explanations_transaction ON freeagent_bank_transaction_explanations(bank_transaction_id);
CREATE INDEX ix_freeagent_bank_explanations_category ON freeagent_bank_transaction_explanations(category_id);
```

#### `freeagent_transactions`
Double-entry bookkeeping (general ledger).

```sql
CREATE TABLE freeagent_transactions (
    transaction_id TEXT PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'freeagent',
    dated_on TIMESTAMP WITH TIME ZONE,
    description TEXT,
    category_id TEXT,
    category_name TEXT,
    nominal_code TEXT,
    debit_value NUMERIC(15,2),
    credit_value NUMERIC(15,2),
    source_item_url TEXT,                         -- Link to source document
    foreign_currency_data TEXT,                   -- JSON
    created_at_api TIMESTAMP WITH TIME ZONE,
    updated_at_api TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX ix_freeagent_transactions_dated_on ON freeagent_transactions(dated_on);
CREATE INDEX ix_freeagent_transactions_category ON freeagent_transactions(category_id);
CREATE INDEX ix_freeagent_transactions_nominal_code ON freeagent_transactions(nominal_code);
```

#### `freeagent_users`
Team members and access control.

```sql
CREATE TABLE freeagent_users (
    user_id TEXT PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'freeagent',
    email TEXT,
    first_name TEXT,
    last_name TEXT,
    ni_number TEXT,                               -- National Insurance Number
    unique_tax_reference TEXT,
    role TEXT,                                    -- 'Owner' | 'Director' | 'Employee'
    permission_level INTEGER,
    opening_mileage NUMERIC(10,2),
    current_payroll_profile TEXT,                 -- JSON
    created_at_api TIMESTAMP WITH TIME ZONE,
    updated_at_api TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX ix_freeagent_users_email ON freeagent_users(email);
CREATE INDEX ix_freeagent_users_role ON freeagent_users(role);
```

### Database Migrations

Stratus uses Alembic for database schema versioning:

```bash
# List of migration files
alembic/versions/0001_initial_warehouse_schema.py     # Core tables (orders, inventory)
alembic/versions/0002_add_shopify_tables.py           # Shopify customers, products
alembic/versions/0003_update_inventory_orders_shipbob.py  # ShipBob inventory fields
alembic/versions/0004_add_extended_shipbob_tables.py  # ShipBob returns, receiving, products
alembic/versions/0005_add_freeagent_tables.py         # FreeAgent accounting tables

# Run migrations
alembic upgrade head

# Check current migration
alembic current

# Create new migration
alembic revision --autogenerate -m "description"
```

---

## Integration Adapters

### Amazon SP-API Adapter

**File:** `src/adapters/amazon.py`, `src/adapters/amazon_finance.py`, `src/adapters/amazon_inventory.py`

#### Features
- **Authentication**: LWA (Login with Amazon) access tokens with refresh token support
- **Rate Limiting**: Respects Amazon's rate limits with 429 retry handling
- **Pagination**: Handles `NextToken` parameter for large result sets
- **Regional Support**: Configurable endpoints (US, EU, Far East)

#### Configuration

```python
# Environment variables required
AMZ_ACCESS_TOKEN=your_access_token
AMZ_REFRESH_TOKEN=your_refresh_token
AMZ_CLIENT_ID=your_client_id
AMZ_CLIENT_SECRET=your_client_secret
AMZ_MARKETPLACE_IDS=ATVPDKIKX0DER,A1F83G8C2ARO7P  # Comma-separated
AMZ_REGION=eu-west-1  # Optional, defaults to EU
AMZ_ENDPOINT=https://sellingpartnerapi-eu.amazon.com  # Optional
```

#### Key Methods

**AmazonOrdersClient**
```python
from src.adapters.amazon import AmazonOrdersClient

client = AmazonOrdersClient()  # Loads config from environment

# Fetch orders since timestamp
orders, order_items = client.get_orders_since("2024-01-01T00:00:00Z")

# Returns:
# - orders: List[Dict] with normalized order data
# - order_items: List[Dict] with normalized line items
```

**AmazonFinanceClient**
```python
from src.adapters.amazon_finance import AmazonFinanceClient

client = AmazonFinanceClient()

# Fetch financial events for settlement reconciliation
events = client.get_financial_events(
    posted_after="2024-01-01T00:00:00Z"
)
```

**AmazonInventoryClient**
```python
from src.adapters.amazon_inventory import AmazonInventoryClient

client = AmazonInventoryClient()

# Fetch FBA inventory summary
inventory_records = client.get_fba_inventory_summary()
```

#### Data Normalization

```python
# Amazon API response → Stratus normalized format
{
    "AmazonOrderId": "111-2222222-3333333",
    "PurchaseDate": "2024-01-15T10:30:00Z",
    "OrderTotal": {"Amount": "99.99", "CurrencyCode": "USD"},
    "MarketplaceId": "ATVPDKIKX0DER"
}
# ↓
{
    "order_id": "111-2222222-3333333",
    "source": "amazon",
    "purchase_date": datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
    "total": Decimal("99.99"),
    "currency": "USD",
    "marketplace_id": "ATVPDKIKX0DER"
}
```

#### Error Handling

```python
class AmazonRetryableError(Exception):
    """Raised for 429 rate limit errors and 5xx server errors"""

# Automatic retry with exponential backoff (5 attempts)
@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    retry=retry_if_exception_type(AmazonRetryableError)
)
def _make_request(self, method, url, **kwargs):
    # Handles 429 with retry-after header
    # Handles 5xx server errors
    # Raises non-retryable errors immediately
```

### Shopify Admin API Adapter

**File:** `src/adapters/shopify.py`

#### Features
- **Authentication**: Bearer token authentication
- **Rate Limiting**: Monitors `X-Shopify-Shop-Api-Call-Limit` header with progressive delays
- **Pagination**: RFC 5988 Link header parsing for cursor-based pagination
- **API Versioning**: Supports versioned API endpoints (2024-07 recommended)

#### Configuration

```python
# Environment variables required
SHOPIFY_SHOP=your-store.myshopify.com
SHOPIFY_ACCESS_TOKEN=shpat_xxxxxxxxxxxxx
SHOPIFY_API_VERSION=2024-07  # Optional, defaults to 2024-07
```

#### Key Methods

**ShopifyOrdersClient**
```python
from src.adapters.shopify import ShopifyOrdersClient

client = ShopifyOrdersClient()

# Fetch orders since timestamp
orders, order_items = client.get_orders_since(
    since_iso="2024-01-01T00:00:00Z",
    status="any"  # 'any' | 'open' | 'closed'
)
```

**ShopifyCustomersClient**
```python
from src.adapters.shopify import ShopifyCustomersClient

client = ShopifyCustomersClient()

# Fetch customers updated since timestamp
customers = client.get_customers_since("2024-01-01T00:00:00Z")
```

**ShopifyProductsClient**
```python
from src.adapters.shopify import ShopifyProductsClient

client = ShopifyProductsClient()

# Fetch all products and variants
products, variants = client.get_products_and_variants()
```

#### Rate Limiting Strategy

```python
def _check_rate_limit(self, response):
    """Monitor API call limit from response headers."""
    limit_header = response.headers.get('X-Shopify-Shop-Api-Call-Limit')
    # Example: "32/40" means 32 calls used out of 40

    if limit_header:
        current, limit = map(int, limit_header.split('/'))
        ratio = current / limit

        if ratio > 0.9:  # 90% of limit reached
            time.sleep(2.0)  # Long delay
        elif ratio > 0.7:  # 70% of limit reached
            time.sleep(0.5)  # Short delay
```

#### Data Normalization

```python
# Shopify API response → Stratus normalized format
{
    "id": 4123456789012,
    "name": "#1001",
    "created_at": "2024-01-15T10:30:00-05:00",
    "total_price": "99.99",
    "currency": "USD"
}
# ↓
{
    "order_id": "#1001",  # Shopify order name (user-facing)
    "shopify_internal_id": "4123456789012",  # Numeric ID
    "source": "shopify",
    "purchase_date": datetime(2024, 1, 15, 15, 30, 0, tzinfo=UTC),  # Converted to UTC
    "total": Decimal("99.99"),
    "currency": "USD"
}
```

### ShipBob API Adapter

**File:** `src/adapters/shipbob.py`

#### Features
- **Authentication**: Bearer token authentication
- **Rate Limiting**: Default 0.5s delay between requests (configurable)
- **Pagination**: Page-based pagination with configurable page size
- **Comprehensive Endpoints**: Orders, inventory, returns, products, receiving, fulfillment centers

#### Configuration

```python
# Environment variables required
SHIPBOB_TOKEN=your_bearer_token
SHIPBOB_BASE=https://api.shipbob.com/2025-07  # Optional
```

#### Key Methods

**ShipBobInventoryClient**
```python
from src.adapters.shipbob import ShipBobInventoryClient

client = ShipBobInventoryClient()

# Fetch inventory for all fulfillment centers
inventory_records = client.get_inventory()
```

**ShipBobOrdersClient**
```python
from src.adapters.shipbob import ShipBobOrdersClient

client = ShipBobOrdersClient()

# Fetch orders with fulfillment status
orders = client.get_orders(
    start_date="2024-01-01",
    end_date="2024-01-31"
)
```

**ShipBobReturnsClient**
```python
from src.adapters.shipbob import ShipBobReturnsClient

client = ShipBobReturnsClient()

# Fetch return orders
returns = client.get_returns()
```

**ShipBobReceivingClient**
```python
from src.adapters.shipbob import ShipBobReceivingClient

client = ShipBobReceivingClient()

# Fetch warehouse receiving orders (WROs)
wros = client.get_receiving_orders()
```

**ShipBobProductsClient**
```python
from src.adapters.shipbob import ShipBobProductsClient

client = ShipBobProductsClient()

# Fetch products and variants
products, variants = client.get_products_and_variants()
```

**ShipBobFulfillmentCentersClient**
```python
from src.adapters.shipbob import ShipBobFulfillmentCentersClient

client = ShipBobFulfillmentCentersClient()

# Fetch fulfillment center locations
centers = client.get_fulfillment_centers()
```

#### Data Normalization

```python
# ShipBob API response → Stratus normalized format
{
    "id": 123456,
    "reference_id": "SHOP-1001",
    "inventory": [
        {
            "id": 789,
            "name": "Product Name",
            "fulfillable_quantity": 100
        }
    ]
}
# ↓
{
    "shipbob_order_id": "123456",
    "reference_id": "SHOP-1001",  # Links to orders.order_id
    "source": "shipbob"
}
```

### FreeAgent API Adapter

**File:** `src/adapters/freeagent.py`

#### Features
- **Authentication**: OAuth 2.0 bearer token with refresh token support
- **Rate Limiting**: Configurable delay with exponential backoff retry
- **Feature Flags**: YAML-based feature flag system for graceful endpoint degradation
- **Error Handling**: Graceful handling of 403/404 for unavailable features
- **API Versioning**: Support for `X-Api-Version` header

#### Configuration

```python
# Environment variables required
FREEAGENT_ACCESS_TOKEN=your_access_token
FREEAGENT_REFRESH_TOKEN=your_refresh_token  # Optional for token refresh
FREEAGENT_CLIENT_ID=your_client_id
FREEAGENT_CLIENT_SECRET=your_client_secret
FREEAGENT_REDIRECT_URI=http://localhost:8000/auth/freeagent/callback

# Configuration file
config/freeagent.yaml
```

#### Feature Flag System

```yaml
# config/freeagent.yaml
features:
  contacts: true
  invoices: true
  bills: true
  categories: true
  bank_accounts: true
  bank_transactions: true
  bank_transaction_explanations: true
  transactions: true
  users: true

api:
  rate_limit_delay: 0.5
  api_version: "2024-10-01"

sync:
  default_lookback_days: 30
  batch_size: 100
```

#### Key Methods

**FreeAgentContactsClient**
```python
from src.adapters.freeagent import FreeAgentContactsClient

client = FreeAgentContactsClient()

# Fetch contacts updated since date
contacts = client.get_contacts(
    from_date="2024-01-01",
    to_date="2024-01-31"
)
```

**FreeAgentInvoicesClient**
```python
from src.adapters.freeagent import FreeAgentInvoicesClient

client = FreeAgentInvoicesClient()

# Fetch invoices
invoices = client.get_invoices(
    from_date="2024-01-01",
    to_date="2024-01-31"
)
```

**FreeAgentBankTransactionsClient**
```python
from src.adapters.freeagent import FreeAgentBankTransactionsClient

client = FreeAgentBankTransactionsClient()

# Fetch bank transactions for account
transactions = client.get_bank_transactions(
    bank_account_url="https://api.freeagent.com/v2/bank_accounts/123",
    from_date="2024-01-01",
    to_date="2024-01-31"
)
```

#### Error Handling

```python
class FreeAgentAuthError(Exception):
    """Raised for authentication failures (401)"""

class FreeAgentRateLimitError(Exception):
    """Raised for rate limit exceeded (429)"""

# Graceful handling of unavailable features
try:
    invoices = client.get_invoices()
except FreeAgentFeatureUnavailableError:
    logger.warning("Invoices endpoint not available, skipping")
    invoices = []
```

#### Data Normalization

```python
# FreeAgent API response → Stratus normalized format
{
    "url": "https://api.freeagent.com/v2/contacts/123",
    "organisation_name": "ACME Corp",
    "email": "contact@acme.com",
    "created_at": "2024-01-15T10:30:00.000Z",
    "updated_at": "2024-01-20T14:00:00.000Z"
}
# ↓
{
    "contact_id": "123",  # Extracted from URL
    "source": "freeagent",
    "organisation_name": "ACME Corp",
    "email": "contact@acme.com",
    "created_at_api": datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
    "updated_at_api": datetime(2024, 1, 20, 14, 0, 0, tzinfo=UTC)
}
```

---

## ETL Jobs

### Job Architecture

All ETL jobs follow a consistent pattern:

```python
def run_job_etl() -> dict[str, int]:
    """
    Run the ETL job.

    Returns:
        Dictionary with sync statistics
    """
    logger.info("Starting ETL job")

    try:
        # 1. Initialize adapter
        client = PlatformClient()

        # 2. Calculate sync parameters
        since_timestamp = get_sync_timestamp()

        # 3. Extract data from external API
        logger.info("Fetching data from API")
        records = client.get_data_since(since_timestamp)

        if not records:
            logger.info("No records to sync")
            return {"records_processed": 0, "inserted": 0, "updated": 0}

        # 4. Validate data
        validate_records(records)

        # 5. Load data to database
        logger.info(f"Upserting {len(records)} records")
        with get_session() as session:
            inserted, updated = upsert_records(records, session)
            logger.info(f"Inserted: {inserted}, Updated: {updated}")

        # 6. Return statistics
        return {
            "records_processed": len(records),
            "inserted": inserted,
            "updated": updated
        }

    except Exception as e:
        logger.error(f"Job failed: {e}")
        raise


def main():
    """CLI entry point."""
    try:
        stats = run_job_etl()
        print(f"Job completed: {stats}")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Job failed: {e}")
        sys.exit(1)
```

### Amazon ETL Jobs

#### amazon_orders.py
Fetches orders from Amazon SP-API with configurable lookback period.

```bash
# Run job
poetry run python -m src.jobs.amazon_orders

# Environment variables
AMZ_SYNC_LOOKBACK_HOURS=24  # Default: 24 hours
```

**Data Flow:**
1. Fetch orders from Amazon SP-API (Orders API)
2. Normalize order and line item data
3. Validate order_id, source, purchase_date
4. Upsert to `orders` and `order_items` tables
5. Return statistics

**Key Features:**
- Incremental sync with configurable lookback
- Orphaned item filtering (items without orders)
- Foreign key validation before insert

#### amazon_settlements.py
Fetches financial settlement data for revenue reconciliation.

```bash
poetry run python -m src.jobs.amazon_settlements
```

**Data Flow:**
1. Fetch financial events from Amazon Finance API
2. Group transactions into settlement periods
3. Calculate gross, fees, refunds, net amounts
4. Upsert to `settlements` and `settlement_lines` tables

#### amazon_inventory.py
Fetches FBA inventory summary from Amazon fulfillment centers.

```bash
poetry run python -m src.jobs.amazon_inventory
```

**Data Flow:**
1. Fetch inventory summary from Amazon Inventory API
2. Normalize quantity fields (on_hand, available, reserved, incoming)
3. Include ASIN, FNSKU, fulfillment center
4. Upsert to `inventory` table with source='amazon'

### Shopify ETL Jobs

#### shopify_orders.py
Fetches orders from Shopify Admin API.

```bash
poetry run python -m src.jobs.shopify_orders

# Environment variables
SHOPIFY_SYNC_LOOKBACK_HOURS=24  # Default: 24 hours
```

**Data Flow:**
1. Fetch orders from Shopify Admin API (GET /admin/api/2024-07/orders.json)
2. Normalize to Stratus format (order_id = name, shopify_internal_id = id)
3. Extract line items
4. Upsert to `orders` and `order_items` tables with source='shopify'

**Key Features:**
- Pagination with Link header parsing
- Rate limit monitoring
- Handles multi-currency orders
- Tags stored as JSON text

#### shopify_customers.py
Fetches customer data for CRM analytics.

```bash
poetry run python -m src.jobs.shopify_customers

# Environment variables
SHOPIFY_SYNC_LOOKBACK_HOURS=24  # Default: 24 hours
```

**Data Flow:**
1. Fetch customers from Shopify API (updated_at_min filter)
2. Calculate lifetime value (total_spent)
3. Extract tags and last order info
4. Upsert to `shopify_customers` table

#### shopify_products.py
Fetches product catalog for inventory linking.

```bash
poetry run python -m src.jobs.shopify_products
```

**Data Flow:**
1. Fetch all products and variants from Shopify
2. Normalize product data (title, vendor, type)
3. Extract variants with SKU and price
4. Upsert to `shopify_products` and `shopify_variants` tables

**Key Features:**
- Full refresh (no incremental sync)
- Product-variant relationship preservation
- SKU-based inventory linking

### ShipBob ETL Jobs

#### shipbob_inventory.py
Fetches current inventory levels from ShipBob fulfillment centers.

```bash
poetry run python -m src.jobs.shipbob_inventory
```

**Data Flow:**
1. Fetch inventory from ShipBob API
2. Extract fulfillable, backordered, exception quantities
3. Include fulfillment center IDs
4. Upsert to `inventory` table with source='shipbob'

#### shipbob_status.py
Fetches order fulfillment status.

```bash
poetry run python -m src.jobs.shipbob_status
```

**Data Flow:**
1. Fetch orders from ShipBob with fulfillment status
2. Extract tracking information (carrier, tracking_number)
3. Link to e-commerce orders via reference_id
4. Upsert to `shipbob_orders` table

#### shipbob_returns.py
Fetches return orders for cost tracking.

```bash
poetry run python -m src.jobs.shipbob_returns
```

**Data Flow:**
1. Fetch returns from ShipBob API
2. Extract return items and cost transactions (JSON)
3. Link to original orders via reference_id
4. Upsert to `shipbob_returns` table

#### shipbob_receiving.py
Fetches inbound warehouse receiving orders (WROs).

```bash
poetry run python -m src.jobs.shipbob_receiving
```

**Data Flow:**
1. Fetch WROs from ShipBob API
2. Extract expected vs received quantities
3. Include status history
4. Upsert to `shipbob_receiving_orders` table

#### shipbob_products.py
Fetches ShipBob product catalog with dimensions and weight.

```bash
poetry run python -m src.jobs.shipbob_products
```

**Data Flow:**
1. Fetch products and variants from ShipBob
2. Extract dimensions, weight, value (JSON)
3. Include hazmat, bundle, digital flags
4. Upsert to `shipbob_products` and `shipbob_variants` tables

#### shipbob_fulfillment_centers.py
Fetches warehouse location data.

```bash
poetry run python -m src.jobs.shipbob_fulfillment_centers
```

**Data Flow:**
1. Fetch fulfillment centers from ShipBob
2. Extract address and contact info
3. Include timezone for logistics planning
4. Upsert to `shipbob_fulfillment_centers` table

### FreeAgent ETL Jobs

#### freeagent_contacts.py
Fetches customer and supplier contacts.

```bash
poetry run python -m src.jobs.freeagent_contacts

# Options
--from-date YYYY-MM-DD    # Start date for sync
--to-date YYYY-MM-DD      # End date for sync
--full-sync               # Sync all historical data
```

**Data Flow:**
1. Fetch contacts from FreeAgent API (updated_since filter)
2. Extract ID from contact URL
3. Include customer/supplier type, payment terms, account balance
4. Upsert to `freeagent_contacts` table

#### freeagent_invoices.py
Fetches sales invoices for revenue tracking.

```bash
poetry run python -m src.jobs.freeagent_invoices

# Options
--from-date YYYY-MM-DD
--to-date YYYY-MM-DD
--full-sync
```

**Data Flow:**
1. Fetch invoices from FreeAgent API (dated_since filter)
2. Extract invoice ID and contact ID from URLs
3. Handle multi-currency with exchange rates
4. Calculate due amounts (total - paid)
5. Upsert to `freeagent_invoices` table

#### freeagent_bills.py
Fetches purchase invoices for expense tracking.

```bash
poetry run python -m src.jobs.freeagent_bills

# Options
--from-date YYYY-MM-DD
--to-date YYYY-MM-DD
--full-sync
```

#### freeagent_categories.py
Fetches chart of accounts for transaction classification.

```bash
poetry run python -m src.jobs.freeagent_categories
```

**Data Flow:**
1. Fetch all categories (no date filter)
2. Extract category ID and parent ID from URLs
3. Build category hierarchy
4. Upsert to `freeagent_categories` table

#### freeagent_bank_accounts.py
Fetches business bank account configuration.

```bash
poetry run python -m src.jobs.freeagent_bank_accounts
```

#### freeagent_bank_transactions.py
Fetches bank transactions for cash flow tracking.

```bash
poetry run python -m src.jobs.freeagent_bank_transactions

# Options
--from-date YYYY-MM-DD
--to-date YYYY-MM-DD
--full-sync
```

**Data Flow:**
1. Fetch all bank accounts
2. For each account, fetch transactions (from_date filter)
3. Extract bank_account_id from URL
4. Upsert to `freeagent_bank_transactions` table

#### freeagent_bank_transaction_explanations.py
Fetches transaction categorization data.

```bash
poetry run python -m src.jobs.freeagent_bank_transaction_explanations

# Options
--from-date YYYY-MM-DD
--to-date YYYY-MM-DD
--full-sync
```

**Data Flow:**
1. Fetch all bank accounts
2. For each account, fetch explanations
3. Extract IDs from URLs (explanation, transaction, category, invoice, bill)
4. Upsert to `freeagent_bank_transaction_explanations` table

#### freeagent_transactions.py
Fetches general ledger transactions (double-entry bookkeeping).

```bash
poetry run python -m src.jobs.freeagent_transactions

# Options
--from-date YYYY-MM-DD
--to-date YYYY-MM-DD
--full-sync
```

**Data Flow:**
1. Fetch transactions from FreeAgent API (from_date filter)
2. Extract debit and credit values
3. Include nominal code and category
4. Upsert to `freeagent_transactions` table

#### freeagent_users.py
Fetches team members for access control.

```bash
poetry run python -m src.jobs.freeagent_users
```

### Job Scheduling

Jobs can be scheduled using cron or APScheduler:

```python
# Example: Schedule Shopify orders sync every hour
from apscheduler.schedulers.blocking import BlockingScheduler
from src.jobs.shopify_orders import run_shopify_orders_etl

scheduler = BlockingScheduler()
scheduler.add_job(
    run_shopify_orders_etl,
    'cron',
    hour='*/1',
    id='shopify_orders_hourly'
)
scheduler.start()
```

**Recommended Schedule:**
- **High Frequency (hourly)**: Orders, inventory, fulfillment status
- **Medium Frequency (daily)**: Products, customers, returns, receiving
- **Low Frequency (weekly)**: Categories, fulfillment centers, users

---

## Web Dashboard & API

### Flask Web Application

**File:** `src/web/app.py`

The web dashboard provides:
- System health monitoring
- ETL job execution history
- Data statistics and counts
- Business alerts dashboard
- Email notification testing

### Starting the Web Server

```bash
# Development mode
export FLASK_DEBUG=true
poetry run python -m src.web.app

# Production mode with Gunicorn
poetry run gunicorn src.web.app:app \
    --bind 0.0.0.0:5000 \
    --workers 4 \
    --timeout 120
```

### Configuration

```bash
# Environment variables
FLASK_SECRET_KEY=your-secret-key-here
FLASK_DEBUG=false
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
```

### API Endpoints

#### Health Check
```
GET /api/system/health
```

**Response:**
```json
{
    "status": "healthy",
    "timestamp": "2024-01-15T10:30:00.000Z",
    "database": "connected"
}
```

#### System Status
```
GET /api/system/status
```

**Response:**
```json
{
    "status": "operational",
    "timestamp": "2024-01-15T10:30:00.000Z",
    "data_counts": {
        "orders": 12345,
        "order_items": 23456,
        "inventory": 567,
        "settlements": 234
    },
    "recent_activity": [
        {
            "job_name": "shopify_orders",
            "status": "success",
            "started_at": "2024-01-15T10:00:00.000Z",
            "duration": 45.2,
            "records_processed": 23
        }
    ]
}
```

#### Test Email Notification
```
POST /api/test/email
Content-Type: application/json

{
    "email": "admin@example.com"
}
```

#### Dashboard Home
```
GET /
```

Displays:
- System overview (order counts, revenue)
- Recent job executions
- Active alerts
- Integration health status

---

## Analytics & Alerting

### Business Intelligence Alerts

**File:** `src/analytics/alerts.py`

The alerting system monitors operational data and detects business problems automatically.

#### Alert Categories

1. **Fulfillment Alerts**
   - Orders with fulfillment delays (>48 hours)
   - Slow order completion times (>72 hours)

2. **Delivery Alerts**
   - High delivery exception rate (>5%)
   - Fulfilled orders missing tracking numbers

3. **Inventory Alerts**
   - Low stock levels (≤10 units)
   - Out of stock items

4. **Financial Alerts**
   - Revenue drops (>20% decrease)
   - High refund rates (>10%)

5. **Data Quality Alerts**
   - Stale data (not updated in 6+ hours)
   - Missing critical data fields (>5%)

6. **System Alerts**
   - Integration health issues (no recent data)
   - ETL job failures

#### Alert Severity Levels

- **CRITICAL**: Immediate action required (e.g., >20 orders delayed)
- **HIGH**: Urgent attention needed (e.g., delivery exceptions >5%)
- **MEDIUM**: Monitor situation (e.g., low stock, stale data)
- **LOW**: Informational (e.g., data quality issues)

#### Running Business Analytics

```python
from src.analytics.alerts import BusinessAlertsMonitor

# Run all checks
monitor = BusinessAlertsMonitor()
alerts = monitor.check_all_alerts()

# Send critical alerts via email
monitor.send_critical_alerts()

# Filter alerts by severity
critical_alerts = monitor.get_alerts_by_severity(AlertSeverity.CRITICAL)

# Filter alerts by category
inventory_alerts = monitor.get_alerts_by_category(AlertCategory.INVENTORY)
```

#### Alert Data Structure

```python
@dataclass
class Alert:
    id: str                      # Unique alert identifier
    title: str                   # Human-readable title
    description: str             # Detailed description
    category: AlertCategory      # Alert category
    severity: AlertSeverity      # Severity level
    metric_value: float          # Actual metric value
    threshold_value: float       # Threshold that was exceeded
    affected_count: int          # Number of records affected
    created_at: datetime         # Alert timestamp
    metadata: Dict[str, Any]     # Additional context
```

#### Example Alerts

```python
# Fulfillment delay alert
Alert(
    id="fulfillment_delays",
    title="15 Orders with Fulfillment Delays",
    description="Found 15 orders pending fulfillment for over 48 hours. Average delay: 52.3 hours.",
    category=AlertCategory.FULFILLMENT,
    severity=AlertSeverity.HIGH,
    metric_value=52.3,
    threshold_value=48.0,
    affected_count=15,
    metadata={"avg_delay_hours": 52.3}
)

# Inventory alert
Alert(
    id="low_inventory",
    title="23 Items with Low Stock",
    description="Found 23 inventory items with quantities at or below 10 units. Minimum quantity: 3.",
    category=AlertCategory.INVENTORY,
    severity=AlertSeverity.MEDIUM,
    metric_value=3.0,
    threshold_value=10.0,
    affected_count=23,
    metadata={"threshold": 10}
)
```

#### Customizing Thresholds

```python
monitor = BusinessAlertsMonitor()
monitor.thresholds = {
    'max_fulfillment_hours': 24,        # Default: 48
    'delivery_exception_rate': 0.03,    # Default: 0.05 (5%)
    'low_stock_threshold': 20,          # Default: 10
    'revenue_drop_percentage': 0.15,    # Default: 0.20 (20%)
}
```

#### Email Notifications

```python
# Configure email recipients for critical alerts
CRITICAL_ALERT_EMAILS=admin@example.com,ops@example.com

# Alerts are sent automatically when severity is CRITICAL
monitor.send_critical_alerts()
```

### Simple Alerts (Lightweight)

**File:** `src/analytics/simple_alerts.py`

Simplified alerting for quick checks:

```python
from src.analytics.simple_alerts import (
    check_order_volume,
    check_inventory_health,
    check_data_freshness
)

# Quick health checks
order_alert = check_order_volume(threshold=50)  # Alert if <50 orders today
inventory_alert = check_inventory_health(low_stock_threshold=10)
freshness_alert = check_data_freshness(max_age_hours=6)
```

---

## Configuration Management

### Environment Variables (.env)

```bash
# Database Configuration
DATABASE_URL=postgresql://user:password@host:5432/database

# Amazon SP-API
AMZ_ACCESS_TOKEN=your_access_token
AMZ_REFRESH_TOKEN=your_refresh_token
AMZ_CLIENT_ID=your_client_id
AMZ_CLIENT_SECRET=your_client_secret
AMZ_MARKETPLACE_IDS=ATVPDKIKX0DER,A1F83G8C2ARO7P
AMZ_REGION=eu-west-1
AMZ_ENDPOINT=https://sellingpartnerapi-eu.amazon.com
AMZ_SYNC_LOOKBACK_HOURS=24

# Shopify Admin API
SHOPIFY_SHOP=your-store.myshopify.com
SHOPIFY_ACCESS_TOKEN=shpat_xxxxxxxxxxxxx
SHOPIFY_API_VERSION=2024-07
SHOPIFY_SYNC_LOOKBACK_HOURS=24

# ShipBob API
SHIPBOB_TOKEN=your_bearer_token
SHIPBOB_BASE=https://api.shipbob.com/2025-07

# FreeAgent OAuth
FREEAGENT_CLIENT_ID=your_client_id
FREEAGENT_CLIENT_SECRET=your_client_secret
FREEAGENT_REDIRECT_URI=http://localhost:8000/auth/freeagent/callback
FREEAGENT_ACCESS_TOKEN=your_access_token
FREEAGENT_REFRESH_TOKEN=your_refresh_token

# Web Dashboard
FLASK_SECRET_KEY=your-secret-key-here
FLASK_DEBUG=false
FLASK_HOST=0.0.0.0
FLASK_PORT=5000

# Email Notifications
CRITICAL_ALERT_EMAILS=admin@example.com,ops@example.com
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=notifications@example.com
SMTP_PASSWORD=your_smtp_password
```

### YAML Configuration (config/app.yaml)

```yaml
# Global configuration
global:
  timezone: UTC
  log_level: INFO

# Integration configuration
integrations:
  shopify:
    enabled: true
    orders:
      enabled: true
      schedule: "0 * * * *"  # Every hour
      lookback_hours: 24
    customers:
      enabled: true
      schedule: "0 2 * * *"  # Daily at 2 AM
      lookback_hours: 24
    products:
      enabled: true
      schedule: "0 3 * * *"  # Daily at 3 AM

  shipbob:
    enabled: true
    inventory:
      enabled: true
      schedule: "0 */2 * * *"  # Every 2 hours
    status:
      enabled: true
      schedule: "0 * * * *"  # Every hour
    returns:
      enabled: true
      schedule: "0 4 * * *"  # Daily at 4 AM

  freeagent:
    enabled: true
    contacts:
      enabled: true
      schedule: "0 5 * * *"  # Daily at 5 AM
      lookback_days: 30
    invoices:
      enabled: true
      schedule: "0 6 * * *"  # Daily at 6 AM
      lookback_days: 30
    bank_transactions:
      enabled: true
      schedule: "0 7 * * *"  # Daily at 7 AM
      lookback_days: 7

# Business alerts configuration
alerts:
  enabled: true
  schedule: "0 */6 * * *"  # Every 6 hours
  thresholds:
    max_fulfillment_hours: 48
    delivery_exception_rate: 0.05
    low_stock_threshold: 10
    revenue_drop_percentage: 0.2
```

### FreeAgent Feature Flags (config/freeagent.yaml)

```yaml
features:
  contacts: true
  invoices: true
  bills: true
  categories: true
  bank_accounts: true
  bank_transactions: true
  bank_transaction_explanations: true
  transactions: true
  users: true

api:
  rate_limit_delay: 0.5
  api_version: "2024-10-01"

sync:
  default_lookback_days: 30
  batch_size: 100
```

### Configuration Loader

```python
from src.config.loader import (
    cfg,
    env,
    is_integration_enabled,
    is_job_enabled,
    get_job_schedule,
    get_lookback_hours
)

# Get config value with dot notation
timezone = cfg("global.timezone", "UTC")

# Check if integration is enabled
if is_integration_enabled("shopify"):
    # Run Shopify jobs
    pass

# Check if specific job is enabled
if is_job_enabled("shopify", "orders"):
    # Run Shopify orders job
    pass

# Get job schedule
schedule = get_job_schedule("shopify", "orders")  # "0 * * * *"

# Get lookback period
lookback = get_lookback_hours("shopify", "orders", default=24)
```

---

## Development Setup

### Prerequisites

- **Python**: 3.11 or higher
- **Poetry**: 1.7+ for dependency management
- **PostgreSQL**: 14+ (Supabase or local)
- **Git**: For version control

### Initial Setup

```bash
# Clone repository
git clone https://github.com/your-org/stratus.git
cd stratus

# Install Poetry (if not installed)
curl -sSL https://install.python-poetry.org | python3 -

# Install dependencies
poetry install

# Activate virtual environment
poetry shell

# Copy environment template
cp .env.example .env

# Edit .env with your credentials
nano .env

# Run database migrations
alembic upgrade head

# Verify setup
poetry run python -m src.jobs.shopify_products
```

### Development Workflow

```bash
# Format code
poetry run black .

# Lint code
poetry run ruff check .

# Type checking
poetry run mypy src/

# Run tests
poetry run pytest

# Run tests with coverage
poetry run pytest --cov=src --cov-report=html
```

### Pre-commit Hooks

```bash
# Install pre-commit hooks
poetry run pre-commit install

# Run manually
poetry run pre-commit run --all-files
```

**Configuration** (`.pre-commit-config.yaml`):
```yaml
repos:
  - repo: https://github.com/psf/black
    rev: 23.7.0
    hooks:
      - id: black

  - repo: https://github.com/charliermarsh/ruff-pre-commit
    rev: v0.1.5
    hooks:
      - id: ruff
        args: [--fix]
```

### Running Tests

```bash
# Run all tests
poetry run pytest

# Run specific test file
poetry run pytest tests/test_amazon_orders.py

# Run specific test
poetry run pytest tests/test_amazon_orders.py::test_normalize_order

# Run with verbose output
poetry run pytest -v

# Run with coverage report
poetry run pytest --cov=src --cov-report=term-missing

# Generate HTML coverage report
poetry run pytest --cov=src --cov-report=html
open htmlcov/index.html
```

### Database Management

```bash
# Create new migration
alembic revision --autogenerate -m "Add new table"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Check current migration
alembic current

# View migration history
alembic history

# Reset database (WARNING: destroys all data)
alembic downgrade base
alembic upgrade head
```

### Local Development Tips

1. **Use mock data for development**:
   ```python
   # In tests/conftest.py
   @pytest.fixture
   def mock_shopify_response():
       return {
           "orders": [
               {"id": 123, "name": "#1001", ...}
           ]
       }
   ```

2. **Test with small date ranges**:
   ```bash
   # Test with last hour only
   AMZ_SYNC_LOOKBACK_HOURS=1 poetry run python -m src.jobs.amazon_orders
   ```

3. **Use database transactions in tests**:
   ```python
   @pytest.fixture
   def db_session():
       session = SessionLocal()
       yield session
       session.rollback()  # Rollback after test
       session.close()
   ```

4. **Monitor API rate limits**:
   ```python
   # Add logging to adapters
   logger.info(f"Rate limit: {current}/{limit}")
   ```

---

## Deployment Guide

### Production Deployment (Docker)

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install Poetry
RUN pip install poetry

# Copy dependency files
COPY pyproject.toml poetry.lock ./

# Install dependencies
RUN poetry config virtualenvs.create false \
    && poetry install --no-dev --no-interaction --no-ansi

# Copy application code
COPY . .

# Expose web port
EXPOSE 5000

# Run migrations and start server
CMD alembic upgrade head && \
    gunicorn src.web.app:app \
    --bind 0.0.0.0:5000 \
    --workers 4 \
    --timeout 120
```

```yaml
# docker-compose.yml
version: '3.8'

services:
  stratus:
    build: .
    ports:
      - "5000:5000"
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - SHOPIFY_SHOP=${SHOPIFY_SHOP}
      - SHOPIFY_ACCESS_TOKEN=${SHOPIFY_ACCESS_TOKEN}
      # ... other environment variables
    volumes:
      - ./logs:/app/logs
    restart: unless-stopped

  scheduler:
    build: .
    command: poetry run python -m src.scheduler
    environment:
      - DATABASE_URL=${DATABASE_URL}
      # ... other environment variables
    depends_on:
      - stratus
    restart: unless-stopped
```

### Deployment Steps

```bash
# Build Docker image
docker build -t stratus-erp:latest .

# Run with Docker Compose
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Environment-Specific Configuration

**Production (.env.production)**:
```bash
DATABASE_URL=postgresql://prod_user:secure_password@db.example.com:5432/stratus_prod
FLASK_DEBUG=false
LOG_LEVEL=WARNING
CRITICAL_ALERT_EMAILS=ops@example.com,admin@example.com
```

**Staging (.env.staging)**:
```bash
DATABASE_URL=postgresql://staging_user:password@db-staging.example.com:5432/stratus_staging
FLASK_DEBUG=true
LOG_LEVEL=INFO
```

### Monitoring & Logging

**Structured Logging**:
```python
import structlog

logger = structlog.get_logger()

logger.info("job_started", job_name="shopify_orders", lookback_hours=24)
logger.warning("rate_limit_approaching", current=38, limit=40)
logger.error("job_failed", job_name="amazon_orders", error=str(e))
```

**Prometheus Metrics**:
```python
from prometheus_client import Counter, Histogram

job_executions = Counter('job_executions_total', 'Total job executions', ['job_name', 'status'])
job_duration = Histogram('job_duration_seconds', 'Job execution duration', ['job_name'])

with job_duration.labels(job_name='shopify_orders').time():
    run_shopify_orders_etl()

job_executions.labels(job_name='shopify_orders', status='success').inc()
```

### Backup Strategy

```bash
# Daily database backups
pg_dump $DATABASE_URL | gzip > backups/stratus_$(date +%Y%m%d).sql.gz

# Backup environment configuration (encrypted)
gpg --encrypt --recipient admin@example.com .env > .env.gpg

# Backup to S3
aws s3 cp backups/ s3://company-backups/stratus/ --recursive
```

### Disaster Recovery

1. **Database Recovery**:
   ```bash
   # Restore from backup
   gunzip < backups/stratus_20240115.sql.gz | psql $DATABASE_URL
   ```

2. **Environment Recovery**:
   ```bash
   # Decrypt environment file
   gpg --decrypt .env.gpg > .env
   ```

3. **Application Recovery**:
   ```bash
   # Pull latest code
   git pull origin main

   # Rebuild Docker image
   docker-compose build

   # Run migrations
   docker-compose run stratus alembic upgrade head

   # Start services
   docker-compose up -d
   ```

### Security Best Practices

1. **Use secrets management**:
   - AWS Secrets Manager
   - HashiCorp Vault
   - Kubernetes Secrets

2. **Rotate credentials regularly**:
   - API tokens: Every 90 days
   - Database passwords: Every 180 days
   - OAuth tokens: Automatic refresh

3. **Network security**:
   - Use VPC for database access
   - Whitelist IP addresses
   - Enable SSL/TLS for all connections

4. **Access control**:
   - Role-based access control (RBAC)
   - Audit logging for all changes
   - Two-factor authentication (2FA)

---

## Troubleshooting

### Common Issues

#### 1. Database Connection Timeout

**Symptom:**
```
psycopg2.OperationalError: connection to server at "db.example.com" timed out
```

**Solutions:**
- Check if Supabase project is paused (free tier auto-pauses)
- Verify database URL is correct
- Test connection: `nc -zv db.example.com 5432`
- Check firewall rules and IP whitelist

#### 2. Poetry Not Found

**Symptom:**
```
command not found: poetry
```

**Solution:**
```bash
export PATH="$HOME/.local/bin:$PATH"
poetry --version
```

#### 3. Amazon API Authentication Error

**Symptom:**
```
AMZ_MARKETPLACE_IDS environment variable is required
```

**Solutions:**
- Verify `.env` file exists and contains correct variable names
- Check variable names match: `AMZ_*` not `AMAZON_SP_*`
- Ensure dotenv is loaded in adapter initialization

#### 4. Shopify Rate Limit Exceeded

**Symptom:**
```
429 Too Many Requests
```

**Solutions:**
- Increase delay between requests
- Monitor `X-Shopify-Shop-Api-Call-Limit` header
- Implement exponential backoff
- Use bulk operations when available

#### 5. FreeAgent Feature Unavailable

**Symptom:**
```
403 Forbidden: Feature not available for this account
```

**Solutions:**
- Check FreeAgent account plan
- Update `config/freeagent.yaml` to disable unavailable features
- Graceful degradation: Job continues with warning, not error

#### 6. Migration Conflicts

**Symptom:**
```
alembic.util.exc.CommandError: Target database is not up to date
```

**Solutions:**
```bash
# Check current migration
alembic current

# View migration history
alembic history

# Stamp current version (if database is manually updated)
alembic stamp head

# Force upgrade
alembic upgrade head
```

### Debugging Tips

#### Enable Debug Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Or in code
logger.setLevel(logging.DEBUG)
```

#### Test API Connections

```python
# Test Shopify connection
from src.adapters.shopify import ShopifyOrdersClient
client = ShopifyOrdersClient()
print(client._test_connection())

# Test Amazon connection
from src.adapters.amazon import AmazonOrdersClient
client = AmazonOrdersClient()
print(client.config)
```

#### Check Database Schema

```sql
-- List all tables
\dt

-- Describe table structure
\d orders

-- Check indexes
\di

-- View recent records
SELECT * FROM orders ORDER BY created_at DESC LIMIT 10;
```

#### Monitor Job Execution

```python
import time
start_time = time.time()

stats = run_shopify_orders_etl()

duration = time.time() - start_time
print(f"Job completed in {duration:.2f} seconds")
print(f"Stats: {stats}")
```

---

## API Reference

### Adapter Classes

#### AmazonOrdersClient

```python
class AmazonOrdersClient:
    def __init__(self, config: AmazonConfig | None = None)
    def get_orders_since(self, since_iso: str) -> Tuple[List[Dict], List[Dict]]
```

#### ShopifyOrdersClient

```python
class ShopifyOrdersClient:
    def __init__(self)
    def get_orders_since(self, since_iso: str, status: str = "any") -> Tuple[List[Dict], List[Dict]]
```

#### ShipBobInventoryClient

```python
class ShipBobInventoryClient:
    def __init__(self)
    def get_inventory(self) -> List[Dict]
```

#### FreeAgentContactsClient

```python
class FreeAgentContactsClient:
    def __init__(self)
    def get_contacts(self, from_date: str, to_date: str) -> List[Dict]
```

### Upsert Functions

```python
def upsert_orders(orders: List[Dict], session: Session) -> Tuple[int, int]:
    """
    Upsert orders to database.

    Args:
        orders: List of normalized order dictionaries
        session: SQLAlchemy session

    Returns:
        Tuple of (inserted_count, updated_count)
    """

def upsert_order_items(items: List[Dict], session: Session) -> Tuple[int, int]:
    """Upsert order items to database."""

def upsert_inventory(records: List[Dict], session: Session) -> Tuple[int, int]:
    """Upsert inventory records to database."""
```

### Configuration Functions

```python
def cfg(key: str, default: Any = None) -> Any:
    """Get configuration value using dot notation."""

def env(key: str, default: str = None) -> str | None:
    """Get environment variable with optional default."""

def is_integration_enabled(integration: str) -> bool:
    """Check if an integration is enabled."""

def is_job_enabled(integration: str, job: str) -> bool:
    """Check if a specific job is enabled."""
```

### Alert Functions

```python
class BusinessAlertsMonitor:
    def check_all_alerts(self) -> List[Dict[str, Any]]
    def get_alerts_by_severity(self, severity: AlertSeverity) -> List[Alert]
    def get_alerts_by_category(self, category: AlertCategory) -> List[Alert]
    def send_critical_alerts(self) -> None
```

---

## Best Practices

### Code Quality

1. **Follow PEP 8 style guide** (enforced by Black and Ruff)
2. **Add type hints** to all functions (enforced by MyPy)
3. **Write docstrings** for all public functions
4. **Keep functions small** (<50 lines)
5. **Use meaningful variable names** (no single letters except loop counters)

### Error Handling

```python
# Good: Specific exception handling
try:
    orders = client.get_orders()
except AmazonRateLimitError:
    logger.warning("Rate limit exceeded, waiting...")
    time.sleep(60)
    orders = client.get_orders()
except AmazonAuthError:
    logger.error("Authentication failed")
    raise

# Bad: Catch-all exception
try:
    orders = client.get_orders()
except Exception:
    pass  # Silently fails
```

### Database Operations

1. **Always use upsert functions** (never raw SQL for data loading)
2. **Use transactions** for multi-table operations
3. **Add indexes** for frequently queried columns
4. **Use connection pooling** (handled by SQLAlchemy)
5. **Close sessions** after use (use context managers)

```python
# Good: Context manager
with get_session() as session:
    upsert_orders(orders, session)
    upsert_order_items(items, session)
# Session closed automatically

# Bad: Manual session management
session = get_session()
upsert_orders(orders, session)
# Session never closed = connection leak
```

### Testing

1. **Write tests for all adapters** (use mocking)
2. **Test data normalization** extensively
3. **Test error handling** (rate limits, network failures)
4. **Use realistic mock data** (based on actual API responses)
5. **Test idempotency** (run same data twice, verify no duplicates)

```python
def test_normalize_order():
    """Test order normalization from Amazon format."""
    raw_order = {
        "AmazonOrderId": "111-2222222-3333333",
        "PurchaseDate": "2024-01-15T10:30:00Z",
        "OrderTotal": {"Amount": "99.99", "CurrencyCode": "USD"}
    }

    normalized = client._normalize_order(raw_order)

    assert normalized["order_id"] == "111-2222222-3333333"
    assert normalized["source"] == "amazon"
    assert isinstance(normalized["purchase_date"], datetime)
    assert normalized["total"] == Decimal("99.99")
```

### Performance Optimization

1. **Use bulk operations** when possible
2. **Batch database inserts** (handled by upsert functions)
3. **Index frequently queried columns**
4. **Use database connection pooling**
5. **Implement caching** for slow API calls
6. **Monitor query performance** (SQLAlchemy echo=True for debugging)

### Security

1. **Never commit credentials** to Git
2. **Use environment variables** for all secrets
3. **Rotate API tokens** regularly
4. **Use HTTPS** for all API calls
5. **Validate input data** before database insertion
6. **Use parameterized queries** (SQLAlchemy ORM handles this)

---

## Appendix

### Project Structure Reference

```
stratus/
├── alembic/                    # Database migrations
│   ├── versions/              # Migration files
│   └── env.py                 # Alembic configuration
├── config/                     # Configuration files
│   ├── app.yaml               # Main configuration
│   └── freeagent.yaml         # FreeAgent feature flags
├── src/                        # Application source code
│   ├── adapters/              # External API clients
│   │   ├── amazon.py
│   │   ├── shopify.py
│   │   ├── shipbob.py
│   │   └── freeagent.py
│   ├── analytics/             # Business intelligence
│   │   ├── alerts.py          # Alert monitoring
│   │   └── simple_alerts.py
│   ├── common/                # Shared utilities
│   │   ├── etl.py             # ETL helpers
│   │   ├── http.py            # HTTP utilities
│   │   └── notifications.py   # Email notifications
│   ├── config/                # Configuration management
│   │   └── loader.py          # Config loader
│   ├── db/                    # Database layer
│   │   ├── models/            # SQLAlchemy models
│   │   │   ├── core.py        # Core tables
│   │   │   ├── shopify.py
│   │   │   ├── shipbob.py
│   │   │   └── freeagent.py
│   │   ├── upserts/           # Upsert functions
│   │   │   ├── core.py
│   │   │   ├── shopify.py
│   │   │   ├── shipbob.py
│   │   │   └── freeagent.py
│   │   ├── config.py          # Database configuration
│   │   └── deps.py            # Dependency injection
│   ├── jobs/                  # ETL job scripts
│   │   ├── amazon_orders.py
│   │   ├── shopify_orders.py
│   │   ├── shipbob_inventory.py
│   │   └── freeagent_contacts.py
│   ├── utils/                 # Utility functions
│   │   ├── rate_limit.py
│   │   ├── time_windows.py
│   │   └── oauth.py
│   ├── web/                   # Web dashboard
│   │   └── app.py             # Flask application
│   └── server.py              # Main server entry point
├── tests/                      # Test suite
├── .env                        # Environment variables (not in Git)
├── .env.example                # Environment template
├── .gitignore                  # Git ignore rules
├── pyproject.toml              # Poetry dependencies
├── alembic.ini                 # Alembic configuration
└── README.md                   # Project README
```

### Database Entity-Relationship Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         Core Tables                             │
└─────────────────────────────────────────────────────────────────┘

orders (PK: order_id)
    ├── order_items (FK: order_id → orders.order_id)
    ├── shopify_customers (via customer_id)
    └── shipbob_orders (via reference_id = order_id)
         ├── shipbob_returns (via reference_id)
         └── shipbob_fulfillment_centers (via fulfillment_center_id)

inventory (PK: sku, source)
    ├── shopify_variants (via sku)
    └── shipbob_products (via sku)

settlements (PK: settlement_id)
    └── settlement_lines (FK: settlement_id → settlements.settlement_id)

┌─────────────────────────────────────────────────────────────────┐
│                       Shopify Tables                            │
└─────────────────────────────────────────────────────────────────┘

shopify_products (PK: product_id)
    └── shopify_variants (FK: product_id → shopify_products.product_id)
         └── inventory (via sku)

┌─────────────────────────────────────────────────────────────────┐
│                       ShipBob Tables                            │
└─────────────────────────────────────────────────────────────────┘

shipbob_products (PK: product_id)
    └── shipbob_variants (FK: product_id → shipbob_products.product_id)

shipbob_fulfillment_centers (PK: center_id)
    ├── shipbob_orders (via fulfillment_center_id)
    ├── shipbob_returns (via fulfillment_center_id)
    └── shipbob_receiving_orders (via fulfillment_center_id)

┌─────────────────────────────────────────────────────────────────┐
│                      FreeAgent Tables                           │
└─────────────────────────────────────────────────────────────────┘

freeagent_contacts (PK: contact_id)
    ├── freeagent_invoices (via contact_id)
    └── freeagent_bills (via contact_id)

freeagent_categories (PK: category_id)
    ├── freeagent_bank_transaction_explanations (via category_id)
    └── freeagent_transactions (via category_id)

freeagent_bank_accounts (PK: bank_account_id)
    ├── freeagent_bank_transactions (via bank_account_id)
    └── freeagent_bank_transaction_explanations (via bank_account_id)

freeagent_invoices (PK: invoice_id)
    └── freeagent_bank_transaction_explanations (via invoice_id)

freeagent_bills (PK: bill_id)
    └── freeagent_bank_transaction_explanations (via bill_id)
```

### Glossary

- **ASIN**: Amazon Standard Identification Number
- **ETL**: Extract, Transform, Load (data pipeline pattern)
- **FNSKU**: Fulfillment Network Stock Keeping Unit (Amazon)
- **OAuth**: Open Authorization (authentication protocol)
- **SKU**: Stock Keeping Unit (product identifier)
- **SP-API**: Selling Partner API (Amazon)
- **Upsert**: Database operation that inserts or updates (INSERT ... ON CONFLICT UPDATE)
- **WRO**: Warehouse Receiving Order (ShipBob inbound logistics)

---

## Changelog

### Version 0.1.0 (Current)
- Initial release with 4 platform integrations
- 26 ETL jobs for orders, inventory, customers, accounting
- Web dashboard with business alerts
- Comprehensive database schema with 20+ tables
- Idempotent upsert operations
- Cross-platform data linking
- Email notification system
- Docker deployment support

### Planned Features (Future Releases)

**Version 0.2.0**
- Write operations (create orders, update inventory)
- Webhook support for real-time updates
- GraphQL API for flexible data queries
- Advanced analytics dashboard with charts

**Version 0.3.0**
- Workflow automation engine
- Rule-based business logic
- Multi-tenant support
- Advanced access control (RBAC)

---

## Support & Contact

For questions, issues, or feature requests:

- **GitHub Issues**: https://github.com/your-org/stratus/issues
- **Documentation**: https://docs.stratus-erp.example.com
- **Email**: support@example.com

---

**Document Version**: 1.0
**Generated**: October 26, 2025
**Copyright**: © 2025 Your Organization. All rights reserved.

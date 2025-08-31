# Stratus ERP Integration Service

A Python-based ERP integration service that starts as a data warehouse and can evolve into a full ERP system with workflow automation capabilities.

## Overview

Stratus is designed as a flexible integration platform that:

### Current Mode: Data Warehouse
- **Read-only operations**: Fetches data from external APIs
- **Supported integrations**: Amazon SP-API, Shopify, ShipBob, FreeAgent
- **Data normalization**: All data is normalized and stored in Supabase/Postgres
- **Reliable ETL**: Built-in retries, idempotent upserts, comprehensive logging
- **Scheduled execution**: Uses APScheduler for automated data collection
- **Feature flags**: Graceful handling of unavailable endpoints (403/404 errors)
- **Comprehensive testing**: Full test coverage for all integrations

### Future Mode: Full ERP
- **Write operations**: Create invoices, update orders, sync data between systems
- **Workflow automation**: Complex business logic combining multiple systems
- **Examples**: 
  - Auto-create FreeAgent invoices from order data
  - Push Shopify orders directly to ShipBob fulfillment
  - Cross-platform inventory synchronization

## Architecture

```
├── src/
│   ├── db/          # Postgres client, migrations, models
│   ├── adapters/    # API client wrappers (from OpenAPI specs)
│   ├── jobs/        # Read-only ETL jobs (current)
│   ├── writers/     # Outbound integrations (future)
│   └── flows/       # Workflows combining jobs + writers (future)
├── main.py          # APScheduler entrypoint
├── pyproject.toml   # Poetry dependencies
├── Dockerfile       # Container configuration
└── README.md        # This file
```

## Requirements

- **Python**: 3.11+
- **Package Manager**: Poetry
- **Database**: PostgreSQL (via Supabase)
- **Dependencies**: 
  - `requests` - HTTP client for API integrations
  - `psycopg2-binary` - PostgreSQL adapter
  - `sqlalchemy` - ORM and database abstraction
  - `pydantic` - Data validation and serialization
  - `apscheduler` - Job scheduling
  - `tenacity` - Retry logic with exponential backoff

## Development Setup

1. **Install Poetry** (if not already installed):
   ```bash
   curl -sSL https://install.python-poetry.org | python3 -
   ```

2. **Install dependencies**:
   ```bash
   poetry install
   ```

3. **Activate virtual environment**:
   ```bash
   poetry shell
   ```

4. **Database Setup**:
   ```bash
   # Copy environment template and add your Supabase connection string
   cp .env.example .env
   # Edit .env and paste your Supabase DATABASE_URL from dashboard → Settings → Database
   
   # Initialize database schema
   alembic upgrade head
   ```

5. **Run the service**:
   ```bash
   python main.py
   ```

## Docker Usage

1. **Build image**:
   ```bash
   docker build -t stratus-erp .
   ```

2. **Run container**:
   ```bash
   docker run --env-file .env stratus-erp
   ```

## Development Roadmap

### Phase 1: Data Warehouse (Current)
- [x] Project scaffold and dependencies
- [x] Database migrations and schema
- [x] Amazon SP-API orders import
- [ ] Shopify orders import
- [ ] ShipBob inventory import
- [ ] FreeAgent financial data import

### Phase 2: ERP Capabilities (Future)
- [ ] Writer framework for outbound operations
- [ ] FreeAgent invoice creation
- [ ] Shopify → ShipBob order fulfillment
- [ ] Cross-platform inventory sync
- [ ] Workflow orchestration system

### Phase 3: Advanced Features (Future)
- [ ] Web UI for monitoring and configuration
- [ ] Real-time webhooks support
- [ ] Advanced reporting and analytics
- [ ] Multi-tenant support

## Contributing

1. Follow the existing folder structure
2. Add new integrations to `/src/adapters/`
3. Create ETL jobs in `/src/jobs/`
4. Future writers go in `/src/writers/`
5. Complex workflows in `/src/flows/`

## Database Setup

### Initial Setup
1. **Copy environment template**:
   ```bash
   cp .env.example .env
   ```

2. **Configure Supabase connection**:
   - Go to your Supabase dashboard → Settings → Database
   - Copy the connection string (it looks like: `postgresql://postgres:password@db.abc123.supabase.co:5432/postgres`)
   - Paste it as the `DATABASE_URL` value in your `.env` file

3. **Initialize database**:
   ```bash
   # Install dependencies first
   poetry install
   
   # Run database migrations
   alembic upgrade head
   ```

### Database Management
- **Revert last migration**: `alembic downgrade -1`
- **Check migration status**: `alembic current`
- **Create new migration**: `alembic revision --autogenerate -m "description"`

### Database Notes
- Supabase is vanilla PostgreSQL, so you can use standard tools like `pg_dump` and `psql` for backups and direct access
- The database schema supports multiple data sources with proper indexing for performance
- All upsert operations are idempotent and safe to run repeatedly

## Running ETL Jobs

### Amazon Orders Import
Import orders from Amazon SP-API into the data warehouse:

```bash
# Run the Amazon orders sync job
poetry run python -m src.jobs.amazon_orders

# Or run directly
python -m src.jobs.amazon_orders
```

**Environment Variables Required:**
- `AMZ_ACCESS_TOKEN` - Amazon LWA access token
- `AMZ_REFRESH_TOKEN` - Amazon LWA refresh token  
- `AMZ_CLIENT_ID` - Amazon LWA client ID
- `AMZ_CLIENT_SECRET` - Amazon LWA client secret
- `AMZ_MARKETPLACE_IDS` - Comma-separated marketplace IDs (e.g., "A1F83G8C2ARO7P,A13V1IB3VIYZZH")

**Optional Configuration:**
- `AMZ_REGION` - AWS region (default: "eu-west-1")
- `AMZ_ENDPOINT` - SP-API endpoint (default: "https://sellingpartnerapi-eu.amazon.com")
- `AMZ_SYNC_LOOKBACK_HOURS` - Hours to look back for orders (default: 24)

The job will:
1. Fetch orders updated in the last N hours (configurable)
2. Normalize data to match the warehouse schema
3. Upsert orders and order items (idempotent)
4. Log detailed statistics and any errors

### Amazon Settlements Import
Import settlements and settlement lines from Amazon SP-API Reports:

```bash
# Run the Amazon settlements sync job
poetry run python -m src.jobs.amazon_settlements

# Or run directly
python -m src.jobs.amazon_settlements
```

**Environment Variables:**
- Reuses Amazon credentials from the Orders job: `AMZ_ACCESS_TOKEN`, `AMZ_REFRESH_TOKEN`, `AMZ_CLIENT_ID`, `AMZ_CLIENT_SECRET`, `AMZ_MARKETPLACE_IDS`
- `AMZ_SETTLEMENT_LOOKBACK_DAYS` - Days to look back for the report date range (default: 14)

The job will:
1. Request a settlement report for the date range (ends yesterday)
2. Poll until the report is complete, handling rate limits
3. Download and parse the tab-separated settlement CSV
4. Upsert `settlements` and `settlement_lines` (idempotent)
5. Log progress, counts, and errors

 

### Amazon FBA Inventory Import
Import current inventory levels from Amazon FBA:

```bash
# Run the Amazon FBA inventory sync job (full refresh)
poetry run python -m src.jobs.amazon_inventory

# Or run directly
python -m src.jobs.amazon_inventory
```

**Environment Variables Required:**
- Same Amazon API credentials as other jobs (AMZ_ACCESS_TOKEN, etc.)

**Optional Parameters:**
```bash
# Future: Incremental sync for specific SKUs
python -m src.jobs.amazon_inventory --incremental SKU1 SKU2 SKU3
```

The job will:
1. Fetch all FBA inventory summaries with pagination
2. Handle multiple fulfillment centers per SKU (aggregates quantities)
3. Normalize inventory data (on_hand, reserved, inbound quantities)
4. Upsert inventory records by SKU (idempotent full refresh)
5. Log detailed processing statistics

**Note:** This is a full refresh job that updates all inventory records. It aggregates quantities across multiple fulfillment centers for the same SKU.

## Shopify ETL Jobs

### Shopify Orders Import
Import orders and line items from Shopify Admin API:

```bash
# Run the Shopify orders sync job
poetry run python -m src.jobs.shopify_orders

# Or run directly
python -m src.jobs.shopify_orders
```

**Environment Variables Required:**
- `SHOPIFY_SHOP` - Shop name (e.g., "myshop" for myshop.myshopify.com)
- `SHOPIFY_ACCESS_TOKEN` - Admin API access token (e.g., "shpat_xxx")

**Optional Configuration:**
- `SHOPIFY_API_VERSION` - API version (default: "2024-07")
- `SHOPIFY_SYNC_LOOKBACK_HOURS` - Hours to look back for orders (default: 24)

### Shopify Customers Import
Import customer data from Shopify Admin API:

```bash
# Run the Shopify customers sync job
poetry run python -m src.jobs.shopify_customers

# Or run directly
python -m src.jobs.shopify_customers
```

**Environment Variables:** Same as orders job

### Shopify Products Import  
Import products and variants from Shopify Admin API:

```bash
# Run the Shopify products sync job (full refresh)
poetry run python -m src.jobs.shopify_products

# Or run directly
python -m src.jobs.shopify_products
```

**Environment Variables:** Same as orders job (no lookback period needed)

All Shopify jobs will:
1. Fetch data using pagination with proper rate limit handling
2. Normalize data to match warehouse schema
3. Upsert records (idempotent operations)
4. Log detailed processing statistics and handle errors gracefully

## ShipBob ETL Jobs

### ShipBob Inventory Import
Import current inventory levels from ShipBob warehouses:

```bash
# Run the ShipBob inventory sync job (full refresh)
poetry run python -m src.jobs.shipbob_inventory

# Or run directly
python -m src.jobs.shipbob_inventory
```

**Environment Variables Required:**
- `SHIPBOB_TOKEN` - ShipBob API token (Personal Access Token or OAuth)
- `SHIPBOB_BASE` - ShipBob API base URL (default: "https://api.shipbob.com/2025-07")

**Job Behavior:**
- **Full refresh**: Replaces all ShipBob inventory data
- **Merge strategy**: Uses (sku, source) as primary key, where source='shipbob'
- **Conflicting sources**: ShipBob inventory is separate from Amazon FBA inventory
- **Idempotent**: Safe to run repeatedly

The job will:
1. Fetch all inventory levels from ShipBob `/inventory-level` endpoint
2. Normalize inventory data with ShipBob-specific quantity fields:
   - `quantity_on_hand` - Physical inventory in warehouse
   - `quantity_available` - Available for sale (sellable quantity)  
   - `quantity_reserved` - Reserved for existing orders (committed)
   - `quantity_incoming` - Awaiting receipt/processing
   - `fulfillable_quantity` - Available for immediate fulfillment
   - `backordered_quantity` - On backorder
   - `exception_quantity` - Exception/damaged inventory
   - `internal_transfer_quantity` - In internal transfer
3. Upsert inventory records with conflict resolution on (sku, source)
4. Log detailed processing statistics

### ShipBob Order Status Import
Update order status and tracking for Shopify orders fulfilled by ShipBob:

```bash
# Run the ShipBob order status sync job
poetry run python -m src.jobs.shipbob_status  

# Or run directly
python -m src.jobs.shipbob_status
```

**Environment Variables Required:**
- Same ShipBob credentials as inventory job (`SHIPBOB_TOKEN`, `SHIPBOB_BASE`)

**Optional Configuration:**
- `SHIPBOB_STATUS_LOOKBACK_HOURS` - Hours to look back for order updates (default: 24)

**Job Behavior:**
- **Incremental updates**: Only processes orders updated since lookback period
- **Status precedence**: ShipBob status updates override existing order status
- **Tracking enrichment**: Adds tracking numbers, carriers, and tracking URLs
- **Shopify orders only**: Filters to orders with `reference_id` (external order IDs)

The job will:
1. Fetch orders updated in the last N hours from ShipBob `/order` endpoint
2. Filter to orders with external reference IDs (Shopify order IDs)
3. Extract status and tracking information from latest shipments
4. Map ShipBob status to normalized status values:
   - `Processing` → `processing`
   - `Shipped` → `shipped`  
   - `Complete` → `delivered`
   - `Cancelled` → `cancelled`
   - `Exception` → `exception`
5. Update existing orders in database with new status/tracking info
6. Log statistics including orders with tracking information

**Status Precedence Documentation:**
- ShipBob status updates are applied to existing orders only
- No new orders are created (orders must exist from Shopify sync first)
- ShipBob tracking information supplements existing order data
- Last update wins for conflicting status sources

### ShipBob Returns Import
Import return orders from ShipBob for cost analysis and return rate tracking:

```bash
# Run the ShipBob returns sync job
poetry run python -m src.jobs.shipbob_returns

# Or run directly
python -m src.jobs.shipbob_returns
```

**Environment Variables Required:**
- Same ShipBob credentials as other jobs (`SHIPBOB_TOKEN`, `SHIPBOB_BASE`)

**Optional Configuration:**
- `SHIPBOB_RETURNS_LOOKBACK_DAYS` - Days to look back for returns (default: 30)

The job provides:
- Return rate analysis by product and time period
- Cost tracking for return processing and shipping labels
- Fulfillment center performance metrics
- Return reason and action analysis

### ShipBob Receiving Orders Import
Import warehouse receiving orders (WROs) for inbound logistics tracking:

```bash
# Run the ShipBob receiving orders sync job
poetry run python -m src.jobs.shipbob_receiving

# Or run directly
python -m src.jobs.shipbob_receiving
```

**Optional Configuration:**
- `SHIPBOB_RECEIVING_LOOKBACK_DAYS` - Days to look back for WROs (default: 14)

The job provides:
- Purchase order tracking and fulfillment rates
- Expected vs received quantity variance analysis
- Inbound processing time metrics
- Supply chain visibility and performance tracking

### ShipBob Products Import
Import product catalog from ShipBob for product management and analytics:

```bash
# Run the ShipBob products sync job (full refresh)
poetry run python -m src.jobs.shipbob_products

# Or run directly
python -m src.jobs.shipbob_products
```

The job provides:
- Complete product catalog with variants
- Product dimensions, weight, and value tracking
- SKU and barcode management
- Product categorization and attributes
- Multi-variant product support

### ShipBob Fulfillment Centers Import
Import fulfillment center information for geographic analytics:

```bash
# Run the ShipBob fulfillment centers sync job
poetry run python -m src.jobs.shipbob_fulfillment_centers

# Or run directly
python -m src.jobs.shipbob_fulfillment_centers
```

The job provides:
- Fulfillment center locations and contact information
- Geographic distribution analysis
- Timezone and operational data
- Warehouse network visibility

## ShipBob Analytics Capabilities

The extended ShipBob integration enables comprehensive analytics:

### **Operational Intelligence**
- **Return Rate Analysis**: Track return patterns by product, reason, and fulfillment center
- **Inbound Logistics**: Monitor receiving efficiency and purchase order accuracy
- **Geographic Performance**: Analyze fulfillment speed by warehouse location
- **Cost Attribution**: Full visibility into return processing and shipping costs

### **Business Intelligence Queries**
```sql
-- Return rate by product category
SELECT sp.category, COUNT(sr.return_id) as returns, 
       COUNT(sr.return_id) * 100.0 / COUNT(DISTINCT so.order_id) as return_rate
FROM shipbob_products sp
JOIN shipbob_returns sr ON sr.reference_id IN (
    SELECT order_id FROM orders WHERE source = 'shopify'
)
JOIN orders so ON so.order_id = sr.reference_id
GROUP BY sp.category;

-- Fulfillment center performance
SELECT sfc.name, sfc.state,
       AVG(EXTRACT(DAYS FROM (sr.completed_date - sr.insert_date))) as avg_processing_days
FROM shipbob_fulfillment_centers sfc
JOIN shipbob_returns sr ON sr.fulfillment_center_id = sfc.center_id
WHERE sr.completed_date IS NOT NULL
GROUP BY sfc.center_id, sfc.name, sfc.state;

-- Inventory accuracy by receiving
SELECT sro.purchase_order_number,
       SUM((iq->>'expected_quantity')::int) as expected_total,
       SUM((iq->>'received_quantity')::int) as received_total,
       (SUM((iq->>'received_quantity')::int) * 100.0 / 
        NULLIF(SUM((iq->>'expected_quantity')::int), 0)) as accuracy_rate
FROM shipbob_receiving_orders sro,
     jsonb_array_elements(sro.inventory_quantities::jsonb) iq
WHERE sro.status = 'Completed'
GROUP BY sro.wro_id, sro.purchase_order_number;
```

### **Data Relationships**
- **Cross-Platform Linking**: Returns linked to original Shopify orders via `reference_id`
- **Product Consistency**: ShipBob products can be matched with inventory by SKU
- **Geographic Analysis**: Orders, returns, and inventory linked to fulfillment centers
- **Cost Tracking**: Transaction-level cost data for profitability analysis

All ShipBob jobs provide:
- **Idempotent Operations**: Safe to run multiple times without data duplication
- **Incremental Updates**: Configurable lookback periods for efficient processing
- **Comprehensive Logging**: Detailed statistics and error handling
- **Modular Design**: Each job can run independently or as part of scheduled workflows

## FreeAgent ETL Jobs (Phase FA-1)

FreeAgent integration provides comprehensive accounting data ingestion with feature flags and graceful error handling for unavailable endpoints (403/404 errors).

### Configuration

FreeAgent features are controlled via `config/freeagent.yaml`:

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
  max_retries: 3
  backoff_factor: 2
  timeout: 30
  rate_limit_delay: 0.5
  api_version: "2024-10-01"  # Optional API versioning

sync:
  default_lookback_days: 30
  batch_size: 100
  max_pages: 1000
```

**Environment Variables Required:**
- `FREEAGENT_ACCESS_TOKEN` - OAuth 2.0 access token for FreeAgent API

### FreeAgent Contacts Import
Import customers and suppliers from FreeAgent:

```bash
# Default incremental sync (last 30 days)
python -m src.jobs.freeagent_contacts

# Specific date range
python -m src.jobs.freeagent_contacts --from-date 2024-01-01 --to-date 2024-01-31

# Full historical sync
python -m src.jobs.freeagent_contacts --full-sync
```

### FreeAgent Invoices Import
Import sales invoices and revenue data:

```bash
# Default incremental sync
python -m src.jobs.freeagent_invoices

# Specific date range
python -m src.jobs.freeagent_invoices --from-date 2024-01-01 --to-date 2024-01-31

# Full historical sync
python -m src.jobs.freeagent_invoices --full-sync
```

### FreeAgent Bills Import
Import purchase invoices and expense data:

```bash
# Default incremental sync
python -m src.jobs.freeagent_bills

# Full sync with date range
python -m src.jobs.freeagent_bills --from-date 2024-01-01 --full-sync
```

### FreeAgent Categories Import
Import chart of accounts and nominal codes:

```bash
# Full sync only (categories rarely change)
python -m src.jobs.freeagent_categories
```

### FreeAgent Bank Accounts Import
Import bank account configuration:

```bash
# Full sync only
python -m src.jobs.freeagent_bank_accounts
```

### FreeAgent Bank Transactions Import
Import bank transaction data for cash flow tracking:

```bash
# Default incremental sync
python -m src.jobs.freeagent_bank_transactions

# Specific date range
python -m src.jobs.freeagent_bank_transactions --from-date 2024-01-01 --to-date 2024-01-31
```

### FreeAgent Bank Transaction Explanations Import
Import transaction categorizations and explanations:

```bash
# Default incremental sync
python -m src.jobs.freeagent_bank_transaction_explanations

# Full sync
python -m src.jobs.freeagent_bank_transaction_explanations --full-sync
```

### FreeAgent General Ledger Transactions Import
Import double-entry bookkeeping transactions:

```bash
# Default incremental sync
python -m src.jobs.freeagent_transactions

# Specific nominal code filter (handled by API)
python -m src.jobs.freeagent_transactions --from-date 2024-01-01
```

### FreeAgent Users Import
Import team members and access permissions:

```bash
# Full sync only
python -m src.jobs.freeagent_users
```

## FreeAgent Analytics Capabilities

The FreeAgent integration enables comprehensive financial analytics:

### **Core Accounting Data**
- **Contacts**: Customer and supplier relationship management
- **Invoices**: Revenue tracking and accounts receivable analysis  
- **Bills**: Expense management and accounts payable tracking
- **Categories**: Chart of accounts with nominal codes and hierarchies
- **Bank Data**: Cash flow analysis with transaction categorization

### **Financial Intelligence Queries**
```sql
-- Revenue by month and customer type
SELECT DATE_TRUNC('month', dated_on) as month,
       COUNT(*) as invoice_count,
       SUM(total_value::numeric) as total_revenue,
       AVG(total_value::numeric) as avg_invoice_value
FROM freeagent_invoices 
WHERE status = 'Paid' AND dated_on >= '2024-01-01'
GROUP BY DATE_TRUNC('month', dated_on)
ORDER BY month;

-- Outstanding receivables by aging
SELECT 
  CASE 
    WHEN CURRENT_DATE - due_on <= 30 THEN '0-30 days'
    WHEN CURRENT_DATE - due_on <= 60 THEN '31-60 days'  
    WHEN CURRENT_DATE - due_on <= 90 THEN '61-90 days'
    ELSE '90+ days'
  END as aging_bucket,
  COUNT(*) as invoice_count,
  SUM(due_value::numeric) as total_outstanding
FROM freeagent_invoices 
WHERE due_value::numeric > 0
GROUP BY aging_bucket;

-- Cash flow by bank account
SELECT fba.name as bank_account,
       DATE_TRUNC('month', fbt.dated_on) as month,
       SUM(CASE WHEN fbt.amount::numeric > 0 THEN fbt.amount::numeric ELSE 0 END) as inflows,
       SUM(CASE WHEN fbt.amount::numeric < 0 THEN ABS(fbt.amount::numeric) ELSE 0 END) as outflows,
       SUM(fbt.amount::numeric) as net_flow
FROM freeagent_bank_transactions fbt
JOIN freeagent_bank_accounts fba ON fba.bank_account_id = fbt.bank_account_id
WHERE fbt.dated_on >= '2024-01-01'
GROUP BY fba.name, DATE_TRUNC('month', fbt.dated_on)
ORDER BY month, bank_account;

-- Expense analysis by category
SELECT fc.description as category,
       fc.nominal_code,
       COUNT(fb.bill_id) as bill_count,
       SUM(fb.total_value::numeric) as total_expenses,
       AVG(fb.total_value::numeric) as avg_bill_value
FROM freeagent_bills fb
JOIN freeagent_bank_transaction_explanations fbte ON fbte.bill_id = fb.bill_id  
JOIN freeagent_categories fc ON fc.category_id = fbte.category_id
WHERE fb.dated_on >= '2024-01-01' AND fb.status = 'Paid'
GROUP BY fc.category_id, fc.description, fc.nominal_code
ORDER BY total_expenses DESC;
```

### **Feature Flag Benefits**
- **Graceful Degradation**: Jobs continue running even if specific FreeAgent features are unavailable
- **Incremental Rollout**: Enable features progressively as they become available on the account
- **Error Resilience**: 403/404 errors are handled gracefully without stopping the ETL pipeline
- **Audit Trail**: Clear logging of which features are enabled/disabled and why jobs skip certain data

### **Data Completeness**
All FreeAgent ETL jobs provide:
- **Feature-Flag Awareness**: Automatic detection and graceful handling of unavailable endpoints
- **Incremental Sync Support**: Configurable lookback periods for efficient processing
- **Full Historical Sync**: Ability to sync complete historical data when needed
- **Comprehensive Relationships**: Foreign key extraction and relationship mapping
- **Date Range Flexibility**: Support for custom date ranges and default periods
- **Error Recovery**: Robust error handling with detailed logging and retry mechanisms

## License

[Add your license here]

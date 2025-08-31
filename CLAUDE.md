# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Commands

### Development Setup
```bash
poetry install              # Install dependencies
poetry shell               # Activate virtual environment
```

### Database Operations
```bash
cp .env.example .env       # Copy environment template (edit with real credentials)
alembic upgrade head       # Run database migrations
alembic current            # Check migration status
alembic revision --autogenerate -m "description"  # Create new migration
```

### Running ETL Jobs
```bash
# Amazon jobs (require AMZ_* environment variables)
poetry run python -m src.jobs.amazon_orders
poetry run python -m src.jobs.amazon_settlements  
poetry run python -m src.jobs.amazon_inventory

# Shopify jobs (require SHOPIFY_* environment variables)
poetry run python -m src.jobs.shopify_orders
poetry run python -m src.jobs.shopify_customers
poetry run python -m src.jobs.shopify_products

# ShipBob jobs (require SHIPBOB_* environment variables)
poetry run python -m src.jobs.shipbob_inventory
poetry run python -m src.jobs.shipbob_status
poetry run python -m src.jobs.shipbob_returns
poetry run python -m src.jobs.shipbob_receiving
poetry run python -m src.jobs.shipbob_products
poetry run python -m src.jobs.shipbob_fulfillment_centers

# FreeAgent jobs (require FREEAGENT_ACCESS_TOKEN environment variable)
poetry run python -m src.jobs.freeagent_contacts
poetry run python -m src.jobs.freeagent_invoices
poetry run python -m src.jobs.freeagent_bills
poetry run python -m src.jobs.freeagent_categories
poetry run python -m src.jobs.freeagent_bank_accounts
poetry run python -m src.jobs.freeagent_bank_transactions
poetry run python -m src.jobs.freeagent_bank_transaction_explanations
poetry run python -m src.jobs.freeagent_transactions
poetry run python -m src.jobs.freeagent_users
```

### Testing
```bash
poetry run pytest                    # Run all tests
poetry run pytest tests/test_amazon_orders.py  # Run specific test file
poetry run pytest -k test_name      # Run specific test
poetry run pytest -v                # Verbose output
```

### Code Quality
```bash
poetry run black .                  # Format code
poetry run flake8 .                 # Lint code
poetry run mypy src/                 # Type checking
```

## Architecture Overview

### Core Concept
Stratus is a data warehouse that ingests data from multiple external APIs (Amazon SP-API, Shopify, ShipBob, FreeAgent) into a normalized PostgreSQL schema. It's designed to start as read-only ETL but can evolve into a full ERP with write operations.

### Key Architectural Patterns

**Data Flow**: External API → Adapter (normalization) → Job (ETL orchestration) → Upsert (idempotent database operations)

**Adapters** (`src/adapters/`): API client wrappers that handle authentication, rate limiting, pagination, and data normalization. Each adapter exposes clean Python interfaces and converts external API responses to normalized dictionaries.

**Jobs** (`src/jobs/`): ETL orchestration scripts that combine adapters with database operations. Each job can be run independently via CLI (`python -m src.jobs.{job_name}`) and handles logging, error handling, and statistics reporting.

**Database Layer** (`src/db/`):
- `models.py`: SQLAlchemy models with proper relationships and indexes
- `upserts.py`: Generic upsert functions using PostgreSQL's ON CONFLICT for idempotent operations
- `config.py` & `deps.py`: Database configuration and session management

### Critical Implementation Details

**Idempotent Operations**: All database operations use PostgreSQL's `ON CONFLICT DO UPDATE` to ensure jobs can be safely re-run without duplicating data. The `_exec_upsert()` function returns precise counts of inserted vs updated records.

**Rate Limiting**: Amazon and Shopify adapters implement sophisticated rate limiting:
- Amazon: Uses 429 status codes and retry-after headers
- Shopify: Uses `X-Shopify-Shop-Api-Call-Limit` headers with progressive delays

**Pagination**: Adapters handle different pagination patterns:
- Amazon: `NextToken` parameter
- Shopify: RFC 5988 Link headers with `next` relationships

**Data Normalization**: External API responses are converted to consistent formats:
- All IDs stored as strings for consistency
- Monetary values converted to `Decimal` objects
- Timestamps normalized to UTC `datetime` objects
- Complex data (like Shopify tags) serialized to JSON when needed

### Environment Configuration

The system expects comprehensive environment configuration in `.env`:
- Database: `DATABASE_URL` (Supabase connection string)
- Amazon: `AMZ_ACCESS_TOKEN`, `AMZ_REFRESH_TOKEN`, `AMZ_CLIENT_ID`, `AMZ_CLIENT_SECRET`, `AMZ_MARKETPLACE_IDS`
- Shopify: `SHOPIFY_SHOP`, `SHOPIFY_ACCESS_TOKEN`
- ShipBob: `SHIPBOB_TOKEN`, `SHIPBOB_BASE`
- FreeAgent: `FREEAGENT_ACCESS_TOKEN` (OAuth 2.0 bearer token)
- Optional: Various `_LOOKBACK_HOURS` and `_LOOKBACK_DAYS` parameters for incremental syncing

### Testing Strategy

Tests extensively use mocking to simulate API responses. Key patterns:
- `@patch('src.adapters.{service}.requests.Session')` for HTTP mocking
- Realistic mock data that matches actual API response structures  
- Comprehensive validation of data normalization logic
- Database operation testing with return value verification

### Database Schema

The normalized schema supports multiple data sources with proper foreign key relationships:
- `orders` ↔ `order_items` (one-to-many) with tracking fields for fulfillment services
- `inventory` uses composite primary key (sku, source) to support multiple fulfillment centers
- `shopify_products` ↔ `shopify_variants` (one-to-many)
- Each table has `source` column to identify origin system (`amazon`, `shopify`, `shipbob`)
- Proper indexing on frequently queried columns (dates, source, status)
- ShipBob extends inventory with additional quantity fields (fulfillable, backordered, exception)

### ShipBob Extended Integration

The ShipBob integration includes comprehensive functionality beyond basic inventory and order tracking:

**Data Models**:
- `ShipBobReturn` - Return orders with cost tracking and fulfillment center data
- `ShipBobReceivingOrder` - Warehouse receiving orders (WROs) for inbound logistics
- `ShipBobProduct` / `ShipBobVariant` - Product catalog with variants and attributes
- `ShipBobFulfillmentCenter` - Warehouse locations and contact information

**Analytics Capabilities**:
- Return rate analysis by product category and fulfillment center
- Inbound logistics tracking with expected vs received quantity variance
- Geographic performance analysis across fulfillment centers
- Cost attribution for returns and fulfillment operations
- Product catalog management with dimensions, weight, and value tracking

**Key Features**:
- JSON storage for complex data structures (return items, inventory quantities, product attributes)
- Cross-platform linking (returns to Shopify orders via reference_id)
- Comprehensive cost tracking at transaction level
- Geographic analysis with timezone and location data

### Extension Points

Future development should follow established patterns:
- New integrations: Create adapter in `src/adapters/`, corresponding job in `src/jobs/`, models in `src/db/models.py`, upsert functions in `src/db/upserts.py`
- Write operations: Implement in `src/writers/` (currently empty)
- Complex workflows: Implement in `src/flows/` combining multiple jobs and writers

The ShipBob integration demonstrates the modular architecture with 6 independent ETL jobs that can be run separately or combined for comprehensive fulfillment analytics.

### FreeAgent Integration (Phase FA-1)

The FreeAgent integration provides comprehensive accounting data ingestion with robust error handling and feature flags.

**Key Features**:
- **Feature Flag System**: YAML-based configuration (`config/freeagent.yaml`) for enabling/disabling endpoints
- **Graceful Degradation**: 403/404 errors handled gracefully without stopping ETL pipeline  
- **OAuth Authentication**: Bearer token authentication with automatic header management
- **API Versioning Support**: `X-Api-Version` header support for FreeAgent's versioning system
- **Flexible Date Ranges**: Support for incremental sync (default 30 days) and full historical sync
- **Rate Limiting**: Built-in rate limiting (0.5s default) with exponential backoff retry logic

**Data Models (9 Phase FA-1 entities)**:
- `FreeAgentContact` - Customer and supplier relationship management
- `FreeAgentInvoice` - Sales invoices and accounts receivable  
- `FreeAgentBill` - Purchase invoices and accounts payable
- `FreeAgentCategory` - Chart of accounts with nominal codes and hierarchies
- `FreeAgentBankAccount` - Bank account configuration and balances
- `FreeAgentBankTransaction` - Individual bank transactions for cash flow
- `FreeAgentBankTransactionExplanation` - Transaction categorization and explanations
- `FreeAgentTransaction` - Double-entry bookkeeping (general ledger)
- `FreeAgentUser` - Team members and access permissions

**ETL Job Types**:
- **Date-based sync**: Contacts, invoices, bills, bank transactions, explanations, transactions (support `--from-date`, `--to-date`, `--full-sync`)
- **Simple sync**: Categories, bank accounts, users (full refresh only)

**Error Handling Strategy**:
- Feature unavailable (403/404): Log warning, return empty results with error flag
- Authentication (401): Raise `FreeAgentAuthError` to stop execution
- Rate limiting (429): Raise `FreeAgentRateLimitError` for retry handling
- Network issues: Automatic retry with exponential backoff
- Data validation: Skip invalid records, continue processing

**Analytics Capabilities**:
- Revenue analysis by month and customer type
- Accounts receivable aging reports  
- Cash flow analysis by bank account
- Expense categorization and P&L analysis
- Balance sheet data preparation
- Foreign currency transaction support

**Testing Coverage**:
- Unit tests for FreeAgent client (auth, pagination, error handling)
- ETL transformation tests (data mapping, date parsing, ID extraction)  
- Integration tests for complete workflows
- Feature flag and graceful degradation testing
- Mock testing for API responses and error scenarios

**Configuration Pattern**:
```yaml
features:
  contacts: true
  invoices: true
  # ... other features
  
api:
  rate_limit_delay: 0.5
  api_version: "2024-10-01"
  
sync:
  default_lookback_days: 30
  batch_size: 100
```

The FreeAgent integration demonstrates advanced error resilience patterns that can be applied to other integrations requiring feature flag support and graceful handling of unavailable endpoints.
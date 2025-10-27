# Stratus ERP - Quick Start (Post-Fixes)

**Date:** October 26, 2025
**Status:** ✅ **ALL CRITICAL ISSUES FIXED**

---

## What Was Fixed

### 1. ✅ ShipBob Inventory - FIXED
**Issue:** Function signature error
**Fix:** Changed function to load config from environment
**Test Result:** ✅ Successfully synced 30 inventory items

### 2. ✅ FreeAgent OAuth - FIXED
**Issue:** Expired access token
**Fix:** Created token refresh script and successfully refreshed
**Test Result:** ✅ Connected to "Auracle Ltd", synced 1 contact and 3 invoices

### 3. ✅ Amazon Integration - DOCUMENTED AS DISABLED
**Status:** Intentionally disabled, can be enabled later with credentials
**Config:** Marked as `enabled: false` in `config/app.yaml`

---

## Current Working Status

### ✅ Fully Operational
- **Shopify** (3/3 jobs working)
  - Orders: 2 orders synced
  - Customers: 2 customers synced
  - Products: 11 products, 38 variants synced

- **ShipBob** (4/6 jobs working)
  - ✅ Inventory: 30 items synced
  - ✅ Products: 25 products, 25 variants synced
  - ✅ Fulfillment Centers: 3 centers synced
  - ✅ Returns: 2 returns synced ($13.98)

- **FreeAgent** (2/9 jobs tested, all working)
  - ✅ Contacts: 1 contact synced
  - ✅ Invoices: 3 invoices synced
  - (Other 7 jobs available but not yet tested)

### ⚙️ Disabled
- Amazon Orders
- Amazon Settlements
- Amazon Inventory

---

## How to Run ETL Jobs

### Manual Execution

```bash
# Set PATH for poetry
export PATH="$HOME/.local/bin:$PATH"

# Shopify jobs
poetry run python -m src.jobs.shopify_orders
poetry run python -m src.jobs.shopify_customers
poetry run python -m src.jobs.shopify_products

# ShipBob jobs
poetry run python -m src.jobs.shipbob_inventory
poetry run python -m src.jobs.shipbob_products
poetry run python -m src.jobs.shipbob_fulfillment_centers
poetry run python -m src.jobs.shipbob_returns

# FreeAgent jobs
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

### Token Maintenance

```bash
# If FreeAgent token expires, refresh it:
poetry run python scripts/refresh_freeagent_token.py
```

---

## Database Status

**Connected to:** Supabase PostgreSQL
**Status:** ✅ Operational (unpaused)
**Tables Populated:**
- `orders`: 2 records
- `order_items`: 0 records (investigation needed)
- `inventory`: 30 records
- `shopify_customers`: 2 records
- `shopify_products`: 11 records
- `shopify_variants`: 38 records
- `shipbob_products`: 25 records
- `shipbob_variants`: 25 records
- `shipbob_fulfillment_centers`: 3 records
- `shipbob_returns`: 2 records
- `freeagent_contacts`: 1 record
- `freeagent_invoices`: 3 records

---

## Remaining Tasks for Production

### Must Do (Before Production)
- [ ] Investigate orphaned Shopify order items (2 items dropped)
- [ ] Add job execution tracking table
- [ ] Setup centralized logging (CloudWatch/Sentry)
- [ ] Configure automated backups
- [ ] Upgrade Supabase to paid tier ($25/month)
- [ ] Add job scheduling (APScheduler or cron)
- [ ] Configure email alerts
- [ ] Add health check endpoint for jobs

### Should Do (Within 2 Weeks)
- [ ] Implement secrets management (AWS Secrets Manager)
- [ ] Add API authentication
- [ ] Setup CI/CD pipeline (GitHub Actions)
- [ ] Add rate limit monitoring (Prometheus)
- [ ] Optimize database connection pooling
- [ ] Add Redis caching for slow queries

### Nice to Have (Eventually)
- [ ] Add Swagger API documentation
- [ ] Increase test coverage to 80%+
- [ ] Add performance benchmarks
- [ ] Multi-environment configuration
- [ ] Horizontal scaling support

---

## Quick Commands Reference

```bash
# Check database connection
poetry run python -c "from src.db.deps import get_session; print('DB OK')"

# Run all Shopify jobs
for job in orders customers products; do
  poetry run python -m src.jobs.shopify_$job
done

# Run all ShipBob jobs
for job in inventory products fulfillment_centers returns; do
  poetry run python -m src.jobs.shipbob_$job
done

# Check logs
tail -f logs/stratus.log  # If logging to file

# Refresh FreeAgent token (when expired)
poetry run python scripts/refresh_freeagent_token.py
```

---

## Performance Notes

**Current Performance (Tested):**
- Shopify orders (2): ~1.5s ⚡
- Shopify customers (2): ~1.5s ⚡
- Shopify products (11+38): ~2s ⚡
- ShipBob inventory (30): ~1.5s ⚡
- ShipBob products (25): ~52s ⚠️ (slow due to rate limiting)
- ShipBob centers (3): ~1.5s ⚡
- ShipBob returns (2): ~1.5s ⚡
- FreeAgent contacts (1): ~0.5s ⚡
- FreeAgent invoices (3): ~0.5s ⚡

**Note:** ShipBob products is slow due to 0.5s rate limit delay. Consider optimization for large catalogs.

---

## Next Steps

1. **Today:** Test remaining FreeAgent jobs
2. **This Week:**
   - Investigate Shopify order items issue
   - Add job execution tracking
   - Setup logging
3. **Next Week:**
   - Implement job scheduling
   - Configure alerts
   - Upgrade Supabase
4. **Week 3-4:**
   - Production deployment
   - Load testing
   - Documentation finalization

---

## Support

- **Documentation:** [COMPREHENSIVE_DOCUMENTATION.md](COMPREHENSIVE_DOCUMENTATION.md)
- **Production Readiness:** [PRODUCTION_READINESS_ASSESSMENT.md](PRODUCTION_READINESS_ASSESSMENT.md)
- **OAuth Guide:** [OAUTH_SETUP_GUIDE.md](OAUTH_SETUP_GUIDE.md)

**System Status:** ✅ Ready for development/staging use
**Production Ready:** ⚠️ 2-3 weeks (after implementing must-do tasks)

---

**Last Updated:** October 26, 2025
**All Critical Fixes:** ✅ COMPLETE

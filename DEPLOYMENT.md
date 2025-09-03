# Stratus ERP - VPS Deployment Guide

## Production Setup on VPS/Server

### 1. System Prerequisites

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3 python3-pip python3-venv git postgresql-client

# CentOS/RHEL
sudo yum install python3 python3-pip git postgresql
```

### 2. User and Directory Setup

```bash
# Create dedicated user
sudo useradd -m -s /bin/bash stratus
sudo su - stratus

# Clone repository
git clone <your-repo-url> /opt/stratus
cd /opt/stratus

# Set up Python virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Environment Configuration

```bash
# Copy and configure environment
cp .env.example .env
nano .env

# Add your API credentials:
# DATABASE_URL=postgresql://user:pass@host:5432/dbname
# SHOPIFY_SHOP=your-shop
# SHOPIFY_ACCESS_TOKEN=your-token
# SHIPBOB_TOKEN=your-token
# FREEAGENT_ACCESS_TOKEN=your-token
```

### 4. Database Setup

```bash
# Run migrations
source .venv/bin/activate
alembic upgrade head

# Test database connection
python -c "from src.db.config import SessionLocal; print('✅ Database connected')"
```

### 5. Scheduling Options

#### Option A: Cron (Simple)

```bash
# Copy and customize cron configuration
cp crontab.example crontab.production

# Edit paths to match your deployment
sed -i 's|/path/to/stratus|/opt/stratus|g' crontab.production

# Install crontab
crontab crontab.production

# Verify
crontab -l
```

#### Option B: Systemd (Recommended)

```bash
# Copy systemd files
sudo cp systemd/*.service /etc/systemd/system/
sudo cp systemd/*.timer /etc/systemd/system/

# Edit service files to match your paths
sudo sed -i 's|/opt/stratus|/opt/stratus|g' /etc/systemd/system/stratus-etl-*.service

# Enable and start timers
sudo systemctl daemon-reload
sudo systemctl enable stratus-etl-daily.timer
sudo systemctl enable stratus-etl-hourly.timer
sudo systemctl start stratus-etl-daily.timer
sudo systemctl start stratus-etl-hourly.timer

# Check status
sudo systemctl list-timers stratus-etl-*
```

### 6. Manual Testing

```bash
# Test individual platforms
python run_etl.py --shopify
python run_etl.py --shipbob  
python run_etl.py --freeagent

# Test full pipeline
python run_etl.py --all

# Test scheduler
python schedule_etl.py --daily

# Generate business report
python generate_business_report.py
```

### 7. Monitoring and Logs

```bash
# Check logs
tail -f logs/etl.log
tail -f logs/scheduler.log
tail -f logs/cron.log        # For cron
journalctl -f -u stratus-etl-* # For systemd

# Log rotation (add to cron)
0 0 * * 0 find /opt/stratus/logs -name "*.log" -mtime +30 -delete
```

### 8. Security Hardening

```bash
# File permissions
chmod 600 .env
chmod 700 logs/
chmod 755 run_etl.py schedule_etl.py

# Firewall (if needed)
sudo ufw allow from YOUR_MONITORING_IP to any port 22
sudo ufw enable
```

### 9. Backup Strategy

```bash
# Database backup (daily recommended)
pg_dump $DATABASE_URL > backups/stratus_$(date +%Y%m%d).sql

# Config backup
tar -czf backups/stratus_config_$(date +%Y%m%d).tar.gz .env config/
```

## Production Monitoring

### Health Checks

Create `/opt/stratus/health_check.py`:

```python
#!/usr/bin/env python3
import sys
from src.db.config import SessionLocal
from sqlalchemy import text

def check_database():
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
        return True
    except:
        return False

def main():
    if check_database():
        print("✅ Database: OK")
        sys.exit(0)
    else:
        print("❌ Database: FAILED")
        sys.exit(1)

if __name__ == "__main__":
    main()
```

### Alerting (Optional)

Add email alerts to scheduler failures:

```bash
# Install mail utils
sudo apt install mailutils

# Add to cron for error notification
0 2 * * * cd /opt/stratus && python schedule_etl.py --daily || echo "Stratus ETL failed" | mail -s "ETL Alert" admin@yourdomain.com
```

## Common Issues

### Database Connection
- Check `DATABASE_URL` format
- Verify network connectivity to database
- Ensure user has proper permissions

### API Rate Limits
- Monitor logs for rate limit errors
- Adjust scheduling frequency if needed
- Check API key validity

### Disk Space
- Monitor `logs/` directory size
- Implement log rotation
- Check `/tmp` space for large data imports

### Memory Usage
- Monitor during large imports
- Consider splitting large jobs
- Add swap if needed for memory-intensive operations

## Performance Tuning

### Database
- Add indexes for frequently queried columns
- Monitor query performance
- Consider connection pooling for high frequency

### API Efficiency
- Use incremental syncs where possible
- Implement caching for reference data
- Monitor API call patterns

### Resource Management
- Monitor CPU and memory usage
- Adjust job concurrency
- Consider running jobs during off-peak hours
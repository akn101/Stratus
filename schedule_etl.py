#!/usr/bin/env python3
"""
Stratus ERP ETL Scheduler

Production scheduler for automated ETL runs on VPS/server.
Designed to be called by cron or systemd timer.

Usage:
    python schedule_etl.py --daily      # Daily full sync (recommended for cron)
    python schedule_etl.py --hourly     # Hourly incremental sync
    python schedule_etl.py --weekly     # Weekly comprehensive sync
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/scheduler.log', mode='a')
    ]
)

logger = logging.getLogger(__name__)


def run_etl_command(command_args: str) -> bool:
    """Run ETL command and return success status."""
    try:
        logger.info(f"Executing: python run_etl.py {command_args}")
        
        # Run the ETL command
        import subprocess
        result = subprocess.run(
            [sys.executable, "run_etl.py"] + command_args.split(),
            capture_output=True,
            text=True,
            timeout=3600  # 1 hour timeout
        )
        
        if result.returncode == 0:
            logger.info(f"✅ ETL command completed successfully")
            if result.stdout:
                logger.info(f"Output: {result.stdout}")
            return True
        else:
            logger.error(f"❌ ETL command failed with return code {result.returncode}")
            if result.stderr:
                logger.error(f"Error: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("❌ ETL command timed out after 1 hour")
        return False
    except Exception as e:
        logger.error(f"❌ Failed to execute ETL command: {e}")
        return False


def daily_sync():
    """Daily ETL sync - comprehensive but efficient."""
    logger.info("🌅 Starting daily ETL sync")
    
    success_count = 0
    total_count = 3
    
    # Run platform syncs in order of priority
    platforms = ['shopify', 'freeagent', 'shipbob']
    
    for platform in platforms:
        if run_etl_command(f"--{platform}"):
            success_count += 1
        else:
            logger.warning(f"Platform {platform} sync failed, continuing with others")
    
    logger.info(f"🌅 Daily sync completed: {success_count}/{total_count} platforms successful")
    return success_count == total_count


def hourly_sync():
    """Hourly ETL sync - critical data only."""
    logger.info("⏰ Starting hourly ETL sync")
    
    # Only sync the most critical, frequently changing data
    critical_jobs = [
        'shopify_orders',
        'shipbob_orders', 
        'shipbob_inventory'
    ]
    
    success_count = 0
    
    for job in critical_jobs:
        if run_etl_command(f"--job {job}"):
            success_count += 1
        else:
            logger.warning(f"Critical job {job} failed")
    
    logger.info(f"⏰ Hourly sync completed: {success_count}/{len(critical_jobs)} jobs successful")
    return success_count == len(critical_jobs)


def weekly_sync():
    """Weekly comprehensive ETL sync - full data refresh."""
    logger.info("📅 Starting weekly comprehensive ETL sync")
    
    # Run full pipeline
    success = run_etl_command("--all")
    
    if success:
        logger.info("📅 Weekly comprehensive sync completed successfully")
        
        # Generate business report
        try:
            import subprocess
            logger.info("📊 Generating weekly business intelligence report")
            result = subprocess.run([sys.executable, "generate_business_report.py"], 
                                  capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                logger.info("📊 Business report generated successfully")
                
                # Save report with timestamp
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                report_file = f"reports/business_report_{timestamp}.txt"
                os.makedirs("reports", exist_ok=True)
                
                with open(report_file, 'w') as f:
                    f.write(f"Stratus ERP Business Report - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write("=" * 80 + "\n\n")
                    f.write(result.stdout)
                
                logger.info(f"📄 Report saved to {report_file}")
            else:
                logger.warning("📊 Business report generation failed")
                
        except Exception as e:
            logger.warning(f"📊 Failed to generate business report: {e}")
    else:
        logger.error("📅 Weekly comprehensive sync failed")
    
    return success


def main():
    """CLI entry point for ETL scheduler."""
    parser = argparse.ArgumentParser(description="Stratus ERP ETL Scheduler")
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--daily', action='store_true', help='Run daily ETL sync')
    group.add_argument('--hourly', action='store_true', help='Run hourly ETL sync')
    group.add_argument('--weekly', action='store_true', help='Run weekly comprehensive sync')
    
    parser.add_argument('--log-level', default='INFO', help='Logging level')
    
    args = parser.parse_args()
    
    # Set logging level
    logging.getLogger().setLevel(getattr(logging, args.log_level.upper()))
    
    # Create necessary directories
    os.makedirs('logs', exist_ok=True)
    os.makedirs('reports', exist_ok=True)
    
    # Record start time
    start_time = datetime.now()
    logger.info(f"🚀 Stratus ETL Scheduler started at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        if args.daily:
            success = daily_sync()
        elif args.hourly:
            success = hourly_sync()
        elif args.weekly:
            success = weekly_sync()
        
        duration = (datetime.now() - start_time).total_seconds()
        
        if success:
            logger.info(f"🎯 Scheduler completed successfully in {duration:.1f} seconds")
            sys.exit(0)
        else:
            logger.error(f"💥 Scheduler completed with failures in {duration:.1f} seconds")
            sys.exit(1)
            
    except Exception as e:
        duration = (datetime.now() - start_time).total_seconds()
        logger.error(f"💥 Scheduler failed after {duration:.1f} seconds: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
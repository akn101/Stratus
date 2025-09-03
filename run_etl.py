#!/usr/bin/env python3
"""
Stratus ERP ETL Runner

Production-ready ETL orchestration for all platform integrations.
Designed for VPS/server deployment with proper logging and error handling.

Usage:
    python run_etl.py --all                    # Run all ETL jobs
    python run_etl.py --shopify               # Run only Shopify jobs
    python run_etl.py --shipbob               # Run only ShipBob jobs
    python run_etl.py --freeagent            # Run only FreeAgent jobs
    python run_etl.py --job shopify_orders   # Run specific job
"""

import argparse
import logging
import sys
from datetime import datetime
from typing import Dict, List, Optional

# Configure logging for production
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/etl.log', mode='a')
    ]
)

logger = logging.getLogger(__name__)


class ETLJob:
    """Represents a single ETL job."""
    
    def __init__(self, name: str, module_path: str, description: str, platform: str):
        self.name = name
        self.module_path = module_path
        self.description = description
        self.platform = platform


class ETLRunner:
    """Production ETL job runner with proper error handling and reporting."""
    
    def __init__(self):
        self.jobs = {
            # Shopify jobs
            'shopify_orders': ETLJob(
                'shopify_orders', 
                'src.jobs.shopify_orders', 
                'Import Shopify orders and customers',
                'shopify'
            ),
            'shopify_customers': ETLJob(
                'shopify_customers',
                'src.jobs.shopify_customers',
                'Import Shopify customer data',
                'shopify'
            ),
            'shopify_products': ETLJob(
                'shopify_products',
                'src.jobs.shopify_products',
                'Import Shopify products and variants',
                'shopify'
            ),
            
            # ShipBob jobs
            'shipbob_orders': ETLJob(
                'shipbob_orders',
                'src.jobs.shipbob_status',
                'Import ShipBob order status updates',
                'shipbob'
            ),
            'shipbob_inventory': ETLJob(
                'shipbob_inventory',
                'src.jobs.shipbob_inventory',
                'Import ShipBob inventory levels',
                'shipbob'
            ),
            'shipbob_returns': ETLJob(
                'shipbob_returns',
                'src.jobs.shipbob_returns',
                'Import ShipBob returns data',
                'shipbob'
            ),
            'shipbob_products': ETLJob(
                'shipbob_products',
                'src.jobs.shipbob_products',
                'Import ShipBob product catalog',
                'shipbob'
            ),
            
            # FreeAgent jobs
            'freeagent_contacts': ETLJob(
                'freeagent_contacts',
                'src.jobs.freeagent_contacts',
                'Import FreeAgent contacts',
                'freeagent'
            ),
            'freeagent_invoices': ETLJob(
                'freeagent_invoices',
                'src.jobs.freeagent_invoices',
                'Import FreeAgent invoices',
                'freeagent'
            ),
            'freeagent_transactions': ETLJob(
                'freeagent_transactions',
                'src.jobs.freeagent_transactions',
                'Import FreeAgent accounting transactions',
                'freeagent'
            ),
            'freeagent_bank_accounts': ETLJob(
                'freeagent_bank_accounts',
                'src.jobs.freeagent_bank_accounts',
                'Import FreeAgent bank accounts',
                'freeagent'
            ),
            'freeagent_users': ETLJob(
                'freeagent_users',
                'src.jobs.freeagent_users',
                'Import FreeAgent users',
                'freeagent'
            ),
        }
        
        self.platform_jobs = {
            'shopify': ['shopify_orders', 'shopify_customers', 'shopify_products'],
            'shipbob': ['shipbob_orders', 'shipbob_inventory', 'shipbob_returns', 'shipbob_products'],
            'freeagent': ['freeagent_contacts', 'freeagent_invoices', 'freeagent_transactions', 
                         'freeagent_bank_accounts', 'freeagent_users'],
        }

    def run_job(self, job_name: str) -> Dict:
        """Run a single ETL job."""
        if job_name not in self.jobs:
            raise ValueError(f"Unknown job: {job_name}")
            
        job = self.jobs[job_name]
        logger.info(f"Starting ETL job: {job.name} - {job.description}")
        
        start_time = datetime.now()
        try:
            # Dynamically import and run the job
            import importlib
            module = importlib.import_module(job.module_path)
            
            # For jobs with run_* functions, call directly with minimal args
            function_names = [
                f'run_{job_name}_etl',
                f'run_{job_name}_sync',
                f'run_{job_name.replace("_", "_")}_etl',
                f'run_{job_name.replace("_", "_")}_sync'
            ]
            
            run_func = None
            for func_name in function_names:
                if hasattr(module, func_name):
                    run_func = getattr(module, func_name)
                    break
                    
            if run_func:
                
                # Try to call with appropriate arguments based on job type
                if 'freeagent' in job_name:
                    from src.utils.config import get_secret
                    access_token = get_secret("FREEAGENT_ACCESS_TOKEN")
                    if access_token:
                        result = run_func(access_token=access_token)
                    else:
                        raise Exception("FREEAGENT_ACCESS_TOKEN not found")
                elif 'shopify' in job_name:
                    from src.utils.config import get_secret
                    shopify_config = get_secret("SHOPIFY")
                    if shopify_config:
                        result = run_func(
                            shop=shopify_config.get("shop"),
                            access_token=shopify_config.get("access_token")
                        )
                    else:
                        raise Exception("SHOPIFY config not found")
                elif 'shipbob' in job_name:
                    from src.utils.config import get_secret
                    shipbob_config = get_secret("SHIPBOB")
                    if shipbob_config and shipbob_config.get("token"):
                        result = run_func(token=shipbob_config.get("token"))
                    else:
                        raise Exception("SHIPBOB config not found")
                else:
                    result = run_func()
            elif hasattr(module, 'main'):
                # Override sys.argv to prevent argument parsing conflicts
                import sys
                original_argv = sys.argv.copy()
                sys.argv = [sys.argv[0]]  # Only keep script name
                try:
                    result = module.main()
                finally:
                    sys.argv = original_argv
            else:
                raise AttributeError(f"Job {job_name} has no main() or run function")
                
            duration = (datetime.now() - start_time).total_seconds()
            
            logger.info(f"✅ Job {job.name} completed successfully in {duration:.1f}s")
            
            return {
                'job': job_name,
                'status': 'success',
                'duration': duration,
                'result': result if isinstance(result, dict) else {'exit_code': result}
            }
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"❌ Job {job.name} failed after {duration:.1f}s: {str(e)}")
            
            return {
                'job': job_name,
                'status': 'failed',
                'duration': duration,
                'error': str(e)
            }

    def run_platform(self, platform: str) -> Dict:
        """Run all jobs for a specific platform."""
        if platform not in self.platform_jobs:
            raise ValueError(f"Unknown platform: {platform}")
            
        logger.info(f"🚀 Starting {platform.upper()} ETL pipeline")
        start_time = datetime.now()
        
        results = []
        job_names = self.platform_jobs[platform]
        
        for job_name in job_names:
            result = self.run_job(job_name)
            results.append(result)
            
            # Continue with other jobs even if one fails
            if result['status'] == 'failed':
                logger.warning(f"Continuing with remaining {platform} jobs despite failure")
        
        duration = (datetime.now() - start_time).total_seconds()
        successful = sum(1 for r in results if r['status'] == 'success')
        failed = len(results) - successful
        
        logger.info(f"🏁 {platform.upper()} pipeline completed: {successful} successful, {failed} failed in {duration:.1f}s")
        
        return {
            'platform': platform,
            'duration': duration,
            'jobs': results,
            'summary': {'successful': successful, 'failed': failed, 'total': len(results)}
        }

    def run_all(self) -> Dict:
        """Run all ETL jobs across all platforms."""
        logger.info("🌟 Starting FULL ETL pipeline across all platforms")
        start_time = datetime.now()
        
        platform_results = []
        for platform in ['shopify', 'shipbob', 'freeagent']:
            result = self.run_platform(platform)
            platform_results.append(result)
        
        duration = (datetime.now() - start_time).total_seconds()
        
        # Calculate totals
        total_successful = sum(r['summary']['successful'] for r in platform_results)
        total_failed = sum(r['summary']['failed'] for r in platform_results)
        total_jobs = sum(r['summary']['total'] for r in platform_results)
        
        logger.info(f"🎯 FULL ETL pipeline completed: {total_successful}/{total_jobs} successful in {duration:.1f}s")
        
        return {
            'type': 'full_pipeline',
            'duration': duration,
            'platforms': platform_results,
            'summary': {
                'successful': total_successful,
                'failed': total_failed,
                'total': total_jobs
            }
        }


def main():
    """CLI entry point for ETL runner."""
    parser = argparse.ArgumentParser(description="Stratus ERP ETL Runner")
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--all', action='store_true', help='Run all ETL jobs')
    group.add_argument('--shopify', action='store_true', help='Run Shopify jobs only')
    group.add_argument('--shipbob', action='store_true', help='Run ShipBob jobs only')
    group.add_argument('--freeagent', action='store_true', help='Run FreeAgent jobs only')
    group.add_argument('--job', help='Run specific job by name')
    
    parser.add_argument('--log-level', default='INFO', help='Logging level')
    
    args = parser.parse_args()
    
    # Set logging level
    logging.getLogger().setLevel(getattr(logging, args.log_level.upper()))
    
    # Create logs directory if it doesn't exist
    import os
    os.makedirs('logs', exist_ok=True)
    
    runner = ETLRunner()
    
    try:
        if args.all:
            result = runner.run_all()
        elif args.shopify:
            result = runner.run_platform('shopify')
        elif args.shipbob:
            result = runner.run_platform('shipbob')
        elif args.freeagent:
            result = runner.run_platform('freeagent')
        elif args.job:
            result = runner.run_job(args.job)
        
        # Print summary
        if 'summary' in result:
            summary = result['summary']
            print(f"\n📊 SUMMARY: {summary['successful']}/{summary['total']} jobs successful")
            if summary['failed'] > 0:
                print(f"⚠️  {summary['failed']} jobs failed - check logs for details")
                sys.exit(1)
        
        print("✅ ETL run completed successfully")
        
    except Exception as e:
        logger.error(f"💥 ETL run failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
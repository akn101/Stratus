
#!/usr/bin/env python3
"""
Stratus ERP Integration Service

Production-ready ETL scheduler with comprehensive job orchestration,
observability, and graceful shutdown handling.
"""

import logging
import signal
import sys
import argparse
import importlib
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Callable
import json

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, JobExecutionEvent

from src.config.loader import (
    cfg, validate_config, is_integration_enabled, is_job_enabled,
    get_job_schedule, get_job_config, load_config
)
from src.server import start_observability_server, set_scheduler_running
from src.server import record_job_start, record_job_success, record_job_error
from src.db.sync_state import mark_sync_running, mark_sync_success, mark_sync_error
from src.utils.time_windows import utc_now, format_duration

# Configure structured logging
def setup_logging():
    """Setup structured logging based on configuration."""
    log_level = cfg("global.log_level", "INFO")
    log_format = cfg("global.log_format", "json")
    
    if log_format == "json":
        import structlog
        
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer()
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        
        logging.basicConfig(
            level=getattr(logging, log_level.upper()),
            format="%(message)s",
            handlers=[logging.StreamHandler(sys.stdout)]
        )
    else:
        logging.basicConfig(
            level=getattr(logging, log_level.upper()),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler(sys.stdout)]
        )

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler: Optional[BackgroundScheduler] = None
observability_thread = None


def create_job_runner(integration: str, job: str) -> Callable:
    """
    Create a job runner function for a specific integration and job.
    
    Args:
        integration: Integration name (e.g., "shopify", "freeagent")
        job: Job name (e.g., "orders", "contacts")
        
    Returns:
        Callable job runner function
    """
    domain = f"{integration}_{job}"
    
    def run_job():
        """Execute the ETL job with full observability."""
        start_time = record_job_start(domain)
        
        logger.info(f"Starting job {domain}")
        
        try:
            # Mark sync as running
            mark_sync_running(domain)
            
            # Dynamic import of job module
            module_name = f"src.jobs.{domain}"
            module = importlib.import_module(module_name)
            
            # Get the main ETL function
            etl_function_name = f"run_{domain}_etl"
            if not hasattr(module, etl_function_name):
                raise AttributeError(f"Function {etl_function_name} not found in {module_name}")
            
            etl_function = getattr(module, etl_function_name)
            
            # Get job configuration
            job_config = get_job_config(integration, job)
            
            # Prepare arguments based on integration
            kwargs = {}
            
            if integration == "shopify":
                from src.config.loader import get_shopify_config
                shopify_config = get_shopify_config()
                kwargs.update(shopify_config)
                
            elif integration == "shipbob":
                from src.config.loader import get_shipbob_config
                shipbob_config = get_shipbob_config()
                kwargs.update(shipbob_config)
                
            elif integration == "freeagent":
                from src.config.loader import get_freeagent_config
                freeagent_config = get_freeagent_config()
                kwargs["oauth_config"] = freeagent_config
            
            # Add lookback parameters if configured
            if "lookback_hours" in job_config:
                kwargs["lookback_hours"] = job_config["lookback_hours"]
            if "lookback_days" in job_config:
                kwargs["lookback_days"] = job_config["lookback_days"]
            
            # Execute the job
            logger.info(f"Executing {domain} with config: {job_config}")
            result = etl_function(**kwargs)
            
            # Record success metrics
            total_records = result.get("total", 0)
            record_job_success(domain, start_time, total_records)
            
            # Mark sync as successful
            sync_metadata = {
                "inserted": result.get("inserted", 0),
                "updated": result.get("updated", 0),
                "total": total_records,
                "duration_seconds": utc_now().timestamp() - start_time,
                "job_config": job_config
            }
            
            mark_sync_success(
                domain=domain,
                sync_metadata=sync_metadata
            )
            
            duration = utc_now() - datetime.fromtimestamp(start_time, timezone.utc)
            logger.info(
                f"Job {domain} completed successfully",
                extra={
                    "domain": domain,
                    "duration": format_duration(duration),
                    "records": total_records,
                    "result": result
                }
            )
            
        except Exception as e:
            # Record error metrics
            record_job_error(domain, start_time, str(e))
            
            # Mark sync as failed
            mark_sync_error(domain, str(e))
            
            duration = utc_now() - datetime.fromtimestamp(start_time, timezone.utc)
            logger.error(
                f"Job {domain} failed: {e}",
                extra={
                    "domain": domain,
                    "duration": format_duration(duration),
                    "error": str(e)
                },
                exc_info=True
            )
            
            # Don't re-raise - we want the scheduler to continue
    
    return run_job


def setup_job_scheduler() -> BackgroundScheduler:
    """Setup and configure the job scheduler."""
    timezone_str = cfg("global.timezone", "UTC")
    
    scheduler_config = {
        "timezone": timezone_str,
        "job_defaults": cfg("scheduler.job_defaults", {
            "coalesce": False,
            "max_instances": 1,
            "misfire_grace_time": 300
        })
    }
    
    scheduler = BackgroundScheduler(**scheduler_config)
    
    # Job execution event handlers
    def job_listener(event: JobExecutionEvent):
        """Handle job execution events."""
        if event.exception:
            logger.error(f"Job {event.job_id} failed: {event.exception}")
        else:
            logger.info(f"Job {event.job_id} completed successfully")
    
    scheduler.add_listener(job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
    
    return scheduler


def register_jobs(scheduler: BackgroundScheduler) -> int:
    """
    Register all enabled jobs with the scheduler.
    
    Args:
        scheduler: APScheduler instance
        
    Returns:
        Number of jobs registered
    """
    jobs_registered = 0
    
    integrations = ["shopify", "shipbob", "freeagent"]
    
    for integration in integrations:
        if not is_integration_enabled(integration):
            logger.info(f"{integration} integration disabled, skipping jobs")
            continue
        
        integration_config = cfg(f"integrations.{integration}", {})
        
        for job_name, job_config in integration_config.items():
            if job_name in ["enabled"]:  # Skip meta keys
                continue
            
            if not isinstance(job_config, dict) or not job_config.get("enabled", False):
                continue
            
            schedule = job_config.get("schedule")
            if not schedule:
                logger.warning(f"No schedule configured for {integration}.{job_name}")
                continue
            
            try:
                # Create job runner
                job_runner = create_job_runner(integration, job_name)
                
                # Parse cron schedule
                cron_trigger = CronTrigger.from_crontab(schedule, timezone=cfg("global.timezone", "UTC"))
                
                # Add job to scheduler
                job_id = f"{integration}_{job_name}"
                scheduler.add_job(
                    func=job_runner,
                    trigger=cron_trigger,
                    id=job_id,
                    name=f"{integration.title()} {job_name.title()} ETL",
                    replace_existing=True
                )
                
                jobs_registered += 1
                logger.info(f"Registered job: {job_id} with schedule: {schedule}")
                
            except Exception as e:
                logger.error(f"Failed to register job {integration}.{job_name}: {e}")
    
    return jobs_registered


def run_single_job(job_name: str) -> int:
    """
    Run a single job once and exit.
    
    Args:
        job_name: Job name in format "integration_job" (e.g., "shopify_orders")
        
    Returns:
        Exit code (0 for success, 1 for failure)
    """
    try:
        # Parse job name
        if "_" not in job_name:
            logger.error(f"Invalid job name format: {job_name}. Use 'integration_job' format.")
            return 1
        
        integration, job = job_name.split("_", 1)
        
        # Check if job is enabled
        if not is_job_enabled(integration, job):
            logger.error(f"Job {job_name} is not enabled in configuration")
            return 1
        
        # Create and run job
        job_runner = create_job_runner(integration, job)
        
        logger.info(f"Running single job: {job_name}")
        job_runner()
        
        logger.info(f"Single job {job_name} completed successfully")
        return 0
        
    except Exception as e:
        logger.error(f"Single job {job_name} failed: {e}", exc_info=True)
        return 1


def handle_shutdown(signum, frame):
    """Handle graceful shutdown signals."""
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    
    global scheduler, observability_thread
    
    if scheduler:
        logger.info("Shutting down scheduler...")
        set_scheduler_running(False)
        scheduler.shutdown(wait=True)
        logger.info("Scheduler shut down complete")
    
    logger.info("Graceful shutdown complete")
    sys.exit(0)


def main():
    """Main entrypoint for the ERP integration service."""
    global scheduler, observability_thread
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Stratus ERP Integration Service")
    parser.add_argument("--run", help="Run a single job once (format: integration_job)")
    parser.add_argument("--config", default="config/app.yaml", help="Configuration file path")
    parser.add_argument("--validate-config", action="store_true", help="Validate configuration and exit")
    
    args = parser.parse_args()
    
    # Setup logging first
    setup_logging()
    logger.info("Starting Stratus ERP Integration Service")
    
    try:
        # Load and validate configuration
        load_config(args.config)
        
        if args.validate_config:
            validate_config()
            logger.info("Configuration is valid")
            return 0
        
        validate_config()
        logger.info("Configuration validated successfully")
        
        # Handle single job execution
        if args.run:
            return run_single_job(args.run)
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, handle_shutdown)
        signal.signal(signal.SIGINT, handle_shutdown)
        
        # Start observability server
        observability_thread = start_observability_server()
        
        # Setup scheduler
        scheduler = setup_job_scheduler()
        
        # Register jobs
        jobs_count = register_jobs(scheduler)
        
        if jobs_count == 0:
            logger.warning("No jobs registered. Check your configuration.")
            return 1
        
        logger.info(f"Registered {jobs_count} jobs")
        
        # Start scheduler
        set_scheduler_running(True)
        scheduler.start()
        
        logger.info("Scheduler started successfully. Press Ctrl+C to stop.")
        
        # Keep main thread alive
        try:
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
            handle_shutdown(signal.SIGINT, None)
            
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit(main())
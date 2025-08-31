"""
Observability server for health checks and metrics.

Provides HTTP endpoints for monitoring the ETL service health,
metrics, and operational status.
"""

import json
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

try:
    from fastapi import FastAPI, HTTPException, Response
    from fastapi.responses import PlainTextResponse
except ImportError:
    # Fallback to basic HTTP server if FastAPI not available
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.parse import urlparse

    FastAPI = None

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from sqlalchemy import text

from src.config.loader import cfg
from src.db.deps import get_session
from src.db.sync_state import get_all_sync_states, is_sync_healthy

logger = logging.getLogger(__name__)

# Prometheus metrics
REGISTRY = CollectorRegistry()

# Job metrics
job_runs_total = Counter(
    "job_runs_total", "Total number of job runs", ["job", "status"], registry=REGISTRY
)

job_duration_seconds = Histogram(
    "job_duration_seconds", "Job execution duration in seconds", ["job"], registry=REGISTRY
)

records_upserted_total = Counter(
    "records_upserted_total",
    "Total number of records upserted",
    ["table", "operation"],
    registry=REGISTRY,
)

# System metrics
scheduler_running = Gauge(
    "scheduler_running", "Whether the scheduler is running", registry=REGISTRY
)

database_connection_healthy = Gauge(
    "database_connection_healthy", "Database connection health status", registry=REGISTRY
)

sync_health_status = Gauge(
    "sync_health_status", "Health status of sync domains", ["domain"], registry=REGISTRY
)

# Global state
_scheduler_running = False
_app_start_time = datetime.now(UTC)


def set_scheduler_running(running: bool) -> None:
    """Update scheduler running status."""
    global _scheduler_running
    _scheduler_running = running
    scheduler_running.set(1 if running else 0)


def check_database_health() -> bool:
    """Check database connectivity."""
    try:
        with get_session() as session:
            result = session.execute(text("SELECT 1"))
            result.fetchone()
            database_connection_healthy.set(1)
            return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        database_connection_healthy.set(0)
        return False


def update_sync_health_metrics() -> None:
    """Update sync health metrics for all domains."""
    try:
        sync_states = get_all_sync_states()

        for domain, _state in sync_states.items():
            healthy = is_sync_healthy(domain)
            sync_health_status.labels(domain=domain).set(1 if healthy else 0)

    except Exception as e:
        logger.error(f"Failed to update sync health metrics: {e}")


def get_health_status() -> dict[str, Any]:
    """Get comprehensive health status."""
    # Check database
    db_healthy = check_database_health()

    # Update sync metrics
    update_sync_health_metrics()

    # Get sync states
    sync_states = {}
    try:
        states = get_all_sync_states()
        for domain, state in states.items():
            sync_states[domain] = {
                "status": state.status,
                "last_synced_at": state.last_synced_at.isoformat()
                if state.last_synced_at
                else None,
                "error_count": state.error_count,
                "healthy": is_sync_healthy(domain),
            }
    except Exception as e:
        logger.error(f"Failed to get sync states: {e}")

    # Overall health
    overall_healthy = (
        db_healthy
        and _scheduler_running
        and all(state.get("healthy", False) for state in sync_states.values())
    )

    return {
        "status": "healthy" if overall_healthy else "unhealthy",
        "timestamp": datetime.now(UTC).isoformat(),
        "uptime_seconds": (datetime.now(UTC) - _app_start_time).total_seconds(),
        "checks": {
            "database": "healthy" if db_healthy else "unhealthy",
            "scheduler": "running" if _scheduler_running else "stopped",
        },
        "sync_states": sync_states,
    }


# FastAPI application (preferred)
if FastAPI:

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """FastAPI lifespan context manager."""
        logger.info("Starting observability server")
        yield
        logger.info("Stopping observability server")

    app = FastAPI(
        title="Stratus ERP Integration Service",
        description="Observability endpoints for ETL service",
        version="1.0.0",
        lifespan=lifespan,
    )

    @app.get("/healthz")
    async def health_check():
        """Health check endpoint."""
        health = get_health_status()

        if health["status"] == "healthy":
            return health
        else:
            raise HTTPException(status_code=503, detail=health)

    @app.get("/metrics", response_class=PlainTextResponse)
    async def metrics():
        """Prometheus metrics endpoint."""
        # Update metrics before serving
        check_database_health()
        update_sync_health_metrics()

        return generate_latest(REGISTRY)

    @app.get("/")
    async def root():
        """Root endpoint with service info."""
        return {
            "service": "Stratus ERP Integration Service",
            "version": "1.0.0",
            "timestamp": datetime.now(UTC).isoformat(),
            "endpoints": ["/healthz", "/metrics"],
        }


# Fallback HTTP server if FastAPI not available
class ObservabilityHandler(BaseHTTPRequestHandler):
    """HTTP handler for observability endpoints."""

    def do_GET(self):
        """Handle GET requests."""
        path = urlparse(self.path).path

        try:
            if path == "/healthz":
                health = get_health_status()

                if health["status"] == "healthy":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(health).encode())
                else:
                    self.send_response(503)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(health).encode())

            elif path == "/metrics":
                check_database_health()
                update_sync_health_metrics()

                metrics_data = generate_latest(REGISTRY)
                self.send_response(200)
                self.send_header("Content-Type", CONTENT_TYPE_LATEST)
                self.end_headers()
                self.wfile.write(metrics_data)

            elif path == "/":
                info = {
                    "service": "Stratus ERP Integration Service",
                    "version": "1.0.0",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "endpoints": ["/healthz", "/metrics"],
                }
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(info).encode())

            else:
                self.send_response(404)
                self.end_headers()

        except Exception as e:
            logger.error(f"Error handling request {path}: {e}")
            self.send_response(500)
            self.end_headers()

    def log_message(self, format, *args):
        """Override to use our logger."""
        logger.info(f"{self.address_string()} - {format % args}")


def start_observability_server(port: int = 8000) -> threading.Thread | None:
    """
    Start observability server in background thread.

    Args:
        port: Port to listen on

    Returns:
        Thread handle if using fallback server, None if using FastAPI
    """
    if not cfg("observability.metrics.enabled", True):
        logger.info("Observability server disabled by configuration")
        return None

    port = cfg("observability.metrics.port", port)

    if FastAPI:
        # FastAPI will be started separately with uvicorn
        logger.info(f"FastAPI observability server configured for port {port}")
        return None
    else:
        # Use fallback HTTP server
        def run_server():
            server = HTTPServer(("0.0.0.0", port), ObservabilityHandler)
            logger.info(f"Starting fallback observability server on port {port}")
            try:
                server.serve_forever()
            except Exception as e:
                logger.error(f"Observability server error: {e}")

        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()
        return thread


# Metrics helpers for use in jobs
def record_job_start(job_name: str) -> float:
    """Record job start and return start time."""
    return datetime.now(UTC).timestamp()


def record_job_success(job_name: str, start_time: float, records_count: int = 0) -> None:
    """Record successful job completion."""
    duration = datetime.now(UTC).timestamp() - start_time

    job_runs_total.labels(job=job_name, status="success").inc()
    job_duration_seconds.labels(job=job_name).observe(duration)

    if records_count > 0:
        # Infer table name from job name
        table_name = job_name.replace("_", "")
        records_upserted_total.labels(table=table_name, operation="upsert").inc(records_count)


def record_job_error(job_name: str, start_time: float, error: str) -> None:
    """Record job error."""
    duration = datetime.now(UTC).timestamp() - start_time

    job_runs_total.labels(job=job_name, status="error").inc()
    job_duration_seconds.labels(job=job_name).observe(duration)


def record_upsert_operation(table: str, inserted: int, updated: int) -> None:
    """Record upsert operation metrics."""
    if inserted > 0:
        records_upserted_total.labels(table=table, operation="insert").inc(inserted)
    if updated > 0:
        records_upserted_total.labels(table=table, operation="update").inc(updated)

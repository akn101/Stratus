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
    from fastapi.middleware.cors import CORSMiddleware
except ImportError:
    FastAPI = None

# Always import fallback modules
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

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
from src.analytics.simple_alerts import BusinessAlertsMonitor

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

    # Configure CORS for dashboard integration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "https://localhost:3000"],  # Next.js dashboard
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
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
            "endpoints": ["/healthz", "/metrics", "/api/alerts", "/api/analytics", "/api/system-stats", "/api/jobs/recent"],
        }

    @app.get("/api/alerts")
    async def get_alerts():
        """Get current business alerts for the dashboard"""
        try:
            with get_session() as session:
                monitor = BusinessAlertsMonitor(session)
                alerts = monitor.check_all_alerts()
                
                return {
                    "alerts": alerts,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "total_count": len(alerts),
                    "severity_counts": {
                        "critical": len([a for a in alerts if a["severity"] == "critical"]),
                        "high": len([a for a in alerts if a["severity"] == "high"]),
                        "medium": len([a for a in alerts if a["severity"] == "medium"]),
                        "low": len([a for a in alerts if a["severity"] == "low"])
                    }
                }
        except Exception as e:
            logger.error(f"Error getting alerts: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/analytics")
    async def get_analytics_data(days: int = 7):
        """Get analytics data for dashboard charts"""
        try:
            with get_session() as session:
                # Fulfillment performance over time
                fulfillment_query = text("""
                    WITH daily_fulfillment AS (
                        SELECT 
                            DATE(created_at) as date,
                            AVG(CASE 
                                WHEN fulfilled_at IS NOT NULL 
                                THEN EXTRACT(EPOCH FROM (fulfilled_at - created_at))/3600 
                                ELSE NULL 
                            END) as avg_fulfillment_hours,
                            COUNT(*) as orders_count,
                            COUNT(CASE 
                                WHEN fulfillment_status = 'error' OR fulfillment_status = 'cancelled'
                                THEN 1 
                            END) * 100.0 / COUNT(*) as exception_rate
                        FROM orders 
                        WHERE created_at >= NOW() - INTERVAL :days DAY
                        GROUP BY DATE(created_at)
                        ORDER BY date
                    )
                    SELECT * FROM daily_fulfillment
                """)
                
                fulfillment_results = session.execute(fulfillment_query, {"days": days}).fetchall()
                fulfillment_performance = []
                for row in fulfillment_results:
                    fulfillment_performance.append({
                        "date": row.date.strftime("%Y-%m-%d"),
                        "avg_fulfillment_hours": float(row.avg_fulfillment_hours or 0),
                        "orders_count": row.orders_count,
                        "exception_rate": float(row.exception_rate or 0)
                    })
                
                # Delivery metrics
                delivery_query = text("""
                    WITH daily_delivery AS (
                        SELECT 
                            DATE(created_at) as date,
                            COUNT(CASE WHEN fulfillment_status = 'fulfilled' THEN 1 END) as delivered,
                            COUNT(CASE WHEN fulfillment_status IN ('error', 'cancelled') THEN 1 END) as exceptions,
                            COUNT(CASE WHEN fulfillment_status IN ('pending', 'partial') THEN 1 END) as in_transit,
                            COUNT(CASE WHEN fulfillment_status IN ('error', 'cancelled') THEN 1 END) * 100.0 / COUNT(*) as exception_rate
                        FROM orders 
                        WHERE created_at >= NOW() - INTERVAL :days DAY
                        GROUP BY DATE(created_at)
                        ORDER BY date
                    )
                    SELECT * FROM daily_delivery
                """)
                
                delivery_results = session.execute(delivery_query, {"days": days}).fetchall()
                delivery_metrics = []
                for row in delivery_results:
                    delivery_metrics.append({
                        "date": row.date.strftime("%Y-%m-%d"),
                        "delivered": row.delivered,
                        "exceptions": row.exceptions,
                        "in_transit": row.in_transit,
                        "exception_rate": float(row.exception_rate or 0)
                    })
                
                # Revenue trends
                revenue_query = text("""
                    WITH daily_revenue AS (
                        SELECT 
                            DATE(created_at) as date,
                            SUM(total_price) as revenue,
                            COUNT(*) as orders,
                            AVG(total_price) as avg_order_value
                        FROM orders 
                        WHERE created_at >= NOW() - INTERVAL :days DAY
                        AND total_price > 0
                        GROUP BY DATE(created_at)
                        ORDER BY date
                    )
                    SELECT * FROM daily_revenue
                """)
                
                revenue_results = session.execute(revenue_query, {"days": days}).fetchall()
                revenue_trend = []
                for row in revenue_results:
                    revenue_trend.append({
                        "date": row.date.strftime("%Y-%m-%d"),
                        "revenue": float(row.revenue or 0),
                        "orders": row.orders,
                        "avg_order_value": float(row.avg_order_value or 0)
                    })
                
                # Inventory alerts by category (mock data based on business logic)
                inventory_alerts = [
                    {"category": "Low Stock", "count": 15, "severity": "medium"},
                    {"category": "Out of Stock", "count": 3, "severity": "high"},
                    {"category": "Overstock", "count": 8, "severity": "low"},
                    {"category": "Damaged", "count": 2, "severity": "critical"}
                ]
                
                return {
                    "fulfillment_performance": fulfillment_performance,
                    "delivery_metrics": delivery_metrics,
                    "revenue_trend": revenue_trend,
                    "inventory_alerts": inventory_alerts,
                    "timestamp": datetime.now(UTC).isoformat()
                }
                
        except Exception as e:
            logger.error(f"Error getting analytics data: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/system-stats")
    async def get_system_stats():
        """Get system statistics for dashboard overview"""
        try:
            with get_session() as session:
                # Get basic counts and recent activity
                stats_query = text("""
                    SELECT 
                        (SELECT COUNT(*) FROM orders) as total_orders,
                        (SELECT COUNT(*) FROM orders WHERE created_at >= NOW() - INTERVAL '24 HOUR') as orders_24h,
                        (SELECT COUNT(*) FROM inventory) as total_products,
                        (SELECT COUNT(*) FROM shopify_customers) as total_customers,
                        (SELECT MAX(created_at) FROM orders) as last_order_time,
                        (SELECT COUNT(*) FROM orders WHERE fulfillment_status = 'pending') as pending_orders
                """)
                
                result = session.execute(stats_query).fetchone()
                
                return {
                    "total_orders": result.total_orders or 0,
                    "orders_24h": result.orders_24h or 0,
                    "total_products": result.total_products or 0,
                    "total_customers": result.total_customers or 0,
                    "last_order_time": result.last_order_time.isoformat() if result.last_order_time else None,
                    "pending_orders": result.pending_orders or 0,
                    "timestamp": datetime.now(UTC).isoformat()
                }
                
        except Exception as e:
            logger.error(f"Error getting system stats: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/jobs/recent")
    async def get_recent_jobs(limit: int = 20):
        """Get recent ETL job executions (mock data for now)"""
        try:
            from datetime import timedelta
            # This would typically query a job_executions table
            # For now, return mock data that matches the expected format
            recent_jobs = [
                {
                    "id": f"job_{i}",
                    "name": f"shopify_orders_etl" if i % 3 == 0 else f"shipbob_inventory_etl" if i % 3 == 1 else "freeagent_contacts_etl",
                    "status": "completed" if i % 4 != 0 else "failed" if i % 8 == 0 else "running",
                    "started_at": (datetime.now(UTC) - timedelta(hours=i)).isoformat(),
                    "completed_at": (datetime.now(UTC) - timedelta(hours=i) + timedelta(minutes=5)).isoformat() if i % 4 != 0 and i % 8 != 7 else None,
                    "duration": 300 + (i * 30),  # seconds
                    "records_processed": 150 + (i * 25),
                    "records_inserted": 75 + (i * 10),
                    "records_updated": 75 + (i * 15),
                    "error_message": "Connection timeout" if i % 8 == 0 else None
                }
                for i in range(limit)
            ]
            
            return {
                "jobs": recent_jobs,
                "timestamp": datetime.now(UTC).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting recent jobs: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/alerts/{alert_id}/resolve")
    async def resolve_alert(alert_id: str):
        """Mark an alert as resolved"""
        try:
            # This would typically update an alerts table
            logger.info(f"Resolving alert {alert_id}")
            return {
                "success": True,
                "message": f"Alert {alert_id} resolved",
                "timestamp": datetime.now(UTC).isoformat()
            }
        except Exception as e:
            logger.error(f"Error resolving alert {alert_id}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/integration-status")
    async def get_integration_status():
        """Get the health status of external integrations"""
        try:
            from datetime import timedelta
            # This would typically ping each integration's health endpoint
            # For now, return mock status data
            integrations = {
                "shopify": {
                    "status": "active",
                    "last_sync": (datetime.now(UTC) - timedelta(minutes=15)).isoformat(),
                    "health_check": "passed"
                },
                "shipbob": {
                    "status": "active", 
                    "last_sync": (datetime.now(UTC) - timedelta(minutes=20)).isoformat(),
                    "health_check": "passed"
                },
                "freeagent": {
                    "status": "warning",
                    "last_sync": (datetime.now(UTC) - timedelta(hours=2)).isoformat(),
                    "health_check": "rate_limited"
                },
                "amazon": {
                    "status": "disabled",
                    "last_sync": None,
                    "health_check": "not_configured"
                }
            }
            
            return {
                "integrations": integrations,
                "timestamp": datetime.now(UTC).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting integration status: {e}")
            raise HTTPException(status_code=500, detail=str(e))


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

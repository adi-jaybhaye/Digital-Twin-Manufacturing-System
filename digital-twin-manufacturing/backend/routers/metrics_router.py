"""
metrics_router.py
-----------------
FastAPI routes for manufacturing metrics:
  GET /api/machines
  GET /api/machines/{code}
  GET /api/metrics
  GET /api/bottleneck
  GET /api/oee
  GET /api/throughput
  GET /api/workload
  GET /api/products
  GET /api/products/completed
  GET /api/events
  GET /api/dashboard
"""

import os
import sys
from typing import List
from fastapi import APIRouter, HTTPException

# Ensure backend directory and its parent are in sys.path
_current_dir = os.path.dirname(os.path.abspath(__file__))
_backend_dir = os.path.dirname(_current_dir)
_project_root = os.path.dirname(_backend_dir)
for _path in [_backend_dir, _project_root]:
    if _path not in sys.path:
        sys.path.insert(0, _path)

try:
    from simulation.engine import sim_engine
    from schemas.schemas import (
        MachineResponse, BottleneckResponse, ThroughputResponse,
        OEEResponse, WorkloadItem, ProductResponse, EventLogItem,
        ActionResponse
    )
except (ImportError, ModuleNotFoundError):
    try:
        from backend.simulation.engine import sim_engine
        from backend.schemas.schemas import (
            MachineResponse, BottleneckResponse, ThroughputResponse,
            OEEResponse, WorkloadItem, ProductResponse, EventLogItem,
            ActionResponse
        )
    except (ImportError, ModuleNotFoundError):
        from ..simulation.engine import sim_engine
        from ..schemas.schemas import (
            MachineResponse, BottleneckResponse, ThroughputResponse,
            OEEResponse, WorkloadItem, ProductResponse, EventLogItem,
            ActionResponse
        )

router = APIRouter(prefix="/api", tags=["Manufacturing Metrics"])


@router.get("/machines", response_model=List[dict])
def get_all_machines():
    """Current state of all machines on the production line."""
    return sim_engine.get_all_machines()


@router.get("/machines/{machine_code}", response_model=dict)
def get_machine(machine_code: str):
    """State of a specific machine by code (e.g. M_CUT, M_DRILL_1)."""
    code = machine_code.upper()
    if code not in sim_engine.machines:
        raise HTTPException(status_code=404, detail=f"Machine {code} not found")
    return sim_engine.machines[code].to_dict()


@router.get("/bottleneck", response_model=dict)
def get_bottleneck():
    """
    Identify the current bottleneck machine.
    Method: Machine with highest busy-state utilization (per research paper).
    """
    return sim_engine.get_bottleneck()


@router.get("/throughput", response_model=dict)
def get_throughput():
    """Current throughput metrics (products completed, per-minute, per-hour)."""
    return sim_engine.get_throughput()


@router.get("/oee", response_model=dict)
def get_oee():
    """
    Overall Equipment Effectiveness for each machine and system average.
    OEE = Availability × Performance × Quality
    """
    return sim_engine.get_oee_summary()


@router.get("/workload", response_model=List[dict])
def get_workload():
    """Workload distribution across all machines."""
    return sim_engine.get_workload_distribution()


@router.get("/products", response_model=List[dict])
def get_active_products():
    """Products currently in the production line."""
    return sim_engine.get_active_products()


@router.get("/products/completed", response_model=List[dict])
def get_completed_products():
    """Most recently completed products (last 50)."""
    return sim_engine.get_completed_products(limit=50)


@router.get("/events", response_model=List[dict])
def get_events():
    """Live event log (most recent first, max 100 items)."""
    return list(sim_engine.event_log)[:100]


@router.get("/metrics", response_model=dict)
def get_all_metrics():
    """All metrics in one call: machines + throughput + OEE + bottleneck + workload."""
    return {
        "machines":   sim_engine.get_all_machines(),
        "throughput": sim_engine.get_throughput(),
        "bottleneck": sim_engine.get_bottleneck(),
        "oee":        sim_engine.get_oee_summary(),
        "workload":   sim_engine.get_workload_distribution(),
    }


@router.get("/dashboard", response_model=dict)
def get_dashboard():
    """
    Complete dashboard data in one API call.
    The frontend polls this endpoint every 2 seconds.
    """
    return sim_engine.get_full_dashboard_data()

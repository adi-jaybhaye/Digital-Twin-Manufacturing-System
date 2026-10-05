"""
history_router.py
-----------------
FastAPI routes for historical simulation data:
  GET /api/history/runs
  GET /api/history/runs/{run_id}
  GET /api/history/what-if
  GET /api/history/metrics/{run_id}
"""

import os
import sys
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

# Ensure backend directory and its parent are in sys.path
_current_dir = os.path.dirname(os.path.abspath(__file__))
_backend_dir = os.path.dirname(_current_dir)
_project_root = os.path.dirname(_backend_dir)
for _path in [_backend_dir, _project_root]:
    if _path not in sys.path:
        sys.path.insert(0, _path)

try:
    from database import get_db
    from models.db_models import SimulationRun, WhatIfResult, MachineMetric
    from simulation.engine import sim_engine
except (ImportError, ModuleNotFoundError):
    try:
        from backend.database import get_db
        from backend.models.db_models import SimulationRun, WhatIfResult, MachineMetric
        from backend.simulation.engine import sim_engine
    except (ImportError, ModuleNotFoundError):
        from ..database import get_db
        from ..models.db_models import SimulationRun, WhatIfResult, MachineMetric
        from ..simulation.engine import sim_engine

router = APIRouter(prefix="/api/history", tags=["Historical Data"])


@router.get("/runs", response_model=List[dict])
def get_simulation_runs(db: Session = Depends(get_db)):
    """List all past simulation runs."""
    runs = db.query(SimulationRun).order_by(SimulationRun.created_at.desc()).limit(20).all()
    return [
        {
            "id":               r.id,
            "run_name":         r.run_name,
            "status":           r.status,
            "mode":             r.mode,
            "parallel_drilling": r.parallel_drilling,
            "speed_multiplier": r.speed_multiplier,
            "start_time":       r.start_time.isoformat() if r.start_time else None,
            "end_time":         r.end_time.isoformat() if r.end_time else None,
            "total_products":   r.total_products,
        }
        for r in runs
    ]


@router.get("/runs/{run_id}", response_model=dict)
def get_run_detail(run_id: int, db: Session = Depends(get_db)):
    """Details of a specific simulation run."""
    run = db.query(SimulationRun).filter(SimulationRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    return {
        "id":               run.id,
        "run_name":         run.run_name,
        "status":           run.status,
        "mode":             run.mode,
        "parallel_drilling": run.parallel_drilling,
        "speed_multiplier": run.speed_multiplier,
        "start_time":       run.start_time.isoformat() if run.start_time else None,
        "end_time":         run.end_time.isoformat() if run.end_time else None,
        "total_products":   run.total_products,
    }


@router.get("/what-if", response_model=List[dict])
def get_whatif_history(db: Session = Depends(get_db)):
    """All saved what-if analysis results."""
    results = db.query(WhatIfResult).order_by(WhatIfResult.analysis_time.desc()).limit(20).all()
    return [
        {
            "id":                    r.id,
            "analysis_time":         r.analysis_time.isoformat() if r.analysis_time else None,
            "baseline_throughput":   r.baseline_throughput,
            "modified_throughput":   r.modified_throughput,
            "throughput_improvement": r.throughput_improvement,
            "baseline_drilling_util": r.baseline_drilling_util,
            "modified_drilling_util": r.modified_drilling_util,
            "baseline_oee":          r.baseline_oee,
            "modified_oee":          r.modified_oee,
            "oee_improvement":       r.oee_improvement,
            "baseline_completed":    r.baseline_completed,
            "modified_completed":    r.modified_completed,
        }
        for r in results
    ]


@router.get("/metrics/{machine_code}", response_model=List[dict])
def get_machine_metric_history(machine_code: str, db: Session = Depends(get_db)):
    """Historical metric snapshots for a specific machine."""
    metrics = (
        db.query(MachineMetric)
        .filter(MachineMetric.machine_code == machine_code.upper())
        .order_by(MachineMetric.snapshot_time.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "snapshot_time":       m.snapshot_time.isoformat() if m.snapshot_time else None,
            "utilization":         m.utilization,
            "busy_percentage":     m.busy_percentage,
            "idle_percentage":     m.idle_percentage,
            "blocked_percentage":  m.blocked_percentage,
            "breakdown_percentage": m.breakdown_percentage,
            "oee":                 m.oee,
            "units_processed":     m.units_processed,
        }
        for m in metrics
    ]

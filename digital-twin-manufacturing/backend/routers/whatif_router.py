"""
whatif_router.py
----------------
FastAPI routes for What-If Analysis:
  POST /api/what-if/add-drilling-machine
  POST /api/what-if/remove-drilling-machine
  POST /api/what-if/reset-snapshot
  GET  /api/what-if/snapshot
  GET  /api/what-if/results
  POST /api/what-if/save-comparison
"""

import os
import sys
from datetime import datetime
from typing import Dict, Any, Optional

# Ensure backend directory and its parent are in sys.path
_current_dir = os.path.dirname(os.path.abspath(__file__))
_backend_dir = os.path.dirname(_current_dir)
_project_root = os.path.dirname(_backend_dir)
for _path in [_backend_dir, _project_root]:
    if _path not in sys.path:
        sys.path.insert(0, _path)

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

try:
    from database import get_db
    from simulation.engine import sim_engine
    from models.db_models import WhatIfResult
    from schemas.schemas import ActionResponse
except (ImportError, ModuleNotFoundError):
    try:
        from backend.database import get_db
        from backend.simulation.engine import sim_engine
        from backend.models.db_models import WhatIfResult
        from backend.schemas.schemas import ActionResponse
    except (ImportError, ModuleNotFoundError):
        from ..database import get_db
        from ..simulation.engine import sim_engine
        from ..models.db_models import WhatIfResult
        from ..schemas.schemas import ActionResponse

router = APIRouter(prefix="/api/what-if", tags=["What-If Analysis"])

# In-memory storage for baseline snapshot
_baseline_snapshot: Dict[str, Any] = {}


def _take_snapshot(parallel_active: bool) -> Dict[str, Any]:
    """Take a snapshot of current simulation metrics."""
    throughput = sim_engine.get_throughput()
    oee = sim_engine.get_oee_summary()
    bottleneck = sim_engine.get_bottleneck()

    # Calculate drilling utilization (average across parallel machines if active)
    drill_machines = [
        m for code, m in sim_engine.machines.items()
        if "DRILL" in code
    ]
    drill_util = (
        sum(m.get_utilization() for m in drill_machines) / len(drill_machines)
        if drill_machines else 0.0
    )

    return {
        "timestamp":       datetime.now().strftime("%H:%M:%S"),
        "completed":       throughput.get("total_completed", 0),
        "throughput_hr":   throughput.get("per_hour_sim", 0.0),
        "drilling_util":   round(drill_util, 2),
        "system_oee":      oee.get("system_oee", 0.0),
        "parallel_active": parallel_active,
        "bottleneck":      bottleneck.get("machine_name", "None") if bottleneck else "None",
    }


def reset_baseline() -> None:
    """Reset the baseline snapshot."""
    global _baseline_snapshot
    _baseline_snapshot = {}


@router.post("/add-drilling-machine", response_model=ActionResponse)
def add_drilling_machine():
    """
    What-If Analysis: Add a parallel drilling machine.
    
    Before adding: take a baseline snapshot (if not already running parallel).
    After adding: the simulation runs with 2 drilling machines.
    """
    global _baseline_snapshot

    if sim_engine.parallel_drilling:
        return ActionResponse(
            success=False,
            message="Parallel drilling machine is already active. Remove it first before taking a new baseline."
        )

    # Capture baseline before modification
    _baseline_snapshot = _take_snapshot(parallel_active=False)

    result = sim_engine.add_parallel_drilling_machine()
    if not result.get("success", False):
        _baseline_snapshot = {}
        return ActionResponse(success=False, message=result.get("message", "Failed to add parallel machine"))

    return ActionResponse(
        success=True,
        message="Parallel drilling machine added! Compare metrics now.",
        data={"baseline_snapshot": _baseline_snapshot}
    )


@router.post("/remove-drilling-machine", response_model=ActionResponse)
def remove_drilling_machine():
    """Remove the parallel drilling machine (restore baseline configuration)."""
    global _baseline_snapshot
    result = sim_engine.remove_parallel_drilling_machine()
    if result.get("success", False):
        _baseline_snapshot = {}
    return ActionResponse(success=result.get("success", False), message=result.get("message", ""))


@router.post("/reset-snapshot", response_model=ActionResponse)
def reset_snapshot():
    """Reset the what-if baseline snapshot."""
    reset_baseline()
    return ActionResponse(success=True, message="What-If baseline snapshot reset.")


@router.get("/snapshot", response_model=dict)
def get_snapshot():
    """
    Get current snapshot + baseline for comparison.
    The frontend calls this to build the comparison table.
    Only computes comparison if parallel drilling is actively running and a baseline exists.
    """
    current = _take_snapshot(parallel_active=sim_engine.parallel_drilling)

    if _baseline_snapshot and sim_engine.parallel_drilling:
        base_tp = _baseline_snapshot.get("throughput_hr", 0.0)
        curr_tp = current.get("throughput_hr", 0.0)
        if base_tp > 0.5:
            tp_improvement = round(((curr_tp - base_tp) / base_tp) * 100, 2)
        elif curr_tp > 0:
            tp_improvement = 100.0
        else:
            tp_improvement = 0.0

        base_oee = _baseline_snapshot.get("system_oee", 0.0)
        curr_oee = current.get("system_oee", 0.0)
        if base_oee > 0.5:
            oee_improvement = round(((curr_oee - base_oee) / base_oee) * 100, 2)
        elif curr_oee > 0:
            oee_improvement = 100.0
        else:
            oee_improvement = 0.0

        comparison = {
            "baseline":               _baseline_snapshot,
            "current":                current,
            "throughput_improvement": tp_improvement,
            "oee_improvement":        oee_improvement,
            "drilling_util_change":   round(
                current.get("drilling_util", 0.0) - _baseline_snapshot.get("drilling_util", 0.0), 2
            ),
        }
    else:
        comparison = {
            "baseline": None,
            "current":  current,
            "message":  "Add parallel machine first to see comparison",
        }

    return comparison


@router.get("/results", response_model=dict)
def get_whatif_results():
    """
    Full what-if analysis results including all machine metrics.
    """
    machines_data = sim_engine.get_all_machines()
    snapshot = _take_snapshot(parallel_active=sim_engine.parallel_drilling)

    # Separate drilling machines
    drill_data = [m for m in machines_data if m.get("station") == "drilling"]

    return {
        "parallel_active": sim_engine.parallel_drilling,
        "current_snapshot": snapshot,
        "baseline_snapshot": _baseline_snapshot if _baseline_snapshot else None,
        "all_machines":    machines_data,
        "drilling_machines": drill_data,
        "paper_reference": {
            "baseline_throughput":    478,
            "modified_throughput":    760,
            "throughput_improvement": 59.0,
            "drilling_busy_pct":      85.516,
            "baseline_oee":           43.60,
            "modified_oee":           55.49,
            "oee_improvement":        27.27,
            "note": "Research paper reference values — for validation only. Live values above are from the simulation."
        }
    }


@router.post("/save-comparison", response_model=ActionResponse)
def save_comparison(db: Session = Depends(get_db)):
    """Save the current baseline vs modified comparison to the database."""
    if not _baseline_snapshot:
        return ActionResponse(
            success=False,
            message="No baseline snapshot found. Add parallel machine first."
        )

    current = _take_snapshot(parallel_active=sim_engine.parallel_drilling)
    base_tp = float(_baseline_snapshot.get("throughput_hr", 0.0))
    curr_tp = float(current.get("throughput_hr", 0.0))
    if base_tp > 0.5:
        tp_impr = round(((curr_tp - base_tp) / base_tp) * 100, 2)
    elif curr_tp > 0:
        tp_impr = 100.0
    else:
        tp_impr = 0.0

    base_oee = float(_baseline_snapshot.get("system_oee", 0.0))
    curr_oee = float(current.get("system_oee", 0.0))
    if base_oee > 0.5:
        oee_impr = round(((curr_oee - base_oee) / base_oee) * 100, 2)
    elif curr_oee > 0:
        oee_impr = 100.0
    else:
        oee_impr = 0.0

    try:
        result = WhatIfResult(
            baseline_run_id=sim_engine.simulation_run_id,
            modified_run_id=sim_engine.simulation_run_id,
            baseline_throughput=base_tp,
            modified_throughput=curr_tp,
            throughput_improvement=tp_impr,
            baseline_drilling_util=float(_baseline_snapshot.get("drilling_util", 0.0)),
            modified_drilling_util=float(current.get("drilling_util", 0.0)),
            baseline_oee=base_oee,
            modified_oee=curr_oee,
            oee_improvement=oee_impr,
            baseline_completed=int(_baseline_snapshot.get("completed", 0)),
            modified_completed=int(current.get("completed", 0)),
            notes=f"Saved at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        )
        db.add(result)
        db.commit()
        db.refresh(result)

        return ActionResponse(
            success=True,
            message=f"Comparison saved (ID: {result.id}). Throughput improvement: {tp_impr}%",
            data={"result_id": result.id, "improvement": tp_impr}
        )
    except Exception as e:
        db.rollback()
        return ActionResponse(
            success=False,
            message=f"Database error while saving comparison: {e}"
        )

"""
simulation_router.py
--------------------
FastAPI routes for controlling the simulation:
  POST /api/simulation/start
  POST /api/simulation/stop
  POST /api/simulation/pause
  POST /api/simulation/resume
  POST /api/simulation/reset
  GET  /api/simulation/status
  POST /api/simulation/config
  POST /api/simulation/machine/{code}/config
"""

import os
import sys
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
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
    from simulation.engine import sim_engine
    from schemas.schemas import (
        SimulationConfig, MachineConfigUpdate,
        ActionResponse, SimulationStatus
    )
    from models.db_models import SimulationRun
except (ImportError, ModuleNotFoundError):
    try:
        from backend.database import get_db
        from backend.simulation.engine import sim_engine
        from backend.schemas.schemas import (
            SimulationConfig, MachineConfigUpdate,
            ActionResponse, SimulationStatus
        )
        from backend.models.db_models import SimulationRun
    except (ImportError, ModuleNotFoundError):
        from ..database import get_db
        from ..simulation.engine import sim_engine
        from ..schemas.schemas import (
            SimulationConfig, MachineConfigUpdate,
            ActionResponse, SimulationStatus
        )
        from ..models.db_models import SimulationRun

router = APIRouter(prefix="/api/simulation", tags=["Simulation Control"])


# ─── Helper ───────────────────────────────────────────────────────────

def _get_or_create_run(db: Session) -> SimulationRun:
    """Create a new simulation run record in the database."""
    run = SimulationRun(
        run_name=f"Run {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        status="running",
        speed_multiplier=sim_engine.speed_multiplier,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


# ─── Routes ───────────────────────────────────────────────────────────

@router.post("/start", response_model=ActionResponse)
def start_simulation(db: Session = Depends(get_db)):
    """Start the simulation. Creates a new run record in the database."""
    if sim_engine.is_running and not sim_engine.is_paused:
        return ActionResponse(success=False, message="Simulation is already running")

    if sim_engine.is_paused:
        sim_engine.resume()
        return ActionResponse(success=True, message="Simulation resumed")

    try:
        run = _get_or_create_run(db)
        sim_engine.start(run_id=run.id)
        return ActionResponse(
            success=True,
            message="Simulation started",
            data={"run_id": run.id}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start simulation: {e}")


@router.post("/stop", response_model=ActionResponse)
def stop_simulation(db: Session = Depends(get_db)):
    """Stop the simulation and save final state."""
    if not sim_engine.is_running:
        return ActionResponse(success=False, message="Simulation is not running")

    sim_engine.stop()

    # Update DB run record
    try:
        run = db.query(SimulationRun).filter(
            SimulationRun.id == sim_engine.simulation_run_id
        ).first()
        if run:
            run.status = "stopped"
            run.end_time = datetime.now()
            run.total_products = len(sim_engine.completed_products)
            run.parallel_drilling = sim_engine.parallel_drilling
            db.commit()
    except Exception:
        pass  # DB errors shouldn't crash the stop action

    return ActionResponse(success=True, message="Simulation stopped")


@router.post("/pause", response_model=ActionResponse)
def pause_simulation():
    """Pause the running simulation."""
    if not sim_engine.is_running:
        return ActionResponse(success=False, message="Simulation is not running")
    sim_engine.pause()
    return ActionResponse(success=True, message="Simulation paused")


@router.post("/resume", response_model=ActionResponse)
def resume_simulation():
    """Resume a paused simulation."""
    if not sim_engine.is_paused:
        return ActionResponse(success=False, message="Simulation is not paused")
    sim_engine.resume()
    return ActionResponse(success=True, message="Simulation resumed")


@router.post("/reset", response_model=ActionResponse)
def reset_simulation():
    """Reset simulation: clear all state and metrics."""
    sim_engine.reset()
    try:
        from routers.whatif_router import reset_baseline
        reset_baseline()
    except Exception:
        pass
    return ActionResponse(success=True, message="Simulation reset — ready to start fresh")


@router.get("/status", response_model=SimulationStatus)
def get_status():
    """Current simulation status."""
    return sim_engine.get_simulation_status()


@router.post("/config", response_model=ActionResponse)
def update_config(config: SimulationConfig):
    """Update global simulation parameters (speed, arrival rate, etc.)."""
    result = sim_engine.update_simulation_config(config.model_dump(exclude_none=True))
    return ActionResponse(success=result["success"], message="Configuration updated", data=result)


@router.post("/machine/{machine_code}/config", response_model=ActionResponse)
def update_machine_config(machine_code: str, config: MachineConfigUpdate):
    """Update processing parameters for a specific machine."""
    result = sim_engine.update_machine_config(
        machine_code.upper(), config.model_dump(exclude_none=True)
    )
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result["message"])
    return ActionResponse(success=True, message=result["message"])

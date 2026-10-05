"""
schemas.py
----------
Pydantic v2 schemas for request/response validation in FastAPI.
These define the shape of data going in and out of the API.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# ─── Simulation Control ──────────────────────────────────────────────

class SimulationConfig(BaseModel):
    """Parameters to configure the simulation."""
    speed_multiplier: Optional[float] = Field(default=None, ge=0.5, le=50.0,
                                              description="How many sim-seconds per real second")
    arrival_rate: Optional[float] = Field(default=None, ge=1.0, le=60.0,
                                          description="Seconds of sim time between new products")
    breakdown_enabled: Optional[bool] = None


class SimulationStatus(BaseModel):
    is_running: bool
    is_paused: bool
    parallel_drilling: bool
    speed_multiplier: float
    arrival_rate: float
    sim_time_str: str
    sim_elapsed_sec: float
    product_counter: int
    completed: int
    rejected: int
    in_progress: int
    run_id: int


# ─── Machine ─────────────────────────────────────────────────────────

class MachineConfigUpdate(BaseModel):
    """Fields that can be changed at runtime."""
    processing_time_min: Optional[float] = Field(None, ge=1.0, le=120.0)
    processing_time_max: Optional[float] = Field(None, ge=1.0, le=120.0)
    breakdown_prob: Optional[float] = Field(None, ge=0.0, le=1.0)
    breakdown_duration_min: Optional[float] = Field(None, ge=1.0, le=300.0)
    breakdown_duration_max: Optional[float] = Field(None, ge=1.0, le=300.0)
    defect_rate: Optional[float] = Field(None, ge=0.0, le=1.0)


class MachineResponse(BaseModel):
    machine_code:    str
    machine_name:    str
    station:         str
    station_order:   int
    is_parallel:     bool
    state:           str
    current_product: Optional[str]
    utilization:     float
    busy_pct:        float
    idle_pct:        float
    blocked_pct:     float
    breakdown_pct:   float
    units_processed: int
    units_rejected:  int
    breakdown_count: int
    busy_time:       float
    idle_time:       float
    blocked_time:    float
    breakdown_time:  float
    config:          Dict[str, float]


# ─── Bottleneck ───────────────────────────────────────────────────────

class BottleneckResponse(BaseModel):
    bottleneck:   Optional[str]
    machine_name: Optional[str] = None
    station:      Optional[str] = None
    utilization:  float
    state:        Optional[str] = None


# ─── Throughput ───────────────────────────────────────────────────────

class ThroughputResponse(BaseModel):
    total_completed:  int
    total_rejected:   int
    per_minute_real:  int
    per_hour_sim:     float
    elapsed_sim_min:  float


# ─── OEE ─────────────────────────────────────────────────────────────

class MachineOEE(BaseModel):
    availability: float
    performance:  float
    quality:      float
    oee:          float


class OEEResponse(BaseModel):
    machines:   Dict[str, MachineOEE]
    system_oee: float


# ─── Workload ─────────────────────────────────────────────────────────

class WorkloadItem(BaseModel):
    machine_code:  str
    machine_name:  str
    station:       str
    units:         int
    workload_pct:  float


# ─── Products ────────────────────────────────────────────────────────

class StationRecord(BaseModel):
    station:         str
    machine:         str
    processing_time: float
    passed:          bool


class ProductResponse(BaseModel):
    product_code:     str
    status:           str
    current_station:  str
    quality_status:   str
    age:              float
    total_processing: float
    assigned_machine: Optional[str]
    station_history:  List[StationRecord]


# ─── Event Log ────────────────────────────────────────────────────────

class EventLogItem(BaseModel):
    id:           int
    time:         str
    type:         str
    message:      str
    machine_code: Optional[str]
    product_code: Optional[str]
    severity:     str


# ─── What-If Analysis ────────────────────────────────────────────────

class WhatIfSnapshot(BaseModel):
    """A snapshot of metrics taken before/after adding parallel machine."""
    timestamp:       str
    completed:       int
    throughput_hr:   float
    drilling_util:   float
    system_oee:      float
    parallel_active: bool


class WhatIfComparison(BaseModel):
    baseline:              WhatIfSnapshot
    modified:              WhatIfSnapshot
    throughput_improvement: float
    oee_improvement:       float
    drilling_util_change:  float


# ─── Dashboard ────────────────────────────────────────────────────────

class DashboardData(BaseModel):
    status:     SimulationStatus
    machines:   List[MachineResponse]
    throughput: ThroughputResponse
    bottleneck: BottleneckResponse
    oee:        OEEResponse
    workload:   List[WorkloadItem]
    products:   List[ProductResponse]
    event_log:  List[EventLogItem]


# ─── Historical Runs ─────────────────────────────────────────────────

class SimRunSummary(BaseModel):
    id:               int
    run_name:         str
    status:           str
    mode:             str
    parallel_drilling: bool
    speed_multiplier: float
    start_time:       Optional[datetime]
    end_time:         Optional[datetime]
    total_products:   int


# ─── Generic Response ─────────────────────────────────────────────────

class ActionResponse(BaseModel):
    success: bool
    message: str
    data:    Optional[Dict[str, Any]] = None

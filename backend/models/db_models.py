"""
db_models.py
------------
SQLAlchemy ORM models for the Digital Twin Manufacturing database.
These map to the MySQL tables defined in database/schema.sql.
"""

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Enum, 
    ForeignKey, Text, Boolean
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
try:
    from database import Base
except ImportError:
    from ..database import Base
import enum


# ─── Enums ───────────────────────────────────────────────────────────

class SimRunStatus(str, enum.Enum):
    running   = "running"
    paused    = "paused"
    stopped   = "stopped"
    completed = "completed"

class SimMode(str, enum.Enum):
    baseline = "baseline"
    modified = "modified"

class MachineStatus(str, enum.Enum):
    BUSY      = "BUSY"
    IDLE      = "IDLE"
    BLOCKED   = "BLOCKED"
    BREAKDOWN = "BREAKDOWN"

class ProductStatus(str, enum.Enum):
    in_progress = "in_progress"
    completed   = "completed"
    rejected    = "rejected"
    waiting     = "waiting"

class ProductStation(str, enum.Enum):
    cutting    = "cutting"
    turning    = "turning"
    drilling   = "drilling"
    inspection = "inspection"
    packaging  = "packaging"
    completed  = "completed"
    rejected   = "rejected"

class EventSeverity(str, enum.Enum):
    info    = "info"
    warning = "warning"
    error   = "error"
    success = "success"


# ─── Models ───────────────────────────────────────────────────────────

class SimulationRun(Base):
    """Tracks each simulation session."""
    __tablename__ = "simulation_runs"

    id                = Column(Integer, primary_key=True, autoincrement=True)
    run_name          = Column(String(100), default="Simulation Run")
    status            = Column(String(20), default="stopped")
    mode              = Column(String(20), default="baseline")
    parallel_drilling = Column(Boolean, default=False)
    speed_multiplier  = Column(Float, default=1.0)
    start_time        = Column(DateTime, server_default=func.now())
    end_time          = Column(DateTime, nullable=True)
    total_products    = Column(Integer, default=0)
    created_at        = Column(DateTime, server_default=func.now())
    updated_at        = Column(DateTime, server_default=func.now(), onupdate=func.now())

    products = relationship("DBProduct", back_populates="run")
    events   = relationship("EventLog", back_populates="run")
    metrics  = relationship("MachineMetric", back_populates="run")


class DBMachine(Base):
    """Represents a physical machine/station in the manufacturing line."""
    __tablename__ = "machines"

    id                    = Column(Integer, primary_key=True, autoincrement=True)
    machine_code          = Column(String(20), unique=True, nullable=False)
    machine_name          = Column(String(100), nullable=False)
    station               = Column(String(20), nullable=False)
    station_order         = Column(Integer, nullable=False)
    is_parallel           = Column(Boolean, default=False)
    status                = Column(String(20), default="IDLE")
    processing_time_min   = Column(Float, default=5.0)
    processing_time_max   = Column(Float, default=10.0)
    breakdown_prob        = Column(Float, default=0.02)
    breakdown_duration_min= Column(Float, default=5.0)
    breakdown_duration_max= Column(Float, default=15.0)
    defect_rate           = Column(Float, default=0.03)
    busy_time             = Column(Float, default=0.0)
    idle_time             = Column(Float, default=0.0)
    blocked_time          = Column(Float, default=0.0)
    breakdown_time        = Column(Float, default=0.0)
    units_processed       = Column(Integer, default=0)
    breakdown_count       = Column(Integer, default=0)
    is_active             = Column(Boolean, default=True)
    created_at            = Column(DateTime, server_default=func.now())
    updated_at            = Column(DateTime, server_default=func.now(), onupdate=func.now())


class DBProduct(Base):
    """A product moving through the manufacturing line."""
    __tablename__ = "products"

    id                    = Column(Integer, primary_key=True, autoincrement=True)
    product_code          = Column(String(20), unique=True, nullable=False)
    simulation_run_id     = Column(Integer, ForeignKey("simulation_runs.id"), nullable=True)
    status                = Column(String(20), default="waiting")
    current_station       = Column(String(20), default="cutting")
    quality_status        = Column(String(20), default="pending")
    start_time            = Column(DateTime, server_default=func.now())
    completed_at          = Column(DateTime, nullable=True)
    total_processing_time = Column(Float, default=0.0)

    run = relationship("SimulationRun", back_populates="products")


class ProductionRecord(Base):
    """Each time a product passes through a station."""
    __tablename__ = "production_records"

    id                = Column(Integer, primary_key=True, autoincrement=True)
    product_id        = Column(Integer, ForeignKey("products.id"), nullable=False)
    machine_id        = Column(Integer, ForeignKey("machines.id"), nullable=False)
    station           = Column(String(50), nullable=False)
    status            = Column(String(20), default="started")
    processing_time   = Column(Float, nullable=False)
    start_time        = Column(DateTime, server_default=func.now())
    end_time          = Column(DateTime, nullable=True)
    simulation_run_id = Column(Integer, ForeignKey("simulation_runs.id"), nullable=True)


class MachineEvent(Base):
    """State change events for each machine."""
    __tablename__ = "machine_events"

    id                = Column(Integer, primary_key=True, autoincrement=True)
    machine_id        = Column(Integer, ForeignKey("machines.id"), nullable=False)
    machine_code      = Column(String(20), nullable=False)
    event_type        = Column(String(30), nullable=False)
    old_state         = Column(String(20), nullable=True)
    new_state         = Column(String(20), nullable=True)
    product_code      = Column(String(20), nullable=True)
    description       = Column(Text, nullable=True)
    start_time        = Column(DateTime, server_default=func.now())
    end_time          = Column(DateTime, nullable=True)
    duration          = Column(Float, default=0.0)
    simulation_run_id = Column(Integer, ForeignKey("simulation_runs.id"), nullable=True)


class MachineMetric(Base):
    """Periodic metric snapshots for historical analysis."""
    __tablename__ = "machine_metrics"

    id                   = Column(Integer, primary_key=True, autoincrement=True)
    machine_id           = Column(Integer, nullable=True)
    machine_code         = Column(String(20), nullable=False)
    simulation_run_id    = Column(Integer, ForeignKey("simulation_runs.id"), nullable=True)
    snapshot_time        = Column(DateTime, server_default=func.now())
    utilization          = Column(Float, default=0.0)
    busy_percentage      = Column(Float, default=0.0)
    idle_percentage      = Column(Float, default=0.0)
    blocked_percentage   = Column(Float, default=0.0)
    breakdown_percentage = Column(Float, default=0.0)
    throughput           = Column(Float, default=0.0)
    oee_availability     = Column(Float, default=0.0)
    oee_performance      = Column(Float, default=0.0)
    oee_quality          = Column(Float, default=0.0)
    oee                  = Column(Float, default=0.0)
    units_processed      = Column(Integer, default=0)

    run = relationship("SimulationRun", back_populates="metrics")


class WhatIfResult(Base):
    """Comparison results from what-if analysis."""
    __tablename__ = "what_if_results"

    id                     = Column(Integer, primary_key=True, autoincrement=True)
    analysis_time          = Column(DateTime, server_default=func.now())
    baseline_run_id        = Column(Integer, nullable=True)
    modified_run_id        = Column(Integer, nullable=True)
    baseline_throughput    = Column(Float, default=0.0)
    modified_throughput    = Column(Float, default=0.0)
    throughput_improvement = Column(Float, default=0.0)
    baseline_drilling_util = Column(Float, default=0.0)
    modified_drilling_util = Column(Float, default=0.0)
    baseline_oee           = Column(Float, default=0.0)
    modified_oee           = Column(Float, default=0.0)
    oee_improvement        = Column(Float, default=0.0)
    baseline_completed     = Column(Integer, default=0)
    modified_completed     = Column(Integer, default=0)
    notes                  = Column(Text, nullable=True)


class EventLog(Base):
    """Human-readable event log for frontend display."""
    __tablename__ = "event_log"

    id                = Column(Integer, primary_key=True, autoincrement=True)
    event_time        = Column(DateTime, server_default=func.now())
    event_type        = Column(String(50), nullable=False)
    message           = Column(Text, nullable=False)
    machine_code      = Column(String(20), nullable=True)
    product_code      = Column(String(20), nullable=True)
    severity          = Column(String(20), default="info")
    simulation_run_id = Column(Integer, ForeignKey("simulation_runs.id"), nullable=True)

    run = relationship("SimulationRun", back_populates="events")

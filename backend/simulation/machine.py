"""
machine.py
----------
Represents a single manufacturing machine/station in the Digital Twin.

Each machine can be in one of four states (from the research paper):
  - BUSY:      Currently processing a product
  - IDLE:      No product available, waiting
  - BLOCKED:   Finished processing but next station is not ready to accept
  - BREAKDOWN: Machine is temporarily unavailable (fault/maintenance)

Sensor Integration Note (Future Extension):
  - Current sensor  → busy/idle detection (spindle/motor)
  - Photoelectric   → part counts (input/output)
  - Proximity       → blocked state (buffer full)
  - Accelerometer   → early breakdown detection (drilling/turning)
  - Temperature     → overheating / predictive maintenance
  - Vision/Laser    → quality check at inspection
  - Stack light     → confirmed breakdown state
"""

import time
import random
import threading
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Callable


# ─────────────────────────── Enumerations ────────────────────────────

class MachineState(str, Enum):
    BUSY      = "BUSY"
    IDLE      = "IDLE"
    BLOCKED   = "BLOCKED"
    BREAKDOWN = "BREAKDOWN"


class Station(str, Enum):
    CUTTING    = "cutting"
    TURNING    = "turning"
    DRILLING   = "drilling"
    INSPECTION = "inspection"
    PACKAGING  = "packaging"


# ──────────────────────── Machine Dataclass ───────────────────────────

@dataclass
class MachineConfig:
    """Configurable parameters for a machine."""
    machine_code: str
    machine_name: str
    station: Station
    station_order: int
    processing_time_min: float = 5.0   # seconds (simulation time)
    processing_time_max: float = 10.0
    breakdown_prob: float = 0.02        # probability per job
    breakdown_duration_min: float = 5.0
    breakdown_duration_max: float = 15.0
    defect_rate: float = 0.03           # fraction of products that fail inspection
    is_parallel: bool = False           # True for additional parallel machines


class Machine:
    """
    Simulated manufacturing machine with state tracking and metrics.
    
    Corresponds to a physical machine station on the shop floor.
    The state transitions mirror what physical sensors would detect:
      current sensor → BUSY/IDLE
      proximity/ultrasonic → BLOCKED
      accelerometer/temperature/stack-light → BREAKDOWN
    """

    def __init__(self, config: MachineConfig, speed_multiplier: float = 1.0):
        self.config = config
        self.machine_code = config.machine_code
        self.machine_name = config.machine_name
        self.station = config.station
        self.station_order = config.station_order
        self.is_parallel = config.is_parallel

        # Current state
        self.state: MachineState = MachineState.IDLE
        self.current_product_id: Optional[str] = None
        self.processing_end_time: float = 0.0   # sim-time when current job ends

        # Speed: higher multiplier = faster simulation
        self.speed_multiplier = speed_multiplier

        # Cumulative time tracking (seconds of sim time)
        self.busy_time: float = 0.0
        self.idle_time: float = 0.0
        self.blocked_time: float = 0.0
        self.breakdown_time: float = 0.0

        # Counters
        self.units_processed: int = 0
        self.units_rejected: int = 0        # defective products
        self.breakdown_count: int = 0

        # Timestamps for current state (sim time)
        self._state_start: float = time.time()
        self._lock = threading.Lock()

        # Callback: called when a state changes (for event logging)
        self.on_state_change: Optional[Callable] = None

        # Callback: called when a product is finished
        self.on_product_complete: Optional[Callable] = None

    # ─────────── State Management ───────────

    def set_state(self, new_state: MachineState, product_id: str = None):
        """Transition to a new state, accumulating time in the old state."""
        with self._lock:
            now = time.time()
            elapsed = (now - self._state_start) * self.speed_multiplier
            old_state = self.state

            # Accumulate time in old state
            if old_state == MachineState.BUSY:
                self.busy_time += elapsed
            elif old_state == MachineState.IDLE:
                self.idle_time += elapsed
            elif old_state == MachineState.BLOCKED:
                self.blocked_time += elapsed
            elif old_state == MachineState.BREAKDOWN:
                self.breakdown_time += elapsed

            self.state = new_state
            self._state_start = now
            if product_id is not None:
                self.current_product_id = product_id
            elif new_state == MachineState.IDLE:
                self.current_product_id = None

        # Fire callback outside the lock
        if self.on_state_change and old_state != new_state:
            self.on_state_change(self, old_state, new_state, product_id)

    def start_processing(self, product_id: str) -> float:
        """
        Begin processing a product.
        Returns the processing time (seconds of sim time) for this job.
        """
        # Random processing time within configured range
        processing_time = random.uniform(
            self.config.processing_time_min,
            self.config.processing_time_max
        )
        self.processing_end_time = time.time() + (processing_time / self.speed_multiplier)
        self.set_state(MachineState.BUSY, product_id)
        return processing_time

    def check_breakdown(self) -> bool:
        """
        Simulate probabilistic breakdown event.
        Triggered after each job completion (mimics accelerometer/temp spike detection).
        Returns True if a breakdown occurred.
        """
        if random.random() < self.config.breakdown_prob:
            self.breakdown_count += 1
            return True
        return False

    def is_done_processing(self) -> bool:
        """Check if the current job has finished (by wall-clock time)."""
        return time.time() >= self.processing_end_time

    def complete_job(self) -> bool:
        """
        Finish current job. Increments counters.
        Returns True if the product passes quality check (False = defective).
        Mimics vision camera / laser gauge at inspection.
        """
        with self._lock:
            self.units_processed += 1
            is_good = random.random() > self.config.defect_rate
            if not is_good:
                self.units_rejected += 1
            return is_good

    # ─────────── Metrics Calculation ───────────

    def get_total_time(self) -> float:
        """Total elapsed sim time across all states (updates current state bucket)."""
        now = time.time()
        elapsed = (now - self._state_start) * self.speed_multiplier
        total = self.busy_time + self.idle_time + self.blocked_time + self.breakdown_time + elapsed
        return max(total, 0.001)   # avoid division-by-zero

    def get_current_elapsed(self) -> float:
        """Seconds accumulated in current state so far."""
        now = time.time()
        return (now - self._state_start) * self.speed_multiplier

    def _get_live_state_times(self):
        """Return (busy, idle, blocked, breakdown) with current bucket included."""
        now = time.time()
        elapsed = (now - self._state_start) * self.speed_multiplier
        busy      = self.busy_time
        idle      = self.idle_time
        blocked   = self.blocked_time
        breakdown = self.breakdown_time

        if self.state == MachineState.BUSY:
            busy += elapsed
        elif self.state == MachineState.IDLE:
            idle += elapsed
        elif self.state == MachineState.BLOCKED:
            blocked += elapsed
        elif self.state == MachineState.BREAKDOWN:
            breakdown += elapsed

        return busy, idle, blocked, breakdown

    def get_utilization(self) -> float:
        """
        Machine Utilization = Busy Time / Total Available Time × 100
        (From research paper: primary metric for bottleneck detection)
        """
        busy, idle, blocked, breakdown = self._get_live_state_times()
        total = busy + idle + blocked + breakdown
        if total < 0.001:
            return 0.0
        return (busy / total) * 100.0

    def get_state_percentages(self) -> dict:
        """Return all four state percentages."""
        busy, idle, blocked, breakdown = self._get_live_state_times()
        total = busy + idle + blocked + breakdown
        if total < 0.001:
            return {"busy": 0.0, "idle": 0.0, "blocked": 0.0, "breakdown": 0.0}
        return {
            "busy":      round((busy / total) * 100, 3),
            "idle":      round((idle / total) * 100, 3),
            "blocked":   round((blocked / total) * 100, 3),
            "breakdown": round((breakdown / total) * 100, 3),
        }

    def calculate_oee(self, ideal_cycle_time: float, planned_time: float) -> dict:
        """
        OEE = Availability × Performance × Quality
        
        Availability = (Planned Time - Breakdown Time) / Planned Time
        Performance  = (Ideal Cycle Time × Units Produced) / Run Time
        Quality      = Good Units / Total Units
        
        Args:
            ideal_cycle_time: Minimum processing time for one unit (seconds)
            planned_time:     Total planned operating time (seconds)
        """
        busy, idle, blocked, breakdown = self._get_live_state_times()
        run_time = max(planned_time - breakdown, 0.001)

        # Availability: what fraction of planned time was the machine not broken?
        availability = run_time / max(planned_time, 0.001)

        # Performance: how fast compared to ideal cycle?
        total_units = self.units_processed
        if run_time > 0 and total_units > 0:
            performance = (ideal_cycle_time * total_units) / run_time
            performance = min(performance, 1.0)  # cap at 100%
        else:
            performance = 0.0

        # Quality: fraction of good parts (mimics vision/laser sensor data)
        if total_units > 0:
            quality = (total_units - self.units_rejected) / total_units
        else:
            quality = 1.0

        oee = availability * performance * quality
        return {
            "availability": round(availability * 100, 2),
            "performance":  round(performance * 100, 2),
            "quality":      round(quality * 100, 2),
            "oee":          round(oee * 100, 2),
        }

    def to_dict(self) -> dict:
        """Serialise machine state for API responses."""
        percentages = self.get_state_percentages()
        # Call once to avoid redundant computation and minor inter-call inconsistencies
        busy_t, idle_t, blocked_t, breakdown_t = self._get_live_state_times()
        total = busy_t + idle_t + blocked_t + breakdown_t
        utilization = round((busy_t / max(total, 0.001)) * 100.0, 2)
        return {
            "machine_code":      self.machine_code,
            "machine_name":      self.machine_name,
            "station":           self.station.value if isinstance(self.station, Station) else self.station,
            "station_order":     self.station_order,
            "is_parallel":       self.is_parallel,
            "state":             self.state.value,
            "current_product":   self.current_product_id,
            "utilization":       utilization,
            "busy_pct":          percentages["busy"],
            "idle_pct":          percentages["idle"],
            "blocked_pct":       percentages["blocked"],
            "breakdown_pct":     percentages["breakdown"],
            "units_processed":   self.units_processed,
            "units_rejected":    self.units_rejected,
            "breakdown_count":   self.breakdown_count,
            "busy_time":         round(busy_t, 2),
            "idle_time":         round(idle_t, 2),
            "blocked_time":      round(blocked_t, 2),
            "breakdown_time":    round(breakdown_t, 2),
            "config": {
                "processing_time_min": self.config.processing_time_min,
                "processing_time_max": self.config.processing_time_max,
                "breakdown_prob":      self.config.breakdown_prob,
                "defect_rate":         self.config.defect_rate,
            }
        }

    def reset(self):
        """Reset all metrics (start fresh simulation)."""
        with self._lock:
            self.state = MachineState.IDLE
            self.current_product_id = None
            self.processing_end_time = 0.0
            self.busy_time = 0.0
            self.idle_time = 0.0
            self.blocked_time = 0.0
            self.breakdown_time = 0.0
            self.units_processed = 0
            self.units_rejected = 0
            self.breakdown_count = 0
            self._state_start = time.time()

"""
product.py
----------
Represents a product moving through the manufacturing line.

Each product is tracked as it passes through:
  Raw Material → Cutting → Turning → Drilling → Inspection → Packaging → Finished

Product tracking simulates what photoelectric sensors at each machine's
input/output would report (part count and movement detection).
"""

import time
from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum


class ProductStatus(str, Enum):
    WAITING     = "waiting"      # Waiting for a machine to become available
    IN_PROGRESS = "in_progress"  # Currently being processed at a station
    COMPLETED   = "completed"    # Successfully finished all stages
    REJECTED    = "rejected"     # Failed quality inspection


@dataclass
class StationRecord:
    """Records how long a product spent at one station."""
    station: str
    machine_code: str
    processing_time: float        # seconds (sim time)
    start_time: float             # epoch timestamp
    end_time: Optional[float] = None
    passed_quality: bool = True


@dataclass
class Product:
    """
    A single product (work-piece) moving through the manufacturing line.
    
    Analogous to what a photoelectric sensor tracks at each station gate:
    entry count, exit count, and dwell time.
    """
    product_code: str             # e.g. "P001"
    simulation_run_id: int = 0

    status: ProductStatus = ProductStatus.WAITING
    current_station: str = "cutting"    # which station it's at/heading to
    quality_status: str = "pending"

    start_time: float = field(default_factory=time.time)
    completed_at: Optional[float] = None

    station_history: List[StationRecord] = field(default_factory=list)

    # The machine currently processing this product
    assigned_machine: Optional[str] = None

    @property
    def total_processing_time(self) -> float:
        """Sum of all station processing times (seconds)."""
        return sum(r.processing_time for r in self.station_history)

    @property
    def age(self) -> float:
        """Time since product was created (seconds)."""
        return time.time() - self.start_time

    def add_station_record(self, station: str, machine_code: str, 
                           processing_time: float, passed_quality: bool = True):
        """Log completion of a station."""
        record = StationRecord(
            station=station,
            machine_code=machine_code,
            processing_time=processing_time,
            start_time=time.time() - processing_time,
            end_time=time.time(),
            passed_quality=passed_quality,
        )
        self.station_history.append(record)

    def mark_completed(self):
        self.status = ProductStatus.COMPLETED
        self.current_station = "completed"
        self.quality_status = "good"
        self.completed_at = time.time()

    def mark_rejected(self):
        self.status = ProductStatus.REJECTED
        self.current_station = "rejected"
        self.quality_status = "defective"
        self.completed_at = time.time()

    def to_dict(self) -> dict:
        return {
            "product_code":       self.product_code,
            "status":             self.status.value,
            "current_station":    self.current_station,
            "quality_status":     self.quality_status,
            "age":                round(self.age, 1),
            "total_processing":   round(self.total_processing_time, 2),
            "assigned_machine":   self.assigned_machine,
            "station_history":    [
                {
                    "station":         r.station,
                    "machine":         r.machine_code,
                    "processing_time": round(r.processing_time, 2),
                    "passed":          r.passed_quality,
                }
                for r in self.station_history
            ],
        }

"""
engine.py
---------
The main simulation engine for the Digital Twin Manufacturing System.

This is the BRAIN of the application. It:
  1. Manages all machines (stations) on the production line.
  2. Generates new products at a configurable arrival rate.
  3. Moves products through: Cutting → Turning → Drilling → Inspection → Packaging
  4. Detects bottlenecks (highest utilization machine).
  5. Calculates throughput, OEE, utilization.
  6. Supports adding a parallel drilling machine (what-if analysis).
  7. Broadcasts real-time state via an in-memory shared state dict.

IMPORTANT:
  Current version uses SIMULATION-GENERATED real-time data.
  Physical sensor integration (current sensors, photoelectric, proximity,
  accelerometers, temperature, vision cameras, stack lights) can be added
  as a future extension by replacing the random-time generators with actual
  sensor readings from the shop floor.
"""

import time
import random
import asyncio
import threading
from typing import Dict, List, Optional, Callable, Deque
from collections import deque
from datetime import datetime

try:
    from simulation.machine import Machine, MachineConfig, MachineState, Station
    from simulation.product import Product, ProductStatus
except ImportError:
    from .machine import Machine, MachineConfig, MachineState, Station
    from .product import Product, ProductStatus


# ─────────────────── Default Machine Configurations ───────────────────────
# Processing times calibrated to produce bottleneck at Drilling station,
# consistent with research paper findings.

DEFAULT_MACHINES = [
    MachineConfig(
        machine_code="M_CUT",
        machine_name="Cutting Machine",
        station=Station.CUTTING,
        station_order=1,
        processing_time_min=4.0,
        processing_time_max=8.0,
        breakdown_prob=0.02,
        breakdown_duration_min=5.0,
        breakdown_duration_max=15.0,
        defect_rate=0.02,
    ),
    MachineConfig(
        machine_code="M_TURN",
        machine_name="Turning Machine",
        station=Station.TURNING,
        station_order=2,
        processing_time_min=5.0,
        processing_time_max=9.0,
        breakdown_prob=0.02,
        breakdown_duration_min=5.0,
        breakdown_duration_max=15.0,
        defect_rate=0.02,
    ),
    MachineConfig(
        machine_code="M_DRILL_1",
        machine_name="Drilling Machine 1",
        station=Station.DRILLING,
        station_order=3,
        processing_time_min=7.0,  # Drilling takes longer → bottleneck
        processing_time_max=12.0,
        breakdown_prob=0.03,
        breakdown_duration_min=8.0,
        breakdown_duration_max=20.0,
        defect_rate=0.03,
    ),
    MachineConfig(
        machine_code="M_INSP",
        machine_name="Inspection Station",
        station=Station.INSPECTION,
        station_order=4,
        processing_time_min=3.0,
        processing_time_max=6.0,
        breakdown_prob=0.01,
        breakdown_duration_min=3.0,
        breakdown_duration_max=10.0,
        defect_rate=0.0,   # Inspection itself doesn't cause defects
    ),
    MachineConfig(
        machine_code="M_PACK",
        machine_name="Packaging Machine",
        station=Station.PACKAGING,
        station_order=5,
        processing_time_min=2.0,
        processing_time_max=5.0,
        breakdown_prob=0.01,
        breakdown_duration_min=3.0,
        breakdown_duration_max=10.0,
        defect_rate=0.01,
    ),
]

PARALLEL_DRILL_CONFIG = MachineConfig(
    machine_code="M_DRILL_2",
    machine_name="Drilling Machine 2",
    station=Station.DRILLING,
    station_order=3,
    processing_time_min=7.0,
    processing_time_max=12.0,
    breakdown_prob=0.03,
    breakdown_duration_min=8.0,
    breakdown_duration_max=20.0,
    defect_rate=0.03,
    is_parallel=True,
)

STATION_ORDER = [
    Station.CUTTING,
    Station.TURNING,
    Station.DRILLING,
    Station.INSPECTION,
    Station.PACKAGING,
]


class SimulationEngine:
    """
    Core simulation engine for the Digital Twin manufacturing system.

    Uses a tick-based loop running in a background thread.
    Each tick (every ~0.1 wall-clock seconds) updates all machine states,
    moves products between stations, and recalculates metrics.
    """

    def __init__(self):
        # ── Configuration ──
        self.speed_multiplier: float = 5.0    # sim time per real second
        self.arrival_rate: float = 8.0        # seconds between new products (sim time)
        self.breakdown_enabled: bool = True

        # ── State ──
        self.is_running: bool = False
        self.is_paused: bool = False
        self.parallel_drilling: bool = False
        self.simulation_run_id: int = 0
        self.sim_start_time: float = 0.0

        # ── Machines ──
        self.machines: Dict[str, Machine] = {}
        self._setup_machines()

        # ── Products ──
        self.active_products: Dict[str, Product] = {}    # currently in the line
        self.completed_products: List[Product] = []
        self.rejected_products: List[Product] = []

        # ── Queues: one queue per station ──
        # Products waiting to enter that station
        self.queues: Dict[str, Deque[Product]] = {
            "cutting":    deque(),
            "turning":    deque(),
            "drilling":   deque(),
            "inspection": deque(),
            "packaging":  deque(),
        }

        # ── Metrics ──
        self.throughput_history: List[dict] = []   # [{time, count}]
        self.product_counter: int = 0
        self._last_arrival_time: float = 0.0       # sim time of last product arrival

        # ── Event log (in-memory ring buffer, newest first) ──
        self.event_log: Deque[dict] = deque(maxlen=200)

        # ── Threading ──
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # ── Callbacks (registered by FastAPI app) ──
        self.on_metrics_update: Optional[Callable] = None  # called every tick
        self.db_logger: Optional[object] = None            # DB logging service

    # ─────────────────── Machine Setup ───────────────────

    def _setup_machines(self):
        """Initialise all machines with default configs."""
        self.machines = {}
        for cfg in DEFAULT_MACHINES:
            m = Machine(cfg, speed_multiplier=self.speed_multiplier)
            m.on_state_change = self._on_machine_state_change
            self.machines[cfg.machine_code] = m

    def _get_machines_for_station(self, station: str) -> List[Machine]:
        """Return all active machines for a given station (supports parallel)."""
        return [
            m for m in self.machines.values()
            if m.station == station or m.station.value == station
        ]

    # ─────────────────── Simulation Control ───────────────────

    def start(self, run_id: int = 0, speed_multiplier: Optional[float] = None, arrival_rate: Optional[float] = None):
        """Start the simulation background thread."""
        if speed_multiplier is not None:
            self.speed_multiplier = float(speed_multiplier)
            for m in self.machines.values():
                m.speed_multiplier = float(speed_multiplier)
        if arrival_rate is not None:
            self.arrival_rate = float(arrival_rate)

        if self.is_running:
            return

        # If previous run was completed/stopped and not paused, clear previous run products
        if not self.is_paused and (len(self.completed_products) > 0 or len(self.rejected_products) > 0):
            with self._lock:
                self.completed_products.clear()
                self.rejected_products.clear()
                self.throughput_history.clear()
                for q in self.queues.values():
                    q.clear()
                self.active_products.clear()
                self.product_counter = 0
                for m in self.machines.values():
                    m.reset()

        self.simulation_run_id = run_id
        self.is_running = True
        self.is_paused = False
        self.sim_start_time = time.time()
        # Set _last_arrival_time to -arrival_rate so the very first tick
        # immediately generates a product (no delay on start)
        self._last_arrival_time = -self.arrival_rate
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._log_event("info", "Simulation STARTED", severity="success")

    def pause(self):
        """Pause the simulation (machines freeze in current state)."""
        self.is_paused = True
        self._log_event("info", "Simulation PAUSED", severity="warning")

    def resume(self):
        """Resume a paused simulation."""
        self.is_paused = False
        self._log_event("info", "Simulation RESUMED", severity="success")

    def stop(self):
        """Stop the simulation cleanly."""
        self.is_running = False
        self.is_paused = False
        self._log_event("info", "Simulation STOPPED", severity="warning")

    def reset(self):
        """Full reset: clear all state, restart fresh."""
        self.stop()
        time.sleep(0.3)   # let the thread exit

        with self._lock:
            self._setup_machines()
            for station in self.queues:
                self.queues[station].clear()
            self.active_products.clear()
            self.completed_products.clear()
            self.rejected_products.clear()
            self.throughput_history.clear()
            self.event_log.clear()
            self.product_counter = 0
            self._last_arrival_time = 0.0
            self.parallel_drilling = False
            self.sim_start_time = 0.0
            self.simulation_run_id = 0

        self._log_event("info", "Simulation RESET — all data cleared", severity="info")

    def add_parallel_drilling_machine(self) -> dict:
        """
        What-If Analysis: Add a second drilling machine in parallel.
        Both M_DRILL_1 and M_DRILL_2 will share the drilling workload.
        Load balancing: assign next job to the machine with earliest availability.
        """
        if self.parallel_drilling:
            return {"success": False, "message": "Parallel drilling already active"}

        m = Machine(PARALLEL_DRILL_CONFIG, speed_multiplier=self.speed_multiplier)
        m.on_state_change = self._on_machine_state_change
        m.reset()
        m._state_start = time.time()

        with self._lock:
            self.machines["M_DRILL_2"] = m
            self.parallel_drilling = True

        self._log_event(
            "success",
            "⚡ Parallel Drilling Machine 2 ADDED — load balancing active",
            machine_code="M_DRILL_2",
            severity="success",
        )
        return {"success": True, "message": "Parallel drilling machine added"}

    def remove_parallel_drilling_machine(self) -> dict:
        """Remove the parallel drilling machine (restore baseline)."""
        if not self.parallel_drilling:
            return {"success": False, "message": "No parallel machine to remove"}

        # Move any waiting products back to the main queue
        with self._lock:
            if "M_DRILL_2" in self.machines:
                m = self.machines.pop("M_DRILL_2")
                # If it was processing, re-queue the product
                if m.current_product_id and m.current_product_id in self.active_products:
                    product = self.active_products[m.current_product_id]
                    product.assigned_machine = None
                    self.queues["drilling"].appendleft(product)
            self.parallel_drilling = False

        self._log_event("warning", "Parallel Drilling Machine 2 REMOVED", severity="warning")
        return {"success": True, "message": "Parallel drilling machine removed"}

    # ─────────────────── Main Simulation Loop ───────────────────

    def _run_loop(self):
        """
        Main tick loop running in background thread.
        Every 0.1 real seconds:
          1. Generate new products (based on arrival rate).
          2. Process products at each station.
          3. Handle breakdowns.
          4. Move products to next station when done.
          5. Detect blockages.
        """
        tick_interval = 0.1  # real seconds per tick

        while self.is_running:
            if not self.is_paused:
                try:
                    self._tick()
                except Exception as e:
                    self._log_event("error", f"Simulation error: {e}", severity="error")

            time.sleep(tick_interval)

    def _tick(self):
        """One simulation tick — updates all state."""
        now_real = time.time()
        sim_elapsed = (now_real - self.sim_start_time) * self.speed_multiplier

        # 1. Generate new products
        self._generate_products(sim_elapsed)

        # 2. Process each station in order
        for station in STATION_ORDER:
            self._process_station(station.value)

        # 3. Record throughput snapshot every 60 sim-seconds
        self._record_throughput_snapshot(sim_elapsed)

    def _generate_products(self, sim_elapsed: float):
        """Create new products at the configured arrival rate."""
        if sim_elapsed - self._last_arrival_time >= self.arrival_rate:
            self._last_arrival_time = sim_elapsed
            self.product_counter += 1
            product_code = f"P{self.product_counter:04d}"

            product = Product(
                product_code=product_code,
                simulation_run_id=self.simulation_run_id,
                current_station="cutting",
            )
            product.status = ProductStatus.WAITING

            with self._lock:
                self.active_products[product_code] = product
                self.queues["cutting"].append(product)

            self._log_event(
                "info",
                f"📦 {product_code} arrived — entering production line → Cutting",
                product_code=product_code,
            )

    def _process_station(self, station: str):
        """
        Handle all machines at a station:
          - If BUSY and done → try to move to next station (or mark BLOCKED)
          - If IDLE/BLOCKED and queue has product → start processing
          - Handle breakdown recovery
        """
        machines_here = self._get_machines_for_station(station)

        for machine in machines_here:
            state = machine.state

            # ── Handle breakdown recovery ──
            if state == MachineState.BREAKDOWN:
                if time.time() >= machine.processing_end_time:
                    machine.set_state(MachineState.IDLE)
                    self._log_event(
                        "success",
                        f"🔧 {machine.machine_name} REPAIRED — back to service",
                        machine_code=machine.machine_code,
                        severity="success",
                    )
                continue

            # ── If BUSY, check if job is done ──
            if state == MachineState.BUSY and machine.is_done_processing():
                product_code = machine.current_product_id
                product = self.active_products.get(product_code)

                if product is None:
                    machine.set_state(MachineState.IDLE)
                    continue

                passed_quality = machine.complete_job()
                product.add_station_record(station, machine.machine_code,
                                           random.uniform(machine.config.processing_time_min,
                                                          machine.config.processing_time_max),
                                           passed_quality)

                # Inspection: if failed quality, reject the product
                if station == "inspection" and not passed_quality:
                    product.mark_rejected()
                    with self._lock:
                        self.active_products.pop(product_code, None)
                        self.rejected_products.append(product)
                    machine.set_state(MachineState.IDLE)
                    self._log_event(
                        "warning",
                        f"❌ {product_code} REJECTED at Inspection (quality fail)",
                        product_code=product_code,
                        machine_code=machine.machine_code,
                        severity="warning",
                    )
                    continue

                # Try to move product to next station
                next_station = self._get_next_station(station)

                if next_station is None:
                    # Packaging complete → product done!
                    product.mark_completed()
                    with self._lock:
                        self.active_products.pop(product_code, None)
                        self.completed_products.append(product)
                    machine.set_state(MachineState.IDLE)
                    self._log_event(
                        "success",
                        f"✅ {product_code} COMPLETED — Finished Product",
                        product_code=product_code,
                        machine_code=machine.machine_code,
                        severity="success",
                    )
                    # Record throughput timestamp
                    self.throughput_history.append({
                        "time": time.time(),
                        "total": len(self.completed_products),
                    })
                else:
                    # Check if next station's queue can accept it
                    next_machines = self._get_machines_for_station(next_station)
                    next_all_busy = all(
                        m.state == MachineState.BUSY or m.state == MachineState.BREAKDOWN
                        for m in next_machines
                    )

                    product.current_station = next_station
                    product.assigned_machine = None

                    with self._lock:
                        self.queues[next_station].append(product)

                    # If next station is saturated, go BLOCKED
                    if next_all_busy and len(self.queues[next_station]) > len(next_machines):
                        machine.set_state(MachineState.BLOCKED)
                    else:
                        machine.set_state(MachineState.IDLE)

                    self._log_event(
                        "info",
                        f"➡ {product_code} moved: {station.capitalize()} → {next_station.capitalize()}",
                        product_code=product_code,
                        machine_code=machine.machine_code,
                    )

                # Check for breakdown after finishing a job
                if self.breakdown_enabled and machine.state != MachineState.BLOCKED:
                    if machine.check_breakdown():
                        duration = random.uniform(
                            machine.config.breakdown_duration_min,
                            machine.config.breakdown_duration_max
                        ) / self.speed_multiplier  # real seconds
                        machine.processing_end_time = time.time() + duration
                        machine.set_state(MachineState.BREAKDOWN)
                        self._log_event(
                            "error",
                            f"⚠️  {machine.machine_name} BREAKDOWN! Recovery in ~{duration*self.speed_multiplier:.1f}s",
                            machine_code=machine.machine_code,
                            severity="error",
                        )

            # ── If IDLE or BLOCKED (machine free), pull from queue ──
            elif state in (MachineState.IDLE, MachineState.BLOCKED):
                with self._lock:
                    queue = self.queues.get(station, deque())
                    if queue:
                        # For parallel drilling: pick machine with lowest busy time (load balance)
                        if station == "drilling" and self.parallel_drilling:
                            best = self._pick_best_drilling_machine()
                            if best and best.machine_code == machine.machine_code:
                                product = queue.popleft()
                            else:
                                continue  # let the other machine take it
                        else:
                            product = queue.popleft()

                        product.status = ProductStatus.IN_PROGRESS
                        product.assigned_machine = machine.machine_code
                        proc_time = machine.start_processing(product.product_code)

                        self._log_event(
                            "info",
                            f"🔄 {machine.machine_name} started on {product.product_code} "
                            f"(~{proc_time:.1f}s)",
                            product_code=product.product_code,
                            machine_code=machine.machine_code,
                        )

    def _pick_best_drilling_machine(self) -> Optional[Machine]:
        """
        Load balancing for parallel drilling:
        Return the drilling machine with the LOWEST busy-time ratio
        (whichever is more available).
        This simulates an intelligent work scheduler.
        """
        drill_machines = self._get_machines_for_station("drilling")
        idle_ones = [m for m in drill_machines if m.state == MachineState.IDLE]
        if idle_ones:
            # Pick the one with lower utilization for balanced workload
            return min(idle_ones, key=lambda m: m.get_utilization())
        return None

    def _get_next_station(self, current_station: str) -> Optional[str]:
        """Return the next station name, or None if packaging is complete."""
        order = ["cutting", "turning", "drilling", "inspection", "packaging"]
        try:
            idx = order.index(current_station)
            return order[idx + 1] if idx + 1 < len(order) else None
        except ValueError:
            return None

    # ─────────────────── Throughput Tracking ───────────────────

    def _record_throughput_snapshot(self, sim_elapsed: float):
        """Maintain a compact history list (used for chart)."""
        # Already recorded per-completion above; just keep history manageable
        if len(self.throughput_history) > 500:
            self.throughput_history = self.throughput_history[-300:]

    # ─────────────────── Metrics API ───────────────────

    def get_all_machines(self) -> List[dict]:
        """Return list of machine dicts for API."""
        with self._lock:
            machines_snapshot = list(self.machines.values())
        return [m.to_dict() for m in sorted(machines_snapshot, key=lambda x: x.station_order)]

    def get_bottleneck(self) -> dict:
        """
        Identify bottleneck: machine with highest busy-state percentage.
        (Research paper method: highest busy% = primary bottleneck)
        """
        best_machine = None
        best_util = -1.0

        for machine in self.machines.values():
            util = machine.get_utilization()
            if util > best_util:
                best_util = util
                best_machine = machine

        if best_machine is None or best_util <= 0.0:
            return {
                "bottleneck": None,
                "machine_name": "None (System Idle)",
                "station": "None",
                "utilization": 0.0,
                "state": "IDLE",
            }

        return {
            "bottleneck":    best_machine.machine_code,
            "machine_name":  best_machine.machine_name,
            "station":       best_machine.station.value if hasattr(best_machine.station, 'value') else best_machine.station,
            "utilization":   round(best_util, 2),
            "state":         best_machine.state.value,
        }

    def get_throughput(self) -> dict:
        """Calculate throughput metrics from completed products."""
        # Take a snapshot under lock to avoid race conditions with the sim thread
        with self._lock:
            total = len(self.completed_products)
            rejected = len(self.rejected_products)
            completed_snapshot = list(self.completed_products)

        # Products per minute (real time, scaled to 1-minute windows)
        now = time.time()
        window_60s = [
            p for p in completed_snapshot
            if p.completed_at is not None and (now - p.completed_at) < 60
        ]
        per_minute = len(window_60s)

        # Per hour estimate
        elapsed_real = max(now - self.sim_start_time, 1.0)  # seconds
        elapsed_sim = elapsed_real * self.speed_multiplier   # sim-seconds
        if elapsed_sim > 0:
            per_hour_sim = (total / elapsed_sim) * 3600      # units per sim-hour
        else:
            per_hour_sim = 0.0

        return {
            "total_completed":   total,
            "total_rejected":    rejected,
            "per_minute_real":   per_minute,
            "per_hour_sim":      round(per_hour_sim, 1),
            "elapsed_sim_min":   round(elapsed_sim / 60, 1),
        }

    def get_oee_summary(self) -> dict:
        """Calculate OEE for each machine and system average."""
        if not self.sim_start_time:
            # Simulation hasn't started yet
            return {"machines": {}, "system_oee": 0.0}
        planned_time = max(
            (time.time() - self.sim_start_time) * self.speed_multiplier,
            1.0
        )
        with self._lock:
            machines_snapshot = list(self.machines.items())
        oee_data = {}
        for code, machine in machines_snapshot:
            ideal_cycle = machine.config.processing_time_min
            oee_data[code] = machine.calculate_oee(ideal_cycle, planned_time)

        if oee_data:
            avg_oee = sum(d["oee"] for d in oee_data.values()) / len(oee_data)
        else:
            avg_oee = 0.0

        return {"machines": oee_data, "system_oee": round(avg_oee, 2)}

    def get_workload_distribution(self) -> List[dict]:
        """Workload = units_processed share per machine."""
        total_units = sum(m.units_processed for m in self.machines.values())
        if total_units == 0:
            total_units = 1

        result = []
        for machine in sorted(self.machines.values(), key=lambda x: x.station_order):
            result.append({
                "machine_code": machine.machine_code,
                "machine_name": machine.machine_name,
                "station":      machine.station.value if hasattr(machine.station, 'value') else machine.station,
                "units":        machine.units_processed,
                "workload_pct": round((machine.units_processed / total_units) * 100, 2),
            })
        return result

    def get_active_products(self) -> List[dict]:
        """Active products currently in the production line."""
        with self._lock:
            return [p.to_dict() for p in self.active_products.values()]

    def get_completed_products(self, limit: int = 50) -> List[dict]:
        """Most recently completed products."""
        with self._lock:
            snapshot = list(self.completed_products[-limit:])
        return [p.to_dict() for p in snapshot]

    def get_simulation_status(self) -> dict:
        """High-level simulation status."""
        now = time.time()
        elapsed = (now - self.sim_start_time) if self.sim_start_time else 0
        sim_time = elapsed * self.speed_multiplier

        hours = int(sim_time // 3600)
        minutes = int((sim_time % 3600) // 60)
        seconds = int(sim_time % 60)

        return {
            "is_running":        self.is_running,
            "is_paused":         self.is_paused,
            "parallel_drilling": self.parallel_drilling,
            "speed_multiplier":  self.speed_multiplier,
            "arrival_rate":      self.arrival_rate,
            "sim_time_str":      f"{hours:02d}:{minutes:02d}:{seconds:02d}",
            "sim_elapsed_sec":   round(sim_time, 1),
            "product_counter":   self.product_counter,
            "completed":         len(self.completed_products),
            "rejected":          len(self.rejected_products),
            "in_progress":       len(self.active_products),
            "run_id":            self.simulation_run_id,
        }

    def get_full_dashboard_data(self) -> dict:
        """One-shot data grab for the dashboard polling endpoint."""
        return {
            "status":     self.get_simulation_status(),
            "machines":   self.get_all_machines(),
            "throughput": self.get_throughput(),
            "bottleneck": self.get_bottleneck(),
            "oee":        self.get_oee_summary(),
            "workload":   self.get_workload_distribution(),
            "products":   self.get_active_products(),
            "event_log":  list(self.event_log)[:50],
        }

    def update_machine_config(self, machine_code: str, config: dict) -> dict:
        """Update configurable parameters for a specific machine."""
        if machine_code not in self.machines:
            return {"success": False, "message": f"Machine {machine_code} not found"}

        machine = self.machines[machine_code]
        cfg = machine.config

        if "processing_time_min" in config:
            cfg.processing_time_min = float(config["processing_time_min"])
        if "processing_time_max" in config:
            cfg.processing_time_max = float(config["processing_time_max"])
        if "breakdown_prob" in config:
            cfg.breakdown_prob = float(config["breakdown_prob"])
        if "breakdown_duration_min" in config:
            cfg.breakdown_duration_min = float(config["breakdown_duration_min"])
        if "breakdown_duration_max" in config:
            cfg.breakdown_duration_max = float(config["breakdown_duration_max"])
        if "defect_rate" in config:
            cfg.defect_rate = float(config["defect_rate"])

        return {"success": True, "message": f"Config updated for {machine_code}"}

    def update_simulation_config(self, config: dict) -> dict:
        """Update global simulation parameters."""
        if "speed_multiplier" in config:
            self.speed_multiplier = float(config["speed_multiplier"])
            for m in self.machines.values():
                m.speed_multiplier = self.speed_multiplier
        if "arrival_rate" in config:
            self.arrival_rate = float(config["arrival_rate"])
        if "breakdown_enabled" in config:
            self.breakdown_enabled = bool(config["breakdown_enabled"])
        return {"success": True, "config": {
            "speed_multiplier": self.speed_multiplier,
            "arrival_rate":     self.arrival_rate,
            "breakdown_enabled": self.breakdown_enabled,
        }}

    # ─────────────────── Event Logging ───────────────────

    def _log_event(self, event_type: str, message: str,
                   machine_code: str = None, product_code: str = None,
                   severity: str = "info"):
        """Add event to the in-memory ring buffer."""
        event = {
            "id":           int(time.time() * 1000),
            "time":         datetime.now().strftime("%H:%M:%S"),
            "type":         event_type,
            "message":      message,
            "machine_code": machine_code,
            "product_code": product_code,
            "severity":     severity,
        }
        self.event_log.appendleft(event)   # newest first

    def _on_machine_state_change(self, machine: Machine, old: MachineState, 
                                  new: MachineState, product_id: str):
        """Callback fired when any machine changes state."""
        self._log_event(
            "state_change",
            f"{machine.machine_name}: {old.value} → {new.value}",
            machine_code=machine.machine_code,
            product_code=product_id,
            severity="info",
        )


# ────────────────────── Singleton Instance ───────────────────────────
# Shared across all FastAPI route handlers

sim_engine = SimulationEngine()

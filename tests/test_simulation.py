"""
test_simulation.py
------------------
Unit tests for the Digital Twin Manufacturing Simulation.

Tests cover:
  - Machine state transitions
  - Product movement through stations
  - Utilization calculation
  - OEE calculation
  - Bottleneck detection
  - Throughput calculation
  - Parallel machine allocation
  - What-if improvement percentage

Run with:
  cd digital-twin-manufacturing/backend
  python -m pytest ../tests/test_simulation.py -v
"""

import sys
import os
import time

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from simulation.machine import Machine, MachineConfig, MachineState, Station
from simulation.product import Product, ProductStatus
from simulation.engine import SimulationEngine


# ─────────────────────────────────────────────────────────────────
# FIXTURES / HELPERS
# ─────────────────────────────────────────────────────────────────

def make_machine(code="M_TEST", station=Station.CUTTING, order=1,
                 min_t=2.0, max_t=4.0, breakdown_prob=0.0, defect_rate=0.0):
    cfg = MachineConfig(
        machine_code=code,
        machine_name=f"Test Machine {code}",
        station=station,
        station_order=order,
        processing_time_min=min_t,
        processing_time_max=max_t,
        breakdown_prob=breakdown_prob,
        defect_rate=defect_rate,
    )
    return Machine(cfg, speed_multiplier=1.0)


# ─────────────────────────────────────────────────────────────────
# TEST: Machine State Transitions
# ─────────────────────────────────────────────────────────────────

class TestMachineStateTransitions:
    def test_initial_state_is_idle(self):
        m = make_machine()
        assert m.state == MachineState.IDLE

    def test_start_processing_sets_busy(self):
        m = make_machine()
        m.start_processing("P001")
        assert m.state == MachineState.BUSY
        assert m.current_product_id == "P001"

    def test_set_state_blocked(self):
        m = make_machine()
        m.start_processing("P001")
        m.set_state(MachineState.BLOCKED, "P001")
        assert m.state == MachineState.BLOCKED

    def test_set_state_breakdown(self):
        m = make_machine()
        m.set_state(MachineState.BREAKDOWN)
        assert m.state == MachineState.BREAKDOWN

    def test_set_state_idle_clears_product(self):
        m = make_machine()
        m.start_processing("P001")
        m.set_state(MachineState.IDLE)
        assert m.current_product_id is None

    def test_state_accumulation(self):
        """Time in each state should accumulate."""
        m = make_machine()
        m.set_state(MachineState.BUSY, "P001")
        time.sleep(0.05)
        m.set_state(MachineState.IDLE)
        # Busy time should be about 0.05 seconds
        assert m.busy_time > 0.01, f"Expected busy_time > 0.01, got {m.busy_time}"


# ─────────────────────────────────────────────────────────────────
# TEST: Utilization Calculation
# ─────────────────────────────────────────────────────────────────

class TestUtilizationCalculation:
    def test_zero_utilization_when_idle(self):
        m = make_machine()
        time.sleep(0.05)  # Let some idle time accumulate
        # Utilization = busy / total → 0 when all time is idle
        util = m.get_utilization()
        assert util == 0.0, f"Expected 0% util when idle, got {util}"

    def test_utilization_increases_when_busy(self):
        m = make_machine()
        time.sleep(0.02)  # some idle
        m.set_state(MachineState.BUSY, "P001")
        time.sleep(0.05)  # some busy
        m.set_state(MachineState.IDLE)
        util = m.get_utilization()
        assert 0 < util < 100, f"Expected 0 < util < 100, got {util}"

    def test_utilization_formula(self):
        """Manually force busy_time and check calculation."""
        m = make_machine()
        # Manually set accumulated times
        m.busy_time = 70.0
        m.idle_time = 30.0
        m.state = MachineState.IDLE
        m._state_start = time.time()  # reset current bucket

        time.sleep(0.001)  # tiny tick so total > 0
        util = m.get_utilization()
        # Expect roughly 70/(70+30+epsilon) ≈ 70%
        assert 60 < util < 80, f"Expected ~70% util, got {util}"

    def test_state_percentages_sum_to_100(self):
        m = make_machine()
        m.busy_time = 40.0
        m.idle_time = 30.0
        m.blocked_time = 20.0
        m.breakdown_time = 10.0
        m.state = MachineState.IDLE
        m._state_start = time.time()
        time.sleep(0.001)

        pcts = m.get_state_percentages()
        total = sum(pcts.values())
        assert abs(total - 100.0) < 1.0, f"Percentages should sum to ~100, got {total}"


# ─────────────────────────────────────────────────────────────────
# TEST: OEE Calculation
# ─────────────────────────────────────────────────────────────────

class TestOEECalculation:
    def test_oee_zero_when_no_units(self):
        m = make_machine()
        oee = m.calculate_oee(ideal_cycle_time=5.0, planned_time=100.0)
        assert oee["oee"] == 0.0

    def test_oee_availability_drops_with_breakdown(self):
        m = make_machine()
        m.breakdown_time = 50.0  # 50% of time was breakdown
        oee = m.calculate_oee(ideal_cycle_time=5.0, planned_time=100.0)
        # Availability = (100 - 50) / 100 = 0.5 = 50%
        assert abs(oee["availability"] - 50.0) < 5.0, f"Expected ~50% availability, got {oee['availability']}"

    def test_oee_quality_affects_oee(self):
        m = make_machine()
        m.units_processed = 10
        m.units_rejected = 5  # 50% defects
        oee = m.calculate_oee(ideal_cycle_time=5.0, planned_time=100.0)
        assert oee["quality"] == 50.0, f"Expected 50% quality, got {oee['quality']}"

    def test_oee_is_product_of_three(self):
        m = make_machine()
        m.units_processed = 10
        m.units_rejected = 0  # perfect quality
        m.breakdown_time = 0  # no breakdown
        m.busy_time = 50.0

        oee = m.calculate_oee(ideal_cycle_time=5.0, planned_time=100.0)
        expected = (oee["availability"] / 100) * (oee["performance"] / 100) * (oee["quality"] / 100) * 100
        assert abs(oee["oee"] - expected) < 0.5, f"OEE {oee['oee']} ≠ A×P×Q ({expected})"


# ─────────────────────────────────────────────────────────────────
# TEST: Product Movement
# ─────────────────────────────────────────────────────────────────

class TestProductMovement:
    def test_product_initial_station(self):
        p = Product(product_code="P001", current_station="cutting")
        assert p.current_station == "cutting"
        assert p.status == ProductStatus.WAITING

    def test_product_mark_completed(self):
        p = Product(product_code="P001")
        p.mark_completed()
        assert p.status == ProductStatus.COMPLETED
        assert p.current_station == "completed"
        assert p.completed_at is not None

    def test_product_mark_rejected(self):
        p = Product(product_code="P001")
        p.mark_rejected()
        assert p.status == ProductStatus.REJECTED
        assert p.quality_status == "defective"

    def test_station_history_accumulates(self):
        p = Product(product_code="P001")
        p.add_station_record("cutting", "M_CUT", 5.0, True)
        p.add_station_record("turning", "M_TURN", 7.0, True)
        assert len(p.station_history) == 2
        assert p.total_processing_time == 12.0


# ─────────────────────────────────────────────────────────────────
# TEST: Bottleneck Detection
# ─────────────────────────────────────────────────────────────────

class TestBottleneckDetection:
    def test_bottleneck_is_highest_utilization(self):
        engine = SimulationEngine()
        # Manually set busy times to force drilling as bottleneck
        engine.machines["M_CUT"].busy_time   = 30.0
        engine.machines["M_TURN"].busy_time  = 40.0
        engine.machines["M_DRILL_1"].busy_time = 80.0  # highest
        engine.machines["M_INSP"].busy_time  = 20.0
        engine.machines["M_PACK"].busy_time  = 15.0

        # All in IDLE so only accumulated busy times count
        now = time.time()
        for m in engine.machines.values():
            m.state = MachineState.IDLE
            m.idle_time = 0.0
            m.blocked_time = 0.0
            m.breakdown_time = 0.0
            m._state_start = now

        bottleneck = engine.get_bottleneck()
        assert bottleneck["bottleneck"] == "M_DRILL_1", \
            f"Expected M_DRILL_1 as bottleneck, got {bottleneck['bottleneck']}"

    def test_bottleneck_changes_dynamically(self):
        """If we change which machine has most busy time, bottleneck updates."""
        engine = SimulationEngine()
        # Make cutting the bottleneck
        engine.machines["M_CUT"].busy_time    = 90.0
        engine.machines["M_DRILL_1"].busy_time = 50.0
        now = time.time()
        for m in engine.machines.values():
            m.state = MachineState.IDLE
            m.idle_time = 0.0
            m.blocked_time = 0.0
            m.breakdown_time = 0.0
            m._state_start = now

        bottleneck = engine.get_bottleneck()
        assert bottleneck["bottleneck"] == "M_CUT", \
            f"Expected M_CUT as bottleneck, got {bottleneck['bottleneck']}"


# ─────────────────────────────────────────────────────────────────
# TEST: Throughput Calculation
# ─────────────────────────────────────────────────────────────────

class TestThroughputCalculation:
    def test_zero_throughput_before_completion(self):
        engine = SimulationEngine()
        engine.sim_start_time = time.time()
        t = engine.get_throughput()
        assert t["total_completed"] == 0
        assert t["total_rejected"] == 0

    def test_throughput_counts_completed(self):
        engine = SimulationEngine()
        engine.sim_start_time = time.time() - 60  # 60 seconds ago

        # Add fake completed products
        for i in range(10):
            p = Product(product_code=f"P{i:03d}")
            p.mark_completed()
            engine.completed_products.append(p)

        t = engine.get_throughput()
        assert t["total_completed"] == 10

    def test_throughput_improvement_formula(self):
        """Test the improvement percentage formula used in what-if."""
        baseline = 478.0
        modified = 760.0
        improvement = ((modified - baseline) / baseline) * 100
        assert abs(improvement - 59.0) < 1.0, f"Expected ~59% improvement, got {improvement:.1f}%"


# ─────────────────────────────────────────────────────────────────
# TEST: Parallel Machine Allocation
# ─────────────────────────────────────────────────────────────────

class TestParallelMachineAllocation:
    def test_add_parallel_drilling_machine(self):
        engine = SimulationEngine()
        assert not engine.parallel_drilling
        assert "M_DRILL_2" not in engine.machines

        result = engine.add_parallel_drilling_machine()
        assert result["success"] is True
        assert engine.parallel_drilling is True
        assert "M_DRILL_2" in engine.machines

    def test_adding_parallel_twice_fails(self):
        engine = SimulationEngine()
        engine.add_parallel_drilling_machine()
        result2 = engine.add_parallel_drilling_machine()
        assert result2["success"] is False

    def test_remove_parallel_machine(self):
        engine = SimulationEngine()
        engine.add_parallel_drilling_machine()
        result = engine.remove_parallel_drilling_machine()
        assert result["success"] is True
        assert not engine.parallel_drilling
        assert "M_DRILL_2" not in engine.machines

    def test_load_balancing_picks_lower_utilization(self):
        engine = SimulationEngine()
        engine.add_parallel_drilling_machine()

        # Set M_DRILL_1 to high utilization, M_DRILL_2 to low
        engine.machines["M_DRILL_1"].busy_time = 80.0
        engine.machines["M_DRILL_2"].busy_time = 10.0

        for code in ["M_DRILL_1", "M_DRILL_2"]:
            engine.machines[code].state = MachineState.IDLE
            engine.machines[code]._state_start = time.time()

        best = engine._pick_best_drilling_machine()
        assert best is not None
        assert best.machine_code == "M_DRILL_2", \
            f"Expected M_DRILL_2 (lower util), got {best.machine_code}"


# ─────────────────────────────────────────────────────────────────
# TEST: Machine Reset
# ─────────────────────────────────────────────────────────────────

class TestMachineReset:
    def test_reset_clears_all_metrics(self):
        m = make_machine()
        m.busy_time = 100.0
        m.idle_time = 50.0
        m.units_processed = 20
        m.breakdown_count = 3
        m.reset()

        assert m.busy_time == 0.0
        assert m.idle_time == 0.0
        assert m.units_processed == 0
        assert m.breakdown_count == 0
        assert m.state == MachineState.IDLE


# ─────────────────────────────────────────────────────────────────
# TEST: Configuration Update
# ─────────────────────────────────────────────────────────────────

class TestConfigUpdate:
    def test_update_machine_config(self):
        engine = SimulationEngine()
        result = engine.update_machine_config("M_DRILL_1", {
            "processing_time_min": 10.0,
            "processing_time_max": 15.0,
            "breakdown_prob": 0.05,
        })
        assert result["success"] is True
        assert engine.machines["M_DRILL_1"].config.processing_time_min == 10.0
        assert engine.machines["M_DRILL_1"].config.breakdown_prob == 0.05

    def test_update_nonexistent_machine(self):
        engine = SimulationEngine()
        result = engine.update_machine_config("M_FAKE", {"processing_time_min": 5.0})
        assert result["success"] is False

    def test_update_simulation_config(self):
        engine = SimulationEngine()
        result = engine.update_simulation_config({"speed_multiplier": 10.0, "arrival_rate": 5.0})
        assert result["success"] is True
        assert engine.speed_multiplier == 10.0
        assert engine.arrival_rate == 5.0


# ─────────────────────────────────────────────────────────────────
# TEST: Engine Start/Stop/Reset
# ─────────────────────────────────────────────────────────────────

class TestEngineControl:
    def test_start_stop(self):
        engine = SimulationEngine()
        engine.start(run_id=0)
        time.sleep(0.1)
        assert engine.is_running is True
        engine.stop()
        time.sleep(0.15)
        assert engine.is_running is False

    def test_reset_clears_products(self):
        engine = SimulationEngine()
        engine.start(run_id=0)
        time.sleep(0.5)   # Let some products generate
        engine.stop()
        time.sleep(0.2)
        engine.reset()
        assert len(engine.active_products) == 0
        assert len(engine.completed_products) == 0
        assert engine.product_counter == 0


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "--tb=short"])

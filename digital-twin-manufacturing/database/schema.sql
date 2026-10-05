-- ============================================================
-- Digital Twin Manufacturing System - MySQL Database Schema
-- Based on: Digital Twin-Based Bottleneck Analysis and 
--            Parallel Machine Allocation for Improving 
--            Manufacturing System Performance
-- ============================================================

CREATE DATABASE IF NOT EXISTS digital_twin_mfg;
USE digital_twin_mfg;

-- ============================================================
-- Table: simulation_runs
-- Tracks each simulation session
-- ============================================================
CREATE TABLE IF NOT EXISTS simulation_runs (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    run_name        VARCHAR(100) DEFAULT 'Simulation Run',
    status          ENUM('running','paused','stopped','completed') DEFAULT 'stopped',
    mode            ENUM('baseline','modified') DEFAULT 'baseline',
    parallel_drilling TINYINT(1) DEFAULT 0,  -- 0 = single drilling, 1 = parallel drilling
    speed_multiplier FLOAT DEFAULT 1.0,
    start_time      DATETIME DEFAULT CURRENT_TIMESTAMP,
    end_time        DATETIME NULL,
    total_products  INT DEFAULT 0,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- ============================================================
-- Table: machines
-- Represents each manufacturing station
-- ============================================================
CREATE TABLE IF NOT EXISTS machines (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    machine_code    VARCHAR(20) UNIQUE NOT NULL,  -- e.g. M_CUT, M_TURN, M_DRILL_1
    machine_name    VARCHAR(100) NOT NULL,          -- e.g. Cutting Machine
    station         ENUM('cutting','turning','drilling','inspection','packaging') NOT NULL,
    station_order   INT NOT NULL,                   -- 1=cutting, 2=turning, 3=drilling, 4=inspection, 5=packaging
    is_parallel     TINYINT(1) DEFAULT 0,           -- 1 if this is an extra parallel machine
    status          ENUM('BUSY','IDLE','BLOCKED','BREAKDOWN') DEFAULT 'IDLE',
    processing_time_min FLOAT DEFAULT 5.0,          -- min processing time in seconds (sim)
    processing_time_max FLOAT DEFAULT 10.0,         -- max processing time in seconds (sim)
    breakdown_prob  FLOAT DEFAULT 0.02,             -- probability of breakdown per job
    breakdown_duration_min FLOAT DEFAULT 5.0,       -- min breakdown duration seconds
    breakdown_duration_max FLOAT DEFAULT 15.0,      -- max breakdown duration seconds
    current_product_id VARCHAR(20) DEFAULT NULL,
    busy_time       FLOAT DEFAULT 0.0,              -- cumulative seconds
    idle_time       FLOAT DEFAULT 0.0,
    blocked_time    FLOAT DEFAULT 0.0,
    breakdown_time  FLOAT DEFAULT 0.0,
    units_processed INT DEFAULT 0,
    breakdown_count INT DEFAULT 0,
    defect_rate     FLOAT DEFAULT 0.03,             -- fraction of products that are defective
    is_active       TINYINT(1) DEFAULT 1,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- ============================================================
-- Table: products
-- Each product moving through the manufacturing line
-- ============================================================
CREATE TABLE IF NOT EXISTS products (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    product_code    VARCHAR(20) UNIQUE NOT NULL,    -- e.g. P001
    simulation_run_id INT,
    status          ENUM('in_progress','completed','rejected','waiting') DEFAULT 'waiting',
    current_station ENUM('cutting','turning','drilling','inspection','packaging','completed','rejected') DEFAULT 'cutting',
    quality_status  ENUM('good','defective','pending') DEFAULT 'pending',
    start_time      DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at    DATETIME NULL,
    total_processing_time FLOAT DEFAULT 0.0,        -- seconds
    FOREIGN KEY (simulation_run_id) REFERENCES simulation_runs(id) ON DELETE SET NULL
);

-- ============================================================
-- Table: production_records
-- Each time a product passes through a station
-- ============================================================
CREATE TABLE IF NOT EXISTS production_records (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    product_id      INT NOT NULL,
    machine_id      INT NOT NULL,
    station         VARCHAR(50) NOT NULL,
    status          ENUM('started','completed','rejected') DEFAULT 'started',
    processing_time FLOAT NOT NULL,                 -- actual processing time in seconds
    start_time      DATETIME DEFAULT CURRENT_TIMESTAMP,
    end_time        DATETIME NULL,
    simulation_run_id INT,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    FOREIGN KEY (machine_id) REFERENCES machines(id),
    FOREIGN KEY (simulation_run_id) REFERENCES simulation_runs(id) ON DELETE SET NULL
);

-- ============================================================
-- Table: machine_events
-- State change events for each machine
-- ============================================================
CREATE TABLE IF NOT EXISTS machine_events (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    machine_id      INT NOT NULL,
    machine_code    VARCHAR(20) NOT NULL,
    event_type      ENUM('BUSY','IDLE','BLOCKED','BREAKDOWN','REPAIR','STATE_CHANGE') NOT NULL,
    old_state       VARCHAR(20) DEFAULT NULL,
    new_state       VARCHAR(20) DEFAULT NULL,
    product_code    VARCHAR(20) DEFAULT NULL,
    description     TEXT DEFAULT NULL,
    start_time      DATETIME DEFAULT CURRENT_TIMESTAMP,
    end_time        DATETIME NULL,
    duration        FLOAT DEFAULT 0.0,              -- seconds
    simulation_run_id INT,
    FOREIGN KEY (machine_id) REFERENCES machines(id),
    FOREIGN KEY (simulation_run_id) REFERENCES simulation_runs(id) ON DELETE SET NULL
);

-- ============================================================
-- Table: machine_metrics
-- Periodic snapshots of machine performance metrics
-- ============================================================
CREATE TABLE IF NOT EXISTS machine_metrics (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    machine_id          INT NOT NULL,
    machine_code        VARCHAR(20) NOT NULL,
    simulation_run_id   INT,
    snapshot_time       DATETIME DEFAULT CURRENT_TIMESTAMP,
    utilization         FLOAT DEFAULT 0.0,          -- busy/(busy+idle+blocked+breakdown)*100
    busy_percentage     FLOAT DEFAULT 0.0,
    idle_percentage     FLOAT DEFAULT 0.0,
    blocked_percentage  FLOAT DEFAULT 0.0,
    breakdown_percentage FLOAT DEFAULT 0.0,
    throughput          FLOAT DEFAULT 0.0,          -- units/hour at this snapshot
    oee_availability    FLOAT DEFAULT 0.0,
    oee_performance     FLOAT DEFAULT 0.0,
    oee_quality         FLOAT DEFAULT 0.0,
    oee                 FLOAT DEFAULT 0.0,
    units_processed     INT DEFAULT 0,
    FOREIGN KEY (machine_id) REFERENCES machines(id),
    FOREIGN KEY (simulation_run_id) REFERENCES simulation_runs(id) ON DELETE SET NULL
);

-- ============================================================
-- Table: what_if_results
-- Results from what-if analysis (baseline vs modified)
-- ============================================================
CREATE TABLE IF NOT EXISTS what_if_results (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    analysis_time           DATETIME DEFAULT CURRENT_TIMESTAMP,
    baseline_run_id         INT,
    modified_run_id         INT,
    baseline_throughput     FLOAT DEFAULT 0.0,
    modified_throughput     FLOAT DEFAULT 0.0,
    throughput_improvement  FLOAT DEFAULT 0.0,      -- percentage
    baseline_drilling_util  FLOAT DEFAULT 0.0,
    modified_drilling_util  FLOAT DEFAULT 0.0,
    baseline_oee            FLOAT DEFAULT 0.0,
    modified_oee            FLOAT DEFAULT 0.0,
    oee_improvement         FLOAT DEFAULT 0.0,
    baseline_completed      INT DEFAULT 0,
    modified_completed      INT DEFAULT 0,
    notes                   TEXT DEFAULT NULL,
    FOREIGN KEY (baseline_run_id) REFERENCES simulation_runs(id) ON DELETE SET NULL,
    FOREIGN KEY (modified_run_id) REFERENCES simulation_runs(id) ON DELETE SET NULL
);

-- ============================================================
-- Table: event_log
-- Human-readable event log for frontend display
-- ============================================================
CREATE TABLE IF NOT EXISTS event_log (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    event_time      DATETIME DEFAULT CURRENT_TIMESTAMP,
    event_type      VARCHAR(50) NOT NULL,
    message         TEXT NOT NULL,
    machine_code    VARCHAR(20) DEFAULT NULL,
    product_code    VARCHAR(20) DEFAULT NULL,
    severity        ENUM('info','warning','error','success') DEFAULT 'info',
    simulation_run_id INT,
    FOREIGN KEY (simulation_run_id) REFERENCES simulation_runs(id) ON DELETE SET NULL
);

-- ============================================================
-- Seed: Default machines for the manufacturing line
-- ============================================================
INSERT INTO machines (machine_code, machine_name, station, station_order, is_parallel,
    processing_time_min, processing_time_max, breakdown_prob, breakdown_duration_min, 
    breakdown_duration_max, defect_rate) VALUES
('M_CUT',    'Cutting Machine',    'cutting',    1, 0, 4.0,  8.0,  0.02, 5.0,  15.0, 0.02),
('M_TURN',   'Turning Machine',    'turning',    2, 0, 5.0,  9.0,  0.02, 5.0,  15.0, 0.02),
('M_DRILL_1','Drilling Machine 1', 'drilling',   3, 0, 7.0, 12.0,  0.03, 8.0,  20.0, 0.03),
('M_INSP',   'Inspection Station', 'inspection', 4, 0, 3.0,  6.0,  0.01, 3.0,  10.0, 0.0),
('M_PACK',   'Packaging Machine',  'packaging',  5, 0, 2.0,  5.0,  0.01, 3.0,  10.0, 0.01);

-- Note: M_DRILL_2 is created dynamically when the user clicks "Add Parallel Drilling Machine"

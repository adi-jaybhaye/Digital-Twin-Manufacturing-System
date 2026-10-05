# Digital Twin Manufacturing System

> **Web-Based Digital Twin for Real-Time Manufacturing Bottleneck Analysis and Parallel Machine Allocation**  
> Calibrated to and based on the research paper: *"Digital Twin-Based Bottleneck Analysis and Parallel Machine Allocation for Improving Manufacturing System Performance"*.

---

## 📌 Project Overview

This application is an Industry 4.0 Digital Twin of a discrete manufacturing assembly line. It simulates the physical workflow of raw materials entering a production system and moving through five consecutive processing stations:

```
[Raw Material] ➔ [Cutting] ➔ [Turning] ➔ [Drilling] ➔ [Inspection] ➔ [Packaging] ➔ [Finished Goods]
```

### Key Capabilities
- **Real-Time Factory Floor Telemetry**: Dynamic tracking of machine states (`BUSY`, `IDLE`, `BLOCKED`, `BREAKDOWN`), current WIP units, and cumulative processing times.
- **Dynamic Bottleneck Detection**: Automatically evaluates utilization rates across all stations in real-time. Identifies the primary constraint (the Drilling machine) based on highest busy-state percentage.
- **What-If Analysis & Parallel Machine Allocation**: Test the impact of adding a second parallel drilling machine to relieve the bottleneck, comparing throughput rates, busy utilization, and system OEE.
- **OEE Analytics**: Live Overall Equipment Effectiveness calculation incorporating Availability, Performance, and Quality metrics.
- **Dual Persistence Architecture**: Production-grade MySQL support via PyMySQL with automatic zero-configuration SQLite fallback for instant local execution.

---

## 🎨 UI Design & Theme

- **Palette**: **Bubblegum Pop** (`#FF69B4` Hot Pink · `#069494` Deep Teal · `#FFFFFF` Pure White · `#00F0FF` / `#00bcd4` Electric Cyan).
- **Background**: Fresh, clean, light aesthetic with airy slate-50 (`#F8FAFC`) surfaces, crisp white cards, elevated soft drop shadows, and subtle ambient pastel radial glows.
- **Iconography**: **Remix Icon (`v4.2.0`)** vector icons across navigation, cards, flow nodes, and status indicators.

---

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────────┐
│                   JavaScript Frontend                  │
│   (HTML5, Vanilla CSS Design System, Chart.js, WS)     │
└───────────────────────────▲────────────────────────────┘
                            │ REST APIs & WebSocket
┌───────────────────────────▼────────────────────────────┐
│                    FastAPI Backend                     │
│  (main.py, routers: metrics, simulation, what-if, hist)│
└─────────────▲────────────────────────────▲─────────────┘
              │                            │
┌─────────────▼──────────────┐ ┌───────────▼─────────────┐
│      Simulation Engine     │ │   Database Layer        │
│ (Discrete-Event Simulator) │ │ (MySQL / SQLite Fallback)│
└────────────────────────────┘ └─────────────────────────┘
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- Python 3.10+ installed
- Web browser (Chrome, Edge, Firefox)

### 2. Dependencies
Install all required packages:
```bash
pip install -r requirements.txt
```

### 3. Running the Application
From the `digital-twin-manufacturing` directory, execute:
```bash
python run.py
```

Open your browser at:
- **Interactive Dashboard**: [http://localhost:8000](http://localhost:8000)
- **Interactive API Documentation (Swagger UI)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **OpenAPI Schema**: [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

---

## 📡 API Endpoints Summary

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Serves the main Single-Page Application (SPA) |
| `GET` | `/api/dashboard` | Aggregated real-time dashboard data (polled every 2s) |
| `GET` | `/api/machines` | All machine states, cumulative runtimes, and utilization |
| `GET` | `/api/bottleneck` | Current identified bottleneck machine and state |
| `GET` | `/api/throughput` | Completed and rejected units, per-hour simulation rate |
| `GET` | `/api/oee` | System-wide and per-machine Availability, Performance, Quality, and OEE |
| `GET` | `/api/workload` | Units processed and workload distribution per machine |
| `GET` | `/api/products` | Active WIP products and station history |
| `GET` | `/api/events` | Real-time event log of breakdowns, completions, and transitions |
| `POST` | `/api/simulation/start` | Start the discrete simulation run |
| `POST` | `/api/simulation/pause` | Pause active simulation |
| `POST` | `/api/simulation/resume` | Resume paused simulation |
| `POST` | `/api/simulation/stop` | Stop simulation and record history |
| `POST` | `/api/simulation/reset` | Reset simulation state and buffers |
| `POST` | `/api/simulation/config` | Update speed multiplier, arrival rate, or breakdowns |
| `POST` | `/api/what-if/add-drilling-machine` | Add second parallel drilling machine for load balancing |
| `POST` | `/api/what-if/remove-drilling-machine` | Remove parallel drilling machine |
| `GET` | `/api/what-if/snapshot` | Get baseline vs modified comparison data |
| `POST` | `/api/what-if/save-comparison` | Save comparison analysis to database |
| `GET` | `/api/history/runs` | Retrieve list of historical simulation runs |
| `GET` | `/api/history/what-if` | Retrieve saved what-if analysis comparisons |
| `WS` | `/ws/live` | WebSocket stream for live real-time simulation updates |

---

## 🧪 Running Unit Tests

Unit tests validate machine state transitions, OEE calculations, throughput, bottleneck detection, and parallel machine allocation:

```bash
cd backend
python -m pytest ../tests/test_simulation.py -v
```

---

## 🔌 Sensor Integration Roadmap

While the current engine produces high-fidelity simulation-generated telemetry, the architecture supports physical shop-floor IoT sensors as a future extension:
- **Current Sensors**: Motor spindle current monitoring for precise `BUSY` / `IDLE` state detection.
- **Photoelectric Sensors**: Machine infeed / outfeed counters for cycle times and parts completed.
- **Proximity / Ultrasonic Sensors**: Inter-machine buffer occupancy for `BLOCKED` states.
- **Accelerometers & Thermistors**: Vibration and bearing temperature monitoring for predictive maintenance.
- **Vision Systems / Laser Gauges**: Quality inspection sorting conforming vs defective workpieces.
- **Stack Lights / E-Stop Relays**: Physical control panel telemetry for `BREAKDOWN` confirmations.

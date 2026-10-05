"""
main.py
-------
FastAPI application entry point for the Digital Twin Manufacturing System.

Architecture:
  Simulation Engine → FastAPI Backend → REST APIs → JavaScript Frontend

Endpoints overview:
  GET  /                          → serve frontend
  GET  /api/dashboard             → all dashboard data (polled every 2s)
  GET  /api/machines              → all machine states
  GET  /api/bottleneck            → current bottleneck
  GET  /api/throughput            → throughput metrics
  GET  /api/oee                   → OEE metrics
  GET  /api/workload              → workload distribution
  GET  /api/products              → active products
  GET  /api/events                → event log
  POST /api/simulation/start      → start simulation
  POST /api/simulation/stop       → stop simulation
  POST /api/simulation/pause      → pause simulation
  POST /api/simulation/resume     → resume simulation
  POST /api/simulation/reset      → reset simulation
  POST /api/simulation/config     → update sim parameters
  POST /api/what-if/add-drilling-machine  → parallel drilling
  GET  /api/what-if/snapshot      → comparison data
  GET  /api/history/runs          → past simulation runs
  WS   /ws/live                   → WebSocket real-time updates

Note on sensor integration:
  Current version uses simulation-generated real-time data.
  Physical sensor integration (current sensors, photoelectric, proximity sensors,
  accelerometers, temperature sensors, vision cameras, stack lights) can be added
  as a future extension by routing sensor data to the simulation engine.
"""

import os
import sys
import json
import asyncio
import time
from pathlib import Path
from contextlib import asynccontextmanager

# Ensure backend directory is in sys.path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from routers.simulation_router import router as sim_router
from routers.metrics_router import router as metrics_router
from routers.whatif_router import router as whatif_router
from routers.history_router import router as history_router
from simulation.engine import sim_engine


# ─────────────────── Lifespan (startup/shutdown) ────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup and shutdown logic."""
    print("\n[STARTUP] Digital Twin Manufacturing System starting up...")

    # Initialize database tables
    try:
        init_db()
    except Exception as e:
        print(f"[WARNING] DB init warning: {e}")

    print("[OK] Application ready!")
    print("-> Open: http://localhost:8000")
    print("-> API Docs: http://localhost:8000/docs")
    yield

    # Shutdown
    if sim_engine.is_running:
        sim_engine.stop()
    print("[SHUTDOWN] Digital Twin Manufacturing System shut down.")


# ─────────────────── FastAPI App ─────────────────────────────────────

app = FastAPI(
    title="Digital Twin Manufacturing System",
    description="""
    Web-Based Digital Twin for Real-Time Manufacturing Bottleneck Analysis 
    and Parallel Machine Allocation.
    
    Based on the research paper:
    "Digital Twin-Based Bottleneck Analysis and Parallel Machine Allocation 
     for Improving Manufacturing System Performance"
    
    Manufacturing Flow:
    Raw Material → Cutting → Turning → Drilling → Inspection → Packaging → Finished Product
    """,
    version="1.0.0",
    lifespan=lifespan,
)

# ─── CORS (allow frontend to call API) ────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Register routers ─────────────────────────────────────────────────
app.include_router(sim_router)
app.include_router(metrics_router)
app.include_router(whatif_router)
app.include_router(history_router)

# ─── Serve frontend static files ──────────────────────────────────────
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
    app.mount("/css",    StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css")
    app.mount("/js",     StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")


# ─────────────────── WebSocket Manager ───────────────────────────────

class ConnectionManager:
    """Manages active WebSocket connections for real-time push."""
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, data: dict):
        message = json.dumps(data)
        dead = []
        for ws in self.active:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


# ─────────────────── WebSocket Endpoint ──────────────────────────────

@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time dashboard updates.
    Pushes dashboard data every 1 second while connected.
    Uses asyncio.to_thread to avoid blocking the event loop when
    the simulation engine holds its threading.Lock.
    """
    await manager.connect(websocket)
    try:
        while True:
            # Run the blocking get_full_dashboard_data() in a thread pool
            # so it never blocks the async event loop
            data = await asyncio.to_thread(sim_engine.get_full_dashboard_data)
            await websocket.send_text(json.dumps(data))
            await asyncio.sleep(1.0)  # push every 1s for snappier UI
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"[WS] Connection error: {e}")
        manager.disconnect(websocket)


# ─────────────────── Frontend Routes ─────────────────────────────────

@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def root():
    """Serve the main dashboard page."""
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return HTMLResponse(content="""
    <html><body>
    <h1>Digital Twin Manufacturing System</h1>
    <p>Frontend not found. Make sure the frontend directory exists.</p>
    <p><a href="/docs">View API Documentation</a></p>
    </body></html>
    """)


@app.api_route("/dashboard", methods=["GET", "HEAD"])
async def dashboard():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    """Simple health check."""
    return {
        "status": "ok",
        "simulation_running": sim_engine.is_running,
        "products_completed": len(sim_engine.completed_products),
    }


@app.get("/favicon.ico")
async def favicon():
    from fastapi.responses import Response
    return Response(status_code=204)


# ─────────────────── Entry Point ─────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=os.getenv("APP_HOST", "0.0.0.0"),
        port=int(os.getenv("APP_PORT", "8000")),
        log_level="info",
    )

"""
run.py — Startup launcher for Digital Twin Manufacturing System.

Run this file from the project root:
    python run.py

Or from any directory:
    python path/to/digital-twin-manufacturing/run.py
"""

import os
import sys

# Ensure the backend directory is on the Python path
project_root = os.path.dirname(os.path.abspath(__file__))
backend_dir  = os.path.join(project_root, "backend")

if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

os.chdir(backend_dir)   # set cwd so relative imports and .env paths resolve

import uvicorn
from main import app

if __name__ == "__main__":
    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("APP_PORT", "8000"))

    print("\n" + "=" * 60)
    print("  Digital Twin Manufacturing System")
    print("=" * 60)
    print(f"  Frontend : http://localhost:{port}")
    print(f"  API Docs : http://localhost:{port}/docs")
    print("=" * 60 + "\n")

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        log_level="info",
        reload=True,
        reload_dirs=[backend_dir],
    )

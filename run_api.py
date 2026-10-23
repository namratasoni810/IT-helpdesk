"""Convenience entrypoint: `python run_api.py` starts the FastAPI server."""

import os

import uvicorn

from app.config import get_settings

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("DATABRICKS_APP_PORT", settings.api_port)),
        reload=False,
    )

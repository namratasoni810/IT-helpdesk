"""Run the FastAPI backend and Streamlit UI as one Databricks App."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import requests

from app.config import get_settings

ROOT = Path(__file__).resolve().parent
API_STARTUP_TIMEOUT = 120


def _wait_for_api(process: subprocess.Popen, api_base_url: str) -> None:
    deadline = time.monotonic() + API_STARTUP_TIMEOUT
    health_url = f"{api_base_url}/health"

    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"FastAPI exited during startup with code {process.returncode}."
            )
        try:
            response = requests.get(health_url, timeout=2)
            if response.status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(1)

    raise TimeoutError(
        f"FastAPI did not become healthy within {API_STARTUP_TIMEOUT} seconds "
        f"at {health_url}."
    )


def _stop_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def main() -> int:
    settings = get_settings()
    app_port = int(os.getenv("DATABRICKS_APP_PORT", settings.streamlit_port))
    api_base_url = settings.api_base_url
    environment = os.environ.copy()

    api_process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(settings.api_port),
        ],
        cwd=ROOT,
        env=environment,
    )
    streamlit_process: subprocess.Popen | None = None

    try:
        _wait_for_api(api_process, api_base_url)
        streamlit_process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                "app/frontend/streamlit_app.py",
                "--server.address=0.0.0.0",
                f"--server.port={app_port}",
                "--server.headless=true",
            ],
            cwd=ROOT,
            env=environment,
        )

        while streamlit_process.poll() is None:
            if api_process.poll() is not None:
                raise RuntimeError(
                    f"FastAPI exited with code {api_process.returncode}."
                )
            time.sleep(1)

        return streamlit_process.returncode or 0
    except KeyboardInterrupt:
        return 0
    finally:
        _stop_process(streamlit_process)
        _stop_process(api_process)


if __name__ == "__main__":
    raise SystemExit(main())

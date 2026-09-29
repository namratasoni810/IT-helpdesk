"""Convenience entrypoint: `python run_worker.py` runs the worker standalone.

Useful if you'd rather keep classification in its own process instead of the
FastAPI background thread. Ctrl-C stops it cleanly.
"""

import logging
import signal
import time

from app import db, worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("helpdesk.worker")


def main() -> None:
    db.init_pool()

    def _shutdown(signum, frame):
        logger.info("Shutdown signal received")
        worker.stop_worker()
        db.close_pool()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # Blocking call: classify once, then keep polling in the background thread.
    logger.info("Running one classification pass on startup")
    worker.process_new_tickets()
    worker.start_worker()

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        _shutdown(None, None)


if __name__ == "__main__":
    main()

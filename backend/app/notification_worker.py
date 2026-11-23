"""Notification queue worker with graceful shutdown.

Run with: python -m app.notification_worker
"""
import os
import time
import logging
from threading import Event

from app.database import SessionLocal
from app.notification_service import process_pending

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("lushora.notification_worker")


def _poll_seconds():
    raw = os.getenv("NOTIFICATION_WORKER_POLL_SECONDS", "10")
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError("NOTIFICATION_WORKER_POLL_SECONDS must be an integer") from exc
    if value < 1 or value > 300:
        raise RuntimeError("NOTIFICATION_WORKER_POLL_SECONDS must be between 1 and 300")
    return value


def run_worker(stop_event=None, poll_seconds=None):
    stop_event = stop_event or Event()
    poll_seconds = poll_seconds if poll_seconds is not None else _poll_seconds()
    if not isinstance(poll_seconds, int) or poll_seconds < 1 or poll_seconds > 300:
        raise ValueError("poll_seconds must be between 1 and 300")
    log.info("Notification worker started; polling every %s seconds", poll_seconds)
    while not stop_event.is_set():
        db = SessionLocal()
        try:
            count = process_pending(db)
            if count:
                log.info("Processed %s notification deliveries", count)
        except Exception:
            log.exception("Notification worker loop error")
        finally:
            db.close()
        stop_event.wait(poll_seconds)
    log.info("Notification worker stopped")


def main():
    import signal
    stop_event = Event()
    signal.signal(signal.SIGTERM, lambda *_: stop_event.set())
    signal.signal(signal.SIGINT, lambda *_: stop_event.set())
    run_worker(stop_event)


if __name__ == "__main__":
    main()

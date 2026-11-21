"""Run the notification queue worker: python -m app.notification_worker"""
import os,time,logging
from app.database import SessionLocal
from app.notification_service import process_pending
logging.basicConfig(level=os.getenv("LOG_LEVEL","INFO"))
log=logging.getLogger("lushora.notification_worker")
POLL_SECONDS=int(os.getenv("NOTIFICATION_WORKER_POLL_SECONDS","10"))
while True:
    db=SessionLocal()
    try:
        count=process_pending(db)
        if count: log.info("Processed %s notification deliveries",count)
    except Exception:
        log.exception("Notification worker loop error")
    finally: db.close()
    time.sleep(POLL_SECONDS)

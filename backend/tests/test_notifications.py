from datetime import datetime, timedelta

import pytest

from app.database import Base, engine, SessionLocal
from app.models import User, Notification, NotificationDelivery, NotificationPreference
from app import notification_service


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _delivery(status="queued", channel="sms", enabled=True):
    db = SessionLocal()
    user = User(full_name="Notification Test", email="notification-test@example.com", phone="9876543210", password_hash="unused", role="customer")
    db.add(user)
    db.flush()
    notification = Notification(recipient_user_id=user.id, title="Test", message="Test message")
    db.add(notification)
    db.flush()
    pref = NotificationPreference(user_id=user.id, sms_enabled=enabled, whatsapp_enabled=False, push_enabled=False)
    db.add(pref)
    row = NotificationDelivery(notification_id=notification.id, user_id=user.id, channel=channel, status=status, attempts=0)
    db.add(row)
    db.commit()
    row_id = row.id
    db.close()
    return row_id


def test_notification_retry_uses_backoff_then_succeeds(monkeypatch):
    delivery_id = _delivery()
    monkeypatch.setattr(notification_service, "MAX_ATTEMPTS", 3)
    calls = {"n": 0}

    def send(db, row):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient provider error")
        return "provider-id-1"

    monkeypatch.setattr(notification_service, "dispatch_delivery", send)
    db = SessionLocal()
    try:
        assert notification_service.process_pending(db) == 1
        row = db.query(NotificationDelivery).filter_by(id=delivery_id).first()
        assert row.status == "retry"
        assert row.attempts == 1
        assert row.next_attempt_at and row.next_attempt_at > datetime.utcnow()
        row.next_attempt_at = datetime.utcnow() - timedelta(seconds=1)
        db.commit()
        assert notification_service.process_pending(db) == 1
        row = db.query(NotificationDelivery).filter_by(id=delivery_id).first()
        assert row.status == "sent"
        assert row.attempts == 2
        assert row.provider_message_id == "provider-id-1"
        assert row.next_attempt_at is None
    finally:
        db.close()


def test_notification_delivery_becomes_failed_at_attempt_limit(monkeypatch):
    delivery_id = _delivery()
    monkeypatch.setattr(notification_service, "MAX_ATTEMPTS", 2)
    monkeypatch.setattr(notification_service, "dispatch_delivery", lambda *_: (_ for _ in ()).throw(RuntimeError("provider down")))
    db = SessionLocal()
    try:
        for _ in range(2):
            row = db.query(NotificationDelivery).filter_by(id=delivery_id).first()
            row.next_attempt_at = datetime.utcnow() - timedelta(seconds=1)
            db.commit()
            assert notification_service.process_pending(db) == 1
        row = db.query(NotificationDelivery).filter_by(id=delivery_id).first()
        assert row.status == "failed"
        assert row.attempts == 2
        assert "provider down" in row.last_error
    finally:
        db.close()


def test_notification_delivery_suppressed_when_consent_disabled(monkeypatch):
    delivery_id = _delivery(enabled=False)
    db = SessionLocal()
    try:
        assert notification_service.process_pending(db) == 1
        row = db.query(NotificationDelivery).filter_by(id=delivery_id).first()
        assert row.status == "suppressed"
        assert row.next_attempt_at is None
        assert row.attempts == 1
    finally:
        db.close()

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


def test_delivery_claim_is_atomic_and_only_one_worker_wins():
    delivery_id = _delivery()
    first = SessionLocal()
    second = SessionLocal()
    try:
        claimed_by_first = notification_service._claim_delivery(first, delivery_id)
        claimed_by_second = notification_service._claim_delivery(second, delivery_id)
        assert claimed_by_first is not None
        assert claimed_by_first.status == "sending"
        assert claimed_by_first.attempts == 1
        assert claimed_by_second is None
        row = first.query(NotificationDelivery).filter_by(id=delivery_id).first()
        assert row.status == "sending"
        assert row.attempts == 1
    finally:
        first.close()
        second.close()


def test_stale_sending_delivery_is_failed_for_reconciliation(monkeypatch):
    delivery_id = _delivery(status="sending")
    monkeypatch.setattr(notification_service, "SENDING_STALE_SECONDS", 60)
    db = SessionLocal()
    try:
        row = db.query(NotificationDelivery).filter_by(id=delivery_id).first()
        row.updated_at = datetime.utcnow() - timedelta(seconds=61)
        db.commit()

        calls = {"n": 0}
        monkeypatch.setattr(
            notification_service,
            "dispatch_delivery",
            lambda *_: calls.__setitem__("n", calls["n"] + 1),
        )

        assert notification_service.process_pending(db) == 0
        row = db.query(NotificationDelivery).filter_by(id=delivery_id).first()
        assert row.status == "failed"
        assert row.next_attempt_at is None
        assert "provider acceptance is unknown" in row.last_error
        assert calls["n"] == 0
    finally:
        db.close()


@pytest.mark.parametrize("raw", ["0", "-1", "21", "not-a-number"])
def test_notification_attempt_limit_configuration_validation(monkeypatch, raw):
    monkeypatch.setenv("NOTIFICATION_MAX_ATTEMPTS", raw)
    with pytest.raises((RuntimeError, ValueError)):
        import importlib
        importlib.reload(notification_service)

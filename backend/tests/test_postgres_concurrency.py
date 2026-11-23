"""PostgreSQL concurrency regression tests.

These tests intentionally run only against a disposable database named
*concurrency_test*. They exercise real PostgreSQL row-locking/conditional-update
semantics; SQLite-only unit tests are not a substitute for these checks.
"""
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, time as day_time
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app import notification_service

# Never point this test module at a developer or production database by accident.
if engine.dialect.name != "postgresql":
    pytest.skip("Requires PostgreSQL; run with LUSHORA_DATABASE_URL", allow_module_level=True)
if os.getenv("LUSHORA_ALLOW_POSTGRES_CONCURRENCY_TESTS") != "1":
    pytest.skip(
        "Opt in only for a disposable PostgreSQL concurrency-test database",
        allow_module_level=True,
    )
database_name = (engine.url.database or "").lower()
if "concurrency" not in database_name or not database_name.endswith("_test"):
    raise RuntimeError(
        "Refusing PostgreSQL concurrency tests unless the database name contains "
        "'concurrency' and ends with '_test'."
    )

import app.main as main_module
from app.models import (
    AuthRateLimitEntry,
    Booking,
    Notification,
    NotificationDelivery,
    OTPChallenge,
    Provider,
    Service,
    User,
)


WORKERS = 12
LOCAL_TZ = ZoneInfo("Asia/Kolkata")


@pytest.fixture(scope="module", autouse=True)
def ensure_postgres_schema():
    # The CI step runs Alembic upgrade head first. create_all is intentionally
    # additive here and does not drop or reset the dedicated database.
    Base.metadata.create_all(bind=engine)


def _parallel_sessions(worker_count, operation):
    gate = threading.Barrier(worker_count)

    def invoke(index):
        db = SessionLocal()
        try:
            gate.wait(timeout=30)
            return operation(index, db)
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        return list(pool.map(invoke, range(worker_count)))


def _parallel_requests(worker_count, operation):
    gate = threading.Barrier(worker_count)

    def invoke(index):
        gate.wait(timeout=30)
        return operation(index)

    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        return list(pool.map(invoke, range(worker_count)))


def _create_provider_and_service(db, suffix):
    provider = Provider(
        name=f"Concurrency Studio {suffix}",
        category="Salon",
        city="Coimbatore",
        locality="Vadavalli",
        description="Disposable PostgreSQL concurrency test data",
        approval_status="approved",
        verified=True,
        availability_config=json.dumps(
            {
                "working_days": [0, 1, 2, 3, 4, 5, 6],
                "start_time": "09:00",
                "end_time": "18:00",
                "break_start": "",
                "break_end": "",
                "closed_dates": [],
            }
        ),
    )
    db.add(provider)
    db.flush()
    service = Service(
        provider_id=provider.id,
        name="Concurrency Test Service",
        price_inr=500,
        duration_minutes=30,
    )
    db.add(service)
    db.commit()
    return provider.id, service.id


def _future_local_time(days_ahead, hour):
    date = (datetime.now(LOCAL_TZ) + timedelta(days=days_ahead)).date()
    return datetime.combine(date, day_time(hour, 0))


def test_postgres_auth_rate_limit_enforces_one_shared_parallel_budget():
    suffix = uuid4().hex
    scope = f"pg_concurrency_{suffix[:12]}"
    identifier = f"parallel-auth-{suffix}"
    limit = 4

    def consume(_index, db):
        try:
            main_module._consume_auth_limit(
                db, scope, identifier, limit=limit, window_seconds=300
            )
            return "allowed"
        except HTTPException as exc:
            return exc.status_code

    results = _parallel_sessions(WORKERS, consume)
    assert results.count("allowed") == limit
    assert results.count(429) == WORKERS - limit

    db = SessionLocal()
    try:
        rows = (
            db.query(AuthRateLimitEntry)
            .filter_by(
                scope=scope,
                identifier_hash=main_module._rate_limit_identifier(identifier),
            )
            .all()
        )
        assert len(rows) == 1
        assert rows[0].attempts == limit + 1
        assert rows[0].blocked_until is not None
        assert rows[0].blocked_until > datetime.utcnow()
    finally:
        db.close()


def test_postgres_otp_challenge_is_consumed_once_under_parallel_verification():
    suffix = uuid4().hex
    db = SessionLocal()
    try:
        challenge = OTPChallenge(
            phone=f"+9199{suffix[:8]}",
            code_hash="not-used-by-this-atomic-consumption-test",
            expires_at=datetime.utcnow() + timedelta(minutes=5),
            consumed=False,
            attempts=0,
        )
        db.add(challenge)
        db.commit()
        challenge_id = challenge.id
    finally:
        db.close()

    results = _parallel_sessions(
        WORKERS,
        lambda _index, session: main_module._consume_otp_challenge(
            session, challenge_id
        ),
    )
    assert results.count(True) == 1
    assert results.count(False) == WORKERS - 1

    db = SessionLocal()
    try:
        stored = db.query(OTPChallenge).filter_by(id=challenge_id).one()
        assert stored.consumed is True
        assert stored.attempts == 1
    finally:
        db.close()



def test_postgres_parallel_otp_verification_returns_one_customer_session():
    suffix = uuid4().hex
    phone = "9" + suffix[:9]
    client = TestClient(main_module.app)
    requested = client.post("/api/v2/customer/otp/request", json={"phone": phone})
    assert requested.status_code == 200, requested.text
    otp = requested.json()["development_otp"]

    responses = _parallel_requests(
        WORKERS,
        lambda _index: client.post(
            "/api/v2/customer/otp/verify",
            json={"phone": phone, "otp": otp},
        ),
    )
    statuses = [response.status_code for response in responses]
    assert statuses.count(200) == 1, statuses
    assert statuses.count(401) == WORKERS - 1, statuses

    db = SessionLocal()
    try:
        normalized_phone = "+91" + phone
        customers = (
            db.query(User)
            .filter(User.phone == normalized_phone, User.role == "customer")
            .all()
        )
        assert len(customers) == 1
    finally:
        db.close()


def test_postgres_notification_workers_dispatch_one_queued_delivery(monkeypatch):
    suffix = uuid4().hex
    db = SessionLocal()
    try:
        user = User(
            full_name="Concurrency Notification User",
            email=f"notify-{suffix}@example.test",
            phone="+919876543210",
            password_hash="unused-test-hash",
            role="customer",
            is_active=True,
        )
        db.add(user)
        db.flush()
        notification = Notification(
            recipient_user_id=user.id,
            title="Concurrency test",
            message="This message must be dispatched once",
        )
        db.add(notification)
        db.flush()
        delivery = NotificationDelivery(
            notification_id=notification.id,
            user_id=user.id,
            channel="sms",
            status="queued",
            attempts=0,
        )
        db.add(delivery)
        db.commit()
        delivery_id = delivery.id
    finally:
        db.close()

    dispatch_calls = []
    dispatch_lock = threading.Lock()

    def fake_dispatch(_db, delivery):
        with dispatch_lock:
            dispatch_calls.append(delivery.id)
        return "simulated-provider-message"

    monkeypatch.setattr(notification_service, "dispatch_delivery", fake_dispatch)
    processed = _parallel_sessions(
        WORKERS,
        lambda _index, session: notification_service.process_pending(
            session, batch_size=10
        ),
    )

    assert sum(processed) == 1
    assert dispatch_calls == [delivery_id]

    db = SessionLocal()
    try:
        stored = db.query(NotificationDelivery).filter_by(id=delivery_id).one()
        assert stored.status == "sent"
        assert stored.attempts == 1
        assert stored.provider_message_id == "simulated-provider-message"
    finally:
        db.close()


def test_postgres_parallel_booking_creation_cannot_double_book_a_slot():
    suffix = uuid4().hex
    db = SessionLocal()
    try:
        provider_id, service_id = _create_provider_and_service(db, suffix)
    finally:
        db.close()

    appointment = _future_local_time(days_ahead=8, hour=10)
    payload = {
        "customer_name": "Parallel Booking Customer",
        "customer_phone": "9876543210",
        "provider_id": provider_id,
        "service_id": service_id,
        "appointment_at": appointment.isoformat(),
        "notes": "PostgreSQL concurrency test",
    }

    with TestClient(main_module.app) as client:
        responses = _parallel_requests(
            8, lambda _index: client.post("/api/bookings", json=payload)
        )

    statuses = [response.status_code for response in responses]
    assert statuses.count(201) == 1, statuses
    assert statuses.count(409) == 7, statuses

    db = SessionLocal()
    try:
        active_count = (
            db.query(Booking)
            .filter(
                Booking.provider_id == provider_id,
                Booking.appointment_at == appointment,
                Booking.status.in_(["requested", "confirmed"]),
            )
            .count()
        )
        assert active_count == 1
    finally:
        db.close()


def test_postgres_parallel_reschedules_cannot_claim_the_same_provider_slot():
    suffix = uuid4().hex
    db = SessionLocal()
    try:
        customer = User(
            full_name="Parallel Reschedule Customer",
            email=f"reschedule-{suffix}@example.test",
            phone=f"+9198{suffix[:8]}",
            password_hash=main_module._password_hash("StrongPassword123!"),
            role="customer",
            is_active=True,
        )
        db.add(customer)
        db.flush()
        provider_id, service_id = _create_provider_and_service(db, suffix)
        first_time = _future_local_time(days_ahead=10, hour=10)
        second_time = _future_local_time(days_ahead=10, hour=11)
        bookings = [
            Booking(
                customer_user_id=customer.id,
                customer_name=customer.full_name,
                customer_phone=customer.phone,
                provider_id=provider_id,
                service_id=service_id,
                appointment_at=first_time,
                status="requested",
                notes="",
                expires_at=datetime.utcnow() + timedelta(hours=24),
            ),
            Booking(
                customer_user_id=customer.id,
                customer_name=customer.full_name,
                customer_phone=customer.phone,
                provider_id=provider_id,
                service_id=service_id,
                appointment_at=second_time,
                status="requested",
                notes="",
                expires_at=datetime.utcnow() + timedelta(hours=24),
            ),
        ]
        db.add_all(bookings)
        db.commit()
        booking_ids = [booking.id for booking in bookings]
        token = main_module._make_token(customer.id, customer.auth_token_version)
    finally:
        db.close()

    target_time = _future_local_time(days_ahead=10, hour=13)
    headers = {"Authorization": f"Bearer {token}"}

    with TestClient(main_module.app) as client:
        responses = _parallel_requests(
            2,
            lambda index: client.patch(
                f"/api/bookings/{booking_ids[index]}/reschedule",
                headers=headers,
                json={"appointment_at": target_time.isoformat()},
            ),
        )

    statuses = [response.status_code for response in responses]
    assert statuses.count(200) == 1, [
        (response.status_code, response.text) for response in responses
    ]
    assert statuses.count(409) == 1, [
        (response.status_code, response.text) for response in responses
    ]

    db = SessionLocal()
    try:
        final_times = [
            row[0]
            for row in db.query(Booking.appointment_at)
            .filter(Booking.id.in_(booking_ids))
            .all()
        ]
        assert final_times.count(target_time) == 1
    finally:
        db.close()

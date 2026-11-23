import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import create_admin
from app.models import User


@pytest.fixture
def setup_database(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'admin-setup.db').as_posix()}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    monkeypatch.setattr(create_admin, "engine", engine)
    monkeypatch.setattr(create_admin, "SessionLocal", session_factory)
    create_admin.Base.metadata.create_all(bind=engine)
    yield session_factory
    engine.dispose()


def _set_credentials(monkeypatch, email, password):
    monkeypatch.setenv("LUSHORA_ADMIN_EMAIL", email)
    monkeypatch.setenv("LUSHORA_ADMIN_PASSWORD", password)


def test_admin_bootstrap_creates_account_with_strong_password(setup_database, monkeypatch):
    _set_credentials(monkeypatch, "lushora-admin@example.com", "StrongAdmin123!")
    create_admin.main()

    db = setup_database()
    try:
        user = db.query(User).filter_by(email="lushora-admin@example.com").one()
        assert user.role == "admin"
        assert user.is_active is True
        assert user.password_hash.startswith("pbkdf2_sha256$180000$")
    finally:
        db.close()


def test_admin_bootstrap_refuses_to_promote_existing_customer(setup_database, monkeypatch):
    db = setup_database()
    customer = User(
        full_name="Existing Customer",
        email="existing-customer@example.com",
        phone="9876543210",
        password_hash="existing-hash",
        role="customer",
        is_active=True,
    )
    db.add(customer)
    db.commit()
    original_hash = customer.password_hash
    db.close()

    _set_credentials(monkeypatch, "existing-customer@example.com", "StrongAdmin123!")
    with pytest.raises(SystemExit) as exc:
        create_admin.main()
    assert exc.value.code == 1

    db = setup_database()
    try:
        unchanged = db.query(User).filter_by(email="existing-customer@example.com").one()
        assert unchanged.role == "customer"
        assert unchanged.password_hash == original_hash
    finally:
        db.close()


@pytest.mark.parametrize(
    "password",
    [
        "short",
        "alllowercase123!",
        "ALLUPPERCASE123!",
        "NoDigitsHere!!",
        "NoSpecialCharacter123",
        "x" * 129,
    ],
)
def test_admin_bootstrap_rejects_weak_passwords(setup_database, monkeypatch, password):
    _set_credentials(monkeypatch, "weak-admin@example.com", password)
    with pytest.raises(SystemExit) as exc:
        create_admin.main()
    assert exc.value.code == 1

    db = setup_database()
    try:
        assert db.query(User).filter_by(email="weak-admin@example.com").first() is None
    finally:
        db.close()


def test_admin_bootstrap_rejects_invalid_email(setup_database, monkeypatch):
    _set_credentials(monkeypatch, "not-an-email", "StrongAdmin123!")
    with pytest.raises(SystemExit) as exc:
        create_admin.main()
    assert exc.value.code == 1


def test_existing_admin_can_rotate_password_without_duplication(setup_database, monkeypatch):
    db = setup_database()
    original = User(
        full_name="Existing Admin",
        email="existing-admin@example.com",
        phone="",
        password_hash="old-hash",
        role="admin",
        is_active=True,
    )
    db.add(original)
    db.commit()
    user_id = original.id
    db.close()

    _set_credentials(monkeypatch, "existing-admin@example.com", "NewStrongAdmin456!")
    create_admin.main()

    db = setup_database()
    try:
        rows = db.query(User).filter_by(email="existing-admin@example.com").all()
        assert len(rows) == 1
        assert rows[0].id == user_id
        assert rows[0].password_hash != "old-hash"
        assert rows[0].role == "admin"
    finally:
        db.close()

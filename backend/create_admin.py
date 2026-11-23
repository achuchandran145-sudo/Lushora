import os
import re
import sys
import hashlib
import base64

from app.database import Base, engine, SessionLocal
from app import models


EMAIL_PATTERN = re.compile(r"^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$")


def password_valid(password: str) -> bool:
    return (
        12 <= len(password) <= 128
        and any(ch.islower() for ch in password)
        and any(ch.isupper() for ch in password)
        and any(ch.isdigit() for ch in password)
        and any(not ch.isalnum() for ch in password)
    )


def password_hash(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 180000)
    return (
        "pbkdf2_sha256$180000$"
        + base64.urlsafe_b64encode(salt).decode().rstrip("=")
        + "$"
        + base64.urlsafe_b64encode(digest).decode().rstrip("=")
    )


def main():
    email = os.getenv("LUSHORA_ADMIN_EMAIL", "admin@lushora.local").strip().lower()
    password = os.getenv("LUSHORA_ADMIN_PASSWORD", "")

    if not EMAIL_PATTERN.fullmatch(email):
        print("A valid LUSHORA_ADMIN_EMAIL is required.")
        sys.exit(1)
    if not password_valid(password):
        print(
            "Admin password must be 12-128 characters and include uppercase, "
            "lowercase, a number and a special character."
        )
        sys.exit(1)

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        if user and user.role != "admin":
            print(
                "Refusing to promote an existing non-admin account. "
                "Use a dedicated, unused email address or contact an existing Admin."
            )
            sys.exit(1)

        if user:
            user.full_name = os.getenv("LUSHORA_ADMIN_NAME", "LUSHORA Admin")
            user.password_hash = password_hash(password)
            user.is_active = True
            print("Existing Admin account credentials updated.")
        else:
            user = models.User(
                full_name=os.getenv("LUSHORA_ADMIN_NAME", "LUSHORA Admin"),
                email=email,
                phone="",
                password_hash=password_hash(password),
                role="admin",
                is_active=True,
            )
            db.add(user)
            print("Admin account created.")

        db.commit()
        print(f"Admin email: {email}")
        print("Password: configured (not displayed)")
    finally:
        db.close()


if __name__ == "__main__":
    main()

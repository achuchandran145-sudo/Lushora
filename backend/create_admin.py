import os
import sys

from app.database import Base, engine, SessionLocal
from app import models
import hashlib
import base64

def password_hash(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 180000)
    return "pbkdf2_sha256$180000$" + base64.urlsafe_b64encode(salt).decode().rstrip("=") + "$" + base64.urlsafe_b64encode(digest).decode().rstrip("=")

def main():
    email = os.getenv("LUSHORA_ADMIN_EMAIL", "admin@lushora.local").strip().lower()
    password = os.getenv("LUSHORA_ADMIN_PASSWORD", "")
    if len(password) < 12:
        print("Admin password must be at least 12 characters.")
        sys.exit(1)

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        if user:
            user.full_name = "LUSHORA Admin"
            user.password_hash = password_hash(password)
            user.role = "admin"
            user.is_active = True
            print("Existing account updated and set to admin.")
        else:
            user = models.User(full_name="LUSHORA Admin", email=email, phone="", password_hash=password_hash(password), role="admin", is_active=True)
            db.add(user)
            print("Admin account created.")
        db.commit()
        print(f"Admin email: {email}")
        print("Password: configured (not displayed)")
    finally:
        db.close()

if __name__ == "__main__":
    main()

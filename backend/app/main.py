from datetime import datetime, timedelta
import os, re, json, hmac, hashlib, base64
from fastapi import FastAPI, Depends, HTTPException, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from .database import Base, engine, get_db
from . import models, schemas

Base.metadata.create_all(bind=engine)
app = FastAPI(title="LUSHORA API", version="0.1.0", description="Beauty and wellness discovery and booking MVP")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

AUTH_SECRET = os.getenv("LUSHORA_AUTH_SECRET", "development-only-change-this-secret").encode()
TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")

def _password_hash(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 180000)
    return "pbkdf2_sha256$180000$" + _b64(salt) + "$" + _b64(digest)

def _password_verify(password: str, stored: str) -> bool:
    try:
        scheme, rounds, salt, digest = stored.split("$")
        if scheme != "pbkdf2_sha256": return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.urlsafe_b64decode(salt + "=="), int(rounds))
        return hmac.compare_digest(_b64(actual), digest)
    except Exception:
        return False

def _make_token(user_id: int) -> str:
    payload = _b64(json.dumps({"sub": user_id, "exp": int(datetime.utcnow().timestamp()) + TOKEN_TTL_SECONDS}).encode())
    signature = _b64(hmac.new(AUTH_SECRET, payload.encode(), hashlib.sha256).digest())
    return payload + "." + signature

def _get_user_from_token(token: str, db: Session):
    try:
        payload, signature = token.split(".")
        expected = _b64(hmac.new(AUTH_SECRET, payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected): return None
        data = json.loads(base64.urlsafe_b64decode(payload + "=="))
        if int(data["exp"]) < int(datetime.utcnow().timestamp()): return None
        user = db.query(models.User).filter(models.User.id == int(data["sub"]), models.User.is_active == True).first()
        return user
    except Exception:
        return None

def current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Authentication required")
    user = _get_user_from_token(authorization[7:].strip(), db)
    if not user: raise HTTPException(401, "Invalid or expired token")
    return user

def require_role(role: str):
    def dependency(user: models.User = Depends(current_user)):
        if user.role != role: raise HTTPException(403, "Insufficient permissions")
        return user
    return dependency


@app.on_event("startup")
def bootstrap_admin_from_environment():
    email = os.getenv("LUSHORA_ADMIN_EMAIL", "").strip().lower()
    password = os.getenv("LUSHORA_ADMIN_PASSWORD", "")
    if not email or not password or len(password) < 12:
        return
    db = next(get_db())
    try:
        existing = db.query(models.User).filter(models.User.email == email).first()
        if existing is None:
            db.add(models.User(full_name=os.getenv("LUSHORA_ADMIN_NAME", "LUSHORA Admin"), email=email, password_hash=_password_hash(password), role="admin", is_active=True))
            db.commit()
    finally:
        db.close()

CATEGORIES = ["Makeup", "Salon", "Skin Clinic", "Nail Studio"]


@app.post("/api/auth/register", response_model=schemas.TokenOut, status_code=201)
def register(payload: schemas.RegisterIn, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email): raise HTTPException(400, "Valid email is required")
    if payload.role not in ["customer", "provider"]: raise HTTPException(400, "Role must be customer or provider")
    if db.query(models.User).filter(models.User.email == email).first(): raise HTTPException(409, "Email already registered")
    user = models.User(full_name=payload.full_name.strip(), email=email, phone=payload.phone.strip(), password_hash=_password_hash(payload.password), role=payload.role)
    db.add(user); db.commit(); db.refresh(user)
    return {"access_token": _make_token(user.id), "user": user}

@app.post("/api/auth/login", response_model=schemas.TokenOut)
def login(payload: schemas.LoginIn, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == payload.email.strip().lower()).first()
    if not user or not _password_verify(payload.password, user.password_hash) or not user.is_active:
        raise HTTPException(401, "Email or password is incorrect")
    return {"access_token": _make_token(user.id), "user": user}

@app.get("/api/auth/me", response_model=schemas.UserOut)
def me(user: models.User = Depends(current_user)):
    return user

@app.post("/api/provider/register", status_code=201)
def provider_registration(payload: schemas.ProviderRegistrationIn, user: models.User = Depends(require_role("provider")), db: Session = Depends(get_db)):
    existing = db.query(models.Provider).filter(models.Provider.owner_user_id == user.id).first()
    if existing: raise HTTPException(409, "A business profile already exists for this account")
    provider = models.Provider(owner_user_id=user.id, approval_status="pending", verified=False, name=payload.name, category=payload.category, city=payload.city, locality=payload.locality, description=payload.description)
    db.add(provider); db.commit(); db.refresh(provider)
    return {"id": provider.id, "approval_status": provider.approval_status, "message": "Business submitted for admin approval"}

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "lushora-api", "version": "0.1.0"}

@app.get("/api/categories")
def categories():
    return [{"name": c} for c in CATEGORIES]

@app.get("/api/providers", response_model=list[schemas.ProviderOut])
def list_providers(category: str | None = None, city: str | None = None, locality: str | None = None,
                   min_price: int | None = Query(default=None, ge=0), max_price: int | None = Query(default=None, ge=0),
                   verified: bool | None = None, db: Session = Depends(get_db)):
    q = db.query(models.Provider).options(joinedload(models.Provider.services)).filter(models.Provider.approval_status == "approved")
    if category: q = q.filter(func.lower(models.Provider.category) == category.lower())
    if city: q = q.filter(func.lower(models.Provider.city) == city.lower())
    if locality: q = q.filter(func.lower(models.Provider.locality).contains(locality.lower()))
    if verified is not None: q = q.filter(models.Provider.verified == verified)
    providers = q.order_by(models.Provider.verified.desc(), models.Provider.rating.desc()).all()
    if min_price is not None or max_price is not None:
        providers = [p for p in providers if any((min_price is None or s.price_inr >= min_price) and (max_price is None or s.price_inr <= max_price) for s in p.services)]
    return providers

@app.get("/api/providers/{provider_id}", response_model=schemas.ProviderOut)
def get_provider(provider_id: int, db: Session = Depends(get_db)):
    provider = db.query(models.Provider).options(joinedload(models.Provider.services)).filter(models.Provider.id == provider_id, models.Provider.approval_status == "approved").first()
    if not provider: raise HTTPException(404, "Provider not found")
    return provider

@app.post("/api/bookings", response_model=schemas.BookingOut, status_code=201)
def create_booking(payload: schemas.BookingCreate, db: Session = Depends(get_db), authorization: str | None = Header(default=None)):
    provider = db.query(models.Provider).filter(models.Provider.id == payload.provider_id).first()
    service = db.query(models.Service).filter(models.Service.id == payload.service_id, models.Service.provider_id == payload.provider_id).first()
    if not provider or not service: raise HTTPException(404, "Provider or service not found")
    if payload.appointment_at <= datetime.now(): raise HTTPException(400, "Appointment must be in the future")

    # Prevent overlapping requests for the same provider. Requested bookings block the
    # slot until the provider accepts, rejects, or cancels them.
    new_end = payload.appointment_at + timedelta(minutes=service.duration_minutes)
    active = db.query(models.Booking, models.Service).join(
        models.Service, models.Booking.service_id == models.Service.id
    ).filter(
        models.Booking.provider_id == payload.provider_id,
        models.Booking.status.in_(["requested", "confirmed"]),
    ).all()
    for existing_booking, existing_service in active:
        existing_end = existing_booking.appointment_at + timedelta(minutes=existing_service.duration_minutes)
        if payload.appointment_at < existing_end and new_end > existing_booking.appointment_at:
            raise HTTPException(409, "This provider already has a booking during the selected time")

    attached_user = None\n    if authorization and authorization.lower().startswith("bearer "):\n        attached_user = _get_user_from_token(authorization[7:].strip(), db)\n        if not attached_user: raise HTTPException(401, "Invalid or expired token")\n        if attached_user.role != "customer": raise HTTPException(403, "Only customer accounts can book")\n    booking = models.Booking(**payload.model_dump(), customer_user_id=attached_user.id if attached_user else None)
    db.add(booking)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(booking)
    return booking


@app.patch("/api/bookings/{booking_id}/status")
def update_booking_status(booking_id: int, status: str = Query(...), user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    allowed = {"confirmed", "rejected", "cancelled", "completed"}
    if status not in allowed: raise HTTPException(400, "Unsupported booking status")
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking: raise HTTPException(404, "Booking not found")
    provider = db.query(models.Provider).filter(models.Provider.id == booking.provider_id).first()
    is_admin = user.role == "admin"
    is_provider_owner = user.role == "provider" and provider and provider.owner_user_id == user.id
    is_customer_owner = user.role == "customer" and booking.customer_user_id == user.id
    if not (is_admin or is_provider_owner or is_customer_owner): raise HTTPException(403, "You cannot update this booking")
    if status in {"confirmed", "rejected", "completed"} and not (is_admin or is_provider_owner):
        raise HTTPException(403, "Only the provider or admin can set this status")
    if status == "completed" and booking.status != "confirmed": raise HTTPException(400, "Only confirmed bookings can be completed")
    if status == "confirmed" and booking.status != "requested": raise HTTPException(400, "Only requested bookings can be confirmed")
    if status == "rejected" and booking.status != "requested": raise HTTPException(400, "Only requested bookings can be rejected")
    if status == "cancelled" and booking.status not in {"requested", "confirmed"}: raise HTTPException(400, "This booking cannot be cancelled")
    booking.status = status
    db.commit()
    return {"id": booking.id, "status": booking.status}

@app.get("/api/provider/me/bookings")
def provider_bookings(user: models.User = Depends(require_role("provider")), db: Session = Depends(get_db)):
    provider = db.query(models.Provider).filter(models.Provider.owner_user_id == user.id).first()
    if not provider: raise HTTPException(404, "Business profile not found")
    return db.query(models.Booking).filter(models.Booking.provider_id == provider.id).order_by(models.Booking.appointment_at.asc()).all()

@app.get("/api/provider/me")
def provider_me(user: models.User = Depends(require_role("provider")), db: Session = Depends(get_db)):
    provider = db.query(models.Provider).options(joinedload(models.Provider.services)).filter(models.Provider.owner_user_id == user.id).first()
    if not provider: raise HTTPException(404, "Business profile not found")
    return provider

@app.get("/api/bookings", response_model=list[schemas.BookingOut])
def list_bookings(db: Session = Depends(get_db), user: models.User = Depends(require_role("admin"))):
    return db.query(models.Booking).order_by(models.Booking.created_at.desc()).all()


@app.get("/api/admin/providers")
def admin_providers(user: models.User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    return db.query(models.Provider).order_by(models.Provider.approval_status.asc(), models.Provider.name.asc()).all()

@app.patch("/api/admin/providers/{provider_id}/approval")
def provider_approval(provider_id: int, status: str = Query(...), user: models.User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    if status not in {"approved", "rejected"}: raise HTTPException(400, "Status must be approved or rejected")
    provider = db.query(models.Provider).filter(models.Provider.id == provider_id).first()
    if not provider: raise HTTPException(404, "Provider not found")
    provider.approval_status = status
    provider.verified = status == "approved"
    db.commit()
    return {"id": provider.id, "approval_status": provider.approval_status}

@app.post("/api/provider/me/services", status_code=201)
def provider_add_service(name: str = Query(..., min_length=2, max_length=120), price_inr: int = Query(..., ge=0), duration_minutes: int = Query(..., ge=5, le=600), user: models.User = Depends(require_role("provider")), db: Session = Depends(get_db)):
    provider = db.query(models.Provider).filter(models.Provider.owner_user_id == user.id, models.Provider.approval_status == "approved").first()
    if not provider: raise HTTPException(403, "Business is not approved")
    service = models.Service(provider_id=provider.id, name=name, price_inr=price_inr, duration_minutes=duration_minutes)
    db.add(service); db.commit(); db.refresh(service)
    return service

@app.delete("/api/provider/me/services/{service_id}")
def provider_delete_service(service_id: int, user: models.User = Depends(require_role("provider")), db: Session = Depends(get_db)):
    provider = db.query(models.Provider).filter(models.Provider.owner_user_id == user.id).first()
    service = db.query(models.Service).filter(models.Service.id == service_id, models.Service.provider_id == (provider.id if provider else -1)).first()
    if not service: raise HTTPException(404, "Service not found")
    db.delete(service); db.commit()
    return {"message": "Service deleted"}

@app.get("/api/admin/summary")
def admin_summary(db: Session = Depends(get_db), user: models.User = Depends(require_role("admin"))):
    return {"providers": db.query(models.Provider).count(), "services": db.query(models.Service).count(),
            "bookings": db.query(models.Booking).count(),
            "requested_bookings": db.query(models.Booking).filter(models.Booking.status == "requested").count()}

@app.post("/api/admin/demo-seed")
def seed_demo(db: Session = Depends(get_db)):
    if db.query(models.Provider).count(): return {"message": "Demo data already exists"}
    records = [
      ("Glow & Glam Salon", "Salon", "Coimbatore", "Vadavalli", "Hair, skin and grooming services", True, 4.8, [("Eyebrow Threading",40,10),("Basic Facial",699,60),("Haircut & Styling",299,30)]),
      ("Aadhira Bridal Studio", "Makeup", "Chennai", "Adyar", "Bridal and event makeup artist", True, 4.9, [("Party Makeup",2500,90),("Bridal Makeup",15000,180)]),
      ("DermaCare Skin Clinic", "Skin Clinic", "Coimbatore", "RS Puram", "Consultation-led dermatology clinic", False, 4.5, [("Skin Consultation",500,30)]),
      ("Nail Story Studio", "Nail Studio", "Tiruvannamalai", "Town Centre", "Nail art and nail care", True, 4.6, [("Gel Polish",699,45),("Nail Art",999,60)])
    ]
    for name,cat,city,loc,desc,verified,rating,services in records:
        p=models.Provider(name=name,category=cat,city=city,locality=loc,description=desc,verified=verified,rating=rating)
        db.add(p); db.flush()
        for sn,price,duration in services: db.add(models.Service(provider_id=p.id,name=sn,price_inr=price,duration_minutes=duration))
    db.commit()
    return {"message":"Demo providers created", "providers":len(records)}

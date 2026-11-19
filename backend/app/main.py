from datetime import datetime, timedelta
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from .database import Base, engine, get_db
from . import models, schemas

Base.metadata.create_all(bind=engine)
app = FastAPI(title="LUSHORA API", version="0.1.0", description="Beauty and wellness discovery and booking MVP")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
CATEGORIES = ["Makeup", "Salon", "Skin Clinic", "Nail Studio"]

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
    q = db.query(models.Provider).options(joinedload(models.Provider.services))
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
    provider = db.query(models.Provider).options(joinedload(models.Provider.services)).filter(models.Provider.id == provider_id).first()
    if not provider: raise HTTPException(404, "Provider not found")
    return provider

@app.post("/api/bookings", response_model=schemas.BookingOut, status_code=201)
def create_booking(payload: schemas.BookingCreate, db: Session = Depends(get_db)):
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

    booking = models.Booking(**payload.model_dump())
    db.add(booking)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(booking)
    return booking

@app.get("/api/bookings", response_model=list[schemas.BookingOut])
def list_bookings(db: Session = Depends(get_db)):
    return db.query(models.Booking).order_by(models.Booking.created_at.desc()).all()

@app.get("/api/admin/summary")
def admin_summary(db: Session = Depends(get_db)):
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

from datetime import datetime, timedelta
import os, re, json, hmac, hashlib, base64, secrets
from fastapi import FastAPI, Depends, HTTPException, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from io import BytesIO
from openpyxl import Workbook
from fastapi.responses import StreamingResponse
from .database import Base, engine, get_db, migrate_sqlite_schema
from . import models, schemas

Base.metadata.create_all(bind=engine)
# Add availability settings to existing SQLite provider tables.
try:
    from sqlalchemy import inspect as _inspect
    if engine.dialect.name == 'sqlite' and 'availability_config' not in [c['name'] for c in _inspect(engine).get_columns('providers')]:
        with engine.begin() as _conn: _conn.exec_driver_sql("ALTER TABLE providers ADD COLUMN availability_config TEXT DEFAULT '{}'")
except Exception: pass
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
    migrate_sqlite_schema()
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

@app.get("/api/v2/customer/profile")
def customer_profile(user: models.User = Depends(require_role("customer"))):
    return {"first_name": user.first_name, "last_name": user.last_name, "street_address": user.street_address, "city": user.city, "locality": user.locality, "phone": user.phone, "profile_complete": bool(user.first_name and user.last_name and user.street_address and user.city and user.locality)}

@app.patch("/api/v2/customer/profile")
def update_customer_profile(payload: dict, user: models.User = Depends(require_role("customer")), db: Session = Depends(get_db)):
    first = str(payload.get("first_name", "")).strip()
    last = str(payload.get("last_name", "")).strip()
    street = str(payload.get("street_address", "")).strip()
    city = str(payload.get("city", "")).strip()
    locality = str(payload.get("locality", "")).strip()
    if not all([first, last, street, city, locality]):
        raise HTTPException(400, "Please complete all profile and address fields")
    if city not in {"Chennai", "Coimbatore", "Tiruvannamalai"}:
        raise HTTPException(400, "Select a supported city")
    user.first_name, user.last_name = first, last
    user.full_name = f"{first} {last}"
    user.street_address, user.city, user.locality = street, city, locality
    db.commit(); db.refresh(user)
    return {"first_name": first, "last_name": last, "street_address": street, "city": city, "locality": locality, "phone": user.phone, "profile_complete": True, "message": "Profile saved"}




@app.post("/api/v2/admin/subscriptions",status_code=201)
def create_subscription(payload:dict,user:models.User=Depends(require_role("admin")),db:Session=Depends(get_db)):
    provider_id=int(payload.get("provider_id",0));area_id=int(payload.get("area_id",0));category=str(payload.get("category","")).strip();tier=str(payload.get("tier","")).lower()
    if tier not in {"premium","standard"}: raise HTTPException(400,"Tier must be premium or standard")
    price=3000 if tier=="premium" else 1500
    provider=db.query(models.Provider).filter(models.Provider.id==provider_id,models.Provider.approval_status=="approved",models.Provider.category==category).first()
    area=db.query(models.MarketplaceArea).filter(models.MarketplaceArea.id==area_id,models.MarketplaceArea.is_active==True).first()
    if not provider or not area: raise HTTPException(404,"Approved business or area not found")
    sub=models.BusinessSubscription(provider_id=provider_id,area_id=area_id,category=category,tier=tier,monthly_price_inr=price,status="pending")
    db.add(sub);db.commit();db.refresh(sub)
    return {"id":sub.id,"tier":tier,"monthly_price_inr":price,"status":sub.status,"message":"Subscription created pending payment/activation"}

@app.get("/api/v2/admin/subscriptions")
def list_subscriptions(user:models.User=Depends(require_role("admin")),db:Session=Depends(get_db)):
    rows=db.query(models.BusinessSubscription,models.Provider,models.MarketplaceArea).join(models.Provider,models.Provider.id==models.BusinessSubscription.provider_id).join(models.MarketplaceArea,models.MarketplaceArea.id==models.BusinessSubscription.area_id).order_by(models.BusinessSubscription.created_at.desc()).all()
    return [{"id":s.id,"business":p.name,"provider_id":p.id,"city":a.city,"locality":a.locality,"category":s.category,"tier":s.tier,"price":s.monthly_price_inr,"status":s.status,"starts_at":s.starts_at,"ends_at":s.ends_at} for s,p,a in rows]

@app.patch("/api/v2/admin/subscriptions/{subscription_id}")
def update_subscription(subscription_id:int,payload:dict,user:models.User=Depends(require_role("admin")),db:Session=Depends(get_db)):
    sub=db.query(models.BusinessSubscription).filter(models.BusinessSubscription.id==subscription_id).first()
    if not sub: raise HTTPException(404,"Subscription not found")
    status=str(payload.get("status","")).lower()
    if status not in {"active","paused","expired","cancelled"}: raise HTTPException(400,"Unsupported subscription status")
    sub.status=status
    if status=="active" and not sub.starts_at: sub.starts_at=datetime.utcnow();sub.ends_at=datetime.utcnow()+timedelta(days=30)
    db.commit();return {"id":sub.id,"status":sub.status,"starts_at":sub.starts_at,"ends_at":sub.ends_at}

# LUSHORA v2: area-based marketplace and sequential customer-lead distribution.
@app.post("/api/v2/admin/areas", status_code=201)
def create_area(payload: dict, user: models.User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    city = str(payload.get("city", "")).strip(); locality = str(payload.get("locality", "")).strip()
    if not city or not locality: raise HTTPException(400, "City and locality are required")
    area = db.query(models.MarketplaceArea).filter(func.lower(models.MarketplaceArea.city)==city.lower(),func.lower(models.MarketplaceArea.locality)==locality.lower()).first()
    if area: return {"id": area.id, "city": area.city, "locality": area.locality, "message": "Area already exists"}
    area=models.MarketplaceArea(city=city,locality=locality);db.add(area);db.commit();db.refresh(area)
    return {"id":area.id,"city":area.city,"locality":area.locality}

@app.get("/api/v2/areas")
def list_areas(db: Session = Depends(get_db)):
    return db.query(models.MarketplaceArea).filter(models.MarketplaceArea.is_active==True).order_by(models.MarketplaceArea.city,models.MarketplaceArea.locality).all()

@app.put("/api/v2/admin/rankings")
def set_area_rankings(payload: dict, user: models.User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    area_id=int(payload.get("area_id",0));category=str(payload.get("category","")).strip();items=payload.get("providers",[])
    if not area_id or not category: raise HTTPException(400,"Area and category are required")
    if len(items)>10: raise HTTPException(400,"Only Top 10 placements are allowed")
    db.query(models.AreaRanking).filter(models.AreaRanking.area_id==area_id,models.AreaRanking.category==category).delete()
    for i,item in enumerate(items,1):
        provider_id=int(item.get("provider_id"));tier="premium" if i<=5 else "standard"
        provider=db.query(models.Provider).filter(models.Provider.id==provider_id,models.Provider.approval_status=="approved",models.Provider.category==category).first()
        if not provider: raise HTTPException(400,f"Provider {provider_id} is not an approved provider in this category")
        db.add(models.AreaRanking(area_id=area_id,category=category,provider_id=provider_id,rank_position=i,subscription_tier=tier,is_active=True))
    db.commit();return {"area_id":area_id,"category":category,"rankings_saved":len(items)}

@app.get("/api/v2/admin/rankings")
def get_area_rankings(area_id:int,category:str,user:models.User=Depends(require_role("admin")),db:Session=Depends(get_db)):
    rows=db.query(models.AreaRanking,models.Provider).join(models.Provider,models.Provider.id==models.AreaRanking.provider_id).filter(models.AreaRanking.area_id==area_id,models.AreaRanking.category==category,models.AreaRanking.is_active==True).order_by(models.AreaRanking.rank_position).all()
    return [{"rank":r.rank_position,"provider_id":p.id,"business":p.name,"tier":r.subscription_tier} for r,p in rows]

@app.post("/api/v2/customer/leads",status_code=201)
def create_customer_lead(payload:dict,user:models.User=Depends(require_role("customer")),db:Session=Depends(get_db)):
    if payload.get("contact_consent") is not True: raise HTTPException(400,"Customer consent to share contact details is required")
    area_id=int(payload.get("area_id",0));category=str(payload.get("category","")).strip();interest=str(payload.get("service_interest","")).strip()
    if not area_id or not category: raise HTTPException(400,"Area and category are required")
    area=db.query(models.MarketplaceArea).filter(models.MarketplaceArea.id==area_id,models.MarketplaceArea.is_active==True).first()
    if not area: raise HTTPException(404,"Area not found")
    if not user.phone: raise HTTPException(400,"Verified customer phone number is missing")
    rankings=db.query(models.AreaRanking).filter(models.AreaRanking.area_id==area_id,models.AreaRanking.category==category,models.AreaRanking.is_active==True).order_by(models.AreaRanking.rank_position).all()
    if not rankings: raise HTTPException(404,"No ranked businesses are available for this area and category")
    lead=models.CustomerLead(customer_user_id=user.id,area_id=area_id,category=category,service_interest=interest,customer_phone=user.phone,contact_consent=True)
    db.add(lead);db.flush();now=datetime.utcnow()
    for ranking in rankings[:10]: db.add(models.LeadDelivery(lead_id=lead.id,provider_id=ranking.provider_id,rank_position=ranking.rank_position,scheduled_at=now+timedelta(minutes=3*(ranking.rank_position-1))))
    db.commit();return {"lead_id":lead.id,"deliveries_scheduled":min(len(rankings),10),"first_delivery_at":now.isoformat(),"interval_minutes":3,"message":"Lead created. Sequential distribution is scheduled."}

@app.get("/api/v2/provider/me/leads")
def provider_leads(user:models.User=Depends(require_role("provider")),db:Session=Depends(get_db)):
    provider=db.query(models.Provider).filter(models.Provider.owner_user_id==user.id).first()
    if not provider: raise HTTPException(403,"Business profile not found")
    now=datetime.utcnow()
    due=db.query(models.LeadDelivery).filter(models.LeadDelivery.provider_id==provider.id,models.LeadDelivery.status=="scheduled",models.LeadDelivery.scheduled_at<=now).all()
    for delivery in due: delivery.status="sent";delivery.sent_at=now
    db.commit()
    rows=db.query(models.LeadDelivery,models.CustomerLead,models.MarketplaceArea).join(models.CustomerLead,models.CustomerLead.id==models.LeadDelivery.lead_id).join(models.MarketplaceArea,models.MarketplaceArea.id==models.CustomerLead.area_id).filter(models.LeadDelivery.provider_id==provider.id,models.LeadDelivery.status=="sent").order_by(models.LeadDelivery.sent_at.desc()).all()
    return [{"lead_id":lead.id,"delivery_id":delivery.id,"rank":delivery.rank_position,"city":area.city,"locality":area.locality,"category":lead.category,"service_interest":lead.service_interest,"customer_phone":lead.customer_phone if lead.contact_consent else None,"sent_at":delivery.sent_at,"response_status":delivery.response_status} for delivery,lead,area in rows]


# Customer phone OTP authentication (development OTP only until SMS gateway is configured)
OTP_DEV_MODE = os.getenv("LUSHORA_OTP_DEV_MODE", "true").lower() == "true"
OTP_TTL_MINUTES = 5

def _normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if len(digits) != 10:
        raise HTTPException(400, "Enter a valid 10-digit Indian mobile number")
    return "+91" + digits


def _otp_digest(phone: str, otp: str) -> str:
    return hashlib.sha256((phone + ":" + otp + ":" + os.getenv("LUSHORA_AUTH_SECRET", "development-only-change-this-secret")).encode()).hexdigest()


@app.post("/api/v2/customer/otp/request")
def customer_otp_request(payload: dict, db: Session = Depends(get_db)):
    phone = _normalize_phone(str(payload.get("phone", "")))
    if not OTP_DEV_MODE:
        raise HTTPException(503, "SMS OTP delivery is not configured yet. Configure an SMS provider before enabling production customer login.")
    recent = db.query(models.OTPChallenge).filter(models.OTPChallenge.phone == phone, models.OTPChallenge.created_at > datetime.utcnow() - timedelta(seconds=60)).first()
    if recent:
        raise HTTPException(429, "Please wait 60 seconds before requesting another OTP")
    code = f"{secrets.randbelow(1000000):06d}"
    db.add(models.OTPChallenge(phone=phone, code_hash=_otp_digest(phone, code), expires_at=datetime.utcnow() + timedelta(minutes=OTP_TTL_MINUTES)))
    db.commit()
    return {"message": "Development OTP generated. SMS delivery is not connected yet.", "development_otp": code if OTP_DEV_MODE else None, "expires_in_seconds": OTP_TTL_MINUTES * 60}


@app.post("/api/v2/customer/otp/verify")
def customer_otp_verify(payload: dict, db: Session = Depends(get_db)):
    phone = _normalize_phone(str(payload.get("phone", "")))
    otp = str(payload.get("otp", "")).strip()
    if not re.fullmatch(r"\d{6}", otp):
        raise HTTPException(400, "Enter the 6-digit OTP")
    challenge = db.query(models.OTPChallenge).filter(models.OTPChallenge.phone == phone, models.OTPChallenge.consumed == False).order_by(models.OTPChallenge.created_at.desc()).first()
    if not challenge or challenge.expires_at < datetime.utcnow():
        raise HTTPException(401, "OTP expired. Request a new code.")
    if challenge.attempts >= 5:
        challenge.consumed = True; db.commit()
        raise HTTPException(429, "Too many attempts. Request a new OTP.")
    challenge.attempts += 1
    if not hmac.compare_digest(challenge.code_hash, _otp_digest(phone, otp)):
        db.commit()
        raise HTTPException(401, "Incorrect OTP")
    challenge.consumed = True
    user = db.query(models.User).filter(models.User.phone == phone, models.User.role == "customer").first()
    if not user:
        placeholder_email = phone.replace("+", "") + "@customer.lushora.local"
        user = models.User(full_name="LUSHORA Customer", email=placeholder_email, phone=phone, password_hash=_password_hash(secrets.token_urlsafe(32)), role="customer", is_active=True)
        db.add(user); db.flush()
    db.commit(); db.refresh(user)
    return {"access_token": _make_token(user.id), "token_type": "bearer", "user": user}



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
def list_providers(category: str | None = None, categories: str | None = None, city: str | None = None, locality: str | None = None,
                   min_price: int | None = Query(default=None, ge=0), max_price: int | None = Query(default=None, ge=0),
                   verified: bool | None = None, db: Session = Depends(get_db)):
    q = db.query(models.Provider).options(joinedload(models.Provider.services)).filter(models.Provider.approval_status == "approved")
    selected_categories = [x.strip().lower() for x in (categories or "").split(",") if x.strip()]
    if category: selected_categories.append(category.strip().lower())
    if selected_categories: q = q.filter(func.lower(models.Provider.category).in_(list(set(selected_categories))))
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

def _create_notification(db:Session,user_id:int,title:str,message:str,notification_type:str="info",booking_id:int|None=None):
    notification=models.Notification(recipient_user_id=user_id,title=title,message=message,notification_type=notification_type,booking_id=booking_id)
    db.add(notification)
    db.flush()
    preference=db.query(models.NotificationPreference).filter(models.NotificationPreference.user_id==user_id).first()
    from .notification_service import create_delivery_records
    create_delivery_records(db,notification,preference)


@app.get("/api/me/notification-preferences")
def get_notification_preferences(user:models.User=Depends(current_user),db:Session=Depends(get_db)):
    pref=db.query(models.NotificationPreference).filter(models.NotificationPreference.user_id==user.id).first()
    if not pref: pref=models.NotificationPreference(user_id=user.id);db.add(pref);db.commit();db.refresh(pref)
    return {"in_app_enabled":pref.in_app_enabled,"push_enabled":pref.push_enabled,"whatsapp_enabled":pref.whatsapp_enabled,"sms_enabled":pref.sms_enabled}
@app.put("/api/me/notification-preferences")
def update_notification_preferences(payload:dict,user:models.User=Depends(current_user),db:Session=Depends(get_db)):
    pref=db.query(models.NotificationPreference).filter(models.NotificationPreference.user_id==user.id).first()
    if not pref: pref=models.NotificationPreference(user_id=user.id);db.add(pref)
    for field in ("in_app_enabled","push_enabled","whatsapp_enabled","sms_enabled"):
        if field in payload:
            if not isinstance(payload[field],bool): raise HTTPException(400,f"{field} must be true or false")
            setattr(pref,field,payload[field])
    db.commit();db.refresh(pref)
    return {"in_app_enabled":pref.in_app_enabled,"push_enabled":pref.push_enabled,"whatsapp_enabled":pref.whatsapp_enabled,"sms_enabled":pref.sms_enabled}
@app.get("/api/admin/notification-channels")
def admin_notification_channels(user:models.User=Depends(require_role("admin"))):
    from .notification_service import channel_status
    return channel_status()
@app.get("/api/admin/notification-deliveries")
def admin_notification_deliveries(limit:int=Query(100,ge=1,le=500),user:models.User=Depends(require_role("admin")),db:Session=Depends(get_db)):
    rows=db.query(models.NotificationDelivery).order_by(models.NotificationDelivery.created_at.desc()).limit(limit).all()
    return [{"id":r.id,"notification_id":r.notification_id,"user_id":r.user_id,"channel":r.channel,"status":r.status,"attempts":r.attempts,"provider_message_id":r.provider_message_id,"last_error":r.last_error,"created_at":r.created_at,"updated_at":r.updated_at} for r in rows]

@app.get("/api/me/notifications")
def my_notifications(user:models.User=Depends(current_user),db:Session=Depends(get_db)):
    items=db.query(models.Notification).filter(models.Notification.recipient_user_id==user.id).order_by(models.Notification.created_at.desc()).limit(100).all()
    return [{"id":n.id,"title":n.title,"message":n.message,"type":n.notification_type,"booking_id":n.booking_id,"is_read":n.is_read,"created_at":n.created_at} for n in items]

@app.patch("/api/me/notifications/{notification_id}/read")
def mark_notification_read(notification_id:int,user:models.User=Depends(current_user),db:Session=Depends(get_db)):
    n=db.query(models.Notification).filter(models.Notification.id==notification_id,models.Notification.recipient_user_id==user.id).first()
    if not n: raise HTTPException(404,"Notification not found")
    n.is_read=True;db.commit();return {"id":n.id,"is_read":True}

@app.patch("/api/me/notifications/read-all")
def mark_all_notifications_read(user:models.User=Depends(current_user),db:Session=Depends(get_db)):
    db.query(models.Notification).filter(models.Notification.recipient_user_id==user.id,models.Notification.is_read==False).update({"is_read":True})
    db.commit();return {"message":"All notifications marked as read"}

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

    attached_user = None
    if authorization and authorization.lower().startswith("bearer "):
        attached_user = _get_user_from_token(authorization[7:].strip(), db)
        if not attached_user: raise HTTPException(401, "Invalid or expired token")
        if attached_user.role != "customer": raise HTTPException(403, "Only customer accounts can book")
    booking = models.Booking(**payload.model_dump(), customer_user_id=attached_user.id if attached_user else None)
    db.add(booking)
    if provider.owner_user_id:
        _create_notification(db,provider.owner_user_id,"New booking request",f'{payload.customer_name} requested {service.name} for {payload.appointment_at.strftime("%d %b %Y, %I:%M %p")}.',"booking_request")
    if attached_user:
        _create_notification(db,attached_user.id,"Booking request sent",f'Your request for {provider.name} — {service.name} was sent to the business.',"booking_created")
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
    if booking.customer_user_id:
        status_title={"confirmed":"Booking confirmed","rejected":"Booking declined","cancelled":"Booking cancelled","completed":"Booking completed"}.get(status,"Booking update")
        _create_notification(db,booking.customer_user_id,status_title,f'Your booking #{booking.id} status is now {status}.',"booking_status",booking.id)
    if is_provider_owner and status in {"confirmed","rejected","cancelled","completed"}:
        _create_notification(db,user.id,"Booking updated",f'Booking #{booking.id} is now {status}.',"booking_status",booking.id)
    db.commit()
    return {"id": booking.id, "status": booking.status}


@app.get("/api/customer/me/bookings")
def customer_bookings(user: models.User = Depends(require_role("customer")), db: Session = Depends(get_db)):
    return db.query(models.Booking).filter(models.Booking.customer_user_id == user.id).order_by(models.Booking.appointment_at.desc()).all()

@app.get("/api/admin/bookings")
def admin_bookings(user: models.User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    return db.query(models.Booking).order_by(models.Booking.appointment_at.desc()).all()

@app.get("/api/provider/me/bookings/export.xlsx")
def provider_bookings_export(period:str=Query("all"),month:str=Query(""),day:str=Query(""),status:str=Query(""),service_id:int|None=Query(None),search:str=Query(""),user:models.User=Depends(require_role("provider")),db:Session=Depends(get_db)):
    provider=db.query(models.Provider).filter(models.Provider.owner_user_id==user.id).first()
    if not provider: raise HTTPException(404,"Business profile not found")
    q=db.query(models.Booking).filter(models.Booking.provider_id==provider.id)
    if period=="day" and day:q=q.filter(func.date(models.Booking.appointment_at)==day)
    elif period=="month" and month:q=q.filter(func.strftime("%Y-%m",models.Booking.appointment_at)==month)
    elif period=="year" and month:q=q.filter(func.strftime("%Y",models.Booking.appointment_at)==month[:4])
    if status:q=q.filter(models.Booking.status==status)
    if service_id:q=q.filter(models.Booking.service_id==service_id)
    if search:
        term=f"%{search.strip()}%";q=q.filter((models.Booking.customer_name.ilike(term))|(models.Booking.customer_phone.ilike(term))|(models.Booking.notes.ilike(term)))
    bookings=q.order_by(models.Booking.appointment_at.asc()).all()
    services={s.id:s for s in db.query(models.Service).filter(models.Service.provider_id==provider.id).all()}
    wb=Workbook();ws=wb.active;ws.title="Bookings";ws.append(["Date","Client","Phone","Service","Price (INR)","Status","Appointment","Notes"])
    for b in bookings:
        s=services.get(b.service_id);ws.append([b.appointment_at.strftime("%Y-%m-%d"),b.customer_name,b.customer_phone,s.name if s else "",s.price_inr if s else 0,b.status,b.appointment_at.strftime("%Y-%m-%d %H:%M"),b.notes or ""])
    for cell in ws[1]:cell.font=cell.font.copy(bold=True)
    for col,width in enumerate([14,24,18,24,14,16,22,36],1):ws.column_dimensions[chr(64+col)].width=width
    ws.freeze_panes="A2";ws.auto_filter.ref=ws.dimensions
    out=BytesIO();wb.save(out);out.seek(0)
    return StreamingResponse(out,media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":"attachment; filename=LUSHORA_Business_Report.xlsx"})
@app.get("/api/provider/me/availability")
def provider_availability(user: models.User = Depends(require_role("provider")), db: Session = Depends(get_db)):
    provider=db.query(models.Provider).filter(models.Provider.owner_user_id==user.id).first()
    if not provider: raise HTTPException(404,"Business profile not found")
    try: cfg=json.loads(provider.availability_config or "{}")
    except Exception: cfg={}
    return cfg or {"working_days":[0,1,2,3,4,5],"start_time":"09:00","end_time":"18:00","break_start":"","break_end":"","closed_dates":[]}

@app.put("/api/provider/me/availability")
def update_provider_availability(payload: dict, user: models.User = Depends(require_role("provider")), db: Session = Depends(get_db)):
    provider=db.query(models.Provider).filter(models.Provider.owner_user_id==user.id).first()
    if not provider: raise HTTPException(404,"Business profile not found")
    days=payload.get("working_days",[])
    start=str(payload.get("start_time","09:00"));end=str(payload.get("end_time","18:00"))
    if not isinstance(days,list) or any(not isinstance(d,int) or d<0 or d>6 for d in days): raise HTTPException(400,"Select valid working days")
    try:
        sh,sm=map(int,start.split(":"));eh,em=map(int,end.split(":"))
        if sh*60+sm>=eh*60+em: raise ValueError()
    except Exception: raise HTTPException(400,"End time must be later than start time")
    bs=str(payload.get("break_start",""));be=str(payload.get("break_end",""))
    if bool(bs)!=bool(be): raise HTTPException(400,"Enter both break start and end times")
    if bs:
        try:
            bsm,bss=map(int,bs.split(":"));bem,bes=map(int,be.split(":"))
            if not (sh*60+sm<=bsm*60+bss<bem*60+bes<=eh*60+em): raise ValueError()
        except Exception: raise HTTPException(400,"Break must fall within working hours")
    cfg={"working_days":sorted(set(days)),"start_time":start,"end_time":end,"break_start":bs,"break_end":be,"closed_dates":payload.get("closed_dates",[])}
    provider.availability_config=json.dumps(cfg);db.commit()
    return cfg

@app.get("/api/providers/{provider_id}/available-slots")
def available_slots(provider_id:int,date:str=Query(...),service_id:int=Query(...),db:Session=Depends(get_db)):
    provider=db.query(models.Provider).filter(models.Provider.id==provider_id,models.Provider.approval_status=="approved").first()
    service=db.query(models.Service).filter(models.Service.id==service_id,models.Service.provider_id==provider_id).first()
    if not provider or not service: raise HTTPException(404,"Provider or service not found")
    try: day=datetime.strptime(date,"%Y-%m-%d").date()
    except Exception: raise HTTPException(400,"Invalid date")
    try: cfg=json.loads(provider.availability_config or "{}")
    except Exception: cfg={}
    cfg=cfg or {"working_days":[0,1,2,3,4,5],"start_time":"09:00","end_time":"18:00","break_start":"","break_end":"","closed_dates":[]}
    if day.weekday() not in cfg.get("working_days",[]) or date in cfg.get("closed_dates",[]): return {"slots":[],"duration_minutes":service.duration_minutes}
    start=datetime.combine(day,datetime.strptime(cfg["start_time"],"%H:%M").time());end=datetime.combine(day,datetime.strptime(cfg["end_time"],"%H:%M").time())
    bs=cfg.get("break_start");be=cfg.get("break_end")
    break_s=datetime.combine(day,datetime.strptime(bs,"%H:%M").time()) if bs and be else None
    break_e=datetime.combine(day,datetime.strptime(be,"%H:%M").time()) if bs and be else None
    active=db.query(models.Booking,models.Service).join(models.Service,models.Booking.service_id==models.Service.id).filter(models.Booking.provider_id==provider_id,models.Booking.status.in_(["requested","confirmed"]),func.date(models.Booking.appointment_at)==date).all()
    slots=[];step=30;now=datetime.now()
    t=start
    while t+timedelta(minutes=service.duration_minutes)<=end:
        finish=t+timedelta(minutes=service.duration_minutes)
        if t>now and not (break_s and t<break_e and finish>break_s) and not any(t<eb+timedelta(minutes=es.duration_minutes) and finish>eb for b,es in active for eb in [b.appointment_at]):
            slots.append(t.strftime("%H:%M"))
        t+=timedelta(minutes=step)
    return {"slots":slots,"duration_minutes":service.duration_minutes}

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


@app.get("/api/admin/users/report")
def admin_users_report(start_date:str=Query(""),end_date:str=Query(""),role:str=Query(""),search:str=Query(""),user:models.User=Depends(require_role("admin")),db:Session=Depends(get_db)):
    q=db.query(models.User)
    if role in {"customer","provider","admin"}: q=q.filter(models.User.role==role)
    if start_date: q=q.filter(func.date(models.User.created_at)>=start_date)
    if end_date: q=q.filter(func.date(models.User.created_at)<=end_date)
    if search:
        term=f"%{search.strip()}%"
        q=q.filter((models.User.full_name.ilike(term))|(models.User.email.ilike(term))|(models.User.phone.ilike(term)))
    users=q.order_by(models.User.created_at.desc()).all()
    provider_users=db.query(models.User).filter(models.User.role=="provider")
    customer_users=db.query(models.User).filter(models.User.role=="customer")
    if start_date:
        provider_users=provider_users.filter(func.date(models.User.created_at)>=start_date)
        customer_users=customer_users.filter(func.date(models.User.created_at)>=start_date)
    if end_date:
        provider_users=provider_users.filter(func.date(models.User.created_at)<=end_date)
        customer_users=customer_users.filter(func.date(models.User.created_at)<=end_date)
    return {"total_customers":customer_users.count(),"total_business_accounts":provider_users.count(),"new_customers":customer_users.count(),"new_business_accounts":provider_users.count(),"users":[{"id":u.id,"name":u.full_name,"email":u.email,"phone":u.phone,"role":u.role,"active":u.is_active,"created_at":u.created_at.isoformat() if u.created_at else None,"address":None} for u in users]}

@app.get("/api/admin/users/export.xlsx")
def admin_users_export(start_date:str=Query(""),end_date:str=Query(""),role:str=Query(""),search:str=Query(""),user:models.User=Depends(require_role("admin")),db:Session=Depends(get_db)):
    q=db.query(models.User)
    if role in {"customer","provider","admin"}:q=q.filter(models.User.role==role)
    if start_date:q=q.filter(func.date(models.User.created_at)>=start_date)
    if end_date:q=q.filter(func.date(models.User.created_at)<=end_date)
    if search:
        term=f"%{search.strip()}%";q=q.filter((models.User.full_name.ilike(term))|(models.User.email.ilike(term))|(models.User.phone.ilike(term)))
    records=q.order_by(models.User.created_at.desc()).all()
    wb=Workbook();ws=wb.active;ws.title="User Accounts";ws.append(["User ID","Name","Phone","Email","Account Type","Active","Registered At","Address"])
    for u in records:ws.append([u.id,u.full_name,u.phone,u.email,u.role,u.is_active,u.created_at.strftime("%Y-%m-%d %H:%M") if u.created_at else "", "Not collected in current profile schema"])
    for c in ws[1]:c.font=c.font.copy(bold=True)
    for col,width in enumerate([12,24,18,32,18,12,24,40],1):ws.column_dimensions[chr(64+col)].width=width
    ws.freeze_panes="A2";ws.auto_filter.ref=ws.dimensions
    out=BytesIO();wb.save(out);out.seek(0)
    return StreamingResponse(out,media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":"attachment; filename=LUSHORA_Admin_User_Report.xlsx"})

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

# Business verification and subscription policy MVP
from pathlib import Path
from fastapi import UploadFile, File
from fastapi.responses import FileResponse
import uuid

VERIFICATION_UPLOAD_DIR = Path(os.getenv("LUSHORA_VERIFICATION_UPLOAD_DIR", "./private_verification_uploads")).resolve()
VERIFICATION_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_DOC_TYPES = {"application/pdf", "image/jpeg", "image/png"}
MAX_DOC_BYTES = 8 * 1024 * 1024

@app.post("/api/v2/provider/verification/submit", status_code=201)
def submit_business_verification(payload: dict, user: models.User = Depends(require_role("provider")), db: Session = Depends(get_db)):
    name=str(payload.get("business_name","")).strip(); city=str(payload.get("city","")).strip(); locality=str(payload.get("locality","")).strip(); address=str(payload.get("address","")).strip()
    categories=payload.get("categories",[])
    if not name or not city or not locality or not address: raise HTTPException(400,"Business name, city, locality and address are required")
    if not isinstance(categories,list) or not categories or any(c not in CATEGORIES for c in categories): raise HTTPException(400,"Select one or more valid business categories")
    last4=str(payload.get("aadhaar_last4","")).strip()
    pan=str(payload.get("pan_number","")).strip().upper()
    if last4 and not re.fullmatch(r"\d{4}",last4): raise HTTPException(400,"Aadhaar last 4 digits must be numeric")
    if pan and not re.fullmatch(r"[A-Z]{5}\d{4}[A-Z]",pan): raise HTTPException(400,"Enter a valid PAN format")
    row=db.query(models.BusinessVerification).filter(models.BusinessVerification.owner_user_id==user.id).first()
    if row and row.status in {"under_review","approved"}: raise HTTPException(409,"Your verification is already under review or approved. Contact Admin for changes.")
    if not row: row=models.BusinessVerification(owner_user_id=user.id,business_name=name,categories_json=json.dumps(categories),city=city,locality=locality,address=address,aadhaar_last4=last4,pan_number=pan,status="submitted");db.add(row)
    else:
        row.business_name=name;row.categories_json=json.dumps(categories);row.city=city;row.locality=locality;row.address=address;row.aadhaar_last4=last4;row.pan_number=pan;row.status="submitted";row.admin_notes=""
    db.commit();db.refresh(row)
    return {"id":row.id,"status":row.status,"message":"Verification submitted. Your account remains pending admin approval."}

@app.post("/api/v2/provider/verification/document/{doc_type}")
async def upload_verification_document(doc_type: str, file: UploadFile = File(...), user: models.User = Depends(require_role("provider")), db: Session = Depends(get_db)):
    if doc_type not in {"aadhaar","pan","business"}: raise HTTPException(400,"Unsupported document type")
    row=db.query(models.BusinessVerification).filter(models.BusinessVerification.owner_user_id==user.id).first()
    if not row: raise HTTPException(404,"Submit verification details before uploading documents")
    if file.content_type not in ALLOWED_DOC_TYPES: raise HTTPException(400,"Only PDF, JPG or PNG files are accepted")
    data=await file.read(MAX_DOC_BYTES+1)
    if len(data)>MAX_DOC_BYTES: raise HTTPException(413,"Document must be 8 MB or smaller")
    suffix={"application/pdf":".pdf","image/jpeg":".jpg","image/png":".png"}[file.content_type]
    safe_name=f"{user.id}_{doc_type}_{uuid.uuid4().hex}{suffix}"
    (VERIFICATION_UPLOAD_DIR/safe_name).write_bytes(data)
    setattr(row,doc_type+"_document_name",safe_name);db.commit()
    return {"uploaded":True,"document_type":doc_type,"message":"Document uploaded to private local storage"}

@app.get("/api/v2/admin/verifications")
def admin_verification_list(status: str = "submitted", user: models.User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    rows=db.query(models.BusinessVerification).filter(models.BusinessVerification.status==status).order_by(models.BusinessVerification.submitted_at.asc()).all()
    return [{"id":r.id,"owner_user_id":r.owner_user_id,"owner_name":(u.full_name if (u:=db.query(models.User).filter(models.User.id==r.owner_user_id).first()) else ""),"owner_email":(u.email if u else ""),"owner_phone":(u.phone if u else ""),"business_name":r.business_name,"categories":json.loads(r.categories_json),"city":r.city,"locality":r.locality,"address":r.address,"aadhaar_last4":r.aadhaar_last4,"pan_number":r.pan_number,"documents":{"aadhaar":bool(r.aadhaar_document_name),"pan":bool(r.pan_document_name),"business":bool(r.business_document_name)},"status":r.status,"admin_notes":r.admin_notes,"submitted_at":r.submitted_at} for r in rows]

@app.get("/api/v2/admin/verifications/{verification_id}/document/{doc_type}")
def admin_get_verification_document(verification_id:int,doc_type:str,user:models.User=Depends(require_role("admin")),db:Session=Depends(get_db)):
    if doc_type not in {"aadhaar","pan","business"}: raise HTTPException(400,"Unsupported document type")
    row=db.query(models.BusinessVerification).filter(models.BusinessVerification.id==verification_id).first()
    if not row: raise HTTPException(404,"Verification not found")
    filename=getattr(row,doc_type+"_document_name","")
    if not filename or not (VERIFICATION_UPLOAD_DIR/filename).exists(): raise HTTPException(404,"Document not uploaded")
    return FileResponse(VERIFICATION_UPLOAD_DIR/filename,filename=doc_type+"_verification_document",media_type="application/octet-stream")

@app.patch("/api/v2/admin/verifications/{verification_id}")
def admin_review_verification(verification_id:int,payload:dict,user:models.User=Depends(require_role("admin")),db:Session=Depends(get_db)):
    row=db.query(models.BusinessVerification).filter(models.BusinessVerification.id==verification_id).first()
    if not row: raise HTTPException(404,"Verification not found")
    action=str(payload.get("status","")).lower();notes=str(payload.get("admin_notes","")).strip()
    if action not in {"approved","rejected","under_review"}: raise HTTPException(400,"Status must be approved, rejected or under_review")
    if action=="approved" and (not row.aadhaar_document_name or not row.pan_document_name or not row.business_document_name): raise HTTPException(400,"All three verification documents must be uploaded before approval")
    row.status=action;row.admin_notes=notes;row.reviewed_at=datetime.utcnow() if action in {"approved","rejected"} else None
    if action=="approved":
        userrow=db.query(models.User).filter(models.User.id==row.owner_user_id).first()
        if userrow: userrow.is_active=True
        cats=json.loads(row.categories_json)
        # Create provider listing records per selected category; MVP uses category-specific provider records.
        for cat in cats:
            existing=db.query(models.Provider).filter(models.Provider.owner_user_id==row.owner_user_id,models.Provider.category==cat).first()
            if not existing: db.add(models.Provider(owner_user_id=row.owner_user_id,approval_status="approved",name=row.business_name,category=cat,city=row.city,locality=row.locality,description=row.address,verified=True))
    db.commit();return {"id":row.id,"status":row.status,"message":"Verification review updated"}

@app.get("/api/v2/provider/verification/me")
def provider_verification_me(user:models.User=Depends(require_role("provider")),db:Session=Depends(get_db)):
    row=db.query(models.BusinessVerification).filter(models.BusinessVerification.owner_user_id==user.id).first()
    if not row: return {"status":"not_submitted"}
    return {"id":row.id,"business_name":row.business_name,"categories":json.loads(row.categories_json),"city":row.city,"locality":row.locality,"address":row.address,"documents":{"aadhaar":bool(row.aadhaar_document_name),"pan":bool(row.pan_document_name),"business":bool(row.business_document_name)},"status":row.status,"admin_notes":row.admin_notes}

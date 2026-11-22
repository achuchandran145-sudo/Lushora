from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os, re, json, hmac, hashlib, base64, secrets
from fastapi import FastAPI, Depends, HTTPException, Query, Header, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, update
from io import BytesIO
from openpyxl import Workbook
from fastapi.responses import StreamingResponse
from PIL import Image
from .database import Base, engine, get_db, migrate_sqlite_schema
from . import models, schemas
from . import payment_gateway

Base.metadata.create_all(bind=engine)
# Add availability settings to existing SQLite provider tables.
try:
    from sqlalchemy import inspect as _inspect
    if engine.dialect.name == 'sqlite' and 'availability_config' not in [c['name'] for c in _inspect(engine).get_columns('providers')]:
        with engine.begin() as _conn: _conn.exec_driver_sql("ALTER TABLE providers ADD COLUMN availability_config TEXT DEFAULT '{}'")
except Exception: pass
# Add provider booking mutex version to older SQLite databases.
try:
    from sqlalchemy import inspect as _inspect
    if engine.dialect.name == 'sqlite' and 'booking_lock_version' not in [col['name'] for col in _inspect(engine).get_columns('providers')]:
        with engine.begin() as _conn: _conn.exec_driver_sql("ALTER TABLE providers ADD COLUMN booking_lock_version INTEGER NOT NULL DEFAULT 0")
except Exception: pass
app = FastAPI(title="LUSHORA API", version="0.1.0", description="Beauty and wellness discovery and booking MVP")
# Configure production frontend origins through LUSHORA_CORS_ORIGINS (comma-separated).
_CORS_ORIGINS=[origin.strip().rstrip("/") for origin in os.getenv("LUSHORA_CORS_ORIGINS","").split(",") if origin.strip()]
if os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "development")).lower() != "production":
    _CORS_ORIGINS.extend(["http://localhost:5173","http://127.0.0.1:5173"])
if os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "development")).lower() == "production":
    app.add_middleware(CORSMiddleware, allow_origins=list(dict.fromkeys(_CORS_ORIGINS)), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
else:
    app.add_middleware(CORSMiddleware, allow_origins=list(dict.fromkeys(_CORS_ORIGINS)), allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?", allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

AUTH_SECRET = os.getenv("LUSHORA_AUTH_SECRET", "development-only-change-this-secret").encode()

def _is_production_environment() -> bool:
    return os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "development")).lower() == "production"

def _validate_production_settings() -> None:
    if not _is_production_environment():
        return
    if len(AUTH_SECRET) < 32 or AUTH_SECRET == b"development-only-change-this-secret":
        raise RuntimeError("Production requires LUSHORA_AUTH_SECRET to be a strong secret of at least 32 bytes.")
    if OTP_DEV_MODE if "OTP_DEV_MODE" in globals() else os.getenv("LUSHORA_OTP_DEV_MODE", "true").lower() == "true":
        raise RuntimeError("Production must disable development OTP mode (LUSHORA_OTP_DEV_MODE=false).")
TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7
LUSHORA_LOCAL_TZ = ZoneInfo('Asia/Kolkata')
BOOKING_SLOT_STEP_MINUTES = 30

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
    _validate_production_settings()
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
    if len(first) > 80 or len(last) > 80:
        raise HTTPException(400, "First and last names must be 80 characters or fewer")
    if len(street) > 500:
        raise HTTPException(400, "Street address must be 500 characters or fewer")
    if len(locality) > 120:
        raise HTTPException(400, "Locality must be 120 characters or fewer")
    if city not in {"Chennai", "Coimbatore", "Tiruvannamalai"}:
        raise HTTPException(400, "Select a supported city")
    user.first_name, user.last_name = first, last
    user.full_name = f"{first} {last}"
    user.street_address, user.city, user.locality = street, city, locality
    db.commit(); db.refresh(user)
    return {"first_name": first, "last_name": last, "street_address": street, "city": city, "locality": locality, "phone": user.phone, "profile_complete": True, "message": "Profile saved"}





@app.post("/api/payments",status_code=201)
def create_payment(payload:dict,user:models.User=Depends(current_user),db:Session=Depends(get_db),idempotency_key:str=Header(...,alias="Idempotency-Key")):
    key=idempotency_key.strip()
    if len(key)<8 or len(key)>120: raise HTTPException(400,"Idempotency-Key must be 8 to 120 characters")
    existing=db.query(models.Payment).filter(models.Payment.idempotency_key==key).first()
    if existing:
        if existing.customer_user_id!=user.id: raise HTTPException(409,"Idempotency key already used")
        return {"id":existing.id,"booking_id":existing.booking_id,"amount_inr":existing.amount_inr,"payment_type":existing.payment_type,"balance_due_inr":existing.balance_due_inr,"status":existing.status,"gateway":existing.gateway,"message":"Existing payment request returned"}
    booking_id=int(payload.get("booking_id",0))
    booking=db.query(models.Booking).filter(models.Booking.id==booking_id,models.Booking.customer_user_id==user.id).first()
    if not booking: raise HTTPException(404,"Booking not found for this customer")
    if booking.status not in {"requested","confirmed"}: raise HTTPException(400,"Payment is not available for this booking status")
    pending=db.query(models.Payment).filter(models.Payment.booking_id==booking.id,models.Payment.status=="pending").first()
    if pending: raise HTTPException(409,"A pending payment already exists for this booking")
    service=db.query(models.Service).filter(models.Service.id==booking.service_id).first()
    if not service: raise HTTPException(404,"Booking service not found")
    payment_type=str(payload.get("payment_type","full")).lower()
    if payment_type not in {"full","advance"}: raise HTTPException(400,"payment_type must be full or advance")
    total=int(service.price_inr)
    amount=total if payment_type=="full" else max(1,(total*20+99)//100)
    balance_due=total-amount
    payment=models.Payment(booking_id=booking.id,customer_user_id=user.id,amount_inr=amount,payment_type=payment_type,balance_due_inr=balance_due,status="pending",idempotency_key=key,gateway="unconfigured")
    db.add(payment)
    try: db.commit()
    except Exception:
        db.rollback()
        existing=db.query(models.Payment).filter(models.Payment.idempotency_key==key).first()
        if existing and existing.customer_user_id==user.id: return {"id":existing.id,"booking_id":existing.booking_id,"amount_inr":existing.amount_inr,"status":existing.status,"gateway":existing.gateway,"message":"Existing payment request returned"}
        raise HTTPException(409,"Payment request conflict")
    db.refresh(payment)
    gateway_details=None
    if payment_gateway.razorpay_configured():
        try:
            receipt=payment.receipt_number or f"LUSHORA-PAY-{payment.id}"
            order=payment_gateway.create_order(payment.amount_inr,receipt,{"lushora_payment_id":str(payment.id),"booking_id":str(payment.booking_id)})
            payment.gateway="razorpay";payment.gateway_order_id=order["id"];payment.receipt_number=receipt;db.commit()
            gateway_details={"key_id":os.getenv("RAZORPAY_KEY_ID"),"order_id":payment.gateway_order_id,"amount":order.get("amount"),"currency":order.get("currency","INR")}
        except Exception as exc:
            payment.status="failed";db.commit()
            raise HTTPException(502,"Payment gateway order creation failed; payment record marked failed")
    return {"id":payment.id,"booking_id":payment.booking_id,"amount_inr":payment.amount_inr,"payment_type":payment.payment_type,"balance_due_inr":payment.balance_due_inr,"status":payment.status,"gateway":payment.gateway,"gateway_details":gateway_details,"message":"Razorpay order created; complete checkout" if gateway_details else "Payment record created; gateway not configured, no money collected"}



@app.post("/api/payments/{payment_id}/retry-order")
def retry_payment_order(payment_id:int,user:models.User=Depends(current_user),db:Session=Depends(get_db)):
    payment=db.query(models.Payment).filter(models.Payment.id==payment_id,models.Payment.customer_user_id==user.id).first()
    if not payment:raise HTTPException(404,"Payment not found")
    if payment.status=="paid":raise HTTPException(409,"Payment is already paid")
    if payment.gateway=="razorpay" and payment.gateway_order_id and payment.status=="pending":return {"id":payment.id,"gateway":"razorpay","gateway_details":{"key_id":os.getenv("RAZORPAY_KEY_ID"),"order_id":payment.gateway_order_id,"amount":payment.amount_inr*100,"currency":"INR"},"status":payment.status,"message":"Existing payment order returned; do not create a duplicate"}
    if not payment_gateway.razorpay_configured():raise HTTPException(400,"Razorpay credentials are not configured")
    receipt=payment.receipt_number or f"LUSHORA-PAY-{payment.id}"
    try:order=payment_gateway.create_order(payment.amount_inr,receipt,{"lushora_payment_id":str(payment.id),"booking_id":str(payment.booking_id)})
    except Exception:raise HTTPException(502,"Gateway order retry failed; check gateway status before retrying")
    payment.gateway="razorpay";payment.gateway_order_id=order["id"];payment.receipt_number=receipt;payment.status="pending";db.commit()
    return {"id":payment.id,"gateway":"razorpay","gateway_details":{"key_id":os.getenv("RAZORPAY_KEY_ID"),"order_id":order["id"],"amount":order.get("amount"),"currency":order.get("currency","INR")},"status":"pending","message":"Gateway order recreated for retry"}

@app.get("/api/payments/{payment_id}/receipt")
def payment_receipt(payment_id:int,user:models.User=Depends(current_user),db:Session=Depends(get_db)):
    payment=db.query(models.Payment).filter(models.Payment.id==payment_id,models.Payment.customer_user_id==user.id).first()
    if not payment:raise HTTPException(404,"Payment not found")
    if payment.status not in {"paid","partially_refunded","refunded"}:raise HTTPException(400,"Receipt is available after payment is verified")
    booking=db.query(models.Booking).filter_by(id=payment.booking_id).first();service=db.query(models.Service).filter_by(id=booking.service_id).first() if booking else None;provider=db.query(models.Provider).filter_by(id=booking.provider_id).first() if booking else None
    return {"receipt_number":payment.receipt_number or f"LUSHORA-PAY-{payment.id}","payment_id":payment.id,"gateway_payment_id":payment.gateway_payment_id,"booking_id":payment.booking_id,"provider_name":provider.name if provider else "","service_name":service.name if service else "","customer_name":booking.customer_name if booking else user.full_name,"amount_inr":payment.amount_inr,"payment_type":payment.payment_type,"balance_due_inr":payment.balance_due_inr,"status":payment.status,"gateway":payment.gateway,"paid_at":payment.updated_at}

@app.post("/api/payments/{payment_id}/verify")
def verify_payment_checkout(payment_id:int,payload:dict,user:models.User=Depends(current_user),db:Session=Depends(get_db)):
    payment=db.query(models.Payment).filter(models.Payment.id==payment_id,models.Payment.customer_user_id==user.id).first()
    if not payment: raise HTTPException(404,"Payment not found")
    order_id=str(payload.get("razorpay_order_id",""));payment_id_gateway=str(payload.get("razorpay_payment_id",""));signature=str(payload.get("razorpay_signature",""))
    if payment.gateway!="razorpay" or not payment.gateway_order_id or order_id!=payment.gateway_order_id: raise HTTPException(400,"Payment order mismatch")
    if not payment_gateway.verify_checkout_signature(order_id,payment_id_gateway,signature): raise HTTPException(400,"Payment signature verification failed")
    if payment.status=="paid": return {"id":payment.id,"status":"paid","message":"Payment already verified"}
    payment.gateway_payment_id=payment_id_gateway;payment.gateway_reference=payment_id_gateway;payment.status="paid";db.commit()
    return {"id":payment.id,"status":payment.status,"message":"Payment signature verified and payment marked paid"}

@app.post("/api/payments/razorpay/webhook")
async def razorpay_webhook(request:Request,db:Session=Depends(get_db)):
    raw=await request.body();signature=request.headers.get("X-Razorpay-Signature","");event_id=request.headers.get("x-razorpay-event-id","")
    if not payment_gateway.verify_webhook_signature(raw,signature): raise HTTPException(400,"Webhook signature verification failed")
    if not event_id: raise HTTPException(400,"Missing gateway event id")
    try: data=json.loads(raw.decode());event_type=str(data.get("event",""));entity=(data.get("payload") or {}).get("payment",{}).get("entity",{})
    except Exception: raise HTTPException(400,"Invalid webhook JSON")
    existing=db.query(models.PaymentWebhookEvent).filter_by(event_id=event_id).first()
    if existing:return {"received":True,"duplicate":True,"event_id":event_id}
    event=models.PaymentWebhookEvent(gateway="razorpay",event_id=event_id,event_type=event_type,payload_json=raw.decode(errors="replace"),status="received")
    db.add(event)
    try:db.commit()
    except Exception:db.rollback();return {"received":True,"duplicate":True,"event_id":event_id}
    try:
        order_id=entity.get("order_id");payment=db.query(models.Payment).filter_by(gateway_order_id=order_id,gateway="razorpay").first()
        if event_type in {"payment.captured","order.paid"} and payment:
            amount=entity.get("amount")
            if amount is not None and int(amount)!=payment.amount_inr*100: raise ValueError("Captured amount does not match expected payment amount")
            payment.status="paid";payment.gateway_payment_id=entity.get("id","");payment.gateway_reference=entity.get("id","")
        elif event_type=="payment.failed" and payment and payment.status!="paid":payment.status="failed";payment.gateway_payment_id=entity.get("id","")
        event.status="processed";event.processed_at=datetime.utcnow();db.commit()
    except Exception as exc:
        event.status="failed";event.last_error=str(exc)[:1000];db.commit()
    return {"received":True,"event_id":event_id,"status":event.status}
@app.get("/api/payments/me")
def my_payments(user:models.User=Depends(current_user),db:Session=Depends(get_db)):
    return db.query(models.Payment).filter(models.Payment.customer_user_id==user.id).order_by(models.Payment.created_at.desc()).all()


@app.get("/api/admin/payments")
def admin_payment_list(status:str|None=None,booking_id:int|None=None,customer_user_id:int|None=None,limit:int=Query(100,ge=1,le=500),offset:int=Query(0,ge=0),user:models.User=Depends(require_role("admin")),db:Session=Depends(get_db)):
    q=db.query(models.Payment)
    if status:
        if status not in {"pending","cancelled","failed","paid","refunded","partially_refunded"}: raise HTTPException(400,"Invalid payment status filter")
        q=q.filter(models.Payment.status==status)
    if booking_id is not None: q=q.filter(models.Payment.booking_id==booking_id)
    if customer_user_id is not None: q=q.filter(models.Payment.customer_user_id==customer_user_id)
    total=q.count()
    rows=q.order_by(models.Payment.created_at.desc()).offset(offset).limit(limit).all()
    return {"total":total,"limit":limit,"offset":offset,"payments":[{"id":p.id,"booking_id":p.booking_id,"customer_user_id":p.customer_user_id,"amount_inr":p.amount_inr,"payment_type":p.payment_type,"balance_due_inr":p.balance_due_inr,"status":p.status,"gateway":p.gateway,"gateway_reference":p.gateway_reference,"created_at":p.created_at,"updated_at":p.updated_at} for p in rows]}


@app.get("/api/admin/payments/summary")
def admin_payment_summary(user:models.User=Depends(require_role("admin")),db:Session=Depends(get_db)):
    rows=db.query(models.Payment.status,func.count(models.Payment.id),func.coalesce(func.sum(models.Payment.amount_inr),0)).group_by(models.Payment.status).all()
    by_status={status:{"count":int(count),"amount_inr":int(amount)} for status,count,amount in rows}
    total_count=sum(item["count"] for item in by_status.values())
    total_amount=sum(item["amount_inr"] for item in by_status.values())
    paid_amount=by_status.get("paid",{}).get("amount_inr",0)
    pending_amount=by_status.get("pending",{}).get("amount_inr",0)
    type_rows=db.query(models.Payment.payment_type,func.count(models.Payment.id),func.coalesce(func.sum(models.Payment.amount_inr),0),func.coalesce(func.sum(models.Payment.balance_due_inr),0)).group_by(models.Payment.payment_type).all()
    by_type={kind:{"count":int(count),"amount_inr":int(amount),"balance_due_inr":int(balance)} for kind,count,amount,balance in type_rows}
    return {"total_count":total_count,"total_amount_inr":total_amount,"paid_amount_inr":paid_amount,"pending_amount_inr":pending_amount,"by_status":by_status,"by_payment_type":by_type}


@app.get("/api/admin/commission-rules")
def admin_commission_rules(user:models.User=Depends(require_role("admin")),db:Session=Depends(get_db)):
    rules=db.query(models.CommissionRule).order_by(models.CommissionRule.category.asc()).all()
    configured={r.category:r.commission_percent for r in rules}
    return [{"category":category,"commission_percent":configured.get(category,0)} for category in CATEGORIES]

@app.put("/api/admin/commission-rules")
def update_admin_commission_rules(payload:dict,user:models.User=Depends(require_role("admin")),db:Session=Depends(get_db)):
    rules=payload.get("rules")
    if not isinstance(rules,list) or len(rules)>len(CATEGORIES): raise HTTPException(400,"rules must be a list of category commission settings")
    seen=set()
    for item in rules:
        if not isinstance(item,dict): raise HTTPException(400,"Invalid commission rule")
        category=item.get("category");percent=item.get("commission_percent")
        if category not in CATEGORIES or category in seen: raise HTTPException(400,"Unsupported or duplicate commission category")
        if not isinstance(percent,int) or percent<0 or percent>30: raise HTTPException(400,"Commission percent must be between 0 and 30")
        seen.add(category)
    for item in rules:
        row=db.query(models.CommissionRule).filter_by(category=item["category"]).first()
        if row: row.commission_percent=item["commission_percent"]
        else: db.add(models.CommissionRule(category=item["category"],commission_percent=item["commission_percent"]))
    db.commit()
    configured={r.category:r.commission_percent for r in db.query(models.CommissionRule).all()}
    return [{"category":category,"commission_percent":configured.get(category,0)} for category in CATEGORIES]


@app.get("/api/admin/payments/reconciliation")
def admin_payment_reconciliation(limit:int=Query(100,ge=1,le=500),offset:int=Query(0,ge=0),user:models.User=Depends(require_role("admin")),db:Session=Depends(get_db)):
    rows=(db.query(models.Payment,models.Booking)
          .join(models.Booking,models.Payment.booking_id==models.Booking.id)
          .order_by(models.Payment.updated_at.desc())
          .offset(offset).limit(limit).all())
    findings=[]
    for payment,booking in rows:
        issue=None
        if booking.status=="cancelled" and payment.status=="pending":
            issue="cancelled_booking_with_pending_payment"
        elif booking.status!="cancelled" and payment.status=="cancelled":
            issue="cancelled_payment_with_active_booking"
        elif booking.status=="cancelled" and payment.status=="paid":
            issue="paid_payment_for_cancelled_booking_refund_review"
        if issue:
            findings.append({"payment_id":payment.id,"booking_id":booking.id,"customer_user_id":payment.customer_user_id,"provider_id":booking.provider_id,"payment_amount_inr":payment.amount_inr,"payment_status":payment.status,"booking_status":booking.status,"issue":issue,"updated_at":payment.updated_at})
    return {"checked_records":len(rows),"limit":limit,"offset":offset,"findings_count":len(findings),"findings":findings,"note":"Read-only reconciliation report. Findings require manual review; no payment/refund action was performed."}


@app.post("/api/refunds",status_code=201)
def request_refund(payload:dict,user:models.User=Depends(current_user),db:Session=Depends(get_db)):
    payment_id=int(payload.get("payment_id",0))
    reason=str(payload.get("reason","")).strip()[:1000]
    payment=db.query(models.Payment).filter(models.Payment.id==payment_id,models.Payment.customer_user_id==user.id).first()
    if not payment: raise HTTPException(404,"Payment not found")
    if payment.status!="paid": raise HTTPException(400,"Refund requests require a paid payment")
    booking=db.query(models.Booking).filter(models.Booking.id==payment.booking_id,models.Booking.customer_user_id==user.id).first()
    if not booking: raise HTTPException(404,"Booking not found")
    active=db.query(models.Refund).filter(models.Refund.payment_id==payment.id,models.Refund.status.in_({"requested","reviewing","approved"})).first()
    if active: raise HTTPException(409,"An active refund request already exists for this payment")
    amount=int(payload.get("amount_inr",payment.amount_inr))
    if amount<=0 or amount>payment.amount_inr: raise HTTPException(400,"Refund amount must be between 1 and the paid amount")
    refund=models.Refund(payment_id=payment.id,booking_id=booking.id,customer_user_id=user.id,amount_inr=amount,status="requested",reason=reason)
    db.add(refund); db.commit(); db.refresh(refund)
    return {"id":refund.id,"payment_id":refund.payment_id,"booking_id":refund.booking_id,"amount_inr":refund.amount_inr,"status":refund.status,"message":"Refund request recorded for manual review; no money has been refunded"}

@app.get("/api/refunds/me")
def my_refunds(user:models.User=Depends(current_user),db:Session=Depends(get_db)):
    rows=db.query(models.Refund).filter(models.Refund.customer_user_id==user.id).order_by(models.Refund.requested_at.desc()).all()
    return [{"id":r.id,"payment_id":r.payment_id,"booking_id":r.booking_id,"amount_inr":r.amount_inr,"status":r.status,"reason":r.reason,"requested_at":r.requested_at,"reviewed_at":r.reviewed_at,"reviewer_note":r.reviewer_note} for r in rows]

@app.get("/api/admin/refunds")
def admin_refund_list(status:str|None=None,limit:int=Query(100,ge=1,le=500),offset:int=Query(0,ge=0),user:models.User=Depends(require_role("admin")),db:Session=Depends(get_db)):
    allowed={"requested","reviewing","approved","rejected","processed"}
    if status and status not in allowed: raise HTTPException(400,"Invalid refund status filter")
    q=db.query(models.Refund)
    if status: q=q.filter(models.Refund.status==status)
    total=q.count(); rows=q.order_by(models.Refund.requested_at.desc()).offset(offset).limit(limit).all()
    return {"total":total,"limit":limit,"offset":offset,"refunds":[{"id":r.id,"payment_id":r.payment_id,"booking_id":r.booking_id,"customer_user_id":r.customer_user_id,"amount_inr":r.amount_inr,"status":r.status,"reason":r.reason,"requested_at":r.requested_at,"reviewed_at":r.reviewed_at,"reviewer_user_id":r.reviewer_user_id,"reviewer_note":r.reviewer_note,"external_reference":r.external_reference} for r in rows]}

@app.patch("/api/admin/refunds/{refund_id}/review")
def review_refund(refund_id:int,payload:dict,user:models.User=Depends(require_role("admin")),db:Session=Depends(get_db)):
    refund=db.query(models.Refund).filter(models.Refund.id==refund_id).first()
    if not refund: raise HTTPException(404,"Refund not found")
    action=str(payload.get("status","")).strip().lower()
    if action not in {"reviewing","approved","rejected","processed"}: raise HTTPException(400,"Invalid refund review status")
    if action=="processed":
        if refund.status!="approved":raise HTTPException(409,"Refund must be approved before processing")
        payment=db.query(models.Payment).filter_by(id=refund.payment_id).first()
        if not payment or payment.gateway!="razorpay" or not payment.gateway_payment_id:raise HTTPException(400,"Refund execution requires a verified Razorpay payment")
        if not payment_gateway.razorpay_configured():raise HTTPException(400,"Razorpay credentials are not configured")
        processed_total=db.query(func.coalesce(func.sum(models.Refund.amount_inr),0)).filter(models.Refund.payment_id==payment.id,models.Refund.status=="processed").scalar() or 0
        if processed_total+refund.amount_inr>payment.amount_inr:raise HTTPException(400,"Refund exceeds remaining captured amount")
        try:
            gateway_refund=payment_gateway.create_refund(payment.gateway_payment_id,refund.amount_inr,f"lushora-refund-{refund.id}",{"lushora_refund_id":str(refund.id)})
        except Exception as exc:raise HTTPException(502,"Gateway refund request failed; refund remains approved")
        refund.status="processed";refund.external_reference=str(gateway_refund.get("id",""));refund.reviewer_user_id=user.id;refund.reviewer_note=str(payload.get("reviewer_note","")).strip()[:1000];refund.reviewed_at=datetime.utcnow()
        total_processed=processed_total+refund.amount_inr
        payment.status="refunded" if total_processed>=payment.amount_inr else "partially_refunded"
        db.commit();db.refresh(refund)
        return {"id":refund.id,"status":refund.status,"external_reference":refund.external_reference,"payment_status":payment.status,"message":"Refund submitted to Razorpay; gateway response recorded"}
    if refund.status not in {"requested","reviewing","approved"}: raise HTTPException(409,"Refund is no longer reviewable")
    refund.status=action; refund.reviewer_user_id=user.id; refund.reviewer_note=str(payload.get("reviewer_note","")).strip()[:1000]; refund.reviewed_at=datetime.utcnow()
    db.commit(); db.refresh(refund)
    return {"id":refund.id,"status":refund.status,"reviewer_user_id":refund.reviewer_user_id,"reviewed_at":refund.reviewed_at,"reviewer_note":refund.reviewer_note,"message":"Refund review updated; approval does not transfer money"}

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
    now=datetime.utcnow()
    sub.status=status
    # Explicit activation or renewal starts a fresh 30-day term; pausing/cancelling
    # preserves the current term dates for audit and reporting.
    if status=="active" and (not sub.starts_at or payload.get("renew") is True or (sub.ends_at and sub.ends_at<=now)):
        sub.starts_at=now
        sub.ends_at=now+timedelta(days=30)
    elif status=="expired":
        sub.ends_at=now
    db.commit();return {"id":sub.id,"status":sub.status,"starts_at":sub.starts_at,"ends_at":sub.ends_at,"renewal_supported":True}

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
    existing = db.query(models.Provider).filter(models.Provider.owner_user_id == user.id, models.Provider.category == payload.category).first()
    if existing: raise HTTPException(409, "A business profile already exists for this account in this category")
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
    approved_reviews = db.query(models.Review.provider_id, func.avg(models.Review.rating), func.count(models.Review.id)).filter(models.Review.status == "approved").group_by(models.Review.provider_id).all()
    review_stats = {pid: (float(avg), int(count)) for pid, avg, count in approved_reviews}
    for provider_row in providers:
        if provider_row.id in review_stats: provider_row.rating = round(review_stats[provider_row.id][0], 2)
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



@app.post("/api/me/notification-devices")
def register_notification_device(payload:dict,user:models.User=Depends(current_user),db:Session=Depends(get_db)):
    token=str(payload.get("device_token","")).strip();platform=str(payload.get("platform","web")).strip().lower()
    if not token: raise HTTPException(400,"device_token is required")
    if platform not in {"web","android","ios"}: raise HTTPException(400,"platform must be web, android or ios")
    device=db.query(models.NotificationDevice).filter_by(device_token=token).first()
    if device: device.user_id=user.id;device.platform=platform;device.is_active=True
    else: db.add(models.NotificationDevice(user_id=user.id,device_token=token,platform=platform,is_active=True))
    db.commit();return {"message":"Device registered for push notifications"}
@app.delete("/api/me/notification-devices")
def unregister_notification_device(payload:dict,user:models.User=Depends(current_user),db:Session=Depends(get_db)):
    token=str(payload.get("device_token","")).strip()
    if not token: raise HTTPException(400,"device_token is required")
    db.query(models.NotificationDevice).filter_by(user_id=user.id,device_token=token).update({"is_active":False})
    db.commit();return {"message":"Device unregistered"}
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
    for channel in ("push","whatsapp","sms"):
        if getattr(pref,f"{channel}_enabled") is False:
            db.query(models.NotificationDelivery).filter(
                models.NotificationDelivery.user_id==user.id,
                models.NotificationDelivery.channel==channel,
                models.NotificationDelivery.status.in_(["queued","retry"])
            ).update({"status":"suppressed","last_error":"User consent withdrawn","next_attempt_at":None},synchronize_session=False)
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


BOOKING_REQUEST_TTL_HOURS = 24

def _expire_stale_bookings(db:Session,provider_id:int|None=None):
    now=datetime.utcnow()
    query=db.query(models.Booking).filter(models.Booking.status=="requested",models.Booking.expires_at.isnot(None),models.Booking.expires_at<=now)
    if provider_id is not None: query=query.filter(models.Booking.provider_id==provider_id)
    stale=query.all()
    for booking in stale:
        booking.status="expired"
        if booking.customer_user_id:
            _create_notification(db,booking.customer_user_id,"Booking request expired",f"Your booking request #{booking.id} expired because it was not confirmed within 24 hours.","booking_status",booking.id)
        provider=db.query(models.Provider).filter(models.Provider.id==booking.provider_id).first()
        if provider and provider.owner_user_id:
            _create_notification(db,provider.owner_user_id,"Booking request expired",f"Booking request #{booking.id} expired after 24 hours without confirmation.","booking_status",booking.id)
    return len(stale)


@app.post("/api/customer/me/waitlist",response_model=schemas.WaitlistOut,status_code=201)
def create_waitlist_entry(payload:schemas.WaitlistCreate,user:models.User=Depends(require_role("customer")),db:Session=Depends(get_db)):
    provider=db.query(models.Provider).filter(models.Provider.id==payload.provider_id).first()
    service=db.query(models.Service).filter(models.Service.id==payload.service_id,models.Service.provider_id==payload.provider_id).first()
    if not provider or not service: raise HTTPException(404,"Provider or service not found")
    if payload.preferred_date.tzinfo is not None: raise HTTPException(400,"Preferred date must be local India time without timezone offset")
    if payload.preferred_date.date()<=datetime.now(LUSHORA_LOCAL_TZ).date(): raise HTTPException(400,"Preferred date must be in the future")
    for value in [payload.preferred_time_start,payload.preferred_time_end]:
        if value and (len(value)!=5 or value[2]!=':' or not value[:2].isdigit() or not value[3:].isdigit() or int(value[:2])>23 or int(value[3:])>59): raise HTTPException(400,"Time preference must use HH:MM format")
    if payload.preferred_time_start and payload.preferred_time_end and payload.preferred_time_start>=payload.preferred_time_end: raise HTTPException(400,"Preferred time range start must be before end")
    duplicate=db.query(models.BookingWaitlistEntry).filter_by(customer_user_id=user.id,provider_id=provider.id,service_id=service.id,preferred_date=payload.preferred_date,status="active").first()
    if duplicate: raise HTTPException(409,"You already have an active waitlist entry for this provider, service and date")
    entry=models.BookingWaitlistEntry(customer_user_id=user.id,provider_id=provider.id,service_id=service.id,preferred_date=payload.preferred_date,preferred_time_start=payload.preferred_time_start,preferred_time_end=payload.preferred_time_end,status="active")
    db.add(entry);db.commit();db.refresh(entry);return entry

@app.get("/api/customer/me/waitlist",response_model=list[schemas.WaitlistOut])
def list_waitlist_entries(user:models.User=Depends(require_role("customer")),db:Session=Depends(get_db)):
    return db.query(models.BookingWaitlistEntry).filter_by(customer_user_id=user.id).order_by(models.BookingWaitlistEntry.created_at.desc()).all()

@app.delete("/api/customer/me/waitlist/{entry_id}")
def cancel_waitlist_entry(entry_id:int,user:models.User=Depends(require_role("customer")),db:Session=Depends(get_db)):
    entry=db.query(models.BookingWaitlistEntry).filter_by(id=entry_id,customer_user_id=user.id).first()
    if not entry: raise HTTPException(404,"Waitlist entry not found")
    if entry.status!="active": raise HTTPException(400,"Waitlist entry is not active")
    entry.status="cancelled";db.commit();return {"message":"Waitlist entry cancelled"}

@app.post("/api/bookings", response_model=schemas.BookingOut, status_code=201)
def create_booking(payload: schemas.BookingCreate, db: Session = Depends(get_db), authorization: str | None = Header(default=None)):
    provider = db.query(models.Provider).filter(models.Provider.id == payload.provider_id).first()
    if not provider: raise HTTPException(404, "Provider or service not found")
    # Atomically update the provider lock row before reading booking conflicts.
    # This serializes competing booking writes on SQLite and locks the provider row on PostgreSQL.
    db.execute(update(models.Provider).where(models.Provider.id==provider.id).values(booking_lock_version=models.Provider.booking_lock_version+1))
    _expire_stale_bookings(db,provider.id)
    service = db.query(models.Service).filter(models.Service.id == payload.service_id, models.Service.provider_id == payload.provider_id).first()
    if not service: raise HTTPException(404, "Provider or service not found")
    if payload.appointment_at.tzinfo is not None: raise HTTPException(400, "Send appointment time as local India time without timezone offset")
    local_now=datetime.now(LUSHORA_LOCAL_TZ).replace(tzinfo=None)
    if payload.appointment_at <= local_now: raise HTTPException(400, "Appointment must be in the future")
    if payload.appointment_at.minute % BOOKING_SLOT_STEP_MINUTES != 0 or payload.appointment_at.second or payload.appointment_at.microsecond: raise HTTPException(400, "Appointment must align to a 30-minute slot")
    # Enforce the provider's saved working hours, working days, closure dates and break
    # during booking creation (not only when the UI displays available slots).
    try:
        availability=json.loads(provider.availability_config or "{}")
    except Exception:
        availability={}
    availability=availability or {"working_days":[0,1,2,3,4,5,6],"start_time":"09:00","end_time":"18:00","break_start":"","break_end":"","closed_dates":[]}
    appointment_day=payload.appointment_at.date()
    appointment_date=appointment_day.isoformat()
    if appointment_day.weekday() not in availability.get("working_days",[]): raise HTTPException(400,"Provider is closed on the selected day")
    if appointment_date in availability.get("closed_dates",[]): raise HTTPException(400,"Provider is closed on the selected date")
    try:
        work_start=datetime.combine(appointment_day,datetime.strptime(availability["start_time"],"%H:%M").time())
        work_end=datetime.combine(appointment_day,datetime.strptime(availability["end_time"],"%H:%M").time())
    except Exception:
        raise HTTPException(400,"Provider availability configuration is invalid")
    if payload.appointment_at < work_start or payload.appointment_at + timedelta(minutes=service.duration_minutes) > work_end:
        raise HTTPException(400,"Appointment is outside provider working hours")
    bs=availability.get("break_start");be=availability.get("break_end")
    if bs and be:
        break_start=datetime.combine(appointment_day,datetime.strptime(bs,"%H:%M").time())
        break_end=datetime.combine(appointment_day,datetime.strptime(be,"%H:%M").time())
        if payload.appointment_at < break_end and payload.appointment_at + timedelta(minutes=service.duration_minutes) > break_start:
            raise HTTPException(400,"Appointment overlaps provider break time")


    # Optional staff assignment: only active staff belonging to this provider may be selected.
    if payload.staff_id is not None:
        assigned_staff=db.query(models.ProviderStaff).filter(models.ProviderStaff.id==payload.staff_id,models.ProviderStaff.provider_id==provider.id,models.ProviderStaff.is_active==True).first()
        if not assigned_staff: raise HTTPException(400,"Selected staff member is unavailable for this provider")
    # Optional staff assignment: only active staff belonging to this provider may be selected.
    if payload.staff_id is not None:
        assigned_staff=db.query(models.ProviderStaff).filter(models.ProviderStaff.id==payload.staff_id,models.ProviderStaff.provider_id==provider.id,models.ProviderStaff.is_active==True).first()
        if not assigned_staff: raise HTTPException(400,"Selected staff member is unavailable for this provider")
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
        # Unassigned bookings reserve provider capacity. Staff-assigned bookings may overlap only when different active staff are assigned.
        if payload.staff_id is not None and existing_booking.staff_id is not None and existing_booking.staff_id != payload.staff_id:
            continue
        existing_end = existing_booking.appointment_at + timedelta(minutes=existing_service.duration_minutes)
        if payload.appointment_at < existing_end and new_end > existing_booking.appointment_at:
            raise HTTPException(409, "This provider or selected staff member already has a booking during the selected time")

    attached_user = None
    if authorization and authorization.lower().startswith("bearer "):
        attached_user = _get_user_from_token(authorization[7:].strip(), db)
        if not attached_user: raise HTTPException(401, "Invalid or expired token")
        if attached_user.role != "customer": raise HTTPException(403, "Only customer accounts can book")
    booking = models.Booking(**payload.model_dump(), customer_user_id=attached_user.id if attached_user else None, expires_at=datetime.utcnow()+timedelta(hours=BOOKING_REQUEST_TTL_HOURS))
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



@app.post("/api/admin/bookings/expire-stale")
def admin_expire_stale_bookings(user:models.User=Depends(require_role("admin")),db:Session=Depends(get_db)):
    expired_count=_expire_stale_bookings(db)
    db.commit()
    return {"expired_count":expired_count,"message":"Expired stale booking requests"}

@app.patch("/api/bookings/{booking_id}/status")
def update_booking_status(booking_id: int, status: str = Query(...), user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    allowed = {"confirmed", "rejected", "cancelled", "completed"}
    if status not in allowed: raise HTTPException(400, "Unsupported booking status")
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking: raise HTTPException(404, "Booking not found")
    if booking.status=="requested" and booking.expires_at and booking.expires_at<=datetime.utcnow():
        _expire_stale_bookings(db,booking.provider_id);db.commit();raise HTTPException(400,"Booking request has expired")
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
    if status == "cancelled" and is_customer_owner and booking.status not in {"requested", "confirmed"}: raise HTTPException(400, "Customers can cancel only requested or confirmed bookings")
    if status == "cancelled" and is_provider_owner and booking.status not in {"requested", "confirmed"}: raise HTTPException(400, "Providers can cancel only requested or confirmed bookings")
    booking.status = status
    if status == "cancelled":
        # Cancel pending payment records; no gateway transaction has been collected yet.
        db.query(models.Payment).filter(models.Payment.booking_id==booking.id,models.Payment.status=="pending").update({models.Payment.status:"cancelled"},synchronize_session=False)
    if booking.customer_user_id:
        status_title={"confirmed":"Booking confirmed","rejected":"Booking declined","cancelled":"Booking cancelled","completed":"Booking completed"}.get(status,"Booking update")
        _create_notification(db,booking.customer_user_id,status_title,f'Your booking #{booking.id} status is now {status}.',"booking_status",booking.id)
    if is_provider_owner and status in {"confirmed","rejected","cancelled","completed"}:
        _create_notification(db,user.id,"Booking updated",f'Booking #{booking.id} is now {status}.',"booking_status",booking.id)
    db.commit()
    cancellation_policy={"fee_applies":False,"fee_percent":0,"notice_hours":None}
    if status=="cancelled" and is_customer_owner:
        try: availability_cfg=json.loads(provider.availability_config or "{}")
        except Exception: availability_cfg={}
        min_hours=int(availability_cfg.get("cancellation_min_hours",0) or 0)
        fee_percent=int(availability_cfg.get("cancellation_fee_percent",0) or 0)
        hours_until=(booking.appointment_at-datetime.now(LUSHORA_LOCAL_TZ).replace(tzinfo=None)).total_seconds()/3600
        fee_applies=hours_until<min_hours and fee_percent>0
        cancellation_policy={"fee_applies":fee_applies,"fee_percent":fee_percent if fee_applies else 0,"notice_hours":round(hours_until,2)}
    return {"id": booking.id, "status": booking.status,"cancellation_policy":cancellation_policy}


@app.get("/api/customer/me/bookings")
def customer_bookings(user: models.User = Depends(require_role("customer")), db: Session = Depends(get_db)):
    _expire_stale_bookings(db);db.commit()
    return db.query(models.Booking).filter(models.Booking.customer_user_id == user.id).order_by(models.Booking.appointment_at.desc()).all()

@app.get("/api/admin/bookings")
def admin_bookings(user: models.User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    _expire_stale_bookings(db);db.commit()
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
    return cfg or {"working_days":[0,1,2,3,4,5,6],"start_time":"09:00","end_time":"18:00","break_start":"","break_end":"","closed_dates":[]}

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
    closed_dates=payload.get("closed_dates",[])
    if not isinstance(closed_dates,list) or len(closed_dates)>366:
        raise HTTPException(400,"Closed dates must be a list of at most 366 dates")
    normalized_closed=[]
    for value in closed_dates:
        if not isinstance(value,str):
            raise HTTPException(400,"Closed dates must use YYYY-MM-DD format")
        try:
            parsed=datetime.strptime(value,"%Y-%m-%d")
            if parsed.strftime("%Y-%m-%d")!=value: raise ValueError()
        except Exception:
            raise HTTPException(400,"Closed dates must use YYYY-MM-DD format")
        if value not in normalized_closed: normalized_closed.append(value)
    cancel_min_hours=payload.get("cancellation_min_hours",0)
    cancel_fee_percent=payload.get("cancellation_fee_percent",0)
    if not isinstance(cancel_min_hours,int) or cancel_min_hours<0 or cancel_min_hours>168: raise HTTPException(400,"Cancellation notice hours must be between 0 and 168")
    if not isinstance(cancel_fee_percent,int) or cancel_fee_percent<0 or cancel_fee_percent>100: raise HTTPException(400,"Cancellation fee percentage must be between 0 and 100")
    cfg={"working_days":sorted(set(days)),"start_time":start,"end_time":end,"break_start":bs,"break_end":be,"closed_dates":normalized_closed,"cancellation_min_hours":cancel_min_hours,"cancellation_fee_percent":cancel_fee_percent}
    provider.availability_config=json.dumps(cfg);db.commit()
    return cfg

@app.get("/api/providers/{provider_id}/available-slots")
def available_slots(provider_id:int,date:str=Query(...),service_id:int=Query(...),staff_id:int|None=Query(None),db:Session=Depends(get_db)):
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
    _expire_stale_bookings(db,provider_id);db.commit()
    active=db.query(models.Booking,models.Service).join(models.Service,models.Booking.service_id==models.Service.id).filter(models.Booking.provider_id==provider_id,models.Booking.status.in_(["requested","confirmed"]),func.date(models.Booking.appointment_at)==date).all()
    slots=[];step=BOOKING_SLOT_STEP_MINUTES;now=datetime.now(LUSHORA_LOCAL_TZ).replace(tzinfo=None)
    t=start
    while t+timedelta(minutes=service.duration_minutes)<=end:
        finish=t+timedelta(minutes=service.duration_minutes)
        if t>now and not (break_s and t<break_e and finish>break_s) and not any((staff_id is None or b.staff_id is None or b.staff_id==staff_id) and t<eb+timedelta(minutes=es.duration_minutes) and finish>eb for b,es in active for eb in [b.appointment_at]):
            slots.append(t.strftime("%H:%M"))
        t+=timedelta(minutes=step)
    return {"slots":slots,"duration_minutes":service.duration_minutes}

@app.get("/api/provider/me/bookings")
def provider_bookings(user: models.User = Depends(require_role("provider")), db: Session = Depends(get_db)):
    provider = db.query(models.Provider).filter(models.Provider.owner_user_id == user.id).first()
    if not provider: raise HTTPException(404, "Business profile not found")
    _expire_stale_bookings(db,provider.id);db.commit()
    return db.query(models.Booking).filter(models.Booking.provider_id == provider.id).order_by(models.Booking.appointment_at.asc()).all()

@app.patch("/api/provider/me/profile")
def update_provider_profile(payload: dict, user: models.User = Depends(require_role("provider")), db: Session = Depends(get_db)):
    provider_id = int(payload.get("provider_id", 0)) if payload.get("provider_id") else None
    q = db.query(models.Provider).filter(models.Provider.owner_user_id == user.id)
    if provider_id: q = q.filter(models.Provider.id == provider_id)
    provider = q.first()
    if not provider: raise HTTPException(404, "Business profile not found for this account")
    name = str(payload.get("name", provider.name)).strip()
    description = str(payload.get("description", provider.description)).strip()
    city = str(payload.get("city", provider.city)).strip()
    locality = str(payload.get("locality", provider.locality)).strip()
    allowed_cities = {"Chennai", "Coimbatore", "Tiruvannamalai"}
    if not name or len(name) > 120: raise HTTPException(400, "Business name is required and must be at most 120 characters")
    if city not in allowed_cities: raise HTTPException(400, "Select a supported city")
    if not locality or len(locality) > 100: raise HTTPException(400, "Locality is required and must be at most 100 characters")
    if len(description) > 4000: raise HTTPException(400, "Description must be at most 4000 characters")
    provider.name, provider.description, provider.city, provider.locality = name, description, city, locality
    db.commit(); db.refresh(provider)
    return {"id": provider.id, "name": provider.name, "category": provider.category, "city": provider.city, "locality": provider.locality, "description": provider.description, "approval_status": provider.approval_status, "message": "Business profile updated"}

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
    if _is_production_environment():
        raise HTTPException(404, "Not found")
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
    # Store verification files in a private, searchable business/city/locality folder.
    def _safe_folder(value: str) -> str:
        cleaned=re.sub(r"[^A-Za-z0-9._-]+","_",value.strip()).strip("._-")
        return cleaned[:80] or "unknown"
    folder=VERIFICATION_UPLOAD_DIR/_safe_folder(row.business_name)/_safe_folder(row.city)/_safe_folder(row.locality)/f"account_{user.id}_verification_{row.id}"
    folder.mkdir(parents=True,exist_ok=True)
    safe_name=f"{doc_type}_{uuid.uuid4().hex}{suffix}"
    (folder/safe_name).write_bytes(data)
    # Persist relative private-storage path for authenticated document retrieval.
    stored_path=str((folder/safe_name).relative_to(VERIFICATION_UPLOAD_DIR))
    setattr(row,doc_type+"_document_name",stored_path);db.commit()
    return {"uploaded":True,"document_type":doc_type,"message":"Document uploaded to private business verification folder"}

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
    if not filename: raise HTTPException(404,"Document not uploaded")
    target=(VERIFICATION_UPLOAD_DIR/filename).resolve()
    if VERIFICATION_UPLOAD_DIR not in target.parents or not target.is_file(): raise HTTPException(404,"Document not uploaded")
    # Return a PDF consistently: preserve uploaded PDFs and convert JPG/PNG uploads to PDF.
    business_label=re.sub(r"[^A-Za-z0-9._-]+","_",row.business_name.strip()).strip("._-") or "business"
    download_name=f"{business_label}_{doc_type}_verification.pdf"
    if target.suffix.lower()==".pdf":
        return FileResponse(target,filename=download_name,media_type="application/pdf")
    try:
        with Image.open(target) as source:
            pdf_image=source.convert("RGB")
            pdf_buffer=BytesIO()
            pdf_image.save(pdf_buffer,format="PDF",resolution=150.0)
        pdf_buffer.seek(0)
        return StreamingResponse(pdf_buffer,media_type="application/pdf",headers={"Content-Disposition":f'attachment; filename="{download_name}"'})
    except Exception:
        raise HTTPException(422,"Unable to convert this verification image to PDF")

@app.patch("/api/v2/admin/verifications/{verification_id}")
def admin_review_verification(verification_id:int,payload:dict,user:models.User=Depends(require_role("admin")),db:Session=Depends(get_db)):
    row=db.query(models.BusinessVerification).filter(models.BusinessVerification.id==verification_id).first()
    if not row: raise HTTPException(404,"Verification not found")
    action=str(payload.get("status","")).lower();notes=str(payload.get("admin_notes","")).strip()
    if action=="pending": action="submitted"
    if action not in {"approved","rejected","under_review","submitted"}: raise HTTPException(400,"Status must be approved, rejected, under_review or submitted")
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

@app.delete("/api/v2/admin/verifications/{verification_id}")
def admin_delete_verification(verification_id:int,user:models.User=Depends(require_role("admin")),db:Session=Depends(get_db)):
    row=db.query(models.BusinessVerification).filter(models.BusinessVerification.id==verification_id).first()
    if not row: raise HTTPException(404,"Verification not found")
    owner_id=row.owner_user_id
    # Remove verification files only after resolving paths within the private storage root.
    for doc_type in ("aadhaar","pan","business"):
        stored=getattr(row,doc_type+"_document_name","")
        if stored:
            target=(VERIFICATION_UPLOAD_DIR/stored).resolve()
            if VERIFICATION_UPLOAD_DIR in target.parents and target.is_file():
                try: target.unlink()
                except OSError: pass
    # Remove provider listings created for this business owner/category, including their services.
    providers=db.query(models.Provider).filter(models.Provider.owner_user_id==owner_id,models.Provider.name==row.business_name,models.Provider.city==row.city,models.Provider.locality==row.locality).all()
    for provider in providers:
        db.query(models.Service).filter(models.Service.provider_id==provider.id).delete(synchronize_session=False)
        db.delete(provider)
    db.delete(row);db.commit()
    return {"id":verification_id,"deleted":True,"message":"Business verification and associated private documents deleted"}

@app.get("/api/v2/provider/verification/me")
def provider_verification_me(user:models.User=Depends(require_role("provider")),db:Session=Depends(get_db)):
    row=db.query(models.BusinessVerification).filter(models.BusinessVerification.owner_user_id==user.id).first()
    if not row: return {"status":"not_submitted"}
    return {"id":row.id,"business_name":row.business_name,"categories":json.loads(row.categories_json),"city":row.city,"locality":row.locality,"address":row.address,"documents":{"aadhaar":bool(row.aadhaar_document_name),"pan":bool(row.pan_document_name),"business":bool(row.business_document_name)},"status":row.status,"admin_notes":row.admin_notes}

# Verified booking reviews
@app.post("/api/customer/me/reviews", status_code=201)
def create_review(payload: dict, user: models.User = Depends(require_role("customer")), db: Session = Depends(get_db)):
    booking_id = payload.get("booking_id")
    try: rating = int(payload.get("rating"))
    except (TypeError, ValueError): raise HTTPException(400, "Rating must be an integer from 1 to 5")
    comment = str(payload.get("comment", "")).strip()
    if rating < 1 or rating > 5: raise HTTPException(400, "Rating must be between 1 and 5")
    if len(comment) > 2000: raise HTTPException(400, "Review comment is too long")
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id, models.Booking.customer_user_id == user.id).first()
    if not booking: raise HTTPException(404, "Customer booking not found")
    if booking.status != "completed": raise HTTPException(400, "Reviews are allowed only for completed bookings")
    if db.query(models.Review).filter(models.Review.booking_id == booking.id).first(): raise HTTPException(409, "This booking already has a review")
    review = models.Review(booking_id=booking.id, customer_user_id=user.id, provider_id=booking.provider_id, rating=rating, comment=comment)
    db.add(review); db.commit(); db.refresh(review)
    return {"id":review.id,"booking_id":review.booking_id,"provider_id":review.provider_id,"rating":review.rating,"comment":review.comment,"status":review.status,"created_at":review.created_at}

@app.get("/api/providers/{provider_id}/reviews")
def provider_reviews(provider_id: int, db: Session = Depends(get_db)):
    provider = db.query(models.Provider).filter(models.Provider.id == provider_id, models.Provider.approval_status == "approved").first()
    if not provider: raise HTTPException(404, "Provider not found")
    rows = db.query(models.Review).filter(models.Review.provider_id == provider_id, models.Review.status == "approved").order_by(models.Review.created_at.desc()).all()
    return {"provider_id":provider_id,"average_rating":round(sum(x.rating for x in rows)/len(rows),2) if rows else 0,"review_count":len(rows),"reviews":[{"id":x.id,"rating":x.rating,"comment":x.comment,"provider_reply":x.provider_reply,"created_at":x.created_at} for x in rows]}

@app.get("/api/customer/me/reviews")
def customer_reviews(user: models.User = Depends(require_role("customer")), db: Session = Depends(get_db)):
    rows=db.query(models.Review).filter(models.Review.customer_user_id==user.id).order_by(models.Review.created_at.desc()).all()
    return [{"id":x.id,"booking_id":x.booking_id,"provider_id":x.provider_id,"rating":x.rating,"comment":x.comment,"status":x.status,"provider_reply":x.provider_reply,"created_at":x.created_at} for x in rows]

@app.patch("/api/provider/me/reviews/{review_id}/reply")
def provider_review_reply(review_id:int,payload:dict,user:models.User=Depends(require_role("provider")),db:Session=Depends(get_db)):
    provider=db.query(models.Provider).filter(models.Provider.owner_user_id==user.id).first()
    review=db.query(models.Review).filter(models.Review.id==review_id,models.Review.provider_id==(provider.id if provider else -1),models.Review.status=="approved").first()
    if not review: raise HTTPException(404,"Review not found")
    reply=str(payload.get("reply","")).strip()
    if not reply or len(reply)>2000: raise HTTPException(400,"Reply must be between 1 and 2000 characters")
    review.provider_reply=reply;db.commit()
    return {"id":review.id,"provider_reply":review.provider_reply}

@app.get("/api/admin/reviews")
def admin_reviews(status:str=Query("all"),user:models.User=Depends(require_role("admin")),db:Session=Depends(get_db)):
    q=db.query(models.Review)
    if status!="all": q=q.filter(models.Review.status==status)
    return [{"id":x.id,"booking_id":x.booking_id,"customer_user_id":x.customer_user_id,"provider_id":x.provider_id,"rating":x.rating,"comment":x.comment,"status":x.status,"provider_reply":x.provider_reply,"created_at":x.created_at} for x in q.order_by(models.Review.created_at.desc()).all()]

@app.patch("/api/admin/reviews/{review_id}")
def admin_review_moderation(review_id:int,payload:dict,user:models.User=Depends(require_role("admin")),db:Session=Depends(get_db)):
    status=str(payload.get("status",""))
    if status not in {"approved","rejected"}: raise HTTPException(400,"Status must be approved or rejected")
    review=db.query(models.Review).filter(models.Review.id==review_id).first()
    if not review: raise HTTPException(404,"Review not found")
    review.status=status;db.commit()
    return {"id":review.id,"status":review.status}

@app.patch("/api/provider/me/services/{service_id}")
def provider_update_service(service_id:int,payload:dict,user:models.User=Depends(require_role("provider")),db:Session=Depends(get_db)):
    provider=db.query(models.Provider).filter(models.Provider.owner_user_id==user.id).first()
    service=db.query(models.Service).filter(models.Service.id==service_id,models.Service.provider_id==(provider.id if provider else -1)).first()
    if not service: raise HTTPException(404,"Service not found")
    if "name" in payload:
        name=str(payload["name"]).strip()
        if len(name)<2 or len(name)>120: raise HTTPException(400,"Service name must be 2 to 120 characters")
        service.name=name
    if "price_inr" in payload:
        try: price=int(payload["price_inr"])
        except (TypeError,ValueError): raise HTTPException(400,"Price must be a whole number")
        if price<0: raise HTTPException(400,"Price cannot be negative")
        service.price_inr=price
    if "duration_minutes" in payload:
        try: duration=int(payload["duration_minutes"])
        except (TypeError,ValueError): raise HTTPException(400,"Duration must be a whole number")
        if duration<5 or duration>600: raise HTTPException(400,"Duration must be between 5 and 600 minutes")
        service.duration_minutes=duration
    db.commit();db.refresh(service)
    return service


# Provider portfolio/gallery uploads (public portfolio images, owner-managed)
PORTFOLIO_UPLOAD_DIR = Path(os.getenv("LUSHORA_PORTFOLIO_UPLOAD_DIR", "./portfolio_uploads")).resolve()
PORTFOLIO_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_PORTFOLIO_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_PORTFOLIO_FORMATS = {"JPEG", "PNG", "WEBP"}

@app.post("/api/provider/me/portfolio", status_code=201)
async def upload_provider_portfolio_image(file: UploadFile = File(...), caption: str = Form(default=""), user: models.User = Depends(require_role("provider")), db: Session = Depends(get_db)):
    provider=db.query(models.Provider).filter(models.Provider.owner_user_id==user.id).first()
    if not provider: raise HTTPException(404,"Business profile not found")
    if len(caption.strip())>240: raise HTTPException(400,"Caption must be 240 characters or fewer")
    raw=await file.read(MAX_PORTFOLIO_IMAGE_BYTES+1)
    if len(raw)>MAX_PORTFOLIO_IMAGE_BYTES: raise HTTPException(413,"Portfolio image must be 5 MB or smaller")
    try:
        image=Image.open(BytesIO(raw))
        image.verify()
        image=Image.open(BytesIO(raw))
        if image.format not in ALLOWED_PORTFOLIO_FORMATS: raise ValueError("Unsupported format")
        if image.width<1 or image.height<1 or image.width*image.height>20_000_000: raise ValueError("Image dimensions are invalid or too large")
    except Exception:
        raise HTTPException(400,"Upload a valid JPEG, PNG or WEBP image")
    ext={"JPEG":"jpg","PNG":"png","WEBP":"webp"}[image.format]
    name=f"{uuid.uuid4().hex}.{ext}"
    folder=PORTFOLIO_UPLOAD_DIR/f"provider_{provider.id}"
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/name
    path.write_bytes(raw)
    record=models.ProviderPortfolioImage(provider_id=provider.id,storage_path=str(path),caption=caption.strip())
    db.add(record);db.commit();db.refresh(record)
    return {"id":record.id,"caption":record.caption,"image_url":f"/api/providers/{provider.id}/portfolio/{record.id}","created_at":record.created_at}

@app.get("/api/provider/me/portfolio")
def list_provider_portfolio(user: models.User = Depends(require_role("provider")), db: Session = Depends(get_db)):
    provider=db.query(models.Provider).filter(models.Provider.owner_user_id==user.id).first()
    if not provider: raise HTTPException(404,"Business profile not found")
    records=db.query(models.ProviderPortfolioImage).filter(models.ProviderPortfolioImage.provider_id==provider.id).order_by(models.ProviderPortfolioImage.created_at.desc()).all()
    return [{"id":r.id,"caption":r.caption,"image_url":f"/api/providers/{provider.id}/portfolio/{r.id}","created_at":r.created_at} for r in records]

@app.delete("/api/provider/me/portfolio/{image_id}")
def delete_provider_portfolio_image(image_id:int,user: models.User = Depends(require_role("provider")),db: Session = Depends(get_db)):
    provider=db.query(models.Provider).filter(models.Provider.owner_user_id==user.id).first()
    if not provider: raise HTTPException(404,"Business profile not found")
    record=db.query(models.ProviderPortfolioImage).filter(models.ProviderPortfolioImage.id==image_id,models.ProviderPortfolioImage.provider_id==provider.id).first()
    if not record: raise HTTPException(404,"Portfolio image not found")
    try: Path(record.storage_path).unlink(missing_ok=True)
    except OSError: raise HTTPException(500,"Could not remove portfolio image file")
    db.delete(record);db.commit();return {"message":"Portfolio image removed"}

@app.get("/api/providers/{provider_id}/portfolio/{image_id}")
def get_public_portfolio_image(provider_id:int,image_id:int,db: Session = Depends(get_db)):
    record=db.query(models.ProviderPortfolioImage).filter(models.ProviderPortfolioImage.id==image_id,models.ProviderPortfolioImage.provider_id==provider_id).first()
    if not record: raise HTTPException(404,"Portfolio image not found")
    path=Path(record.storage_path)
    if not path.is_file(): raise HTTPException(404,"Portfolio image file not found")
    return FileResponse(path)


# Provider staff roster (owner-managed; staff login/RBAC is a later security phase)
def _provider_for_owner(user,db):
    provider=db.query(models.Provider).filter(models.Provider.owner_user_id==user.id).first()
    if not provider: raise HTTPException(404,"Business profile not found")
    return provider

@app.get("/api/providers/{provider_id}/staff")
def public_provider_staff(provider_id:int,db:Session=Depends(get_db)):
    provider=db.query(models.Provider).filter(models.Provider.id==provider_id,models.Provider.approval_status=="approved").first()
    if not provider: raise HTTPException(404,"Provider not found")
    rows=db.query(models.ProviderStaff).filter(models.ProviderStaff.provider_id==provider_id,models.ProviderStaff.is_active==True).order_by(models.ProviderStaff.full_name).all()
    return [{"id":row.id,"full_name":row.full_name,"role":row.role} for row in rows]

@app.get("/api/provider/me/staff")
def provider_staff_list(user: models.User = Depends(require_role("provider")),db: Session = Depends(get_db)):
    provider=_provider_for_owner(user,db)
    rows=db.query(models.ProviderStaff).filter(models.ProviderStaff.provider_id==provider.id).order_by(models.ProviderStaff.created_at.desc()).all()
    return [{"id":r.id,"full_name":r.full_name,"role":r.role,"phone":r.phone,"is_active":r.is_active,"created_at":r.created_at} for r in rows]

@app.post("/api/provider/me/staff",status_code=201)
def provider_staff_create(payload:dict,user: models.User = Depends(require_role("provider")),db: Session = Depends(get_db)):
    provider=_provider_for_owner(user,db)
    name=str(payload.get("full_name","")).strip();role=str(payload.get("role","staff")).strip().lower();phone=str(payload.get("phone","")).strip()
    if not name or len(name)>120: raise HTTPException(400,"Staff name is required and must be 120 characters or fewer")
    if role not in {"staff","manager"}: raise HTTPException(400,"Role must be staff or manager")
    if len(phone)>20: raise HTTPException(400,"Phone must be 20 characters or fewer")
    row=models.ProviderStaff(provider_id=provider.id,full_name=name,role=role,phone=phone,is_active=True);db.add(row);db.commit();db.refresh(row)
    return {"id":row.id,"full_name":row.full_name,"role":row.role,"phone":row.phone,"is_active":row.is_active,"created_at":row.created_at}

@app.patch("/api/provider/me/staff/{staff_id}")
def provider_staff_update(staff_id:int,payload:dict,user: models.User = Depends(require_role("provider")),db: Session = Depends(get_db)):
    provider=_provider_for_owner(user,db)
    row=db.query(models.ProviderStaff).filter(models.ProviderStaff.id==staff_id,models.ProviderStaff.provider_id==provider.id).first()
    if not row: raise HTTPException(404,"Staff member not found")
    if "full_name" in payload:
        name=str(payload["full_name"]).strip()
        if not name or len(name)>120: raise HTTPException(400,"Staff name is required and must be 120 characters or fewer")
        row.full_name=name
    if "role" in payload:
        role=str(payload["role"]).strip().lower()
        if role not in {"staff","manager"}: raise HTTPException(400,"Role must be staff or manager")
        row.role=role
    if "phone" in payload:
        phone=str(payload["phone"]).strip()
        if len(phone)>20: raise HTTPException(400,"Phone must be 20 characters or fewer")
        row.phone=phone
    if "is_active" in payload:
        if not isinstance(payload["is_active"],bool): raise HTTPException(400,"is_active must be boolean")
        row.is_active=payload["is_active"]
    db.commit();db.refresh(row)
    return {"id":row.id,"full_name":row.full_name,"role":row.role,"phone":row.phone,"is_active":row.is_active,"created_at":row.created_at}

@app.delete("/api/provider/me/staff/{staff_id}")
def provider_staff_delete(staff_id:int,user: models.User = Depends(require_role("provider")),db: Session = Depends(get_db)):
    provider=_provider_for_owner(user,db)
    row=db.query(models.ProviderStaff).filter(models.ProviderStaff.id==staff_id,models.ProviderStaff.provider_id==provider.id).first()
    if not row: raise HTTPException(404,"Staff member not found")
    db.delete(row);db.commit();return {"message":"Staff member removed"}


# Multi-location provider branches (each provider listing is a service category)
SUPPORTED_BRANCH_CITIES={"Chennai","Coimbatore","Tiruvannamalai"}

def _branch_out(row):
    return {"id":row.id,"branch_name":row.branch_name,"city":row.city,"locality":row.locality,"address":row.address,"phone":row.phone,"is_active":row.is_active,"created_at":row.created_at}

@app.get("/api/provider/me/branches")
def provider_branches_list(user:models.User=Depends(require_role("provider")),db:Session=Depends(get_db)):
    provider=_provider_for_owner(user,db)
    rows=db.query(models.ProviderBranch).filter(models.ProviderBranch.provider_id==provider.id).order_by(models.ProviderBranch.created_at.desc()).all()
    return [_branch_out(r) for r in rows]

@app.post("/api/provider/me/branches",status_code=201)
def provider_branch_create(payload:dict,user:models.User=Depends(require_role("provider")),db:Session=Depends(get_db)):
    provider=_provider_for_owner(user,db)
    name=str(payload.get("branch_name","")).strip();city=str(payload.get("city","")).strip();locality=str(payload.get("locality","")).strip();address=str(payload.get("address","")).strip();phone=str(payload.get("phone","")).strip()
    if not name or len(name)>120 or not locality or len(locality)>120 or not address or len(address)>1000: raise HTTPException(400,"Branch name, locality and address are required and must fit their limits")
    if city not in SUPPORTED_BRANCH_CITIES: raise HTTPException(400,"Select a supported city")
    if len(phone)>20: raise HTTPException(400,"Phone must be 20 characters or fewer")
    row=models.ProviderBranch(provider_id=provider.id,branch_name=name,city=city,locality=locality,address=address,phone=phone,is_active=True);db.add(row);db.commit();db.refresh(row);return _branch_out(row)

@app.patch("/api/provider/me/branches/{branch_id}")
def provider_branch_update(branch_id:int,payload:dict,user:models.User=Depends(require_role("provider")),db:Session=Depends(get_db)):
    provider=_provider_for_owner(user,db)
    row=db.query(models.ProviderBranch).filter(models.ProviderBranch.id==branch_id,models.ProviderBranch.provider_id==provider.id).first()
    if not row: raise HTTPException(404,"Branch not found")
    for field,limit in [("branch_name",120),("locality",120),("address",1000),("phone",20)]:
        if field in payload:
            value=str(payload[field]).strip()
            if field in {"branch_name","locality","address"} and not value: raise HTTPException(400,f"{field} is required")
            if len(value)>limit: raise HTTPException(400,f"{field} exceeds maximum length")
            setattr(row,field,value)
    if "city" in payload:
        city=str(payload["city"]).strip()
        if city not in SUPPORTED_BRANCH_CITIES: raise HTTPException(400,"Select a supported city")
        row.city=city
    if "is_active" in payload:
        if not isinstance(payload["is_active"],bool): raise HTTPException(400,"is_active must be boolean")
        row.is_active=payload["is_active"]
    db.commit();db.refresh(row);return _branch_out(row)

@app.delete("/api/provider/me/branches/{branch_id}")
def provider_branch_delete(branch_id:int,user:models.User=Depends(require_role("provider")),db:Session=Depends(get_db)):
    provider=_provider_for_owner(user,db)
    row=db.query(models.ProviderBranch).filter(models.ProviderBranch.id==branch_id,models.ProviderBranch.provider_id==provider.id).first()
    if not row: raise HTTPException(404,"Branch not found")
    db.delete(row);db.commit();return {"message":"Branch removed"}


@app.patch("/api/bookings/{booking_id}/reschedule")
def reschedule_booking(booking_id:int,payload:dict,user:models.User=Depends(current_user),db:Session=Depends(get_db)):
    booking=db.query(models.Booking).filter(models.Booking.id==booking_id).first()
    if not booking: raise HTTPException(404,"Booking not found")
    provider=db.query(models.Provider).filter(models.Provider.id==booking.provider_id).first()
    if not provider: raise HTTPException(404,"Provider not found")
    if not (user.role=="admin" or (user.role=="provider" and provider.owner_user_id==user.id) or (user.role=="customer" and booking.customer_user_id==user.id)): raise HTTPException(403,"You cannot reschedule this booking")
    if booking.status not in {"requested","confirmed"}: raise HTTPException(400,"Only requested or confirmed bookings can be rescheduled")
    try:
        appointment=datetime.fromisoformat(str(payload.get("appointment_at","")))
    except Exception: raise HTTPException(400,"Invalid appointment time")
    if appointment.tzinfo is not None: raise HTTPException(400,"Send appointment time as local India time without timezone offset")
    local_now=datetime.now(LUSHORA_LOCAL_TZ).replace(tzinfo=None)
    if appointment<=local_now: raise HTTPException(400,"Appointment must be in the future")
    if appointment.minute%BOOKING_SLOT_STEP_MINUTES!=0 or appointment.second or appointment.microsecond: raise HTTPException(400,"Appointment must align to a 30-minute slot")
    service=db.query(models.Service).filter(models.Service.id==booking.service_id,models.Service.provider_id==booking.provider_id).first()
    if not service: raise HTTPException(404,"Booking service not found")
    db.execute(update(models.Provider).where(models.Provider.id==provider.id).values(booking_lock_version=models.Provider.booking_lock_version+1))
    try: availability=json.loads(provider.availability_config or "{}")
    except Exception: availability={}
    availability=availability or {"working_days":[0,1,2,3,4,5,6],"start_time":"09:00","end_time":"18:00","break_start":"","break_end":"","closed_dates":[]}
    day=appointment.date();date_str=day.isoformat()
    if day.weekday() not in availability.get("working_days",[]): raise HTTPException(400,"Provider is closed on the selected day")
    if date_str in availability.get("closed_dates",[]): raise HTTPException(400,"Provider is closed on the selected date")
    try:
        work_start=datetime.combine(day,datetime.strptime(availability["start_time"],"%H:%M").time())
        work_end=datetime.combine(day,datetime.strptime(availability["end_time"],"%H:%M").time())
    except Exception: raise HTTPException(400,"Provider availability configuration is invalid")
    finish=appointment+timedelta(minutes=service.duration_minutes)
    if appointment<work_start or finish>work_end: raise HTTPException(400,"Appointment is outside provider working hours")
    bs,be=availability.get("break_start"),availability.get("break_end")
    if bs and be:
        break_start=datetime.combine(day,datetime.strptime(bs,"%H:%M").time());break_end=datetime.combine(day,datetime.strptime(be,"%H:%M").time())
        if appointment<break_end and finish>break_start: raise HTTPException(400,"Appointment overlaps provider break time")
    active=db.query(models.Booking,models.Service).join(models.Service,models.Booking.service_id==models.Service.id).filter(models.Booking.provider_id==booking.provider_id,models.Booking.status.in_(["requested","confirmed"]),models.Booking.id!=booking.id).all()
    for other,other_service in active:
        other_end=other.appointment_at+timedelta(minutes=other_service.duration_minutes)
        if appointment<other_end and finish>other.appointment_at: raise HTTPException(409,"This provider already has a booking during the selected time")
    booking.appointment_at=appointment
    if booking.customer_user_id: _create_notification(db,booking.customer_user_id,"Booking rescheduled",f"Your booking #{booking.id} has been moved to {appointment.strftime('%Y-%m-%d %H:%M')} (India local time).","booking_status",booking.id)
    if provider.owner_user_id: _create_notification(db,provider.owner_user_id,"Booking rescheduled",f"Booking #{booking.id} was rescheduled to {appointment.strftime('%Y-%m-%d %H:%M')}.","booking_status",booking.id)
    db.commit();db.refresh(booking)
    return {"id":booking.id,"appointment_at":booking.appointment_at,"status":booking.status,"message":"Booking rescheduled"}

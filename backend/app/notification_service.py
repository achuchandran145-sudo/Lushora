"""LUSHORA notification delivery adapters. Channels send only when credentials and destination exist."""
import os, json, time, logging
from datetime import datetime, timedelta
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
logger=logging.getLogger("lushora.notifications")
CHANNELS=("push","whatsapp","sms")
MAX_ATTEMPTS=int(os.getenv("NOTIFICATION_MAX_ATTEMPTS","5"))
if not 1 <= MAX_ATTEMPTS <= 20:
    raise RuntimeError("NOTIFICATION_MAX_ATTEMPTS must be between 1 and 20")

# A worker can die after claiming a delivery. Do not automatically resend an
# ambiguous in-flight message: the provider may already have accepted it.
# Move stale claims to failed for operator reconciliation instead.
SENDING_STALE_SECONDS=int(os.getenv("NOTIFICATION_SENDING_STALE_SECONDS","900"))
if not 1 <= SENDING_STALE_SECONDS <= 86400:
    raise RuntimeError("NOTIFICATION_SENDING_STALE_SECONDS must be between 1 and 86400")


def _post_json(url,headers,payload):
    req=Request(url,data=json.dumps(payload).encode(),headers={**headers,"Content-Type":"application/json"},method="POST")
    with urlopen(req,timeout=20) as response:
        return response.status,json.loads(response.read().decode() or "{}")

def channel_configured(channel):
    if channel=="push": return bool(os.getenv("FCM_SERVICE_ACCOUNT_JSON"))
    if channel=="whatsapp": return bool(os.getenv("WHATSAPP_ACCESS_TOKEN") and os.getenv("WHATSAPP_PHONE_NUMBER_ID"))
    if channel=="sms": return bool(os.getenv("TWILIO_ACCOUNT_SID") and os.getenv("TWILIO_AUTH_TOKEN") and os.getenv("TWILIO_SMS_FROM"))
    return False

def create_delivery_records(db,notification,preference=None):
    from . import models
    for channel in CHANNELS:
        enabled=bool(getattr(preference,f"{channel}_enabled",False)) if preference else False
        configured=channel_configured(channel)
        status="queued" if enabled and configured else ("suppressed" if not enabled else "not_configured")
        db.add(models.NotificationDelivery(notification_id=notification.id,user_id=notification.recipient_user_id,channel=channel,status=status,last_error="" if status!="not_configured" else "Channel credentials are not configured"))

def channel_status():
    return {c:{"configured":channel_configured(c),"dispatch_enabled":channel_configured(c),"status":"ready" if channel_configured(c) else "not_configured"} for c in CHANNELS}

def _send_push(db,delivery,notification,user):
    from firebase_admin import credentials, initialize_app, messaging, get_app
    from . import models
    raw=os.environ["FCM_SERVICE_ACCOUNT_JSON"]
    try: app=get_app()
    except ValueError: app=initialize_app(credentials.Certificate(json.loads(raw)))
    tokens=[d.device_token for d in db.query(models.NotificationDevice).filter_by(user_id=user.id,is_active=True).all()]
    if not tokens: raise RuntimeError("No active push device registered for this user")
    successes=[]; failures=[]
    for token in tokens:
        try:
            message=messaging.Message(notification=messaging.Notification(title=notification.title,body=notification.message),data={"notification_id":str(notification.id),"booking_id":str(notification.booking_id or "")},token=token)
            successes.append(messaging.send(message,app=app))
        except Exception as exc: failures.append(str(exc))
    if successes: return ",".join(successes[:3])
    raise RuntimeError("; ".join(failures) or "Push delivery failed")

def _send_whatsapp(delivery,notification,user):
    phone=(user.phone or "").strip()
    if not phone: raise RuntimeError("User phone number missing for WhatsApp")
    phone="".join(ch for ch in phone if ch.isdigit())
    if len(phone)==10: phone="91"+phone
    payload={"messaging_product":"whatsapp","to":phone,"type":"text","text":{"preview_url":False,"body":notification.title+"\n"+notification.message}}
    status,data=_post_json("https://graph.facebook.com/v21.0/"+os.environ["WHATSAPP_PHONE_NUMBER_ID"]+"/messages",{"Authorization":"Bearer "+os.environ["WHATSAPP_ACCESS_TOKEN"]},payload)
    return (data.get("messages") or [{}])[0].get("id","")

def _send_sms(delivery,notification,user):
    from twilio.rest import Client
    phone=(user.phone or "").strip()
    if not phone: raise RuntimeError("User phone number missing for SMS")
    if not phone.startswith("+"):
        digits="".join(ch for ch in phone if ch.isdigit())
        phone="+91"+digits if len(digits)==10 else "+"+digits
    client=Client(os.environ["TWILIO_ACCOUNT_SID"],os.environ["TWILIO_AUTH_TOKEN"])
    msg=client.messages.create(to=phone,from_=os.environ["TWILIO_SMS_FROM"],body=(notification.title+" - "+notification.message)[:1500])
    return msg.sid

def dispatch_delivery(db,delivery):
    from . import models
    notification=db.query(models.Notification).filter_by(id=delivery.notification_id).first()
    user=db.query(models.User).filter_by(id=delivery.user_id).first()
    if not notification or not user: raise RuntimeError("Notification recipient or notification not found")
    preference=db.query(models.NotificationPreference).filter_by(user_id=user.id).first()
    if not preference or not bool(getattr(preference,f"{delivery.channel}_enabled",False)):
        delivery.status="suppressed"
        delivery.last_error="User consent is not enabled for this channel"
        delivery.next_attempt_at=None
        raise RuntimeError("Notification channel consent is disabled")
    if delivery.channel=="push": return _send_push(db,delivery,notification,user)
    if delivery.channel=="whatsapp": return _send_whatsapp(delivery,notification,user)
    if delivery.channel=="sms": return _send_sms(delivery,notification,user)
    raise RuntimeError("Unsupported channel")

def _claim_delivery(db, delivery_id, now=None):
    """Atomically claim one due delivery; concurrent workers can only win once."""
    from sqlalchemy import or_
    from . import models

    claimed_at = now or datetime.utcnow()
    claimed = db.query(models.NotificationDelivery).filter(
        models.NotificationDelivery.id == delivery_id,
        models.NotificationDelivery.status.in_(["queued", "retry"]),
        models.NotificationDelivery.attempts < MAX_ATTEMPTS,
        or_(
            models.NotificationDelivery.next_attempt_at.is_(None),
            models.NotificationDelivery.next_attempt_at <= claimed_at,
        ),
    ).update(
        {
            models.NotificationDelivery.status: "sending",
            models.NotificationDelivery.attempts: models.NotificationDelivery.attempts + 1,
            models.NotificationDelivery.updated_at: claimed_at,
        },
        synchronize_session=False,
    )
    if claimed != 1:
        db.rollback()
        return None
    db.commit()
    return db.query(models.NotificationDelivery).filter_by(id=delivery_id).first()


def process_pending(db,batch_size=25):
    from sqlalchemy import or_
    from . import models

    now = datetime.utcnow()
    stale_cutoff = now - timedelta(seconds=SENDING_STALE_SECONDS)

    # A process may stop after the provider accepted a message but before the
    # database records success. Such deliveries have an ambiguous outcome:
    # fail them for manual reconciliation rather than risk an automatic duplicate.
    db.query(models.NotificationDelivery).filter(
        models.NotificationDelivery.status == "sending",
        models.NotificationDelivery.updated_at <= stale_cutoff,
    ).update(
        {
            models.NotificationDelivery.status: "failed",
            models.NotificationDelivery.last_error: (
                "Worker stopped during delivery; provider acceptance is unknown. "
                "Check the provider before manually retrying."
            ),
            models.NotificationDelivery.next_attempt_at: None,
            models.NotificationDelivery.updated_at: now,
        },
        synchronize_session=False,
    )
    db.commit()

    candidate_ids = [
        row[0]
        for row in db.query(models.NotificationDelivery.id).filter(
            models.NotificationDelivery.status.in_(["queued", "retry"]),
            models.NotificationDelivery.attempts < MAX_ATTEMPTS,
            or_(
                models.NotificationDelivery.next_attempt_at.is_(None),
                models.NotificationDelivery.next_attempt_at <= now,
            ),
        ).order_by(models.NotificationDelivery.created_at).limit(batch_size).all()
    ]

    processed = 0
    for delivery_id in candidate_ids:
        # The conditional UPDATE in _claim_delivery is the concurrency boundary.
        # A worker that loses the race receives None and never calls the provider.
        delivery = _claim_delivery(db, delivery_id)
        if delivery is None:
            continue
        try:
            provider_id = dispatch_delivery(db, delivery)
            delivery.status = "sent"
            delivery.provider_message_id = provider_id or ""
            delivery.last_error = ""
            delivery.next_attempt_at = None
            delivery.updated_at = datetime.utcnow()
        except Exception as exc:
            delivery.last_error = str(exc)[:2000]
            delivery.updated_at = datetime.utcnow()
            if "consent is disabled" in str(exc).lower():
                delivery.status = "suppressed"
                delivery.next_attempt_at = None
            elif delivery.attempts >= MAX_ATTEMPTS:
                delivery.status = "failed"
                delivery.next_attempt_at = None
            else:
                delivery.status = "retry"
                delivery.next_attempt_at = datetime.utcnow() + timedelta(
                    seconds=min(3600, 30 * (2 ** (delivery.attempts - 1)))
                )
        db.commit()
        processed += 1
    return processed

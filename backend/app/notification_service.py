"""LUSHORA notification delivery adapters. Channels send only when credentials and destination exist."""
import os, json, time, logging
from datetime import datetime, timedelta
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
logger=logging.getLogger("lushora.notifications")
CHANNELS=("push","whatsapp","sms")
MAX_ATTEMPTS=int(os.getenv("NOTIFICATION_MAX_ATTEMPTS","5"))

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
        enabled=getattr(preference,f"{channel}_enabled",True) if preference else True
        configured=channel_configured(channel)
        status="queued" if enabled and configured else ("suppressed" if not enabled else "not_configured")
        db.add(models.NotificationDelivery(notification_id=notification.id,user_id=notification.recipient_user_id,channel=channel,status=status,last_error="" if status!="not_configured" else "Channel credentials are not configured"))

def channel_status():
    return {c:{"configured":channel_configured(c),"dispatch_enabled":channel_configured(c),"status":"ready" if channel_configured(c) else "not_configured"} for c in CHANNELS}

def _send_push(db,delivery,notification,user):
    from firebase_admin import credentials, initialize_app, messaging, get_app
    raw=os.environ["FCM_SERVICE_ACCOUNT_JSON"]
    try: app=get_app()
    except ValueError: app=initialize_app(credentials.Certificate(json.loads(raw)))
    tokens=[d.device_token for d in db.query(__import__("app.models",fromlist=["NotificationDevice"]).NotificationDevice).filter_by(user_id=user.id,is_active=True).all()]
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
    if delivery.channel=="push": return _send_push(db,delivery,notification,user)
    if delivery.channel=="whatsapp": return _send_whatsapp(delivery,notification,user)
    if delivery.channel=="sms": return _send_sms(delivery,notification,user)
    raise RuntimeError("Unsupported channel")

def process_pending(db,batch_size=25):
    from . import models
    now=datetime.utcnow()
    rows=db.query(models.NotificationDelivery).filter(models.NotificationDelivery.status.in_(["queued","retry"]),models.NotificationDelivery.attempts<MAX_ATTEMPTS).order_by(models.NotificationDelivery.created_at).limit(batch_size).all()
    processed=0
    for d in rows:
        d.status="sending";d.attempts+=1;d.updated_at=now;db.commit()
        try:
            provider_id=dispatch_delivery(db,d)
            d.status="sent";d.provider_message_id=provider_id or "";d.last_error="";d.updated_at=datetime.utcnow()
        except Exception as exc:
            d.last_error=str(exc)[:2000];d.updated_at=datetime.utcnow()
            if d.attempts>=MAX_ATTEMPTS: d.status="failed"
            else: d.status="retry";d.updated_at=datetime.utcnow()+timedelta(seconds=min(3600,30*(2**(d.attempts-1))))
        db.commit();processed+=1
    return processed

"""Notification channel framework. External dispatchers are intentionally disabled until configured."""
import os
CHANNELS = ("push", "whatsapp", "sms")
def channel_configured(channel: str) -> bool:
    if channel == "push": return bool(os.getenv("FCM_PROJECT_ID") and os.getenv("FCM_SERVICE_ACCOUNT_JSON"))
    if channel == "whatsapp": return bool(os.getenv("WHATSAPP_ACCESS_TOKEN") and os.getenv("WHATSAPP_PHONE_NUMBER_ID"))
    if channel == "sms": return bool(os.getenv("SMS_PROVIDER_API_KEY") and os.getenv("SMS_SENDER_ID"))
    return False
def create_delivery_records(db, notification, preference=None):
    from . import models
    for channel in CHANNELS:
        enabled = getattr(preference, f"{channel}_enabled", True) if preference else True
        configured = channel_configured(channel)
        status = "queued" if enabled and configured else ("suppressed" if not enabled else "not_configured")
        db.add(models.NotificationDelivery(notification_id=notification.id,user_id=notification.recipient_user_id,channel=channel,status=status,last_error="" if status!="not_configured" else "Channel credentials are not configured"))
def channel_status():
    return {c: {"configured": channel_configured(c), "dispatch_enabled": False,"status": "credentials_ready_dispatch_not_implemented" if channel_configured(c) else "not_configured"} for c in CHANNELS}

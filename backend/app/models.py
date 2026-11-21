from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    phone: Mapped[str] = mapped_column(String(20), default="")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="customer", nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    first_name: Mapped[str] = mapped_column(String(80), default="")
    last_name: Mapped[str] = mapped_column(String(80), default="")
    street_address: Mapped[str] = mapped_column(Text, default="")
    city: Mapped[str] = mapped_column(String(80), default="")
    locality: Mapped[str] = mapped_column(String(120), default="")

class Provider(Base):
    __tablename__ = "providers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), unique=True, nullable=True)
    approval_status: Mapped[str] = mapped_column(String(20), default="approved", nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    city: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    locality: Mapped[str] = mapped_column(String(100), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    rating: Mapped[float] = mapped_column(default=0.0)
    availability_config: Mapped[str] = mapped_column(Text, default='{}')
    services: Mapped[list["Service"]] = relationship(back_populates="provider", cascade="all, delete-orphan")

class Service(Base):
    __tablename__ = "services"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    price_inr: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    provider: Mapped[Provider] = relationship(back_populates="services")

class Booking(Base):
    __tablename__ = "bookings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    customer_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    customer_name: Mapped[str] = mapped_column(String(120), nullable=False)
    customer_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"), nullable=False)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), nullable=False)
    appointment_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="requested")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class OTPChallenge(Base):
    __tablename__ = "otp_challenges"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    phone: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MarketplaceArea(Base):
    __tablename__ = "marketplace_areas"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    city: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    locality: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AreaRanking(Base):
    __tablename__ = "area_rankings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    area_id: Mapped[int] = mapped_column(ForeignKey("marketplace_areas.id"), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"), index=True, nullable=False)
    rank_position: Mapped[int] = mapped_column(Integer, nullable=False)
    subscription_tier: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BusinessSubscription(Base):
    __tablename__ = "business_subscriptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"), index=True, nullable=False)
    area_id: Mapped[int] = mapped_column(ForeignKey("marketplace_areas.id"), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    tier: Mapped[str] = mapped_column(String(20), nullable=False)
    monthly_price_inr: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CustomerLead(Base):
    __tablename__ = "customer_leads"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    area_id: Mapped[int] = mapped_column(ForeignKey("marketplace_areas.id"), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    service_interest: Mapped[str] = mapped_column(String(120), default="")
    customer_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    contact_consent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LeadDelivery(Base):
    __tablename__ = "lead_deliveries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("customer_leads.id"), index=True, nullable=False)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"), index=True, nullable=False)
    rank_position: Mapped[int] = mapped_column(Integer, nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="scheduled", index=True)
    response_status: Mapped[str] = mapped_column(String(20), default="pending")
    response_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class BusinessVerification(Base):
    __tablename__ = "business_verifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True, nullable=False)
    business_name: Mapped[str] = mapped_column(String(160), nullable=False)
    categories_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    city: Mapped[str] = mapped_column(String(80), nullable=False)
    locality: Mapped[str] = mapped_column(String(120), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    aadhaar_last4: Mapped[str] = mapped_column(String(4), default="", nullable=False)
    pan_number: Mapped[str] = mapped_column(String(10), default="", nullable=False)
    gst_number: Mapped[str] = mapped_column(String(15), default="", nullable=False)
    aadhaar_document_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    pan_document_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    business_document_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="submitted", index=True, nullable=False)
    admin_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    recipient_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    notification_type: Mapped[str] = mapped_column(String(40), default="info")
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id"), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True, nullable=False)
    in_app_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    push_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    whatsapp_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sms_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    notification_id: Mapped[int] = mapped_column(ForeignKey("notifications.id"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    provider_message_id: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    last_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class NotificationDevice(Base):
    __tablename__ = "notification_devices"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    device_token: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    platform: Mapped[str] = mapped_column(String(20), default="web", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

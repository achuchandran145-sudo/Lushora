from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, field_validator

class ServiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    price_inr: int
    duration_minutes: int

class ProviderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    category: str
    city: str
    locality: str
    description: str
    verified: bool
    rating: float
    services: list[ServiceOut] = []

class BookingCreate(BaseModel):
    customer_name: str = Field(min_length=2, max_length=120)
    customer_phone: str = Field(min_length=10, max_length=20)
    provider_id: int
    service_id: int
    appointment_at: datetime
    staff_id: int | None = None
    notes: str = Field(default="", max_length=1000)

class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    customer_name: str
    provider_id: int
    service_id: int
    appointment_at: datetime
    status: str
    notes: str


class RegisterIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=255)
    phone: str = Field(default="", max_length=20)
    password: str = Field(min_length=12, max_length=128)
    role: str = Field(default="customer")

    @field_validator("password")
    @classmethod
    def enforce_password_policy(cls, value: str) -> str:
        if not any(ch.islower() for ch in value):
            raise ValueError("Password must contain a lowercase letter")
        if not any(ch.isupper() for ch in value):
            raise ValueError("Password must contain an uppercase letter")
        if not any(ch.isdigit() for ch in value):
            raise ValueError("Password must contain a number")
        if not any(not ch.isalnum() for ch in value):
            raise ValueError("Password must contain a special character")
        return value

class LoginIn(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=1, max_length=128)

class UserOut(BaseModel):
    id: int
    full_name: str
    email: str
    phone: str
    role: str
    is_active: bool

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut

class ProviderRegistrationIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    category: str
    city: str
    locality: str = ""
    description: str = ""


class WaitlistCreate(BaseModel):
    provider_id: int
    service_id: int
    preferred_date: datetime
    preferred_time_start: str = Field(default="", max_length=5)
    preferred_time_end: str = Field(default="", max_length=5)

class WaitlistOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    provider_id: int
    service_id: int
    preferred_date: datetime
    preferred_time_start: str
    preferred_time_end: str
    status: str
    created_at: datetime

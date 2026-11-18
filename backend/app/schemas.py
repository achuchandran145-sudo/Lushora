from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

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

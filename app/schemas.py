import datetime
from typing import Optional
from pydantic import BaseModel, field_validator


class RegisterIn(BaseModel):
    name: str
    phone: str
    password: str


class LoginIn(BaseModel):
    phone: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    name: str


class UserOut(BaseModel):
    id: str
    name: str
    phone: str
    device_id: Optional[str] = None

    class Config:
        from_attributes = True


class NameUpdateIn(BaseModel):
    name: str


class ContactIn(BaseModel):
    name: str
    phone: str
    relationship: Optional[str] = None

    @field_validator("name", "phone")
    @classmethod
    def not_blank(cls, v):
        if not v or not v.strip():
            raise ValueError("must not be blank")
        return v.strip()


class ContactOut(BaseModel):
    id: str
    name: str
    phone: str
    relationship: Optional[str] = None

    class Config:
        from_attributes = True


class LocationIn(BaseModel):
    latitude: float
    longitude: float
    accuracy_m: Optional[float] = None
    battery_pct: Optional[int] = None
    source: str = "app"


class LocationOut(BaseModel):
    id: str
    latitude: float
    longitude: float
    accuracy_m: Optional[float] = None
    battery_pct: Optional[int] = None
    source: str
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class AlertIn(BaseModel):
    type: str = "SOS"
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class AlertOut(BaseModel):
    id: str
    type: str
    status: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    contacts_notified: int
    created_at: datetime.datetime
    resolved_at: Optional[datetime.datetime] = None

    class Config:
        from_attributes = True


class DevicePairIn(BaseModel):
    device_id: str

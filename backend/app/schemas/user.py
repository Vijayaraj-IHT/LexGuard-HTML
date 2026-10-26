from typing import Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict


class UserBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    email: EmailStr
    role: str = Field(default="public", pattern="^(court_staff|senior_staff|staff|junior_staff|advocate|scholar|public)$")
    credential_id: Optional[str] = Field(default=None, max_length=100)


class UserCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    role: str = Field(default="public", pattern="^(advocate|scholar|public)$")
    credential_id: Optional[str] = Field(default=None, max_length=100)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(UserBase):
    id: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserRoleUpdate(BaseModel):
    role: str = Field(..., pattern="^(court_staff|senior_staff|staff|junior_staff|advocate|scholar|public)$")
    status: Optional[str] = Field(default=None, pattern="^(active|pending_verification|suspended)$")


class AdminUserCreate(BaseModel):
    """Senior-staff provisioning payload; unlike public registration it may create staff."""

    name: str = Field(..., min_length=2, max_length=150)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    role: str = Field(
        default="public",
        pattern="^(court_staff|senior_staff|staff|junior_staff|advocate|scholar|public)$",
    )
    status: str = Field(
        default="active",
        pattern="^(active|pending_verification|suspended)$",
    )
    credential_id: Optional[str] = Field(default=None, max_length=100)


class UserAdminUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=150)
    role: Optional[str] = Field(
        default=None,
        pattern="^(court_staff|senior_staff|staff|junior_staff|advocate|scholar|public)$",
    )
    status: Optional[str] = Field(
        default=None,
        pattern="^(active|pending_verification|suspended)$",
    )
    credential_id: Optional[str] = Field(default=None, max_length=100)

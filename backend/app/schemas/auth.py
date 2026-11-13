"""Request/response models for auth and user endpoints."""

from __future__ import annotations

import re
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def validate_password_strength(value: str) -> str:
    if len(value) < 10 or len(value) > 128:
        raise ValueError("Password must be 10-128 characters")
    if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
        raise ValueError("Password must contain at least one letter and one digit")
    return value


class RegisterIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr
    password: str
    display_name: str = Field(min_length=1, max_length=120)

    @field_validator("password")
    @classmethod
    def _password(cls, v: str) -> str:
        return validate_password_strength(v)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    display_name: str
    role: str


class UserUpdateIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    display_name: str = Field(min_length=1, max_length=120)


class ProfileIO(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    headline: str | None = Field(default=None, max_length=200)
    career_goal: str | None = Field(default=None, max_length=2000)
    target_role: str | None = Field(default=None, max_length=200)
    years_experience: int | None = Field(default=None, ge=0, le=60)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _password(cls, v: str) -> str:
        return validate_password_strength(v)


class AccountDeleteIn(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    confirm: bool


class GuestImportIn(BaseModel):
    consent: bool  # explicit consent to move the guest session's data into this account


class GuestImportOut(BaseModel):
    documents: int
    reports: int

"""Pydantic schemas for users and profiles: the API shape, not the table shape.

The separation earns its keep here more than anywhere else in the app:
`hashed_password` is a column on `users`, and it appears nowhere in this file.
Returning a SQLAlchemy User directly would leak it. (Phase 2/3)
"""

from datetime import datetime
from typing import Annotated, Literal

import email_validator
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.config import settings
from app.models import Role, User
from app.services.security import MAX_PASSWORD_BYTES


def _validate_email(value: str) -> str:
    """Check the address, then lower-case the whole thing.

    Not pydantic's EmailStr, for one reason: email-validator refuses RFC 2606
    reserved domains (.test, .local, .invalid), and every demo account this
    project ships uses one -- admin@vetclinic.test would be a 422 against our own
    documented credentials. `test_environment` is the library's supported switch
    for that, wired to a setting so Phase 10 can tighten it in production.

    Lower-casing matters because users.email is a case-sensitive unique index:
    without it Alice@x.com and alice@x.com are two accounts, and whoever signed
    up with one and logged in with the other gets a baffling 401. The library
    normalises only the domain, so the explicit .lower() covers the local part.
    """
    try:
        result = email_validator.validate_email(
            value,
            check_deliverability=False,  # no DNS lookups on the request path
            test_environment=settings.allow_reserved_email_domains,
        )
    except email_validator.EmailNotValidError as exc:
        raise ValueError(str(exc)) from None
    return result.normalized.lower()


Email = Annotated[str, AfterValidator(_validate_email)]


class _Credentials(BaseModel):
    """E-mail and password rules shared by every account-creating endpoint."""

    # Reject unknown fields rather than ignoring them. On an auth endpoint a
    # silently-dropped key is how "role": "ADMIN" in a register body becomes a
    # bug report instead of a 422.
    model_config = ConfigDict(extra="forbid")

    email: Email
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def _fits_bcrypt(cls, v: str) -> str:
        if len(v.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValueError(
                f"password must be at most {MAX_PASSWORD_BYTES} bytes"
            )
        return v


class ClientRegister(_Credentials):
    """Public sign-up.

    There is deliberately no `role` field. Self-registration may only ever create
    a CLIENT (PROJECT_PLAN.md section 8), so the router hard-codes it; a field
    that accepts exactly one value is just an invitation to widen it later.
    """

    full_name: str = Field(min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    address: str | None = None


class StaffCreate(_Credentials):
    """Admin-only account creation. CLIENT accounts go through /auth/register."""

    role: Literal[Role.VET, Role.ADMIN]
    full_name: str | None = Field(default=None, max_length=120)
    specialty: str | None = Field(default=None, max_length=120)
    license_no: str | None = Field(default=None, max_length=60)

    @model_validator(mode="after")
    def _vets_need_a_name(self) -> "StaffCreate":
        # vet_profiles.full_name is NOT NULL. Admins have no profile table at
        # all, so for them full_name has nowhere to go and is not required.
        if self.role is Role.VET and not self.full_name:
            raise ValueError("full_name is required for a VET account")
        return self


class TokenOut(BaseModel):
    """The OAuth2 password-flow response body."""

    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    """A user as the API describes them. No password material, hashed or not."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    role: Role
    is_active: bool
    created_at: datetime
    full_name: str | None = None

    @classmethod
    def from_user(cls, user: User) -> "UserOut":
        """full_name lives on whichever profile the user has; admins have none.

        An explicit constructor rather than from_attributes alone, because
        full_name genuinely cannot be read off a User row.
        """
        profile = user.client_profile or user.vet_profile
        return cls(
            id=user.id,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
            full_name=profile.full_name if profile is not None else None,
        )

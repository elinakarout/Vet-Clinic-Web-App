"""POST /auth/register, POST /auth/login, GET /auth/me, POST /auth/staff. (Phase 2)

Routers handle HTTP and nothing else: hashing and token minting live in
services/security.py, and the shapes live in schemas/user.py.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user, require_role
from app.models import ClientProfile, Role, User, VetProfile
from app.schemas.user import ClientRegister, StaffCreate, TokenOut, UserOut
from app.services.ratelimit import SlidingWindow
from app.services.security import (
    create_access_token,
    dummy_verify,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# One message for every login failure. Saying which half was wrong turns the
# endpoint into a "does this address have an account here?" oracle.
_BAD_CREDENTIALS = "Incorrect email or password"


# Failed logins only. Phase 9; see services/ratelimit.py for the caveats.
_login_attempts = SlidingWindow()


def _login_key(request: Request, username: str) -> tuple[str, str]:
    """Bucket a login attempt by who is asking and which account they want.

    `request.client` is None under some ASGI transports (including parts of the
    test client), so it cannot be dereferenced blindly -- an AttributeError here
    would turn every login into a 500.
    """
    host = request.client.host if request.client else "unknown"
    return (host, username.strip().lower())


def reset_login_attempts() -> None:
    """Clear the login window. For tests, and for a deliberate reset in a REPL."""
    _login_attempts.clear()


def _get_user_by_email(db: Session, email: str) -> User | None:
    """Look a user up case-insensitively, matching how the schemas store them."""
    return db.scalar(select(User).where(User.email == email.strip().lower()))


@router.post(
    "/register", response_model=UserOut, status_code=status.HTTP_201_CREATED
)
def register(payload: ClientRegister, db: Session = Depends(get_db)) -> UserOut:
    """Public sign-up. Always creates a CLIENT -- staff go through /auth/staff."""
    if _get_user_by_email(db, payload.email) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=Role.CLIENT,  # hard-coded; never read from the request body
    )
    # The profile is created in the same transaction. pets.owner_id references
    # client_profiles.id, so a client without a profile row could never own a
    # pet -- and client_profiles.full_name is NOT NULL anyway.
    user.client_profile = ClientProfile(
        full_name=payload.full_name,
        phone=payload.phone,
        address=payload.address,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Lost the race on the unique index between the check above and here.
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Email already registered"
        ) from None
    db.refresh(user)
    return UserOut.from_user(user)


@router.post("/login", response_model=TokenOut)
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> TokenOut:
    """OAuth2 password flow. The form field is `username`; put the e-mail there."""
    key = _login_key(request, form_data.username)
    retry_after = _login_attempts.is_blocked(key, settings.login_rate_limit_per_minute)
    if retry_after is not None:
        # 429 before the password is checked, so a blocked caller cannot use
        # response timing to keep probing. The message stays deliberately vague
        # about whether the account exists, exactly like _BAD_CREDENTIALS.
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many sign-in attempts. Please wait a moment and try again.",
            headers={"Retry-After": str(retry_after)},
        )

    user = _get_user_by_email(db, form_data.username)
    if user is None:
        # Spend the same ~0.3s a real password check costs, so response latency
        # does not reveal which addresses are registered.
        dummy_verify()
        _login_attempts.record(key)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            _BAD_CREDENTIALS,
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not verify_password(form_data.password, user.hashed_password):
        _login_attempts.record(key)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            _BAD_CREDENTIALS,
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Checked *after* the password on purpose: a wrong password against a
    # deactivated account must look exactly like any other wrong password.
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Inactive user account")

    # A correct password clears the bucket: two typos then a success must not
    # leave a penalty behind for the next sign-in.
    _login_attempts.clear(key)
    return TokenOut(
        access_token=create_access_token(user_id=user.id, role=user.role)
    )


@router.get("/me", response_model=UserOut)
def read_me(current_user: User = Depends(get_current_user)) -> UserOut:
    """Return the caller. Proves the token round-trip works end to end."""
    return UserOut.from_user(current_user)


@router.post("/staff", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_staff(
    payload: StaffCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role(Role.ADMIN)),
) -> UserOut:
    """Create a VET or ADMIN account. Self-registration cannot reach these roles."""
    if _get_user_by_email(db, payload.email) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
    )
    if payload.role is Role.VET:
        user.vet_profile = VetProfile(
            full_name=payload.full_name,
            specialty=payload.specialty,
            license_no=payload.license_no,
        )
    # ADMIN gets no profile row -- there is no admin profile table, which
    # matches what scripts/seed.py builds.
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Duplicate email, or a duplicate vet_profiles.license_no (also UNIQUE).
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Email or licence number already in use"
        ) from None
    db.refresh(user)
    return UserOut.from_user(user)

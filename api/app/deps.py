"""Shared FastAPI dependencies: get_current_user, require_role. (Phase 2)

This is where a token becomes a User row. Every later phase's ownership check
starts from get_current_user, so the rules here are load-bearing.
"""

from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Pet, Role, User
from app.services.security import decode_token

# Relative on purpose -- no leading slash. Swagger resolves it against the docs
# page's base URL, so the Authorize button keeps working behind a proxy that
# sets root_path (Phase 10). An absolute "/auth/login" works today and breaks
# silently on deployment. Must match the real route: router prefix + path.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def _unauthorized(detail: str = "Could not validate credentials") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Decode the bearer token and load the user it names, or raise 401/403.

    A missing Authorization header is already a 401 from oauth2_scheme
    (auto_error=True), so that case needs no code here.
    """
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        # Worth distinguishing: the frontend should re-login rather than show a
        # generic failure. Leaks nothing -- the caller already holds the token.
        raise _unauthorized("Token has expired") from None
    except jwt.PyJWTError:
        # `from None` keeps JWT internals out of any traceback the client could
        # see (PROJECT_PLAN.md section 8: no stack traces in error responses).
        raise _unauthorized() from None

    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise _unauthorized() from None

    user = db.get(User, user_id)
    if user is None:
        # A correctly signed token naming a user who has since been deleted.
        raise _unauthorized()
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account",
        )
    return user


def require_role(*roles: Role) -> Callable[..., User]:
    """Dependency factory: 403 unless the user's *database row* holds one of these.

    The token's `role` claim is deliberately never consulted. get_current_user
    has already loaded the row, so the fresh read costs nothing -- and a trusted
    claim would keep honouring a demoted or deactivated user for up to the
    token's full lifetime.

    Returns the User, so a route gets the guard and the row from one dependency.
    """
    allowed = set(roles)

    def _guard(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return _guard


def get_owned_pet(
    pet_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Pet:
    """Load a pet the caller is allowed to touch, or raise 404/403. (Phase 3)

    PROJECT_PLAN.md section 3 of Phase 3 specifies this as a plain helper called
    from every pet endpoint. It is a *dependency* instead, for one reason: a
    helper you must remember to call is exactly the thing that gets forgotten
    when Phase 4 adds an endpoint. Declared as `pet: Pet = Depends(get_owned_pet)`
    the check cannot be skipped without also losing the pet.

    The comparison is against client_profile.id, never user.id. pets.owner_id is
    a client_profiles.id (see the docstring on models.Pet) -- and user ids and
    profile ids drift apart the moment one admin or vet exists, so the wrong one
    reads as "works on my machine, leaks in production".
    """
    pet = db.get(Pet, pet_id)
    if pet is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pet not found")

    if current_user.role is Role.CLIENT:
        profile = current_user.client_profile
        # /auth/register always creates the profile alongside the user, so this
        # is unreachable through the API. Guarded anyway: a 403 is the right
        # answer for "owns no pets", and an AttributeError would be a 500.
        if profile is None or pet.owner_id != profile.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your pet")

    # VET and ADMIN fall through: clinical staff see every patient.
    return pet

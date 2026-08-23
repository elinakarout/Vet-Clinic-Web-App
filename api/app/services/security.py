"""Password hashing and JWT create/decode.

Phase 1 provided only the hashing half -- seed.py must not write plaintext
passwords. Phase 2 adds create_access_token / decode_token below.

Nothing here raises HTTPException on purpose: services stay free of HTTP
concepts (CLAUDE.md's layering rule). deps.py turns these failures into 401s.
"""

from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.config import settings
from app.models import Role

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# bcrypt hashes only the first 72 bytes, and passlib truncates *silently*
# (truncate_error is False). A 100-byte password and its own first 72 bytes
# verify against the same hash, so anything longer must be rejected at the edge
# rather than quietly stored. Bytes, not characters: 72 emoji are 288 bytes.
MAX_PASSWORD_BYTES = 72


def hash_password(plain: str) -> str:
    """Return a bcrypt hash. Never store, log, or return the plaintext."""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time check of a candidate password against a stored hash."""
    return pwd_context.verify(plain, hashed)


def dummy_verify() -> None:
    """Burn one bcrypt round on a login for an e-mail that does not exist.

    A real hash takes ~0.3s; a dictionary miss returns in ~1ms. That gap is a
    user-enumeration oracle -- feed it a list of addresses and the response time
    tells you which ones are registered. This closes it.
    """
    pwd_context.dummy_verify()


def create_access_token(
    user_id: int,
    role: Role | str,
    expires_delta: timedelta | None = None,
) -> str:
    """A signed JWT carrying `sub` (the user id), `role` and `exp`.

    `sub` is a *string*: RFC 7519 requires it, and PyJWT >= 2.10 raises
    InvalidSubjectError when decoding anything else -- so `"sub": user.id` would
    mint tokens this app's own decode_token rejects.

    `role` is informational only. Authorisation re-reads the database, because a
    token outlives a demotion or a deactivation by up to its full lifetime.
    """
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload = {
        "sub": str(user_id),
        "role": role.value if isinstance(role, Role) else str(role),
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """Verify signature and expiry, and return the claims.

    Raises jwt.PyJWTError -- InvalidSignatureError, ExpiredSignatureError,
    DecodeError, InvalidSubjectError -- on any failure.
    """
    return jwt.decode(
        token,
        settings.secret_key,
        # A list, always. Passing the algorithm explicitly is what refuses a
        # token whose header claims `alg: none`, or an RS256 public key replayed
        # as an HS256 shared secret.
        algorithms=[settings.jwt_algorithm],
    )

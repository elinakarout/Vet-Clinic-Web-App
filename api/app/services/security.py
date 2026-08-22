"""Password hashing and JWT create/decode.

Phase 1 provides only the hashing half -- seed.py must not write plaintext
passwords. Phase 2 adds create_access_token / decode_token to this same file.
"""

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """Return a bcrypt hash. Never store, log, or return the plaintext."""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time check of a candidate password against a stored hash."""
    return pwd_context.verify(plain, hashed)

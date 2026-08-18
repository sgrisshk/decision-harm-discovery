"""Password hashing and session-token generation for `TASK-053`.

`bcrypt` directly, not `passlib` (effectively unmaintained) — a thin, inspectable wrapper is
sufficient at this scope. Session tokens are random opaque strings looked up in the `sessions`
table, not signed/encoded — no secret-key management needed.
"""

import secrets

import bcrypt

#: bcrypt's own input limit; longer passwords are truncated by the algorithm itself, so reject
#: them outright rather than silently hashing only a prefix.
_MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    if len(password.encode("utf-8")) > _MAX_PASSWORD_BYTES:
        raise ValueError(f"password must be at most {_MAX_PASSWORD_BYTES} bytes")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    if len(password.encode("utf-8")) > _MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        # Malformed stored hash — never a valid match.
        return False


def generate_session_token() -> str:
    """A 256-bit random token, URL-safe encoded. Looked up as an opaque primary key — not a JWT,
    nothing to decode, revocation is just deleting the row."""
    return secrets.token_urlsafe(32)

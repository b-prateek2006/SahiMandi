"""Prototype authentication state for mock OTP and officer login."""

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class SessionIdentity:
    role: str
    subject_id: int
    centre_id: int | None = None


_otp_codes: dict[str, tuple[str, datetime]] = {}
_tokens: dict[str, SessionIdentity] = {}


def issue_otp(phone: str) -> str:
    code = f"{secrets.randbelow(1_000_000):06d}"
    _otp_codes[phone] = (code, datetime.now(timezone.utc) + timedelta(minutes=10))
    return code


def verify_otp(phone: str, code: str) -> bool:
    stored = _otp_codes.get(phone)
    if stored is None:
        return False
    expected, expires_at = stored
    if datetime.now(timezone.utc) > expires_at or not secrets.compare_digest(expected, code):
        return False
    del _otp_codes[phone]
    return True


def issue_token(identity: SessionIdentity) -> str:
    token = secrets.token_urlsafe(32)
    _tokens[token] = identity
    return token


def identity_for(token: str) -> SessionIdentity | None:
    return _tokens.get(token)

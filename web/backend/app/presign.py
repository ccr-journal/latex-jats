"""Stateless presigned-URL tokens using HMAC-SHA256.

Tokens encode {doi_suffix, orcid, exp} and are signed with a server secret.
They allow unauthenticated browser requests (new tabs, iframes, <a> downloads)
to access manuscript output files for a short window.
"""

import base64
import hashlib
import hmac
import json
import os
import time

# Default validity: 5 minutes
TOKEN_TTL_SECONDS = 300

_secret: bytes | None = None


def _get_secret() -> bytes:
    global _secret
    if _secret is None:
        env = os.environ.get("PRESIGN_SECRET", "")
        if env:
            _secret = env.encode()
        else:
            # Auto-generate a random secret on first use (per-process).
            # Fine for single-server deployments; set PRESIGN_SECRET in
            # production if running multiple workers/containers.
            _secret = os.urandom(32)
    return _secret


def _sign(payload: bytes) -> str:
    return hmac.new(_get_secret(), payload, hashlib.sha256).hexdigest()


def create_token(doi_suffix: str, orcid: str) -> str:
    """Return a short-lived presigned token for *doi_suffix*."""
    payload = json.dumps(
        {"sub": doi_suffix, "orcid": orcid, "exp": int(time.time()) + TOKEN_TTL_SECONDS},
        separators=(",", ":"),
    ).encode()
    sig = _sign(payload)
    encoded = base64.urlsafe_b64encode(payload).decode()
    return f"{encoded}.{sig}"


def verify_token(token: str, doi_suffix: str) -> str | None:
    """Verify *token* and return the ORCID if valid, else ``None``.

    Checks: signature, expiry, and that the token was issued for
    *doi_suffix*.
    """
    parts = token.split(".", 1)
    if len(parts) != 2:
        return None
    encoded, sig = parts
    try:
        payload = base64.urlsafe_b64decode(encoded)
    except Exception:
        return None
    if not hmac.compare_digest(sig, _sign(payload)):
        return None
    try:
        data = json.loads(payload)
    except Exception:
        return None
    if data.get("sub") != doi_suffix:
        return None
    if data.get("exp", 0) < time.time():
        return None
    return data.get("orcid")


def reset_secret() -> None:
    """Reset the cached secret (for tests)."""
    global _secret
    _secret = None

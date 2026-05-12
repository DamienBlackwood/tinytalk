"""
AES-256-GCM for transcript text. The key sits at .tinytalk/key next to the
log. Wipe the folder then you lose the transcripts, and then get a fresh key.

Only meant to stop someone glancing at the .jsonl on disk, it's just a proof of concept
and just for fun. FOR NOW!

Envelope: {"enc": "aes-gcm-v1", "n": "<b64 nonce>", "ct": "<b64 ct+tag>"}
"""
import base64
import os
import secrets
from pathlib import Path

_KEY_PATH = Path(__file__).parent.parent / ".tinytalk" / "key"
_KEY_BYTES = 32  # AES-256
_NONCE_BYTES = 12  # GCM standard

ENVELOPE_VERSION = "aes-gcm-v1"


def _try_import():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        return AESGCM
    except ImportError:
        return None


def available() -> bool:
    return _try_import() is not None


def _load_or_create_key() -> bytes | None:
    """Load key, or make one if missing. None if something's wrong."""
    try:
        if _KEY_PATH.exists():
            data = _KEY_PATH.read_bytes()
            if len(data) != _KEY_BYTES:
                
                return None
            return data

        _KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
        key = secrets.token_bytes(_KEY_BYTES)

        # write to .tmp then rename
        tmp = _KEY_PATH.with_suffix(".key.tmp")
        tmp.write_bytes(key)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass  # windows does ACLs, whatever
        os.replace(tmp, _KEY_PATH)
        return key
    except OSError:
        return None


_aesgcm = None


def _cipher():
    """Build the AESGCM once, only when actually needed."""
    global _aesgcm
    if _aesgcm is not None:
        return _aesgcm
    AESGCM = _try_import()
    if AESGCM is None:
        return None
    key = _load_or_create_key()
    if key is None:
        return None
    _aesgcm = AESGCM(key)
    return _aesgcm


def encrypt(text: str) -> dict | None:
    """Envelope dict, or None if we can't encrypt."""
    c = _cipher()
    if c is None:
        return None
    nonce = secrets.token_bytes(_NONCE_BYTES)
    ct    = c.encrypt(nonce, text.encode("utf-8"), associated_data=None)
    return {
        "enc": ENVELOPE_VERSION,
        "n":   base64.b64encode(nonce).decode("ascii"),
        "ct":  base64.b64encode(ct).decode("ascii"),
    }


def decrypt(envelope: dict) -> str | None:
    """Plaintext back out. None means skip it because it could be the wrong key,
    newer format, or corrupted."""
    if not isinstance(envelope, dict):
        return None
    if envelope.get("enc") != ENVELOPE_VERSION:
        return None
    c = _cipher()
    if c is None:
        return None
    try:
        nonce = base64.b64decode(envelope["n"])
        ct    = base64.b64decode(envelope["ct"])
        return c.decrypt(nonce, ct, associated_data=None).decode("utf-8")
    except Exception:
        return None

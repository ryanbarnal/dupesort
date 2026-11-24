"""30-day free trial, then activation with a signed license key.

Keys are signed with Ed25519 by the developer's private key (see packaging/license_tool.py)
and checked here with the matching public key, entirely offline. A key holds the licensee's
name and the date it was issued.

After the trial, DupeSort still scans, shows results and previews; only actions that change
files (moving, writing tags, renaming, organizing, converting) need activation. Undo always
works.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from . import APP_NAME

TRIAL_DAYS = 30
# The public half of the developer's signing key, as 64 hex characters. Set by
# `python packaging/license_tool.py init`. Empty means keys can't be checked yet.
PUBLIC_KEY = ""
KEY_PREFIX = "DUPESORT"

# --- Ed25519 signatures (RFC 8032), small and dependency-free -------------------------------
_p = 2**255 - 19
_q = 2**252 + 27742317777372353535851937790883648493
_d = -121665 * pow(121666, _p - 2, _p) % _p
_sqrt_m1 = pow(2, (_p - 1) // 4, _p)


def _sha512(b: bytes) -> bytes:
    return hashlib.sha512(b).digest()


def _add(P, Q):
    A, B = (P[1] - P[0]) * (Q[1] - Q[0]) % _p, (P[1] + P[0]) * (Q[1] + Q[0]) % _p
    C, D = 2 * P[3] * Q[3] * _d % _p, 2 * P[2] * Q[2] % _p
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F, G * H, F * G, E * H)


def _mul(s: int, P):
    Q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            Q = _add(Q, P)
        P = _add(P, P)
        s >>= 1
    return Q


def _equal(P, Q) -> bool:
    return (P[0] * Q[2] - Q[0] * P[2]) % _p == 0 and (P[1] * Q[2] - Q[1] * P[2]) % _p == 0


def _recover_x(y: int, sign: int) -> Optional[int]:
    if y >= _p:
        return None
    x2 = (y * y - 1) * pow(_d * y * y + 1, _p - 2, _p)
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_p + 3) // 8, _p)
    if (x * x - x2) % _p:
        x = x * _sqrt_m1 % _p
    if (x * x - x2) % _p:
        return None
    if (x & 1) != sign:
        x = _p - x
    return x


_gy = 4 * pow(5, _p - 2, _p) % _p
_gx = _recover_x(_gy, 0)
_G = (_gx, _gy, 1, _gx * _gy % _p)


def _compress(P) -> bytes:
    zinv = pow(P[2], _p - 2, _p)
    x, y = P[0] * zinv % _p, P[1] * zinv % _p
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _decompress(s: bytes):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    return None if x is None else (x, y, 1, x * y % _p)


def _expand(secret: bytes):
    h = _sha512(secret)
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def _modq(b: bytes) -> int:
    return int.from_bytes(_sha512(b), "little") % _q


def public_key_of(secret: bytes) -> bytes:
    return _compress(_mul(_expand(secret)[0], _G))


def sign(secret: bytes, message: bytes) -> bytes:
    a, prefix = _expand(secret)
    A = _compress(_mul(a, _G))
    r = _modq(prefix + message)
    Rs = _compress(_mul(r, _G))
    s = (r + _modq(Rs + A + message) * a) % _q
    return Rs + int.to_bytes(s, 32, "little")


def verify(public: bytes, message: bytes, signature: bytes) -> bool:
    if len(public) != 32 or len(signature) != 64:
        return False
    A, R = _decompress(public), _decompress(signature[:32])
    if A is None or R is None:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= _q:
        return False
    h = _modq(signature[:32] + public + message)
    return _equal(_mul(s, _G), _add(R, _mul(h, A)))


# --- license keys ----------------------------------------------------------------------------

@dataclass
class License:
    name: str
    issued: str  # YYYY-MM-DD
    key: str


def make_key(secret: bytes, name: str, issued: Optional[str] = None) -> str:
    """A license key for ``name`` (used by packaging/license_tool.py)."""
    payload = json.dumps({"v": 1, "n": name.strip(), "d": issued or date.today().isoformat()},
                         separators=(",", ":"), ensure_ascii=False).encode()
    if len(payload) > 255:
        raise ValueError("The name is too long for a key.")
    raw = bytes([len(payload)]) + payload + sign(secret, payload)
    text = base64.b32encode(raw).decode().rstrip("=")
    return KEY_PREFIX + "-" + "-".join(text[i:i + 5] for i in range(0, len(text), 5))


def read_key(text: str, public_hex: Optional[str] = None) -> Optional[License]:
    """The license in ``text`` if it is a genuine key, else None. Spaces, line breaks and
    dashes don't matter, so a key pasted from an email works."""
    public_hex = PUBLIC_KEY if public_hex is None else public_hex
    if not public_hex:
        return None
    clean = "".join(ch for ch in (text or "").upper() if ch.isalnum())
    if clean.startswith(KEY_PREFIX):
        clean = clean[len(KEY_PREFIX):]
    try:
        raw = base64.b32decode(clean + "=" * (-len(clean) % 8))
        n = raw[0]
        payload, signature = raw[1:1 + n], raw[1 + n:]
        if not verify(bytes.fromhex(public_hex), payload, signature):
            return None
        data = json.loads(payload)
    except (ValueError, IndexError, TypeError):
        return None
    return License(str(data.get("n", "")), str(data.get("d", "")), text.strip())


# --- trial and activation state ---------------------------------------------------------------

_SALT = b"DupeSort trial v1"  # makes casual edits of the saved dates obvious


def _files() -> list[Path]:
    # Imported here so packaging/license_tool.py runs on a plain Python install.
    from platformdirs import user_config_dir, user_data_dir

    config = Path(os.environ.get("DUPESORT_CONFIG", user_config_dir(APP_NAME, False)))
    data = Path(os.environ.get("DUPESORT_DATA", user_data_dir(APP_NAME, False)))
    return [config / "license.json", data / ".trial"]


def _sign_record(rec: dict) -> str:
    body = f"{rec.get('start', 0):.0f}|{rec.get('seen', 0):.0f}|{rec.get('key', '')}"
    return hmac.new(_SALT, body.encode(), hashlib.sha256).hexdigest()


def _load() -> dict:
    """The saved record; the earliest trial start of the copies that check out."""
    best: dict = {}
    for f in _files():
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(rec, dict) or rec.get("mac") != _sign_record(rec):
            # Edited by hand: keep the trial counting from long ago.
            best.setdefault("start", 0.0)
            best["start"] = min(best["start"], 1.0)
            continue
        if not best or rec.get("start", 0) < best.get("start", float("inf")):
            best = {**best, "start": rec.get("start", 0)}
        best["seen"] = max(best.get("seen", 0), rec.get("seen", 0))
        if rec.get("key"):
            best["key"] = rec["key"]
    return best


def _save(rec: dict) -> None:
    rec = {k: rec[k] for k in ("start", "seen", "key") if k in rec}
    rec["mac"] = _sign_record(rec)
    for f in _files():
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(rec), encoding="utf-8")
        except OSError:
            pass


@dataclass
class Status:
    licensed: Optional[License]
    days_left: int  # whole days of trial left (0 when it has ended)

    @property
    def can_change_files(self) -> bool:
        return self.licensed is not None or self.days_left > 0

    def summary(self) -> str:
        if self.licensed:
            return f"Licensed to {self.licensed.name}"
        if self.days_left > 0:
            return f"Free trial: {self.days_left} day{'s' * (self.days_left != 1)} left"
        return "Free trial ended"


def status(now: Optional[float] = None) -> Status:
    """Where this copy stands. Starts the trial on first use."""
    now = time.time() if now is None else now
    rec = _load()
    if "start" not in rec:
        rec = {"start": now, "seen": now}
    # Setting the clock back doesn't add trial days.
    effective = max(now, rec.get("seen", 0))
    rec["seen"] = effective
    lic = read_key(rec.get("key", "")) if rec.get("key") else None
    _save(rec)
    used = max(0.0, effective - rec["start"]) / 86400
    left = max(0, TRIAL_DAYS - int(used))
    return Status(lic, left)


def activate(text: str) -> tuple[bool, str]:
    """Check and store a license key. Returns (ok, message for the person)."""
    if not PUBLIC_KEY:
        return False, "This copy of DupeSort can't check keys. Please download the latest version."
    lic = read_key(text)
    if lic is None:
        return False, ("That key isn't valid. Copy the whole key from your email, including the "
                       "DUPESORT- at the start, and try again.")
    rec = _load()
    rec.setdefault("start", time.time())
    rec["key"] = lic.key
    _save(rec)
    return True, f"Thank you! DupeSort is activated for {lic.name}."


def deactivate() -> None:
    """Remove the key from this computer (the trial doesn't restart)."""
    rec = _load()
    rec.pop("key", None)
    _save(rec)

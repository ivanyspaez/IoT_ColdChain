import os
import hmac
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import Request
from jose import jwt, JWTError
from passlib.context import CryptContext

# =========================
# AUTH CONFIG
# =========================
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7
ACCESS_TOKEN_COOKIE = "access_token"

pwd_context = CryptContext(
    schemes=["pbkdf2_sha256"],
    deprecated="auto",
)

# =========================
# PASSWORDS
# =========================
def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


# =========================
# JWT
# =========================
def create_access_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": username,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)


def current_username(request: Request) -> Optional[str]:
    token = request.cookies.get(ACCESS_TOKEN_COOKIE)
    if not token:
        return None

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


def hmac_sha256_hex(message: bytes, key: str) -> str:
    return hmac.new(
        key.encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()


# =========================
# SERIALIZERS
# =========================
def serialize_product(row) -> dict:
    return {
        "id": row.id,
        "owner_id": row.owner_id,
        "product_name": row.product_name,
        "product_serial": row.product_serial,
        "device_id": row.device_id,
        "api_key": row.api_key,
        "device_secret": row.device_secret,
        "temp_min": row.temp_min,
        "temp_max": row.temp_max,
        "hum_min": row.hum_min,
        "hum_max": row.hum_max,
        "created_at": row.created_at.isoformat(),
    }


def serialize_telemetry(row) -> dict:
    return {
        "id": row.id,
        "device_id": row.device_id,
        "temperature": row.temperature,
        "humidity": row.humidity,
        "battery": row.battery,
        "status": row.status,
        "decision": row.decision,
        "created_at": row.created_at.isoformat(),
    }


def serialize_alert(row) -> dict:
    return {
        "id": row.id,
        "device_id": row.device_id,
        "telemetry_id": row.telemetry_id,
        "level": row.level,
        "message": row.message,
        "created_at": row.created_at.isoformat(),
    }
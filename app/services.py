import secrets
import json

from sqlalchemy.orm import Session

from app.models import (
    User,
    Product,
    Telemetry
)


# =========================
# USERS
# =========================

def get_user_by_username(
    db: Session,
    username: str
):
    return (
        db.query(User)
        .filter(User.username == username)
        .first()
    )


def create_user(
    db: Session,
    username: str,
    password_hash: str
):
    user = User(
        username=username,
        password_hash=password_hash
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


# =========================
# PRODUCTS
# =========================

def get_user_products(
    db: Session,
    owner_id: int
):
    return (
        db.query(Product)
        .filter(Product.owner_id == owner_id)
        .order_by(Product.id.desc())
        .all()
    )


def get_product_by_serial(
    db: Session,
    serial: str
):
    return (
        db.query(Product)
        .filter(Product.product_serial == serial)
        .first()
    )


def get_product_by_device(
    db: Session,
    device_id: str
):
    return (
        db.query(Product)
        .filter(Product.device_id == device_id)
        .first()
    )


def get_product_by_api_key(
    db: Session,
    api_key: str
):
    return (
        db.query(Product)
        .filter(Product.api_key == api_key)
        .first()
    )


def create_product(
    db: Session,
    owner_id: int,
    product_name: str,
    product_serial: str,
    device_id: str
):
    product = Product(
        owner_id=owner_id,
        product_name=product_name,
        product_serial=product_serial,
        device_id=device_id,
        api_key=secrets.token_urlsafe(32),
        device_secret=secrets.token_urlsafe(48)
    )

    db.add(product)
    db.commit()
    db.refresh(product)

    return product


# =========================
# TELEMETRY
# =========================

def create_telemetry(
    db: Session,
    device_id: str,
    temperature: float,
    humidity: float,
    battery=None,
    status=None,
    raw_json=None
):
    row = Telemetry(
        device_id=device_id,
        temperature=float(temperature),
        humidity=float(humidity),
        battery=int(battery)
        if battery is not None
        else None,
        status=str(status)
        if status is not None
        else None,
        raw_json=raw_json
    )

    db.add(row)
    db.commit()
    db.refresh(row)

    return row


def get_latest(
    db: Session,
    device_id=None
):
    q = db.query(Telemetry)

    if device_id:
        q = q.filter(
            Telemetry.device_id == device_id
        )

    return q.order_by(
        Telemetry.id.desc()
    ).first()


def get_history(
    db: Session,
    device_id=None,
    limit=100
):
    q = db.query(Telemetry)

    if device_id:
        q = q.filter(
            Telemetry.device_id == device_id
        )

    rows = (
        q.order_by(
            Telemetry.id.desc()
        )
        .limit(limit)
        .all()
    )

    return list(reversed(rows))


# =========================
# DEVICE SECRET MIGRATION
# =========================

def backfill_device_secrets(db: Session):
    changed = False

    products = db.query(Product).all()

    for p in products:
        if not p.device_secret:
            p.device_secret = (
                secrets.token_urlsafe(48)
            )
            changed = True

    if changed:
        db.commit()
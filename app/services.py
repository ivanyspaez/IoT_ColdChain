import secrets
from typing import Optional, Tuple, List, Dict

from sqlalchemy.orm import Session

from app.models import User, Product, Telemetry, Alert


# =========================
# USERS
# =========================
def get_user_by_username(db: Session, username: str):
    return db.query(User).filter(User.username == username).first()


def create_user(db: Session, username: str, password_hash: str):
    user = User(
        username=username,
        password_hash=password_hash,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# =========================
# PRODUCTS
# =========================
def get_user_products(db: Session, owner_id: int):
    return (
        db.query(Product)
        .filter(Product.owner_id == owner_id)
        .order_by(Product.id.desc())
        .all()
    )


def get_product_by_serial(db: Session, serial: str):
    return db.query(Product).filter(Product.product_serial == serial).first()


def get_product_by_device(db: Session, device_id: str):
    return db.query(Product).filter(Product.device_id == device_id).first()


def get_product_by_api_key(db: Session, api_key: str):
    return db.query(Product).filter(Product.api_key == api_key).first()


def create_product(
    db: Session,
    owner_id: int,
    product_name: str,
    product_serial: str,
    device_id: str,
    temp_min: float = 2.0,
    temp_max: float = 8.0,
    hum_min: float = 30.0,
    hum_max: float = 70.0,
):
    product = Product(
        owner_id=owner_id,
        product_name=product_name,
        product_serial=product_serial,
        device_id=device_id,
        api_key=secrets.token_urlsafe(32),
        device_secret=secrets.token_urlsafe(48),
        temp_min=float(temp_min),
        temp_max=float(temp_max),
        hum_min=float(hum_min),
        hum_max=float(hum_max),
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def get_product_by_id(db: Session, product_id: int):
    return db.query(Product).filter(Product.id == product_id).first()


def update_product_ranges(
    db: Session,
    product_id: int,
    temp_min: float,
    temp_max: float,
    hum_min: float,
    hum_max: float,
):
    product = get_product_by_id(db, product_id)

    if not product:
        return None

    product.temp_min = float(temp_min)
    product.temp_max = float(temp_max)
    product.hum_min = float(hum_min)
    product.hum_max = float(hum_max)

    db.commit()
    db.refresh(product)
    return product


def delete_product(db: Session, product_id: int):
    product = get_product_by_id(db, product_id)

    if not product:
        return False

    db.delete(product)
    db.commit()
    return True


def transfer_product(
    db: Session,
    product_id: int,
    new_owner_username: str,
):
    product = get_product_by_id(db, product_id)

    if not product:
        return None

    user = (
        db.query(User)
        .filter(User.username == new_owner_username)
        .first()
    )

    if not user:
        return None

    product.owner_id = user.id
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
    decision=None,
    raw_json=None,
):
    row = Telemetry(
        device_id=device_id,
        temperature=float(temperature),
        humidity=float(humidity),
        battery=int(battery) if battery is not None else None,
        status=str(status) if status is not None else None,
        decision=str(decision) if decision is not None else None,
        raw_json=raw_json,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_latest(db: Session, device_id: Optional[str] = None):
    q = db.query(Telemetry)
    if device_id:
        q = q.filter(Telemetry.device_id == device_id)
    return q.order_by(Telemetry.id.desc()).first()


def get_history(db: Session, device_id: Optional[str] = None, limit: int = 100):
    q = db.query(Telemetry)
    if device_id:
        q = q.filter(Telemetry.device_id == device_id)
    rows = q.order_by(Telemetry.id.desc()).limit(limit).all()
    return list(reversed(rows))


# =========================
# ALERTS
# =========================
def create_alert(
    db: Session,
    device_id: str,
    telemetry_id: int,
    level: str,
    message: str,
):
    alert = Alert(
        device_id=device_id,
        telemetry_id=telemetry_id,
        level=level,
        message=message,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def get_alerts(db: Session, device_id: Optional[str] = None, limit: int = 20):
    q = db.query(Alert)
    if device_id:
        q = q.filter(Alert.device_id == device_id)
    rows = q.order_by(Alert.id.desc()).limit(limit).all()
    return list(rows)


# =========================
# BUSINESS LOGIC
# =========================
def evaluate_ranges(
    product: Product,
    temperature: float,
    humidity: float,
) -> Dict[str, str]:
    temp_status = "OK"
    hum_status = "OK"
    decision = "NONE"

    if temperature < product.temp_min:
        temp_status = "LOW_TEMP"
    elif temperature > product.temp_max:
        temp_status = "HIGH_TEMP"

    if humidity < product.hum_min:
        hum_status = "LOW_HUM"
    elif humidity > product.hum_max:
        hum_status = "HIGH_HUM"

    issues = []
    if temp_status != "OK":
        issues.append("A")
    if hum_status != "OK":
        issues.append("B")

    if len(issues) == 2:
        decision = "A_AND_B"
    elif len(issues) == 1:
        decision = issues[0]

    if temp_status != "OK" and hum_status != "OK":
        status = f"{temp_status}_{hum_status}"
    elif temp_status != "OK":
        status = temp_status
    elif hum_status != "OK":
        status = hum_status
    else:
        status = "OK"

    return {
        "status": status,
        "decision": decision,
        "temp_status": temp_status,
        "hum_status": hum_status,
    }


def build_alerts(
    product: Product,
    temperature: float,
    humidity: float,
) -> List[Dict[str, str]]:
    alerts = []

    if temperature < product.temp_min:
        alerts.append({
            "level": "WARNING",
            "message": f"Temperatura baja: {temperature:.1f} °C (mínimo permitido {product.temp_min:.1f} °C)",
        })
    elif temperature > product.temp_max:
        alerts.append({
            "level": "CRITICAL",
            "message": f"Temperatura alta: {temperature:.1f} °C (máximo permitido {product.temp_max:.1f} °C)",
        })

    if humidity < product.hum_min:
        alerts.append({
            "level": "WARNING",
            "message": f"Humedad baja: {humidity:.1f} % (mínimo permitido {product.hum_min:.1f} %)",
        })
    elif humidity > product.hum_max:
        alerts.append({
            "level": "CRITICAL",
            "message": f"Humedad alta: {humidity:.1f} % (máximo permitido {product.hum_max:.1f} %)",
        })

    return alerts


def register_telemetry_with_alert(
    db: Session,
    product: Product,
    device_id: str,
    temperature: float,
    humidity: float,
    battery=None,
    raw_json=None,
):
    evaluation = evaluate_ranges(product, temperature, humidity)

    row = create_telemetry(
        db=db,
        device_id=device_id,
        temperature=temperature,
        humidity=humidity,
        battery=battery,
        status=evaluation["status"],
        decision=evaluation["decision"],
        raw_json=raw_json,
    )

    alerts = build_alerts(product, temperature, humidity)
    for alert_data in alerts:
        create_alert(
            db=db,
            device_id=device_id,
            telemetry_id=row.id,
            level=alert_data["level"],
            message=alert_data["message"],
        )

    return row
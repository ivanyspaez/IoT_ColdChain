import os
import json
import secrets
import hmac
import hashlib
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Form, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from passlib.context import CryptContext
from jose import jwt, JWTError

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Float,
    DateTime,
    Text,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# =========================
# CONFIG
# =========================
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/telemetry.db")
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7
ACCESS_TOKEN_COOKIE = "access_token"
TELEMETRY_WINDOW_SECONDS = 300  # 5 minutos

# =========================
# DB
# =========================
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

pwd_context = CryptContext(
    schemes=["pbkdf2_sha256"],
    deprecated="auto"
)

# =========================
# MODELS
# =========================
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), unique=True, index=True, nullable=False)
    password_hash = Column(Text, nullable=False)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, index=True, nullable=False)

    product_name = Column(String(120), nullable=False)
    product_serial = Column(String(120), unique=True, index=True, nullable=False)

    device_id = Column(String(120), unique=True, index=True, nullable=False)
    api_key = Column(String(200), unique=True, index=True, nullable=False)
    device_secret = Column(String(200), unique=True, index=True, nullable=True)

    min_temp = Column(Float, default=2.0)
    max_temp = Column(Float, default=8.0)
    
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )


class Telemetry(Base):
    __tablename__ = "telemetry"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(120), index=True, nullable=False)
    temperature = Column(Float, nullable=False)
    humidity = Column(Float, nullable=False)
    battery = Column(Integer, nullable=True)
    status = Column(String(50), nullable=True)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    raw_json = Column(Text, nullable=True)


Base.metadata.create_all(bind=engine)


def ensure_device_secret_column():
    """
    Agrega la columna device_secret a SQLite si la tabla products ya existía antes.
    """
    if not DATABASE_URL.startswith("sqlite"):
        return

    with engine.begin() as conn:
        rows = conn.exec_driver_sql("PRAGMA table_info(products)").fetchall()
        cols = {row[1] for row in rows}

        if "device_secret" not in cols:
            conn.exec_driver_sql("ALTER TABLE products ADD COLUMN device_secret TEXT")


def backfill_device_secrets():
    """
    Si ya existían productos sin device_secret, se les asigna uno nuevo.
    """
    db = SessionLocal()
    try:
        changed = False
        products = db.query(Product).all()
        for p in products:
            if not p.device_secret:
                p.device_secret = secrets.token_urlsafe(48)
                changed = True

        if changed:
            db.commit()
    finally:
        db.close()


ensure_device_secret_column()

def ensure_temperature_columns():
    
    if not DATABASE_URL.startswith("sqlite"):
        return

    with engine.begin() as conn:

        rows = conn.exec_driver_sql(
            "PRAGMA table_info(products)"
        ).fetchall()

        cols = {row[1] for row in rows}

        if "min_temp" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE products ADD COLUMN min_temp FLOAT DEFAULT 2"
            )

        if "max_temp" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE products ADD COLUMN max_temp FLOAT DEFAULT 8"
            )

backfill_device_secrets()

# =========================
# APP
# =========================
app = FastAPI(title="IoT ColdChain Dashboard")
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def render_index(request: Request, context: dict, status_code: int = 200):
    ctx = {"request": request, **context}
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context=ctx,
        status_code=status_code,
    )


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


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


def require_user(request: Request) -> str:
    user = current_username(request)
    if not user:
        raise HTTPException(status_code=401, detail="No autenticado")
    return user


def serialize_product(row: Product) -> dict:
    return {
        "id": row.id,
        "owner_id": row.owner_id,
        "product_name": row.product_name,
        "product_serial": row.product_serial,
        "device_id": row.device_id,
        "api_key": row.api_key,
        "device_secret": row.device_secret,
        "min_temp": row.min_temp,
        "max_temp": row.max_temp,
        "created_at": row.created_at.isoformat(),
    }


def serialize_telemetry(row: Telemetry) -> dict:
    return {
        "id": row.id,
        "device_id": row.device_id,
        "temperature": row.temperature,
        "humidity": row.humidity,
        "battery": row.battery,
        "status": row.status,
        "created_at": row.created_at.isoformat(),
    }


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


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    product_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    username = current_username(request)

    if not username:
        return render_index(
            request,
            {
                "user": None,
                "products": [],
                "selected_product": None,
                "latest": None,
                "history": [],
                "error": None,
                "success": None,
            },
        )

    user = db.query(User).filter(User.username == username).first()
    if not user:
        return render_index(
            request,
            {
                "user": None,
                "products": [],
                "selected_product": None,
                "latest": None,
                "history": [],
                "error": "Sesión inválida. Vuelve a iniciar sesión.",
                "success": None,
            },
            status_code=401,
        )

    products = (
        db.query(Product)
        .filter(Product.owner_id == user.id)
        .order_by(Product.id.desc())
        .all()
    )

    selected_product = None
    if product_id is not None:
        selected_product = next((p for p in products if p.id == product_id), None)
    if selected_product is None and products:
        selected_product = products[0]

    latest = None
    history = []
    if selected_product is not None:
        latest_row = get_latest(db, selected_product.device_id)
        if latest_row:
            latest = serialize_telemetry(latest_row)
        history_rows = get_history(db, selected_product.device_id, limit=100)
        history = [serialize_telemetry(r) for r in history_rows]

    return render_index(
        request,
        {
            "user": username,
            "products": [serialize_product(p) for p in products],
            "selected_product": serialize_product(selected_product) if selected_product else None,
            "latest": latest,
            "history": history,
            "error": None,
            "success": None,
        },
    )


@app.post("/register")
def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    username = username.strip().lower()

    if len(username) < 3 or len(password) < 6:
        return render_index(
            request,
            {
                "user": None,
                "products": [],
                "selected_product": None,
                "latest": None,
                "history": [],
                "error": "Usuario mínimo 3 caracteres y contraseña mínimo 6.",
                "success": None,
            },
            status_code=400,
        )

    existing = db.query(User).filter(User.username == username).first()
    if existing:
        return render_index(
            request,
            {
                "user": None,
                "products": [],
                "selected_product": None,
                "latest": None,
                "history": [],
                "error": "Ese usuario ya existe.",
                "success": None,
            },
            status_code=400,
        )

    user = User(
        username=username,
        password_hash=hash_password(password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(username)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=ACCESS_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    )
    return response


@app.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    username = username.strip().lower()
    user = db.query(User).filter(User.username == username).first()

    if not user or not verify_password(password, user.password_hash):
        return render_index(
            request,
            {
                "user": None,
                "products": [],
                "selected_product": None,
                "latest": None,
                "history": [],
                "error": "Credenciales inválidas.",
                "success": None,
            },
            status_code=401,
        )

    token = create_access_token(username)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=ACCESS_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    )
    return response


@app.post("/logout")
def logout():
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(ACCESS_TOKEN_COOKIE)
    return response


@app.post("/products/new")
def create_product(
    request: Request,
    product_name: str = Form(...),
    product_serial: str = Form(...),
    device_id: str = Form(...),
    db: Session = Depends(get_db),
):
    username = require_user(request)

    user = db.query(User).filter(User.username == username).first()
    if not user:
        return RedirectResponse("/", status_code=303)

    product_name = product_name.strip()
    product_serial = product_serial.strip()
    device_id = device_id.strip()

    if not product_name or not product_serial or not device_id:
        return render_index(
            request,
            {
                "user": username,
                "products": [
                    serialize_product(p)
                    for p in db.query(Product).filter(Product.owner_id == user.id).all()
                ],
                "selected_product": None,
                "latest": None,
                "history": [],
                "error": "Todos los campos del producto son obligatorios.",
                "success": None,
            },
            status_code=400,
        )

    duplicate_serial = db.query(Product).filter(Product.product_serial == product_serial).first()
    if duplicate_serial:
        return render_index(
            request,
            {
                "user": username,
                "products": [
                    serialize_product(p)
                    for p in db.query(Product).filter(Product.owner_id == user.id).all()
                ],
                "selected_product": None,
                "latest": None,
                "history": [],
                "error": "Ese serial ya está registrado.",
                "success": None,
            },
            status_code=400,
        )

    duplicate_device = db.query(Product).filter(Product.device_id == device_id).first()
    if duplicate_device:
        return render_index(
            request,
            {
                "user": username,
                "products": [
                    serialize_product(p)
                    for p in db.query(Product).filter(Product.owner_id == user.id).all()
                ],
                "selected_product": None,
                "latest": None,
                "history": [],
                "error": "Ese device_id ya está asociado a otro producto.",
                "success": None,
            },
            status_code=400,
        )

    api_key = secrets.token_urlsafe(32)
    device_secret = secrets.token_urlsafe(48)

    product = Product(
        owner_id=user.id,
        product_name=product_name,
        product_serial=product_serial,
        device_id=device_id,
        api_key=api_key,
        device_secret=device_secret,
    )
    db.add(product)
    db.commit()
    db.refresh(product)

    return RedirectResponse(f"/?product_id={product.id}", status_code=303)


@app.get("/api/latest")
def api_latest(device_id: Optional[str] = None, db: Session = Depends(get_db)):
    row = get_latest(db, device_id=device_id)
    if not row:
        return {
            "device_id": None,
            "temperature": None,
            "humidity": None,
            "battery": None,
            "status": None,
            "created_at": None,
        }
    return serialize_telemetry(row)


@app.get("/api/history")
def api_history(device_id: Optional[str] = None, limit: int = 100, db: Session = Depends(get_db)):
    rows = get_history(db, device_id=device_id, limit=limit)
    return [serialize_telemetry(r) for r in rows]


@app.post("/telemetry")
async def receive_telemetry(request: Request, db: Session = Depends(get_db)):
    api_key = request.headers.get("x-api-key")
    timestamp = request.headers.get("x-timestamp")
    signature = request.headers.get("x-signature")

    if not api_key or not timestamp or not signature:
        raise HTTPException(status_code=401, detail="Faltan headers de autenticación")

    product = db.query(Product).filter(Product.api_key == api_key).first()
    if not product:
        raise HTTPException(status_code=403, detail="API key inválida")

    if not product.device_secret:
        raise HTTPException(status_code=409, detail="El producto no tiene device_secret configurado")

    try:
        ts_int = int(timestamp)
    except ValueError:
        raise HTTPException(status_code=400, detail="Timestamp inválido")

    now = int(time.time())
    if abs(now - ts_int) > TELEMETRY_WINDOW_SECONDS:
        raise HTTPException(status_code=403, detail="Timestamp fuera de ventana")

    body = await request.body()

    expected = hmac.new(
        product.device_secret.encode(),
        f"{product.device_id}.{timestamp}.".encode() + body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=403, detail="Firma inválida")

    try:
        data = json.loads(body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="JSON inválido")

    device_id = str(data.get("device_id", "unknown"))
    temperature = data.get("temperature", None)
    humidity = data.get("humidity", None)

    if device_id != product.device_id:
        raise HTTPException(status_code=403, detail="device_id no coincide con la API key")

    if temperature is None or humidity is None:
        raise HTTPException(status_code=400, detail="temperature y humidity son obligatorios")

    battery = data.get("battery")
    if float(temperature) < product.min_temp:
        status = "LOW_TEMP"

    elif float(temperature) > product.max_temp:
        status = "HIGH_TEMP"

    else:
        status = "OK"
    raw_json = json.dumps(data, ensure_ascii=False)

    row = Telemetry(
        device_id=device_id,
        temperature=float(temperature),
        humidity=float(humidity),
        battery=int(battery) if battery is not None else None,
        status=str(status) if status is not None else None,
        raw_json=raw_json,
    )

    db.add(row)
    db.commit()
    db.refresh(row)

    print("\n==================================================")
    print("PAQUETE RECIBIDO")
    print("==================================================")
    print(raw_json)
    print("==================================================")

    return JSONResponse(
        {
            "ok": True,
            "message": "Telemetry received",
            "id": row.id,
            "created_at": row.created_at.isoformat(),
        }
    )
import os
import hmac
import json
import time
import hashlib
import inspect
from datetime import datetime, timezone

from fastapi import FastAPI, Request, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from passlib.context import CryptContext
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, DateTime, Text
)
from sqlalchemy.orm import sessionmaker, declarative_base, Session

# ===== CONFIG =====
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
DEVICE_ID = os.getenv("DEVICE_ID", "esp32-coldchain-001")
DEVICE_SECRET = os.getenv("DEVICE_SECRET", "device-secret")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/app.db")

# ===== DB =====
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


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), unique=True, index=True, nullable=False)
    password_hash = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Telemetry(Base):
    __tablename__ = "telemetry"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(120), index=True, nullable=False)
    temperature = Column(Float, nullable=False)
    humidity = Column(Float, nullable=False)
    ts = Column(Integer, nullable=False)
    received_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


Base.metadata.create_all(bind=engine)

# ===== APP =====
app = FastAPI()
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    same_site="lax",
    https_only=False
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Detecta la firma real de TemplateResponse para evitar el TypeError entre versiones
_TEMPLATE_PARAMS = list(inspect.signature(templates.TemplateResponse).parameters.keys())
_TEMPLATE_REQUEST_FIRST = len(_TEMPLATE_PARAMS) > 0 and _TEMPLATE_PARAMS[0] == "request"


def render_index(request: Request, context: dict, status_code: int = 200):
    ctx = {"request": request, **context}

    if _TEMPLATE_REQUEST_FIRST:
        # Formato: TemplateResponse(request, name, context, ...)
        return templates.TemplateResponse(
            request,
            "index.html",
            ctx,
            status_code=status_code
        )

    # Formato: TemplateResponse(name, context, ...)
    return templates.TemplateResponse(
        "index.html",
        ctx,
        status_code=status_code
    )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def current_username(request: Request):
    return request.session.get("user")


def require_user(request: Request):
    user = current_username(request)
    if not user:
        raise HTTPException(status_code=401, detail="No autenticado")
    return user


def latest_telemetry(db: Session, limit: int = 20):
    return db.query(Telemetry).order_by(Telemetry.id.desc()).limit(limit).all()


@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    user = current_username(request)
    rows = latest_telemetry(db) if user else []
    return render_index(
        request,
        {
            "user": user,
            "rows": rows,
            "error": None,
        }
    )


@app.post("/register", response_class=HTMLResponse)
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
                "rows": [],
                "error": "Usuario mínimo 3 caracteres y contraseña mínimo 6.",
            },
            status_code=400
        )

    existing = db.query(User).filter(User.username == username).first()
    if existing:
        return render_index(
            request,
            {
                "user": None,
                "rows": [],
                "error": "Ese usuario ya existe.",
            },
            status_code=400
        )

    user = User(
        username=username,
        password_hash=hash_password(password)
    )
    db.add(user)
    db.commit()

    request.session["user"] = username
    return RedirectResponse("/", status_code=303)


@app.post("/login", response_class=HTMLResponse)
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
                "rows": [],
                "error": "Credenciales inválidas.",
            },
            status_code=401
        )

    request.session["user"] = username
    return RedirectResponse("/", status_code=303)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)


@app.get("/api/telemetry/latest")
def api_latest(request: Request, db: Session = Depends(get_db)):
    require_user(request)
    rows = latest_telemetry(db, limit=20)
    return [
        {
            "device_id": r.device_id,
            "temperature": r.temperature,
            "humidity": r.humidity,
            "ts": r.ts,
            "received_at": r.received_at.isoformat(),
        }
        for r in rows
    ]


@app.post("/api/telemetry")
async def api_telemetry(request: Request, db: Session = Depends(get_db)):
    headers = request.headers
    device_id = headers.get("x-device-id")
    timestamp = headers.get("x-timestamp")
    signature = headers.get("x-signature")

    if not device_id or not timestamp or not signature:
        raise HTTPException(status_code=400, detail="Headers faltantes")

    if device_id != DEVICE_ID:
        raise HTTPException(status_code=403, detail="Dispositivo no autorizado")

    try:
        ts_int = int(timestamp)
    except ValueError:
        raise HTTPException(status_code=400, detail="Timestamp inválido")

    now = int(time.time())
    if abs(now - ts_int) > 300:
        raise HTTPException(status_code=403, detail="Timestamp fuera de ventana")

    body = await request.body()
    expected = hmac.new(
        DEVICE_SECRET.encode(),
        f"{device_id}.{timestamp}.".encode() + body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=403, detail="Firma inválida")

    try:
        data = json.loads(body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="JSON inválido")

    temperature = float(data["temperature"])
    humidity = float(data["humidity"])
    payload_device = str(data.get("device_id", device_id))
    payload_ts = int(data.get("ts", ts_int))

    row = Telemetry(
        device_id=payload_device,
        temperature=temperature,
        humidity=humidity,
        ts=payload_ts,
    )
    db.add(row)
    db.commit()

    return JSONResponse(
        {
            "ok": True,
            "message": "Telemetry stored",
        }
    )
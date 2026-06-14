import os
import secrets
from datetime import datetime, timezone

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Float,
    DateTime,
    Text,
)
from sqlalchemy.orm import declarative_base, sessionmaker

# =========================
# CONFIG
# =========================
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/telemetry.db")

# =========================
# DB
# =========================
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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
        nullable=False,
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

    temp_min = Column(Float, nullable=False, default=2.0)
    temp_max = Column(Float, nullable=False, default=8.0)

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
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
        nullable=False,
    )
    raw_json = Column(Text, nullable=True)


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(120), index=True, nullable=False)
    telemetry_id = Column(Integer, index=True, nullable=True)
    level = Column(String(30), nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


Base.metadata.create_all(bind=engine)


def ensure_device_secret_column():
    if not DATABASE_URL.startswith("sqlite"):
        return

    with engine.begin() as conn:
        rows = conn.exec_driver_sql("PRAGMA table_info(products)").fetchall()
        cols = {row[1] for row in rows}

        if "device_secret" not in cols:
            conn.exec_driver_sql("ALTER TABLE products ADD COLUMN device_secret TEXT")


def ensure_temperature_columns():
    if not DATABASE_URL.startswith("sqlite"):
        return

    with engine.begin() as conn:
        rows = conn.exec_driver_sql("PRAGMA table_info(products)").fetchall()
        cols = {row[1] for row in rows}

        if "temp_min" not in cols:
            conn.exec_driver_sql("ALTER TABLE products ADD COLUMN temp_min FLOAT DEFAULT 2.0")

        if "temp_max" not in cols:
            conn.exec_driver_sql("ALTER TABLE products ADD COLUMN temp_max FLOAT DEFAULT 8.0")

        conn.exec_driver_sql("UPDATE products SET temp_min = 2.0 WHERE temp_min IS NULL")
        conn.exec_driver_sql("UPDATE products SET temp_max = 8.0 WHERE temp_max IS NULL")


def backfill_device_secrets():
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


def backfill_temperature_defaults():
    db = SessionLocal()
    try:
        changed = False
        products = db.query(Product).all()
        for p in products:
            if p.temp_min is None:
                p.temp_min = 2.0
                changed = True
            if p.temp_max is None:
                p.temp_max = 8.0
                changed = True
        if changed:
            db.commit()
    finally:
        db.close()

def backfill_missing_ranges():
    db = SessionLocal()

    try:
        changed = False

        products = db.query(Product).all()

        for p in products:

            if p.temp_min is None:
                p.temp_min = 2.0
                changed = True

            if p.temp_max is None:
                p.temp_max = 8.0
                changed = True

        if changed:
            db.commit()

    finally:
        db.close()

ensure_device_secret_column()
ensure_temperature_columns()
backfill_device_secrets()
backfill_temperature_defaults()
backfill_missing_ranges()
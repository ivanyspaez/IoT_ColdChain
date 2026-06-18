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

    hum_min = Column(Float, nullable=False, default=30.0)
    hum_max = Column(Float, nullable=False, default=70.0)

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
    status = Column(String(80), nullable=True)
    decision = Column(String(50), nullable=True)
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


def ensure_product_range_columns():
    if not DATABASE_URL.startswith("sqlite"):
        return

    with engine.begin() as conn:
        rows = conn.exec_driver_sql("PRAGMA table_info(products)").fetchall()
        cols = {row[1] for row in rows}

        # temp_min
        if "temp_min" not in cols:
            if "min_temp" in cols:
                try:
                    conn.exec_driver_sql("ALTER TABLE products RENAME COLUMN min_temp TO temp_min")
                except Exception:
                    conn.exec_driver_sql("ALTER TABLE products ADD COLUMN temp_min FLOAT DEFAULT 2.0")
                    conn.exec_driver_sql("UPDATE products SET temp_min = min_temp WHERE temp_min IS NULL")
            else:
                conn.exec_driver_sql("ALTER TABLE products ADD COLUMN temp_min FLOAT DEFAULT 2.0")

        # temp_max
        if "temp_max" not in cols:
            if "max_temp" in cols:
                try:
                    conn.exec_driver_sql("ALTER TABLE products RENAME COLUMN max_temp TO temp_max")
                except Exception:
                    conn.exec_driver_sql("ALTER TABLE products ADD COLUMN temp_max FLOAT DEFAULT 8.0")
                    conn.exec_driver_sql("UPDATE products SET temp_max = max_temp WHERE temp_max IS NULL")
            else:
                conn.exec_driver_sql("ALTER TABLE products ADD COLUMN temp_max FLOAT DEFAULT 8.0")

        # hum_min
        if "hum_min" not in cols:
            conn.exec_driver_sql("ALTER TABLE products ADD COLUMN hum_min FLOAT DEFAULT 30.0")

        # hum_max
        if "hum_max" not in cols:
            conn.exec_driver_sql("ALTER TABLE products ADD COLUMN hum_max FLOAT DEFAULT 70.0")

        conn.exec_driver_sql("UPDATE products SET temp_min = 2.0 WHERE temp_min IS NULL")
        conn.exec_driver_sql("UPDATE products SET temp_max = 8.0 WHERE temp_max IS NULL")
        conn.exec_driver_sql("UPDATE products SET hum_min = 30.0 WHERE hum_min IS NULL")
        conn.exec_driver_sql("UPDATE products SET hum_max = 70.0 WHERE hum_max IS NULL")


def ensure_telemetry_decision_column():
    if not DATABASE_URL.startswith("sqlite"):
        return

    with engine.begin() as conn:
        rows = conn.exec_driver_sql("PRAGMA table_info(telemetry)").fetchall()
        cols = {row[1] for row in rows}

        if "decision" not in cols:
            conn.exec_driver_sql("ALTER TABLE telemetry ADD COLUMN decision TEXT")


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


def backfill_ranges():
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
            if p.hum_min is None:
                p.hum_min = 30.0
                changed = True
            if p.hum_max is None:
                p.hum_max = 70.0
                changed = True
        if changed:
            db.commit()
    finally:
        db.close()


ensure_device_secret_column()
ensure_product_range_columns()
ensure_telemetry_decision_column()
backfill_device_secrets()
backfill_ranges()
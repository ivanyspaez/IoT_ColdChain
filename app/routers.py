import json
import time
import csv
import io
import hmac
import hashlib

from fastapi.responses import StreamingResponse
from fastapi import APIRouter, Request, HTTPException, Form, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.models import get_db, User
from app.services import (
    get_user_by_username,
    create_user,
    get_user_products,
    get_product_by_serial,
    get_product_by_device,
    get_product_by_api_key,
    create_product,
    get_latest,
    get_history,
    get_alerts,
    register_telemetry_with_alert,
    get_product_by_id,
    update_product_temperature_range,
    delete_product,
    transfer_product,
)
from app.utils import (
    hash_password,
    verify_password,
    create_access_token,
    current_username,
    hmac_sha256_hex,
    serialize_product,
    serialize_telemetry,
    serialize_alert,
)

templates = Jinja2Templates(directory="templates")
router = APIRouter()

ACCESS_TOKEN_COOKIE = "access_token"
TELEMETRY_WINDOW_SECONDS = 300


def render_index(request: Request, context: dict, status_code: int = 200):
    ctx = {"request": request, **context}
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context=ctx,
        status_code=status_code,
    )


@router.get("/health")
def health():
    return {"ok": True}

@router.get("/export/csv")
def export_csv(
    device_id: str,
    db: Session = Depends(get_db),
):
    history = get_history(
        db,
        device_id=device_id,
        limit=10000,
    )

    output = io.StringIO()

    writer = csv.writer(output)

    writer.writerow(
        [
            "fecha",
            "device_id",
            "temperature",
            "humidity",
            "battery",
            "status",
        ]
    )

    for row in history:
        writer.writerow(
            [
                row.created_at.isoformat(),
                row.device_id,
                row.temperature,
                row.humidity,
                row.battery,
                row.status,
            ]
        )

    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition":
            f"attachment; filename={device_id}.csv"
        },
    )

@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    product_id: int | None = None,
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
                "alerts": [],
                "error": None,
                "success": None,
            },
        )

    user = get_user_by_username(db, username)
    if not user:
        return render_index(
            request,
            {
                "user": None,
                "products": [],
                "selected_product": None,
                "latest": None,
                "history": [],
                "alerts": [],
                "error": "Sesión inválida. Vuelve a iniciar sesión.",
                "success": None,
            },
            status_code=401,
        )

    products = get_user_products(db, user.id)

    selected_product = None
    if product_id is not None:
        selected_product = next((p for p in products if p.id == product_id), None)
    if selected_product is None and products:
        selected_product = products[0]

    latest = None
    history = []
    alerts = []

    if selected_product is not None:
        latest_row = get_latest(db, selected_product.device_id)
        if latest_row:
            latest = serialize_telemetry(latest_row)

        history_rows = get_history(db, selected_product.device_id, limit=100)
        history = [serialize_telemetry(r) for r in history_rows]

        alerts_rows = get_alerts(db, selected_product.device_id, limit=20)
        alerts = [serialize_alert(a) for a in alerts_rows]

    return render_index(
        request,
        {
            "user": username,
            "products": [serialize_product(p) for p in products],
            "selected_product": serialize_product(selected_product) if selected_product else None,
            "latest": latest,
            "history": history,
            "alerts": alerts,
            "error": None,
            "success": None,
        },
    )


@router.post("/register")
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
                "alerts": [],
                "error": "Usuario mínimo 3 caracteres y contraseña mínimo 6.",
                "success": None,
            },
            status_code=400,
        )

    existing = get_user_by_username(db, username)
    if existing:
        return render_index(
            request,
            {
                "user": None,
                "products": [],
                "selected_product": None,
                "latest": None,
                "history": [],
                "alerts": [],
                "error": "Ese usuario ya existe.",
                "success": None,
            },
            status_code=400,
        )

    user = create_user(db, username, hash_password(password))

    token = create_access_token(username)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=7 * 24 * 60 * 60,
    )
    return response


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    username = username.strip().lower()
    user = get_user_by_username(db, username)

    if not user or not verify_password(password, user.password_hash):
        return render_index(
            request,
            {
                "user": None,
                "products": [],
                "selected_product": None,
                "latest": None,
                "history": [],
                "alerts": [],
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
        max_age=7 * 24 * 60 * 60,
    )
    return response


@router.post("/logout")
def logout():
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(ACCESS_TOKEN_COOKIE)
    return response


@router.post("/products/new")
def create_product_route(
    request: Request,
    product_name: str = Form(...),
    product_serial: str = Form(...),
    device_id: str = Form(...),
    temp_min: float = Form(2.0),
    temp_max: float = Form(8.0),
    db: Session = Depends(get_db),
):
    username = current_username(request)
    if not username:
        raise HTTPException(status_code=401, detail="No autenticado")

    user = get_user_by_username(db, username)
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
                "products": [serialize_product(p) for p in get_user_products(db, user.id)],
                "selected_product": None,
                "latest": None,
                "history": [],
                "alerts": [],
                "error": "Todos los campos del producto son obligatorios.",
                "success": None,
            },
            status_code=400,
        )

    if temp_min >= temp_max:
        return render_index(
            request,
            {
                "user": username,
                "products": [serialize_product(p) for p in get_user_products(db, user.id)],
                "selected_product": None,
                "latest": None,
                "history": [],
                "alerts": [],
                "error": "El mínimo de temperatura debe ser menor que el máximo.",
                "success": None,
            },
            status_code=400,
        )

    if get_product_by_serial(db, product_serial):
        return render_index(
            request,
            {
                "user": username,
                "products": [serialize_product(p) for p in get_user_products(db, user.id)],
                "selected_product": None,
                "latest": None,
                "history": [],
                "alerts": [],
                "error": "Ese serial ya está registrado.",
                "success": None,
            },
            status_code=400,
        )

    if get_product_by_device(db, device_id):
        return render_index(
            request,
            {
                "user": username,
                "products": [serialize_product(p) for p in get_user_products(db, user.id)],
                "selected_product": None,
                "latest": None,
                "history": [],
                "alerts": [],
                "error": "Ese device_id ya está asociado a otro producto.",
                "success": None,
            },
            status_code=400,
        )

    product = create_product(
        db=db,
        owner_id=user.id,
        product_name=product_name,
        product_serial=product_serial,
        device_id=device_id,
        temp_min=temp_min,
        temp_max=temp_max,
    )

    return RedirectResponse(f"/?product_id={product.id}", status_code=303)

@router.post("/products/update-range")
def update_range(
    request: Request,
    product_id: int = Form(...),
    temp_min: float = Form(...),
    temp_max: float = Form(...),
    db: Session = Depends(get_db),
):
    username = current_username(request)

    if not username:
        raise HTTPException(401)

    product = get_product_by_id(db, product_id)

    if not product:
        raise HTTPException(404)

    if temp_min >= temp_max:
        raise HTTPException(
            400,
            "El mínimo debe ser menor que el máximo"
        )

    update_product_temperature_range(
        db,
        product_id,
        temp_min,
        temp_max,
    )

    return RedirectResponse(
        f"/?product_id={product_id}",
        status_code=303,
    )
@router.post("/products/delete")
def delete_product_route(
    request: Request,
    product_id: int = Form(...),
    db: Session = Depends(get_db),
):
    username = current_username(request)

    if not username:
        raise HTTPException(401)

    delete_product(db, product_id)

    return RedirectResponse(
        "/",
        status_code=303,
    )
@router.post("/products/transfer")
def transfer_product_route(
    request: Request,
    product_id: int = Form(...),
    username_target: str = Form(...),
    db: Session = Depends(get_db),
):
    username = current_username(request)

    if not username:
        raise HTTPException(401)

    product = transfer_product(
        db,
        product_id,
        username_target.strip().lower(),
    )

    if not product:
        raise HTTPException(
            404,
            "Usuario destino no encontrado"
        )

    return RedirectResponse(
        "/",
        status_code=303,
    )
@router.get("/api/latest")
def api_latest(device_id: str | None = None, db: Session = Depends(get_db)):
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


@router.get("/api/history")
def api_history(device_id: str | None = None, limit: int = 100, db: Session = Depends(get_db)):
    rows = get_history(db, device_id=device_id, limit=limit)
    return [serialize_telemetry(r) for r in rows]


@router.get("/api/alerts")
def api_alerts(device_id: str | None = None, limit: int = 20, db: Session = Depends(get_db)):
    rows = get_alerts(db, device_id=device_id, limit=limit)
    return [serialize_alert(r) for r in rows]


@router.post("/telemetry")
async def receive_telemetry(request: Request, db: Session = Depends(get_db)):
    api_key = request.headers.get("x-api-key")
    timestamp = request.headers.get("x-timestamp")
    signature = request.headers.get("x-signature")

    if not api_key or not timestamp or not signature:
        raise HTTPException(status_code=401, detail="Faltan headers de autenticación")

    product = get_product_by_api_key(db, api_key)
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

    expected = hmac_sha256_hex(
        f"{product.device_id}.{timestamp}.".encode("utf-8") + body,
        product.device_secret,
    )

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
    raw_json = json.dumps(data, ensure_ascii=False)

    row = register_telemetry_with_alert(
        db=db,
        product=product,
        device_id=device_id,
        temperature=float(temperature),
        humidity=float(humidity),
        battery=battery,
        raw_json=raw_json,
    )

    return JSONResponse(
        {
            "ok": True,
            "message": "Telemetry received",
            "id": row.id,
            "created_at": row.created_at.isoformat(),
            "status": row.status,
        }
    )
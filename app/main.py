from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import router

# IMPORTANTE
from app import mqtt_client

app = FastAPI(
    title="IoT ColdChain Dashboard"
)

app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static",
)

app.include_router(router)


@app.on_event("startup")
async def startup():

    print(
        "MQTT listener iniciado"
    )
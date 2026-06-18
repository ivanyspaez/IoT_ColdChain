from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import router

app = FastAPI(title="IoT ColdChain Dashboard")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(router)
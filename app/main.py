"""FastAPI entrypoint."""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.db import init_db
from app.routes import router

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logging.getLogger("main").info("Preview app booted · read-only · DB ready")
    yield


app = FastAPI(title="CastleBay Portal Preview", version="0.1.0", lifespan=lifespan)


@app.exception_handler(HTTPException)
async def auth_redirect_handler(request: Request, exc: HTTPException):
    """Convert 302 from _require_user into an actual redirect."""
    if exc.status_code == 302:
        return RedirectResponse(exc.headers.get("Location", "/login"), status_code=303)
    raise exc


app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(router)

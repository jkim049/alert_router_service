import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.database import engine, Base
from app.routers import alerts, routes, stats, dry_run, system


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs("data", exist_ok=True)
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Alert Router Service",
    description=(
        "Ingests monitoring alerts, evaluates them against user-defined routing rules, "
        "and produces routed notification outputs. Visit /docs to explore the API."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    first = exc.errors()[0]
    # Build a readable field path, skipping the top-level "body" wrapper
    loc_parts = [str(p) for p in first["loc"] if p != "body"]
    field = ".".join(loc_parts)
    msg = first["msg"].removeprefix("Value error, ")  # strip Pydantic's prefix on field_validator errors
    error = f"{field}: {msg}" if field else msg
    return JSONResponse(status_code=400, content={"error": error})


app.include_router(alerts.router)
app.include_router(routes.router)
app.include_router(stats.router)
app.include_router(dry_run.router)
app.include_router(system.router)

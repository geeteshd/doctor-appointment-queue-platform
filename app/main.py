"""FastAPI application entrypoint.

Creates tables on startup (fine for this assignment; a production system would
use Alembic migrations) and wires up the routers. Swagger UI is at /docs.
"""
from fastapi import FastAPI

from app.core.database import Base, engine
from app.models import models  # noqa: F401  (ensures models are registered)
from app.routers import doctors, appointments, queue

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Doctor Appointment & Queue Management Platform",
    description="Backend APIs for doctor discovery, appointment booking, "
                "consultation queue management, and prescription uploads.",
    version="1.0.0",
)

app.include_router(doctors.router)
app.include_router(appointments.router)
app.include_router(queue.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}

"""Queue read + call-next endpoints (doctor-scoped)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.schemas import QueueView, AppointmentOut
from app.services import booking

router = APIRouter(prefix="/doctors", tags=["queue"])


@router.get("/{doctor_id}/queue", response_model=QueueView)
def get_queue(doctor_id: int, db: Session = Depends(get_db)):
    return booking.get_queue(db, doctor_id)


@router.post("/{doctor_id}/queue/next", response_model=AppointmentOut)
def call_next(doctor_id: int, db: Session = Depends(get_db)):
    return booking.call_next(db, doctor_id)

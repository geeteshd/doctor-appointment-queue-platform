"""Doctor + schedule + search endpoints."""
from datetime import date, datetime, time
from typing import Optional, List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import Doctor, Slot
from app.schemas.schemas import DoctorCreate, DoctorOut, AvailabilityCreate, SlotOut
from app.services import booking

router = APIRouter(prefix="/doctors", tags=["doctors"])


@router.post("", response_model=DoctorOut, status_code=201)
def create_doctor(data: DoctorCreate, db: Session = Depends(get_db)):
    return booking.create_doctor(db, data)


@router.get("", response_model=List[DoctorOut])
def search_doctors(
    name: Optional[str] = None,
    specialization: Optional[str] = None,
    clinic: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Search doctors by name / specialization / clinic (all optional, ANDed)."""
    stmt = select(Doctor)
    if name:
        stmt = stmt.where(Doctor.name.ilike(f"%{name}%"))
    if specialization:
        stmt = stmt.where(Doctor.specialization.ilike(f"%{specialization}%"))
    if clinic:
        stmt = stmt.where(Doctor.clinic.ilike(f"%{clinic}%"))
    return list(db.scalars(stmt))


@router.get("/{doctor_id}", response_model=DoctorOut)
def get_doctor(doctor_id: int, db: Session = Depends(get_db)):
    from fastapi import HTTPException
    doctor = db.get(Doctor, doctor_id)
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return doctor


@router.post("/{doctor_id}/availability", response_model=List[SlotOut], status_code=201)
def add_availability(doctor_id: int, data: AvailabilityCreate, db: Session = Depends(get_db)):
    return booking.generate_slots(db, doctor_id, data.start_time, data.end_time)


@router.get("/{doctor_id}/slots", response_model=List[SlotOut])
def get_slots(
    doctor_id: int,
    slot_date: Optional[date] = Query(None, alias="date"),
    available_only: bool = True,
    db: Session = Depends(get_db),
):
    """List a doctor's slots, optionally filtered to one date and to free slots."""
    stmt = select(Slot).where(Slot.doctor_id == doctor_id)
    if available_only:
        stmt = stmt.where(Slot.is_booked == False)  # noqa: E712
    if slot_date:
        day_start = datetime.combine(slot_date, time.min)
        day_end = datetime.combine(slot_date, time.max)
        stmt = stmt.where(Slot.start_time >= day_start, Slot.start_time <= day_end)
    return list(db.scalars(stmt.order_by(Slot.start_time)))

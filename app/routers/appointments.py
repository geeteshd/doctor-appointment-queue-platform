"""Appointment lifecycle + queue + prescription endpoints."""
from typing import List

from fastapi import APIRouter, Depends, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.schemas import (
    AppointmentCreate, AppointmentOut, PrescriptionOut
)
from app.services import booking

router = APIRouter(tags=["appointments"])


# ----- booking -----
@router.post("/appointments", response_model=AppointmentOut, status_code=201)
def create_appointment(data: AppointmentCreate, db: Session = Depends(get_db)):
    return booking.book_appointment(db, data.slot_id, data.patient_name)


@router.get("/appointments/{appointment_id}", response_model=AppointmentOut)
def get_appointment(appointment_id: int, db: Session = Depends(get_db)):
    from fastapi import HTTPException
    from app.models.models import Appointment
    appt = db.get(Appointment, appointment_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return appt


@router.delete("/appointments/{appointment_id}", response_model=AppointmentOut)
def cancel_appointment(appointment_id: int, db: Session = Depends(get_db)):
    return booking.cancel_appointment(db, appointment_id)


# ----- queue transitions -----
@router.post("/appointments/{appointment_id}/check-in", response_model=AppointmentOut)
def check_in(appointment_id: int, db: Session = Depends(get_db)):
    return booking.check_in(db, appointment_id)


@router.post("/appointments/{appointment_id}/complete", response_model=AppointmentOut)
def complete(appointment_id: int, db: Session = Depends(get_db)):
    return booking.complete_consultation(db, appointment_id)


@router.post("/appointments/{appointment_id}/no-show", response_model=AppointmentOut)
def no_show(appointment_id: int, db: Session = Depends(get_db)):
    return booking.mark_no_show(db, appointment_id)


# ----- prescriptions -----
@router.post("/appointments/{appointment_id}/prescriptions",
             response_model=PrescriptionOut, status_code=201)
def upload_prescription(appointment_id: int, file: UploadFile = File(...),
                        db: Session = Depends(get_db)):
    return booking.add_prescription(db, appointment_id, file)


@router.get("/appointments/{appointment_id}/prescriptions",
            response_model=List[PrescriptionOut])
def list_prescriptions(appointment_id: int, db: Session = Depends(get_db)):
    return booking.list_prescriptions(db, appointment_id)


@router.get("/prescriptions/{prescription_id}/download")
def download_prescription(prescription_id: int, db: Session = Depends(get_db)):
    pres = booking.get_prescription(db, prescription_id)
    return FileResponse(pres.file_path, media_type=pres.content_type,
                        filename=pres.original_filename)

"""Booking + queue + prescription business logic.

All the interesting engineering decisions are here, isolated from the HTTP
layer so they can be unit-tested and explained independently.
"""
import os
import uuid
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.models import (
    Doctor, Slot, Appointment, Prescription, AppointmentStatus
)


# ---------------- Doctors & slots ----------------
def create_doctor(db: Session, data) -> Doctor:
    doctor = Doctor(**data.model_dump())
    db.add(doctor)
    db.commit()
    db.refresh(doctor)
    return doctor


def generate_slots(db: Session, doctor_id: int, start_time, end_time):
    """Slice an availability window into fixed-length slots.

    Slot length = the doctor's consultation_duration, so a 9:00-10:00 window
    for a 15-min doctor yields four slots. We skip any slot whose start already
    exists (idempotent-ish) to avoid the unique-constraint blowing up a batch.
    """
    doctor = db.get(Doctor, doctor_id)
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
    if end_time <= start_time:
        raise HTTPException(status_code=400, detail="end_time must be after start_time")

    step = timedelta(minutes=doctor.consultation_duration)
    created = []
    cursor = start_time
    existing = {
        s.start_time for s in db.scalars(
            select(Slot).where(Slot.doctor_id == doctor_id)
        )
    }
    while cursor + step <= end_time:
        if cursor not in existing:
            slot = Slot(
                doctor_id=doctor_id,
                start_time=cursor,
                end_time=cursor + step,
                is_booked=False,
            )
            db.add(slot)
            created.append(slot)
        cursor += step
    db.commit()
    for s in created:
        db.refresh(s)
    return created


# ---------------- Appointment booking ----------------
def book_appointment(db: Session, slot_id: int, patient_name: str) -> Appointment:
    """Book a slot, guaranteeing no two patients get the same slot.

    Concurrency strategy:
      We lock the slot row (SELECT ... FOR UPDATE) before reading is_booked.
      Two concurrent requests for the same slot serialize on this lock: the
      first flips is_booked=True and commits; the second then sees is_booked
      and is rejected. On Postgres this is a true row lock. The unique
      constraint on appointments.slot_id is a second safety net at the DB level.
      (SQLite has no row locks, so there we rely on the unique constraint + the
      single-writer nature of SQLite — documented in README.)
    """
    is_postgres = settings.database_url.startswith("postgresql")

    stmt = select(Slot).where(Slot.id == slot_id)
    if is_postgres:
        stmt = stmt.with_for_update()
    slot = db.scalars(stmt).first()

    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")
    if slot.is_booked:
        # Lock released on commit/rollback; the loser lands here.
        raise HTTPException(status_code=409, detail="Slot already booked")

    slot.is_booked = True
    appointment = Appointment(
        doctor_id=slot.doctor_id,
        slot_id=slot.id,
        patient_name=patient_name,
        status=AppointmentStatus.BOOKED,
    )
    db.add(appointment)
    try:
        db.commit()
    except Exception:
        db.rollback()
        # Unique-constraint fallback if two requests slipped past (e.g. SQLite).
        raise HTTPException(status_code=409, detail="Slot already booked")
    db.refresh(appointment)
    return appointment


def cancel_appointment(db: Session, appointment_id: int) -> Appointment:
    appt = db.get(Appointment, appointment_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt.status in (AppointmentStatus.COMPLETED, AppointmentStatus.CANCELLED):
        raise HTTPException(status_code=400, detail=f"Cannot cancel a {appt.status.value} appointment")

    appt.status = AppointmentStatus.CANCELLED
    # Free the slot so it can be re-booked.
    if appt.slot:
        appt.slot.is_booked = False
    db.commit()
    db.refresh(appt)
    return appt


# ---------------- Queue ----------------
def check_in(db: Session, appointment_id: int) -> Appointment:
    """Patient checks in and joins the doctor's queue.

    We assign the next queue number for that doctor (max existing + 1). Numbers
    are never reused, so ordering is stable regardless of later cancellations.
    """
    appt = db.get(Appointment, appointment_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt.status != AppointmentStatus.BOOKED:
        raise HTTPException(
            status_code=400,
            detail=f"Only a BOOKED appointment can check in (current: {appt.status.value})",
        )

    last = db.scalars(
        select(Appointment.queue_number)
        .where(Appointment.doctor_id == appt.doctor_id,
               Appointment.queue_number.isnot(None))
        .order_by(Appointment.queue_number.desc())
    ).first()
    appt.queue_number = (last or 0) + 1
    appt.status = AppointmentStatus.IN_QUEUE
    from app.models.models import utcnow
    appt.checked_in_at = utcnow()
    db.commit()
    db.refresh(appt)
    return appt


def get_queue(db: Session, doctor_id: int):
    """Return the live queue with dynamically computed positions + wait times.

    Position is computed from who is still IN_QUEUE (ordered by queue_number),
    so cancellations and no-shows simply drop out and everyone behind moves up
    without any renumbering. Estimated wait = position * consultation_duration.
    """
    doctor = db.get(Doctor, doctor_id)
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    waiting = list(db.scalars(
        select(Appointment)
        .where(Appointment.doctor_id == doctor_id,
               Appointment.status == AppointmentStatus.IN_QUEUE)
        .order_by(Appointment.queue_number.asc())
    ))

    now_serving = db.scalars(
        select(Appointment.id)
        .where(Appointment.doctor_id == doctor_id,
               Appointment.status == AppointmentStatus.IN_CONSULTATION)
    ).first()

    entries = []
    for position, appt in enumerate(waiting, start=1):
        entries.append({
            "appointment_id": appt.id,
            "patient_name": appt.patient_name,
            "queue_number": appt.queue_number,
            "status": appt.status,
            "position": position,
            "estimated_wait_minutes": (position - 1) * doctor.consultation_duration,
        })
    return {"doctor_id": doctor_id, "now_serving": now_serving, "entries": entries}


def call_next(db: Session, doctor_id: int) -> Appointment:
    """Doctor calls the next patient: lowest queue_number still IN_QUEUE.

    If someone is already IN_CONSULTATION we complete them implicitly? No —
    we require the current consult to be completed first, to keep state honest.
    """
    in_consult = db.scalars(
        select(Appointment).where(
            Appointment.doctor_id == doctor_id,
            Appointment.status == AppointmentStatus.IN_CONSULTATION)
    ).first()
    if in_consult:
        raise HTTPException(
            status_code=409,
            detail=f"Appointment {in_consult.id} is still in consultation; complete it first",
        )

    nxt = db.scalars(
        select(Appointment)
        .where(Appointment.doctor_id == doctor_id,
               Appointment.status == AppointmentStatus.IN_QUEUE)
        .order_by(Appointment.queue_number.asc())
    ).first()
    if not nxt:
        raise HTTPException(status_code=404, detail="Queue is empty")

    nxt.status = AppointmentStatus.IN_CONSULTATION
    db.commit()
    db.refresh(nxt)
    return nxt


def complete_consultation(db: Session, appointment_id: int) -> Appointment:
    appt = db.get(Appointment, appointment_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt.status != AppointmentStatus.IN_CONSULTATION:
        raise HTTPException(
            status_code=400,
            detail=f"Only an IN_CONSULTATION appointment can be completed (current: {appt.status.value})",
        )
    appt.status = AppointmentStatus.COMPLETED
    db.commit()
    db.refresh(appt)
    return appt


def mark_no_show(db: Session, appointment_id: int) -> Appointment:
    """Mark a checked-in patient who didn't appear. They drop out of the queue;
    positions behind them recompute automatically (no renumbering)."""
    appt = db.get(Appointment, appointment_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt.status not in (AppointmentStatus.IN_QUEUE, AppointmentStatus.CHECKED_IN):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot mark {appt.status.value} as no-show",
        )
    appt.status = AppointmentStatus.NO_SHOW
    db.commit()
    db.refresh(appt)
    return appt


# ---------------- Prescriptions ----------------
def _validate_upload(filename: str, size_bytes: int, content_type: str):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    allowed = {e.strip().lower() for e in settings.allowed_image_extensions.split(",")}
    if ext not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"File type .{ext} not allowed. Allowed: {sorted(allowed)}",
        )
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if size_bytes > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({size_bytes} bytes). Max {settings.max_upload_size_mb} MB",
        )


def add_prescription(db: Session, appointment_id: int, file) -> Prescription:
    """Attach a prescription image to a VALID, completed appointment.

    Guardrail from the spec: a prescription must not attach to an unrelated or
    invalid appointment. We require the appointment to exist and to be
    COMPLETED (a prescription is written after the consultation).
    """
    appt = db.get(Appointment, appointment_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt.status != AppointmentStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail="Prescriptions can only be attached to a COMPLETED appointment",
        )

    contents = file.file.read()
    _validate_upload(file.filename, len(contents), file.content_type or "")

    os.makedirs(settings.upload_dir, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}_{os.path.basename(file.filename)}"
    path = os.path.join(settings.upload_dir, safe_name)
    with open(path, "wb") as f:
        f.write(contents)

    pres = Prescription(
        appointment_id=appointment_id,
        file_path=path,
        original_filename=file.filename,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(contents),
    )
    db.add(pres)
    db.commit()
    db.refresh(pres)
    return pres


def list_prescriptions(db: Session, appointment_id: int):
    appt = db.get(Appointment, appointment_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return appt.prescriptions


def get_prescription(db: Session, prescription_id: int) -> Prescription:
    pres = db.get(Prescription, prescription_id)
    if not pres:
        raise HTTPException(status_code=404, detail="Prescription not found")
    return pres

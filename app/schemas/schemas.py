"""Pydantic request/response models (the API contract).

Keeping these separate from the ORM models means the database shape and the
wire shape can evolve independently, and we never accidentally leak internal
columns. `from_attributes=True` lets us return ORM objects directly.
"""
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, Field

from app.models.models import AppointmentStatus


# ---------- Doctor ----------
class DoctorCreate(BaseModel):
    name: str
    specialization: str
    clinic: str
    consultation_duration: int = Field(default=15, gt=0, description="Minutes per consultation")


class DoctorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    specialization: str
    clinic: str
    consultation_duration: int


# ---------- Slots ----------
class AvailabilityCreate(BaseModel):
    """Define a block of availability; the service slices it into slots of
    length = doctor.consultation_duration."""
    start_time: datetime
    end_time: datetime


class SlotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    doctor_id: int
    start_time: datetime
    end_time: datetime
    is_booked: bool


# ---------- Appointments ----------
class AppointmentCreate(BaseModel):
    slot_id: int
    patient_name: str


class AppointmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    doctor_id: int
    slot_id: int
    patient_name: str
    status: AppointmentStatus
    queue_number: Optional[int]
    created_at: datetime


# ---------- Queue ----------
class QueueEntry(BaseModel):
    appointment_id: int
    patient_name: str
    queue_number: int
    status: AppointmentStatus
    position: int
    estimated_wait_minutes: int


class QueueView(BaseModel):
    doctor_id: int
    now_serving: Optional[int]  # appointment_id currently IN_CONSULTATION
    entries: List[QueueEntry]


# ---------- Prescriptions ----------
class PrescriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    appointment_id: int
    original_filename: str
    content_type: str
    size_bytes: int
    uploaded_at: datetime

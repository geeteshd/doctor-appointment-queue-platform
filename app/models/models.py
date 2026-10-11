"""SQLAlchemy ORM models — the database design.

Four core entities:
  Doctor            -> a practitioner with a specialization, clinic, and the
                       average consultation duration used for wait estimates.
  Slot              -> a bookable time window belonging to one doctor.
  Appointment       -> a patient's booking against one slot; carries the
                       lifecycle state machine and the queue number.
  Prescription      -> an uploaded file linked to exactly one appointment.

Design notes:
  * A Slot has an is_booked flag. Booking locks the slot row and flips this,
    which is how we guarantee a slot can't be double-booked (see service layer).
  * queue_number is assigned at check-in time, monotonically per doctor, so the
    queue order is stable even when people cancel or are marked no-show. We
    never renumber; position is computed dynamically from who is still waiting.
"""
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, ForeignKey, Enum, UniqueConstraint
)
from sqlalchemy.orm import relationship

from app.core.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class AppointmentStatus(str, enum.Enum):
    BOOKED = "BOOKED"
    CHECKED_IN = "CHECKED_IN"
    IN_QUEUE = "IN_QUEUE"
    IN_CONSULTATION = "IN_CONSULTATION"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    NO_SHOW = "NO_SHOW"


class Doctor(Base):
    __tablename__ = "doctors"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    specialization = Column(String, nullable=False, index=True)
    clinic = Column(String, nullable=False, index=True)
    # Minutes per consultation — drives both slot length and wait-time estimates.
    consultation_duration = Column(Integer, nullable=False, default=15)

    slots = relationship("Slot", back_populates="doctor", cascade="all, delete-orphan")
    appointments = relationship("Appointment", back_populates="doctor")


class Slot(Base):
    __tablename__ = "slots"
    # A doctor cannot have two slots starting at the same instant.
    __table_args__ = (UniqueConstraint("doctor_id", "start_time", name="uq_doctor_slot_start"),)

    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False, index=True)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    is_booked = Column(Boolean, nullable=False, default=False)

    doctor = relationship("Doctor", back_populates="slots")
    appointment = relationship("Appointment", back_populates="slot", uselist=False)


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False, index=True)
    slot_id = Column(Integer, ForeignKey("slots.id"), nullable=False, unique=True)
    patient_name = Column(String, nullable=False)

    status = Column(Enum(AppointmentStatus), nullable=False, default=AppointmentStatus.BOOKED)

    # Assigned at check-in, monotonic per doctor. Null until the patient checks in.
    queue_number = Column(Integer, nullable=True)
    checked_in_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    doctor = relationship("Doctor", back_populates="appointments")
    slot = relationship("Slot", back_populates="appointment")
    prescriptions = relationship(
        "Prescription", back_populates="appointment", cascade="all, delete-orphan"
    )


class Prescription(Base):
    __tablename__ = "prescriptions"

    id = Column(Integer, primary_key=True, index=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=False, index=True)
    file_path = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    content_type = Column(String, nullable=False)
    size_bytes = Column(Integer, nullable=False)
    uploaded_at = Column(DateTime(timezone=True), default=utcnow)

    appointment = relationship("Appointment", back_populates="prescriptions")

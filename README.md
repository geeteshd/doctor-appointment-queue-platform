# Doctor Appointment & Queue Management Platform

A backend platform where patients can discover doctors, book appointments, join
a consultation queue, and upload prescription images. Built with **FastAPI**,
**SQLAlchemy**, and **PostgreSQL** (SQLite supported for zero-config local runs).

No frontend — all functionality is exposed as REST APIs with interactive
Swagger docs at **`/docs`**.

---

## Architecture

```
app/
  main.py              FastAPI app, router wiring, table creation
  core/
    config.py          Typed settings (DB URL, upload rules) from env
    database.py        Engine + session, get_db() dependency
  models/
    models.py          SQLAlchemy ORM models (the DB design)
  schemas/
    schemas.py         Pydantic request/response models (the API contract)
  services/
    booking.py         All business logic (booking, queue, prescriptions)
  routers/
    doctors.py         Doctor CRUD, availability, slot search
    appointments.py    Booking lifecycle + prescription endpoints
    queue.py           Queue view + call-next
tests/
  test_flow.py         End-to-end tests of the full flow + edge cases
```

**Layering:** routers (HTTP) → services (business logic) → models (persistence).
The service layer holds every important decision so it is testable and
explainable independently of the web framework.

## Database design

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `doctors` | A practitioner | `specialization`, `clinic`, `consultation_duration` |
| `slots` | A bookable time window for one doctor | `start_time`, `end_time`, `is_booked` |
| `appointments` | A patient booking against one slot | `status`, `queue_number`, `checked_in_at` |
| `prescriptions` | A file linked to one appointment | `file_path`, `size_bytes`, `content_type` |

Relationships: a doctor has many slots and appointments; a slot has at most one
appointment (`appointments.slot_id` is **unique**); an appointment has many
prescriptions.

### Appointment state machine
```
BOOKED ──check-in──▶ IN_QUEUE ──call-next──▶ IN_CONSULTATION ──complete──▶ COMPLETED
   │                     │
   └──cancel──▶ CANCELLED └──no-show──▶ NO_SHOW
```

## Key technical decisions

1. **No double-booking.** Booking locks the slot row with `SELECT … FOR UPDATE`
   (PostgreSQL), checks `is_booked`, and flips it inside one transaction. Two
   concurrent requests for the same slot serialize on the lock; the loser gets
   **409 Conflict**. A `UNIQUE` constraint on `appointments.slot_id` is a second
   safety net (and the primary guard on SQLite, which has no row locks).

2. **Queue integrity.** `queue_number` is assigned at check-in, monotonically
   per doctor, and **never reused**. The live queue **position** is computed
   dynamically from who is still `IN_QUEUE` (ordered by `queue_number`), so a
   cancellation or no-show simply drops out and everyone behind moves up — no
   renumbering, order never breaks.

3. **Estimated wait time** = `(position - 1) × consultation_duration`. The
   person at the front waits ~0; each place back adds one average consult.

4. **Prescription validity.** A prescription can only attach to a **COMPLETED**
   appointment (it's written after the consult). File **type** and **size** are
   validated against configurable limits before storage; files are saved with a
   UUID-prefixed name and their metadata recorded in the DB.

## Tech stack
FastAPI · SQLAlchemy 2.0 · PostgreSQL 16 · Pydantic v2 · Docker · pytest

## Assumptions
- Authentication/authorization is out of scope for this assignment; "authorized
  users" is modelled structurally (ownership via appointment linkage) rather
  than with real auth. A production build would add OAuth2/JWT.
- One active appointment per slot. Cancelling frees the slot for rebooking.
- Times are handled in UTC.
- Prescriptions are stored on local disk (volume-mounted); S3 is the production
  path and is noted in the code.

# Instructions — Setup, Run, and Test

## Option A — Run with Docker (recommended)

Requires Docker + Docker Compose.

```bash
docker compose up --build
```

- API:     http://localhost:8000
- Swagger:  http://localhost:8000/docs
- Health:   http://localhost:8000/health

This starts PostgreSQL and the API together; tables are created automatically
on startup.

## Option B — Run locally without Docker (SQLite)

Requires Python 3.11+.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Use SQLite so no database server is needed:
export DATABASE_URL="sqlite:///./clinic.db"        # Windows: set DATABASE_URL=...

uvicorn app.main:app --reload
```

Then open http://localhost:8000/docs.

## Running the tests

```bash
pip install pytest
pytest -q
```

The suite (`tests/test_flow.py`) covers slot generation, search, double-booking
prevention, wait-time estimates, queue integrity on no-show, the call-next
guard, and prescription validity rules.

## Testing the full flow by hand (curl)

```bash
# 1. Create a doctor (15-min consultations)
curl -s -X POST localhost:8000/doctors -H "Content-Type: application/json" \
  -d '{"name":"Dr. Rao","specialization":"Cardiology","clinic":"Apollo","consultation_duration":15}'

# 2. Add availability (9:00–10:00 -> four 15-min slots)
curl -s -X POST localhost:8000/doctors/1/availability -H "Content-Type: application/json" \
  -d '{"start_time":"2026-10-20T09:00:00","end_time":"2026-10-20T10:00:00"}'

# 3. Search doctors
curl -s "localhost:8000/doctors?specialization=cardio"

# 4. See free slots
curl -s "localhost:8000/doctors/1/slots?date=2026-10-20"

# 5. Book a slot
curl -s -X POST localhost:8000/appointments -H "Content-Type: application/json" \
  -d '{"slot_id":1,"patient_name":"Alice"}'

# 6. Check in (joins the queue)
curl -s -X POST localhost:8000/appointments/1/check-in

# 7. View the live queue (positions + estimated waits)
curl -s localhost:8000/doctors/1/queue

# 8. Doctor calls next, then completes
curl -s -X POST localhost:8000/doctors/1/queue/next
curl -s -X POST localhost:8000/appointments/1/complete

# 9. Upload a prescription (only after COMPLETED)
curl -s -X POST localhost:8000/appointments/1/prescriptions -F "file=@rx.png"

# 10. List / download prescriptions
curl -s localhost:8000/appointments/1/prescriptions
curl -s localhost:8000/prescriptions/1/download --output downloaded_rx.png
```

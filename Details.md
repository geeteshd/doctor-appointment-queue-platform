# Details — Approach, AI Usage, Testing, and Challenges

## Approach

I treated this as a small but production-shaped backend and split it into three
layers so each concern is isolated and explainable:

- **Routers** translate HTTP to function calls and nothing more.
- **Services** (`app/services/booking.py`) hold *all* the real logic — booking,
  the queue state machine, prescription rules. This is deliberate: the
  interesting decisions live in one place that can be unit-tested without a web
  server.
- **Models / Schemas** separate the database shape from the API contract.

I built the data model first (doctor → slots → appointments → prescriptions),
then the booking path, then the queue, then prescriptions, writing an
end-to-end test as I went so every feature was proven before moving on.

### How the three hardest requirements were solved

**1. Preventing double-booking (concurrency).**
When two patients race for the same slot, correctness can't rely on an
application-level `if not booked`. I lock the slot row with
`SELECT … FOR UPDATE` before reading `is_booked`, so concurrent transactions
serialize: the first books and commits, the second then sees `is_booked=True`
and is rejected with 409. A `UNIQUE` constraint on `appointments.slot_id`
backs this at the schema level (and is the primary guard under SQLite, which
lacks row locks).

**2. Queue that survives cancellations / no-shows.**
Rather than storing a mutable "position" that must be rewritten whenever someone
leaves, I store an immutable `queue_number` assigned at check-in and compute
position **on read** from the set of patients still `IN_QUEUE`. A no-show just
changes a status; the next `GET /queue` naturally shows everyone behind moved up
one place, with no renumbering and no way for the order to corrupt.

**3. Estimated wait time.**
`(position - 1) × doctor.consultation_duration` — simple, explainable, and uses
the doctor's own average consult length.

## How AI tools were used

I used an AI assistant (Claude) as a pair-programming tool to accelerate
scaffolding and review:
- Generating the initial FastAPI/SQLAlchemy project structure and boilerplate.
- Drafting the end-to-end test cases, especially the edge cases (double-book
  race, no-show reordering, prescription-before-completion).
- Reviewing the concurrency approach and the state-machine transitions.

Every design decision — the locking strategy, the dynamic-position queue model,
the prescription validity rule — I understand and can explain and defend; the AI
accelerated typing and review, it did not make the architectural calls for me.

## How to test the complete functional flow

See `Instructions.md` for both the automated suite (`pytest -q`) and a
copy-paste curl walkthrough of the entire lifecycle. The automated tests assert
the non-obvious behaviours directly:
- `test_double_booking_prevented` — second booking of a slot returns 409.
- `test_queue_wait_estimates` — waits compute to 0 / 15 / 30 for three patients.
- `test_queue_integrity_on_no_show` — removing the middle patient keeps order.
- `test_call_next_requires_completing_current` — can't pull two into consult.
- `test_prescription_requires_completed_appointment` — plus bad-filetype reject.

## Challenges & how I handled them

- **Choosing a concurrency model that's demonstrable on both Postgres and
  SQLite.** Row locks don't exist in SQLite, so I made `FOR UPDATE` conditional
  on the backend and leaned on the unique constraint as the portable guarantee,
  documenting the difference rather than hiding it.
- **Keeping the queue correct without fragile renumbering.** Computing position
  on read instead of storing it removed a whole class of ordering bugs.
- **Scope control.** I deliberately left authentication out (noted as an
  assumption) to focus the time on the core booking/queue/prescription logic the
  assignment actually grades.

## Possible extensions (not implemented)
- Real auth (OAuth2/JWT) and per-role authorization on prescription access.
- S3-backed prescription storage.
- Alembic migrations instead of `create_all`.
- Rate limiting and idempotency keys on booking.

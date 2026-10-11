"""End-to-end tests covering the full functional flow and the key edge cases
the assignment calls out: double-booking, queue integrity on no-show, wait-time
estimates, and prescription validity rules."""


def _make_doctor_with_slots(client, duration=15):
    d = client.post("/doctors", json={
        "name": "Dr. Rao", "specialization": "Cardiology",
        "clinic": "Apollo", "consultation_duration": duration}).json()
    slots = client.post(f"/doctors/{d['id']}/availability", json={
        "start_time": "2026-10-20T09:00:00",
        "end_time": "2026-10-20T10:00:00"}).json()
    return d, slots


def test_slot_generation_and_search(client):
    d, slots = _make_doctor_with_slots(client)
    assert len(slots) == 4  # 60 min / 15 min
    assert len(client.get("/doctors", params={"specialization": "cardio"}).json()) == 1
    assert len(client.get("/doctors", params={"clinic": "nope"}).json()) == 0


def test_double_booking_prevented(client):
    d, slots = _make_doctor_with_slots(client)
    first = client.post("/appointments", json={"slot_id": slots[0]["id"], "patient_name": "Alice"})
    assert first.status_code == 201
    dup = client.post("/appointments", json={"slot_id": slots[0]["id"], "patient_name": "Eve"})
    assert dup.status_code == 409


def test_queue_wait_estimates(client):
    d, slots = _make_doctor_with_slots(client)
    appts = [client.post("/appointments",
             json={"slot_id": slots[i]["id"], "patient_name": n}).json()
             for i, n in enumerate(["Alice", "Bob", "Carol"])]
    for a in appts:
        client.post(f"/appointments/{a['id']}/check-in")
    q = client.get(f"/doctors/{d['id']}/queue").json()
    waits = [e["estimated_wait_minutes"] for e in q["entries"]]
    assert waits == [0, 15, 30]


def test_queue_integrity_on_no_show(client):
    d, slots = _make_doctor_with_slots(client)
    appts = [client.post("/appointments",
             json={"slot_id": slots[i]["id"], "patient_name": n}).json()
             for i, n in enumerate(["Alice", "Bob", "Carol"])]
    for a in appts:
        client.post(f"/appointments/{a['id']}/check-in")
    client.post(f"/appointments/{appts[1]['id']}/no-show")  # Bob drops
    q = client.get(f"/doctors/{d['id']}/queue").json()
    assert [e["patient_name"] for e in q["entries"]] == ["Alice", "Carol"]
    assert [e["position"] for e in q["entries"]] == [1, 2]


def test_call_next_requires_completing_current(client):
    d, slots = _make_doctor_with_slots(client)
    a = client.post("/appointments", json={"slot_id": slots[0]["id"], "patient_name": "Alice"}).json()
    b = client.post("/appointments", json={"slot_id": slots[1]["id"], "patient_name": "Bob"}).json()
    client.post(f"/appointments/{a['id']}/check-in")
    client.post(f"/appointments/{b['id']}/check-in")
    client.post(f"/doctors/{d['id']}/queue/next")  # Alice -> consultation
    blocked = client.post(f"/doctors/{d['id']}/queue/next")  # Bob blocked
    assert blocked.status_code == 409
    client.post(f"/appointments/{a['id']}/complete")
    ok = client.post(f"/doctors/{d['id']}/queue/next")
    assert ok.status_code == 200 and ok.json()["patient_name"] == "Bob"


def test_prescription_requires_completed_appointment(client):
    d, slots = _make_doctor_with_slots(client)
    a = client.post("/appointments", json={"slot_id": slots[0]["id"], "patient_name": "Alice"}).json()
    early = client.post(f"/appointments/{a['id']}/prescriptions",
                        files={"file": ("rx.png", b"data", "image/png")})
    assert early.status_code == 400
    client.post(f"/appointments/{a['id']}/check-in")
    client.post(f"/doctors/{d['id']}/queue/next")
    client.post(f"/appointments/{a['id']}/complete")
    ok = client.post(f"/appointments/{a['id']}/prescriptions",
                     files={"file": ("rx.png", b"data", "image/png")})
    assert ok.status_code == 201
    bad = client.post(f"/appointments/{a['id']}/prescriptions",
                      files={"file": ("rx.exe", b"MZ", "application/x-dosexec")})
    assert bad.status_code == 400

"""Tests for event capacity enforcement during registration (Issue #12).

Acceptance criteria verified:
- Reject new registrations when capacity is reached
- Enforce the rule on the backend
- Avoid overbooking for near-simultaneous requests
- Return a clear capacity-full response (409 Conflict with "This event is full")
- Add tests for full and nearly full events
"""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from app.auth import get_current_user
from app.database import Base, get_db
from app.models import Event, EventRegistration, User
from app.routes import events as events_module

engine = create_engine(
    "sqlite+pysqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

_CURRENT = {"user": None}
_USERS_CACHE = {}


def _override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


def _override_get_current_user(authorization: str = Header(default="")):
    if authorization and authorization.startswith("Bearer user:"):
        username = authorization.split("Bearer user:")[1].strip()
        if username in _USERS_CACHE:
            return _USERS_CACHE[username]
    if _CURRENT["user"] is not None:
        return _CURRENT["user"]
    raise HTTPException(status_code=401, detail="Not authenticated")


app = FastAPI()
app.include_router(events_module.router)
app.dependency_overrides[get_db] = _override_get_db
app.dependency_overrides[get_current_user] = _override_get_current_user
client = TestClient(app)



@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    _CURRENT["user"] = None
    _USERS_CACHE.clear()
    yield


def _seed(capacity=2, num_registered=0):
    """Seed an event with organizer and available attendees.

    num_registered attendees are registered upon setup.
    """
    db = TestSession()
    organizer = User(username="organizer", email="organizer@ex.com", hashed_password="x")
    db.add(organizer)
    db.flush()

    event = Event(
        title="Hackathon Meetup",
        description="A cool tech meetup",
        location="Hall A",
        start_time=datetime(2030, 1, 1, 10, tzinfo=timezone.utc),
        end_time=datetime(2030, 1, 1, 12, tzinfo=timezone.utc),
        capacity=capacity,
        organizer_id=organizer.id,
    )
    db.add(event)
    db.flush()

    users = {}
    for i in range(1, 15):
        name = f"user_{i}"
        u = User(username=name, email=f"{name}@ex.com", hashed_password="x")
        db.add(u)
        users[name] = u
    db.flush()

    for i in range(1, num_registered + 1):
        name = f"user_{i}"
        db.add(EventRegistration(event_id=event.id, user_id=users[name].id))

    db.commit()

    _USERS_CACHE.clear()
    _USERS_CACHE.update(users)
    _USERS_CACHE["organizer"] = organizer

    ids = {name: u.id for name, u in users.items()}
    ids["organizer"] = organizer.id
    ids["event"] = event.id
    db.close()
    return ids



def _as(ids, name):
    db = TestSession()
    _CURRENT["user"] = db.get(User, ids[name])
    db.close()


def _registration_count(event_id):
    db = TestSession()
    count = db.scalar(
        select(func.count()).select_from(EventRegistration).where(EventRegistration.event_id == event_id)
    )
    db.close()
    return count


# --- Single Registration Tests ---

def test_register_for_event_success_when_spots_available():
    ids = _seed(capacity=2, num_registered=0)
    _as(ids, "user_1")

    resp = client.post(f"/events/{ids['event']}/register")

    assert resp.status_code == 201
    assert resp.json() == {"message": "Registration successful"}
    assert _registration_count(ids["event"]) == 1


def test_register_for_event_rejected_when_capacity_reached():
    ids = _seed(capacity=1, num_registered=1)
    _as(ids, "user_2")

    resp = client.post(f"/events/{ids['event']}/register")

    assert resp.status_code == 409
    assert resp.json()["detail"] == "This event is full"
    assert _registration_count(ids["event"]) == 1


def test_nearly_full_event_fills_to_capacity_then_rejects():
    """Event with capacity 3 and 2 already registered (nearly full).

    Next registration should succeed, filling the event to capacity.
    Subsequent registration attempts must be rejected.
    """
    ids = _seed(capacity=3, num_registered=2)

    # Claim the last remaining spot
    _as(ids, "user_3")
    resp_fill = client.post(f"/events/{ids['event']}/register")
    assert resp_fill.status_code == 201
    assert resp_fill.json() == {"message": "Registration successful"}
    assert _registration_count(ids["event"]) == 3

    # Attempt registration now that event is full
    _as(ids, "user_4")
    resp_full = client.post(f"/events/{ids['event']}/register")
    assert resp_full.status_code == 409
    assert resp_full.json()["detail"] == "This event is full"

    # Another user also rejected
    _as(ids, "user_5")
    resp_full_again = client.post(f"/events/{ids['event']}/register")
    assert resp_full_again.status_code == 409
    assert resp_full_again.json()["detail"] == "This event is full"

    # Total registrations remain at exact capacity
    assert _registration_count(ids["event"]) == 3


# --- Concurrency / Overbooking Prevention Tests ---

def test_near_simultaneous_registrations_avoid_overbooking():
    """Near-simultaneous requests attempting to register for a capacity-2 event.

    10 users attempt to register at the same time. Exactly 2 must succeed,
    the remaining 8 must be rejected, and overbooking must never occur.
    """
    ids = _seed(capacity=2, num_registered=0)
    event_id = ids["event"]
    candidate_names = [f"user_{i}" for i in range(1, 11)]

    def attempt_registration(name):
        return client.post(
            f"/events/{event_id}/register",
            headers={"Authorization": f"Bearer user:{name}"},
        )

    with ThreadPoolExecutor(max_workers=10) as executor:
        responses = list(executor.map(attempt_registration, candidate_names))

    statuses = [r.status_code for r in responses]
    successes = statuses.count(201)
    conflicts = statuses.count(409)

    assert successes == 2, f"Expected 2 successful registrations, got {successes}"
    assert conflicts == 8, f"Expected 8 capacity-full rejections, got {conflicts}"
    assert _registration_count(event_id) == 2, "Attendee count must not exceed capacity"

    for r in responses:
        if r.status_code == 409:
            assert r.json()["detail"] == "This event is full"


def test_concurrent_registrations_on_nearly_full_event():
    """Event with capacity 4, already 3 spots filled (1 spot remaining).

    8 users concurrently fight for the single remaining spot.
    Exactly 1 succeeds, 7 fail with capacity-full response.
    """
    ids = _seed(capacity=4, num_registered=3)
    event_id = ids["event"]
    candidate_names = [f"user_{i}" for i in range(4, 12)]

    def attempt_registration(name):
        return client.post(
            f"/events/{event_id}/register",
            headers={"Authorization": f"Bearer user:{name}"},
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        responses = list(executor.map(attempt_registration, candidate_names))

    statuses = [r.status_code for r in responses]
    assert statuses.count(201) == 1
    assert statuses.count(409) == 7
    assert _registration_count(event_id) == 4



# --- Edge Cases & Validation Tests ---

def test_duplicate_registration_rejected():
    ids = _seed(capacity=3, num_registered=0)
    _as(ids, "user_1")

    # First registration succeeds
    resp1 = client.post(f"/events/{ids['event']}/register")
    assert resp1.status_code == 201

    # Second registration by the same user is rejected
    resp2 = client.post(f"/events/{ids['event']}/register")
    assert resp2.status_code == 409
    assert resp2.json()["detail"] == "You are already registered for this event"
    assert _registration_count(ids["event"]) == 1


def test_registration_succeeds_after_cancellation_frees_spot():
    ids = _seed(capacity=1, num_registered=1)  # user_1 is registered, event is full

    # user_2 cannot register because event is full
    _as(ids, "user_2")
    resp_blocked = client.post(f"/events/{ids['event']}/register")
    assert resp_blocked.status_code == 409
    assert resp_blocked.json()["detail"] == "This event is full"

    # user_1 cancels spot
    _as(ids, "user_1")
    resp_cancel = client.delete(f"/events/{ids['event']}/register")
    assert resp_cancel.status_code == 204
    assert _registration_count(ids["event"]) == 0

    # user_2 can now register
    _as(ids, "user_2")
    resp_success = client.post(f"/events/{ids['event']}/register")
    assert resp_success.status_code == 201
    assert _registration_count(ids["event"]) == 1


def test_registration_unknown_event_returns_404():
    ids = _seed()
    _as(ids, "user_1")
    resp = client.post("/events/99999/register")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Event not found"


def test_unauthenticated_registration_rejected():
    ids = _seed(capacity=2, num_registered=0)
    _CURRENT["user"] = None
    resp = client.post(f"/events/{ids['event']}/register")
    assert resp.status_code == 401


def test_event_public_payload_reflects_attendee_count_and_capacity():
    ids = _seed(capacity=5, num_registered=3)
    resp = client.get(f"/events/{ids['event']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["capacity"] == 5
    assert data["attendee_count"] == 3

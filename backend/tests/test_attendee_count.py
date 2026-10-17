"""Tests for attendee count on event details (Issue #11).

Acceptance criteria verified:
- Display the count on event details
- Derive the count from valid registrations
- Update after registration and cancellation
- Do not expose attendee private information
"""

import os
from datetime import datetime, timezone, timedelta

import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
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


@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    db = TestSession()
    db.query(EventRegistration).delete()
    db.query(Event).delete()
    db.query(User).delete()
    db.commit()

    organizer = User(
        username="organizer",
        email="organizer@example.com",
        hashed_password="pw-hash-organizer",
    )
    user_alice = User(
        username="alice",
        email="alice@example.com",
        hashed_password="pw-hash-alice-secret",
    )
    user_bob = User(
        username="bob",
        email="bob@example.com",
        hashed_password="pw-hash-bob-secret",
    )
    db.add_all([organizer, user_alice, user_bob])
    db.commit()

    _USERS_CACHE["organizer"] = organizer
    _USERS_CACHE["alice"] = user_alice
    _USERS_CACHE["bob"] = user_bob
    _CURRENT["user"] = None
    db.close()
    yield
    Base.metadata.drop_all(bind=engine)


def test_attendee_count_zero_on_new_event():
    client = TestClient(app)
    _CURRENT["user"] = _USERS_CACHE["organizer"]

    start = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    end = (datetime.now(timezone.utc) + timedelta(days=2, hours=2)).isoformat()

    resp = client.post(
        "/events",
        json={
            "title": "Clean Tech Summit",
            "description": "Discussing green tech",
            "location": "Auditorium A",
            "start_time": start,
            "end_time": end,
            "capacity": 50,
        },
    )
    assert resp.status_code == 201
    event_id = resp.json()["id"]

    # Verify event details has attendee_count == 0
    get_resp = client.get(f"/events/{event_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["attendee_count"] == 0
    assert data["capacity"] == 50


def test_attendee_count_increments_after_registration_and_decrements_after_cancellation():
    client = TestClient(app)
    db = TestSession()
    org = db.query(User).filter_by(username="organizer").first()
    now = datetime.now(timezone.utc)
    ev = Event(
        title="AI Workshop",
        description="Hands-on LLM engineering",
        location="Lab 101",
        start_time=now + timedelta(days=1),
        end_time=now + timedelta(days=1, hours=3),
        capacity=20,
        organizer_id=org.id,
    )
    db.add(ev)
    db.commit()
    event_id = ev.id
    db.close()

    # Initial count is 0
    res = client.get(f"/events/{event_id}")
    assert res.status_code == 200
    assert res.json()["attendee_count"] == 0

    # Alice registers
    _CURRENT["user"] = _USERS_CACHE["alice"]
    reg_alice = client.post(f"/events/{event_id}/register")
    assert reg_alice.status_code == 201

    # Count is now 1
    res = client.get(f"/events/{event_id}")
    assert res.json()["attendee_count"] == 1

    # Bob registers
    _CURRENT["user"] = _USERS_CACHE["bob"]
    reg_bob = client.post(f"/events/{event_id}/register")
    assert reg_bob.status_code == 201

    # Count is now 2
    res = client.get(f"/events/{event_id}")
    assert res.json()["attendee_count"] == 2

    # Alice cancels registration
    _CURRENT["user"] = _USERS_CACHE["alice"]
    cancel_alice = client.delete(f"/events/{event_id}/register")
    assert cancel_alice.status_code == 204

    # Count decrements back to 1
    res = client.get(f"/events/{event_id}")
    assert res.json()["attendee_count"] == 1

    # Bob cancels registration
    _CURRENT["user"] = _USERS_CACHE["bob"]
    cancel_bob = client.delete(f"/events/{event_id}/register")
    assert cancel_bob.status_code == 204

    # Count decrements back to 0
    res = client.get(f"/events/{event_id}")
    assert res.json()["attendee_count"] == 0


def test_does_not_expose_attendee_private_information():
    client = TestClient(app)
    db = TestSession()
    org = db.query(User).filter_by(username="organizer").first()
    alice = db.query(User).filter_by(username="alice").first()
    now = datetime.now(timezone.utc)
    ev = Event(
        title="Privacy Gathering",
        description="Private meeting",
        location="Room 302",
        start_time=now + timedelta(days=3),
        end_time=now + timedelta(days=3, hours=2),
        capacity=10,
        organizer_id=org.id,
    )
    db.add(ev)
    db.commit()
    db.add(EventRegistration(event_id=ev.id, user_id=alice.id))
    db.commit()
    event_id = ev.id
    db.close()

    res = client.get(f"/events/{event_id}")
    assert res.status_code == 200
    data = res.json()

    # Verify attendee count is present
    assert data["attendee_count"] == 1

    # Ensure no attendee list or private attendee info (emails, passwords) is leaked
    assert "registrations" not in data
    assert "attendees" not in data
    assert "alice@example.com" not in str(data)
    assert "pw-hash-alice-secret" not in str(data)
    assert "hashed_password" not in str(data)

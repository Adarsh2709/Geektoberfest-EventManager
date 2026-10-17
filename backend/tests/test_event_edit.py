import os

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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

# The authenticated user is swapped per test through this holder.
_CURRENT = {"user": None}


def _override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app = FastAPI()
app.include_router(events_module.router)
app.dependency_overrides[get_db] = _override_get_db
app.dependency_overrides[get_current_user] = lambda: _CURRENT["user"]
client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    _CURRENT["user"] = None
    yield


def _valid_body(**overrides):
    body = {
        "title": "Launch",
        "description": "desc",
        "location": "Hall",
        "start_time": "2030-01-01T10:00:00Z",
        "end_time": "2030-01-01T12:00:00Z",
        "capacity": 10,
    }
    body.update(overrides)
    return body


def _seed():
    """Two organizers, each with one event. Carol is registered for Alice's event."""
    db = TestSession()
    alice_org = User(username="alice", email="alice@ex.com", hashed_password="x")
    bob_org = User(username="bob", email="bob@ex.com", hashed_password="x")
    attendee = User(username="carol", email="carol@ex.com", hashed_password="x")
    db.add_all([alice_org, bob_org, attendee])
    db.flush()
    alices_event = Event(
        title="Alice's", description="d", location="L",
        start_time=datetime(2030, 1, 1, 10, tzinfo=timezone.utc),
        end_time=datetime(2030, 1, 1, 12, tzinfo=timezone.utc),
        capacity=5, organizer_id=alice_org.id,
    )
    bobs_event = Event(
        title="Bob's", description="d", location="L",
        start_time=datetime(2030, 1, 1, 10, tzinfo=timezone.utc),
        end_time=datetime(2030, 1, 1, 12, tzinfo=timezone.utc),
        capacity=5, organizer_id=bob_org.id,
    )
    db.add_all([alices_event, bobs_event])
    db.flush()
    db.add(EventRegistration(event_id=alices_event.id, user_id=attendee.id))
    db.commit()
    ids = {
        "alice": alice_org.id, "bob": bob_org.id, "carol": attendee.id,
        "alices_event": alices_event.id, "bobs_event": bobs_event.id,
    }
    db.close()
    return ids


def _as(ids, name):
    db = TestSession()
    _CURRENT["user"] = db.get(User, ids[name])
    db.close()


def _stored(event_id):
    db = TestSession()
    event = db.get(Event, event_id)
    snapshot = {
        "title": event.title, "capacity": event.capacity,
        "start_time": event.start_time, "end_time": event.end_time,
    }
    snapshot["registrations"] = db.scalars(
        select(EventRegistration.user_id).where(EventRegistration.event_id == event_id)
    ).all()
    db.close()
    return snapshot


# --- authorization -----------------------------------------------------------

def test_organizer_can_edit_own_event():
    ids = _seed()
    _as(ids, "alice")

    resp = client.put(f"/events/{ids['alices_event']}", json=_valid_body(title="Renamed", capacity=8))

    assert resp.status_code == 200
    assert resp.json()["title"] == "Renamed"
    assert resp.json()["capacity"] == 8
    assert _stored(ids["alices_event"])["title"] == "Renamed"


def test_non_organizer_cannot_edit_event():
    ids = _seed()
    _as(ids, "bob")

    resp = client.put(f"/events/{ids['alices_event']}", json=_valid_body(title="Hijacked"))

    assert resp.status_code == 403
    assert _stored(ids["alices_event"])["title"] == "Alice's"


def test_changing_event_id_does_not_bypass_ownership():
    """Alice owns her event. Sending her request to Bob's event ID must not let her edit it."""
    ids = _seed()
    _as(ids, "alice")

    resp = client.put(f"/events/{ids['bobs_event']}", json=_valid_body(title="Hijacked"))

    assert resp.status_code == 403
    assert _stored(ids["bobs_event"])["title"] == "Bob's"


def test_attendee_cannot_edit_event_they_are_registered_for():
    ids = _seed()
    _as(ids, "carol")

    resp = client.put(f"/events/{ids['alices_event']}", json=_valid_body(title="Hijacked"))

    assert resp.status_code == 403
    assert _stored(ids["alices_event"])["title"] == "Alice's"


def test_editing_missing_event_returns_404():
    ids = _seed()
    _as(ids, "alice")

    resp = client.put("/events/99999", json=_valid_body())

    assert resp.status_code == 404


# --- validation uses the creation rules --------------------------------------

def test_end_before_start_is_rejected():
    ids = _seed()
    _as(ids, "alice")
    before = _stored(ids["alices_event"])

    resp = client.put(f"/events/{ids['alices_event']}", json=_valid_body(
        start_time="2030-01-01T12:00:00Z", end_time="2030-01-01T10:00:00Z",
    ))

    assert resp.status_code == 422
    assert _stored(ids["alices_event"]) == before


@pytest.mark.parametrize("capacity", [0, -1, 100001])
def test_capacity_outside_creation_bounds_is_rejected(capacity):
    ids = _seed()
    _as(ids, "alice")
    before = _stored(ids["alices_event"])

    resp = client.put(f"/events/{ids['alices_event']}", json=_valid_body(capacity=capacity))

    assert resp.status_code == 422
    assert _stored(ids["alices_event"]) == before


def test_empty_title_is_rejected():
    ids = _seed()
    _as(ids, "alice")

    resp = client.put(f"/events/{ids['alices_event']}", json=_valid_body(title="x"))

    assert resp.status_code == 422


# --- registration consistency ------------------------------------------------

def test_capacity_cannot_drop_below_current_registrations():
    ids = _seed()
    db = TestSession()
    db.add(EventRegistration(event_id=ids["alices_event"], user_id=ids["bob"]))
    db.commit()
    db.close()
    _as(ids, "alice")
    before = _stored(ids["alices_event"])
    assert len(before["registrations"]) == 2

    resp = client.put(f"/events/{ids['alices_event']}", json=_valid_body(capacity=1))

    assert resp.status_code == 400
    assert _stored(ids["alices_event"]) == before


def test_capacity_equal_to_registrations_is_allowed_with_multiple_attendees():
    ids = _seed()
    db = TestSession()
    db.add(EventRegistration(event_id=ids["alices_event"], user_id=ids["bob"]))
    db.commit()
    db.close()
    _as(ids, "alice")

    resp = client.put(f"/events/{ids['alices_event']}", json=_valid_body(capacity=2))

    assert resp.status_code == 200
    assert resp.json()["attendee_count"] == 2


def test_edit_keeps_existing_registrations():
    ids = _seed()
    _as(ids, "alice")
    before = _stored(ids["alices_event"])

    resp = client.put(f"/events/{ids['alices_event']}", json=_valid_body(title="Renamed", capacity=1))

    assert resp.status_code == 200
    assert resp.json()["attendee_count"] == 1
    assert _stored(ids["alices_event"])["registrations"] == before["registrations"]


def test_capacity_equal_to_registrations_is_allowed():
    ids = _seed()
    _as(ids, "alice")

    resp = client.put(f"/events/{ids['alices_event']}", json=_valid_body(capacity=1))

    assert resp.status_code == 200
    assert resp.json()["capacity"] == 1

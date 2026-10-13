import os

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from datetime import datetime, timezone, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
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


def _seed_event(capacity=5):
    db = TestSession()
    organizer = User(username="organizer", email="organizer@ex.com", hashed_password="pw")
    alice = User(username="alice", email="alice@ex.com", hashed_password="pw")
    bob = User(username="bob", email="bob@ex.com", hashed_password="pw")
    db.add_all([organizer, alice, bob])
    db.commit()

    now = datetime.now(timezone.utc)
    ev = Event(
        title="Tech Conference",
        description="Annual conference",
        location="Hall A",
        start_time=now + timedelta(days=2),
        end_time=now + timedelta(days=3),
        capacity=capacity,
        organizer_id=organizer.id,
    )
    db.add(ev)
    db.commit()

    event_id = ev.id
    alice_id = alice.id
    bob_id = bob.id
    db.close()
    return event_id, alice_id, bob_id


def test_first_registration_succeeds():
    event_id, alice_id, _ = _seed_event()
    db = TestSession()
    alice = db.get(User, alice_id)
    _CURRENT["user"] = alice

    resp = client.post(f"/events/{event_id}/register")
    assert resp.status_code == 201
    assert resp.json()["message"] == "Registration successful"

    # Verify 1 record exists in DB
    count = db.scalar(select(func.count()).select_from(EventRegistration).where(
        EventRegistration.event_id == event_id, EventRegistration.user_id == alice_id
    ))
    assert count == 1
    db.close()


def test_repeated_registration_returns_409_conflict():
    event_id, alice_id, _ = _seed_event()
    db = TestSession()
    alice = db.get(User, alice_id)
    _CURRENT["user"] = alice

    # First attempt succeeds
    resp1 = client.post(f"/events/{event_id}/register")
    assert resp1.status_code == 201

    # Second attempt returns 409 with helpful error
    resp2 = client.post(f"/events/{event_id}/register")
    assert resp2.status_code == 409
    assert resp2.json()["detail"] == "You are already registered for this event"

    # Third attempt also returns 409
    resp3 = client.post(f"/events/{event_id}/register")
    assert resp3.status_code == 409

    # Verify only 1 registration record was persisted
    count = db.scalar(select(func.count()).select_from(EventRegistration).where(
        EventRegistration.event_id == event_id, EventRegistration.user_id == alice_id
    ))
    assert count == 1
    db.close()


def test_different_users_can_register_for_same_event():
    event_id, alice_id, bob_id = _seed_event(capacity=5)
    db = TestSession()
    alice = db.get(User, alice_id)
    bob = db.get(User, bob_id)

    _CURRENT["user"] = alice
    resp_alice = client.post(f"/events/{event_id}/register")
    assert resp_alice.status_code == 201

    _CURRENT["user"] = bob
    resp_bob = client.post(f"/events/{event_id}/register")
    assert resp_bob.status_code == 201

    total_count = db.scalar(select(func.count()).select_from(EventRegistration).where(
        EventRegistration.event_id == event_id
    ))
    assert total_count == 2
    db.close()


def test_cancellation_and_reregistration_succeeds():
    event_id, alice_id, _ = _seed_event()
    db = TestSession()
    alice = db.get(User, alice_id)
    _CURRENT["user"] = alice

    # Register
    resp1 = client.post(f"/events/{event_id}/register")
    assert resp1.status_code == 201

    # Cancel
    resp_del = client.delete(f"/events/{event_id}/register")
    assert resp_del.status_code == 204

    # Re-register succeeds
    resp2 = client.post(f"/events/{event_id}/register")
    assert resp2.status_code == 201
    assert resp2.json()["message"] == "Registration successful"

    db.close()


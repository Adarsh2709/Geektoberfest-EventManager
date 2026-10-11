import os

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
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


def _seed():
    db = TestSession()
    organizer = User(username="organizer", email="org@ex.com", hashed_password="x")
    alice = User(username="alice", email="alice@ex.com", hashed_password="x")
    bob = User(username="bob", email="bob@ex.com", hashed_password="x")
    db.add_all([organizer, alice, bob])
    db.flush()

    event = Event(
        title="Launch",
        description="desc",
        location="Hall",
        start_time=datetime(2030, 1, 1, 10, tzinfo=timezone.utc),
        end_time=datetime(2030, 1, 1, 12, tzinfo=timezone.utc),
        capacity=50,
        organizer_id=organizer.id,
    )
    db.add(event)
    db.flush()

    db.add_all([
        EventRegistration(
            event_id=event.id, user_id=alice.id,
            registered_at=datetime(2030, 1, 1, 9, 0, tzinfo=timezone.utc),
        ),
        EventRegistration(
            event_id=event.id, user_id=bob.id,
            registered_at=datetime(2030, 1, 1, 9, 5, tzinfo=timezone.utc),
        ),
    ])
    db.commit()
    ids = {"event": event.id, "organizer": organizer.id, "alice": alice.id, "bob": bob.id}
    db.close()
    return ids


def _user(db_id):
    db = TestSession()
    user = db.get(User, db_id)
    db.close()
    return user


def test_organizer_can_export_registrations_as_csv():
    ids = _seed()
    _CURRENT["user"] = _user(ids["organizer"])

    resp = client.get(f"/events/{ids['event']}/registrations.csv")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    assert f"event-{ids['event']}-registrations.csv" in resp.headers["content-disposition"]

    lines = resp.text.strip().splitlines()
    assert lines[0] == "user_id,username,email,registered_at"
    # Two attendees, ordered by registration time.
    assert lines[1].startswith(f"{ids['alice']},alice,alice@ex.com,")
    assert lines[2].startswith(f"{ids['bob']},bob,bob@ex.com,")
    assert len(lines) == 3


def test_non_organizer_cannot_export():
    ids = _seed()
    _CURRENT["user"] = _user(ids["alice"])

    resp = client.get(f"/events/{ids['event']}/registrations.csv")
    assert resp.status_code == 403


def test_export_missing_event_returns_404():
    ids = _seed()
    _CURRENT["user"] = _user(ids["organizer"])

    resp = client.get("/events/99999/registrations.csv")
    assert resp.status_code == 404


def test_export_empty_event_returns_header_only():
    db = TestSession()
    organizer = User(username="solo", email="solo@ex.com", hashed_password="x")
    db.add(organizer)
    db.flush()
    event = Event(
        title="Empty", description="d", location="L",
        start_time=datetime(2030, 2, 1, 10, tzinfo=timezone.utc),
        end_time=datetime(2030, 2, 1, 12, tzinfo=timezone.utc),
        capacity=10, organizer_id=organizer.id,
    )
    db.add(event)
    db.commit()
    event_id, org_id = event.id, organizer.id
    db.close()

    _CURRENT["user"] = _user(org_id)
    resp = client.get(f"/events/{event_id}/registrations.csv")
    assert resp.status_code == 200
    assert resp.text.strip() == "user_id,username,email,registered_at"

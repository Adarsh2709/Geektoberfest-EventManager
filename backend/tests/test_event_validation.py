"""Tests for event creation form validation (Issue #6).

Acceptance criteria verified:
- Validate required title and date fields
- Reject invalid dates according to product rules (end_time <= start_time)
- Clear validation feedback messages
"""

import os

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_current_user
from app.database import Base, get_db
from app.models import User
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
def clean_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    db = TestSession()
    organizer = User(username="organizer", email="organizer@example.com", hashed_password="pw")
    db.add(organizer)
    db.commit()
    db.refresh(organizer)
    db.close()

    _CURRENT["user"] = organizer
    yield
    _CURRENT["user"] = None


def test_create_event_valid_payload():
    start = datetime.now(timezone.utc) + timedelta(days=2)
    end = start + timedelta(hours=3)

    payload = {
        "title": "Community Workshop",
        "description": "Hands-on coding workshop",
        "location": "Main Hall",
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
        "capacity": 40,
    }
    res = client.post("/events", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["title"] == "Community Workshop"
    assert data["location"] == "Main Hall"


def test_reject_blank_or_whitespace_title():
    start = datetime.now(timezone.utc) + timedelta(days=2)
    end = start + timedelta(hours=3)

    payload = {
        "title": "    ",
        "description": "Workshop description",
        "location": "Main Hall",
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
        "capacity": 25,
    }
    res = client.post("/events", json=payload)
    assert res.status_code == 422
    errors = res.json()["detail"]
    assert any("title" in str(e["loc"]) for e in errors)


def test_reject_end_time_before_start_time():
    start = datetime.now(timezone.utc) + timedelta(days=5)
    end = start - timedelta(hours=1)

    payload = {
        "title": "Sunset Meetup",
        "description": "Meetup description",
        "location": "Park",
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
        "capacity": 20,
    }
    res = client.post("/events", json=payload)
    assert res.status_code == 422
    assert any("End time must be after start time" in str(e["msg"]) for e in res.json()["detail"])


def test_reject_end_time_equal_to_start_time():
    start = datetime.now(timezone.utc) + timedelta(days=3)
    end = start

    payload = {
        "title": "Flash Mob",
        "description": "Meetup description",
        "location": "Plaza",
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
        "capacity": 15,
    }
    res = client.post("/events", json=payload)
    assert res.status_code == 422
    assert any("End time must be after start time" in str(e["msg"]) for e in res.json()["detail"])


def test_reject_missing_required_date_fields():
    payload = {
        "title": "Networking Night",
        "description": "Meet other devs",
        "location": "Cafe",
        "capacity": 30,
    }
    res = client.post("/events", json=payload)
    assert res.status_code == 422
    fields = [str(e["loc"]) for e in res.json()["detail"]]
    assert any("start_time" in f for f in fields)
    assert any("end_time" in f for f in fields)

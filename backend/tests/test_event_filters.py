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
from app.models import Event, User
from app.routes import events as events_module
from app.routes import users as users_module

engine = create_engine(
    "sqlite+pysqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app = FastAPI()
app.include_router(events_module.router)
app.include_router(users_module.router)
app.dependency_overrides[get_db] = _override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


def _seed_mixed_events():
    db = TestSession()
    host = User(username="host", email="host@example.com", hashed_password="pw")
    db.add(host)
    db.flush()

    now = datetime.now(timezone.utc)
    # Past event (ended yesterday)
    past_event = Event(
        title="Yesterday Reunion",
        description="Event in the past",
        location="Historic Hall",
        start_time=now - timedelta(days=2),
        end_time=now - timedelta(days=1),
        capacity=10,
        organizer_id=host.id,
    )
    # Upcoming event (starts tomorrow, ends in 2 days)
    upcoming_event = Event(
        title="Tomorrow Hackathon",
        description="Event in the future",
        location="Innovation Hub",
        start_time=now + timedelta(days=1),
        end_time=now + timedelta(days=2),
        capacity=50,
        organizer_id=host.id,
    )
    # Ongoing event (started an hour ago, ends in 2 hours) -> upcoming
    ongoing_event = Event(
        title="Current Workshop",
        description="Event happening right now",
        location="Room 101",
        start_time=now - timedelta(hours=1),
        end_time=now + timedelta(hours=2),
        capacity=20,
        organizer_id=host.id,
    )

    db.add_all([past_event, upcoming_event, ongoing_event])
    db.commit()
    db.close()


def test_list_events_filter_all():
    _seed_mixed_events()
    res = client.get("/events?filter=all")
    assert res.status_code == 200
    titles = [e["title"] for e in res.json()]
    assert len(titles) == 3
    assert "Yesterday Reunion" in titles
    assert "Tomorrow Hackathon" in titles
    assert "Current Workshop" in titles


def test_list_events_filter_upcoming():
    _seed_mixed_events()
    res = client.get("/events?filter=upcoming")
    assert res.status_code == 200
    titles = [e["title"] for e in res.json()]
    assert len(titles) == 2
    assert "Tomorrow Hackathon" in titles
    assert "Current Workshop" in titles
    assert "Yesterday Reunion" not in titles


def test_list_events_filter_past():
    _seed_mixed_events()
    res = client.get("/events?filter=past")
    assert res.status_code == 200
    titles = [e["title"] for e in res.json()]
    assert len(titles) == 1
    assert titles[0] == "Yesterday Reunion"


def test_search_events_with_filter():
    _seed_mixed_events()
    # Search for "Hackathon" with filter=past should return empty
    res_past = client.get("/events/search?q=Hackathon&filter=past")
    assert res_past.status_code == 200
    assert len(res_past.json()) == 0

    # Search for "Hackathon" with filter=upcoming should return 1
    res_up = client.get("/events/search?q=Hackathon&filter=upcoming")
    assert res_up.status_code == 200
    assert len(res_up.json()) == 1
    assert res_up.json()[0]["title"] == "Tomorrow Hackathon"


def test_invalid_filter_parameter_rejected():
    _seed_mixed_events()
    res = client.get("/events?filter=invalid_filter")
    assert res.status_code == 422

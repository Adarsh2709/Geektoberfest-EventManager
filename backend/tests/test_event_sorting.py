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


def _seed_events():
    db = TestSession()
    host = User(username="host", email="host@example.com", hashed_password="pw")
    db.add(host)
    db.flush()

    e1 = Event(
        title="Spring Gathering",
        description="Spring meetup",
        location="Park",
        start_time=datetime(2030, 3, 1, 10, 0, tzinfo=timezone.utc),
        end_time=datetime(2030, 3, 1, 12, 0, tzinfo=timezone.utc),
        capacity=10,
        organizer_id=host.id,
    )
    e2 = Event(
        title="Summer Summit",
        description="Summer tech conference",
        location="Convention Center",
        start_time=datetime(2030, 7, 15, 9, 0, tzinfo=timezone.utc),
        end_time=datetime(2030, 7, 15, 17, 0, tzinfo=timezone.utc),
        capacity=50,
        organizer_id=host.id,
    )
    e3 = Event(
        title="Autumn Workshop",
        description="Hands-on coding workshop in autumn",
        location="Lab",
        start_time=datetime(2030, 10, 5, 13, 0, tzinfo=timezone.utc),
        end_time=datetime(2030, 10, 5, 16, 0, tzinfo=timezone.utc),
        capacity=20,
        organizer_id=host.id,
    )
    db.add_all([e1, e2, e3])
    db.commit()
    db.close()


def test_list_events_default_sort_soonest():
    _seed_events()
    res = client.get("/events")
    assert res.status_code == 200
    titles = [e["title"] for e in res.json()]
    assert titles == ["Spring Gathering", "Summer Summit", "Autumn Workshop"]


def test_list_events_explicit_sort_soonest():
    _seed_events()
    res = client.get("/events?sort=soonest")
    assert res.status_code == 200
    titles = [e["title"] for e in res.json()]
    assert titles == ["Spring Gathering", "Summer Summit", "Autumn Workshop"]


def test_list_events_sort_latest():
    _seed_events()
    res = client.get("/events?sort=latest")
    assert res.status_code == 200
    titles = [e["title"] for e in res.json()]
    assert titles == ["Autumn Workshop", "Summer Summit", "Spring Gathering"]


def test_search_events_sort_soonest():
    _seed_events()
    # Search for events matching "meetup" or "conference" or "workshop" (all contain words)
    # Search 'Summer'
    res = client.get("/events/search?q=Summit&sort=soonest")
    assert res.status_code == 200
    assert len(res.json()) == 1
    assert res.json()[0]["title"] == "Summer Summit"


def test_search_events_sort_latest():
    _seed_events()
    # Search by location "Convention" vs other
    res = client.get("/events/search?q=Summer&sort=latest")
    assert res.status_code == 200
    assert len(res.json()) == 1
    assert res.json()[0]["title"] == "Summer Summit"


def test_invalid_sort_parameter_rejected():
    _seed_events()
    res = client.get("/events?sort=random_sort")
    assert res.status_code == 422

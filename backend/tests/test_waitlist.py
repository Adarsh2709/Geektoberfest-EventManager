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
from app.models import Event, EventRegistration, Notification, User, WaitlistEntry
from app.routes import events as events_module
from app.routes import users as users_module

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
app.include_router(users_module.router)
app.dependency_overrides[get_db] = _override_get_db
app.dependency_overrides[get_current_user] = lambda: _CURRENT["user"]
client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    _CURRENT["user"] = None
    yield


def _seed(capacity=2):
    """An event with alice and bob registered (full at capacity 2); carol, dave and erin are not."""
    db = TestSession()
    users = {
        name: User(username=name, email=f"{name}@ex.com", hashed_password="x")
        for name in ("organizer", "alice", "bob", "carol", "dave", "erin")
    }
    db.add_all(users.values())
    db.flush()
    event = Event(
        title="Launch", description="desc", location="Hall",
        start_time=datetime(2030, 1, 1, 10, tzinfo=timezone.utc),
        end_time=datetime(2030, 1, 1, 12, tzinfo=timezone.utc),
        capacity=capacity, organizer_id=users["organizer"].id,
    )
    db.add(event)
    db.flush()
    for name in ("alice", "bob"):
        db.add(EventRegistration(event_id=event.id, user_id=users[name].id))
    db.commit()
    ids = {name: user.id for name, user in users.items()}
    ids["event"] = event.id
    db.close()
    return ids


def _as(ids, name):
    db = TestSession()
    _CURRENT["user"] = db.get(User, ids[name])
    db.close()


def _join(ids, name):
    _as(ids, name)
    return client.post(f"/events/{ids['event']}/waitlist")


def _registered(ids):
    db = TestSession()
    rows = db.scalars(select(EventRegistration.user_id).where(EventRegistration.event_id == ids["event"])).all()
    db.close()
    return set(rows)


def _waitlisted(ids):
    db = TestSession()
    rows = db.scalars(
        select(WaitlistEntry.user_id).where(WaitlistEntry.event_id == ids["event"]).order_by(WaitlistEntry.id)
    ).all()
    db.close()
    return rows


def _notifications(user_id):
    db = TestSession()
    rows = db.scalars(select(Notification).where(Notification.user_id == user_id).order_by(Notification.id)).all()
    db.close()
    return rows


# --- joining -----------------------------------------------------------------

def test_join_waitlist_when_full():
    ids = _seed()
    resp = _join(ids, "carol")
    assert resp.status_code == 201
    assert resp.json()["position"] == 1
    assert _waitlisted(ids) == [ids["carol"]]


def test_cannot_join_waitlist_when_event_has_spots():
    ids = _seed(capacity=3)
    resp = _join(ids, "carol")
    assert resp.status_code == 409
    assert _waitlisted(ids) == []


def test_registered_user_cannot_join_waitlist():
    ids = _seed()
    assert _join(ids, "alice").status_code == 409
    assert _waitlisted(ids) == []


def test_join_waitlist_unknown_event_returns_404():
    ids = _seed()
    _as(ids, "carol")
    assert client.post("/events/99999/waitlist").status_code == 404


# --- duplicates --------------------------------------------------------------

def test_duplicate_waitlist_entry_rejected():
    ids = _seed()
    assert _join(ids, "carol").status_code == 201
    assert _join(ids, "carol").status_code == 409
    assert _waitlisted(ids) == [ids["carol"]]


# --- queue order -------------------------------------------------------------

def test_positions_follow_join_order():
    ids = _seed()
    assert _join(ids, "carol").json()["position"] == 1
    assert _join(ids, "dave").json()["position"] == 2
    assert _join(ids, "erin").json()["position"] == 3

    _as(ids, "organizer")
    listing = client.get(f"/events/{ids['event']}/waitlist").json()
    assert [(row["position"], row["user"]["username"]) for row in listing] == [
        (1, "carol"), (2, "dave"), (3, "erin"),
    ]


def test_leaving_waitlist_keeps_order_of_others():
    ids = _seed()
    for name in ("carol", "dave", "erin"):
        _join(ids, name)
    _as(ids, "dave")
    assert client.delete(f"/events/{ids['event']}/waitlist").status_code == 204
    assert _waitlisted(ids) == [ids["carol"], ids["erin"]]
    assert client.delete(f"/events/{ids['event']}/waitlist").status_code == 404


def test_only_organizer_can_view_waitlist():
    ids = _seed()
    _join(ids, "carol")
    _as(ids, "carol")
    assert client.get(f"/events/{ids['event']}/waitlist").status_code == 403


# --- promotion ---------------------------------------------------------------

def test_cancellation_promotes_first_in_queue():
    ids = _seed()
    for name in ("carol", "dave"):
        _join(ids, name)

    _as(ids, "alice")
    assert client.delete(f"/events/{ids['event']}/register").status_code == 204

    assert _registered(ids) == {ids["bob"], ids["carol"]}
    assert _waitlisted(ids) == [ids["dave"]]


def test_promotion_notifies_promoted_user_and_organizer():
    ids = _seed()
    _join(ids, "carol")
    _as(ids, "alice")
    client.delete(f"/events/{ids['event']}/register")

    promoted = _notifications(ids["carol"])
    assert len(promoted) == 1 and "you're in" in promoted[0].message

    organizer = _notifications(ids["organizer"])
    assert len(organizer) == 1
    assert "alice cancelled" in organizer[0].message and "carol" in organizer[0].message


def test_organizer_notified_when_spot_opens_with_empty_waitlist():
    ids = _seed()
    _as(ids, "alice")
    client.delete(f"/events/{ids['event']}/register")

    organizer = _notifications(ids["organizer"])
    assert len(organizer) == 1
    assert "Nobody is on the waitlist" in organizer[0].message
    assert _registered(ids) == {ids["bob"]}


def test_no_organizer_notification_when_event_was_not_full():
    ids = _seed(capacity=5)
    _as(ids, "alice")
    client.delete(f"/events/{ids['event']}/register")
    assert _notifications(ids["organizer"]) == []


def test_raising_capacity_promotes_in_order():
    ids = _seed()
    for name in ("carol", "dave", "erin"):
        _join(ids, name)

    _as(ids, "organizer")
    resp = client.put(f"/events/{ids['event']}", json={
        "title": "Launch", "description": "desc", "location": "Hall",
        "start_time": "2030-01-01T10:00:00Z", "end_time": "2030-01-01T12:00:00Z", "capacity": 4,
    })
    assert resp.status_code == 200
    assert _registered(ids) == {ids["alice"], ids["bob"], ids["carol"], ids["dave"]}
    assert _waitlisted(ids) == [ids["erin"]]
    assert resp.json()["waitlist_count"] == 1


def test_cancelled_user_can_join_waitlist_when_full_again():
    ids = _seed()
    _join(ids, "carol")
    _as(ids, "alice")
    client.delete(f"/events/{ids['event']}/register")
    # Event is full again (bob + carol), so alice may queue for a new spot.
    assert _join(ids, "alice").status_code == 201


# --- user-facing listings ----------------------------------------------------

def test_my_events_lists_waitlisted_with_position():
    ids = _seed()
    _join(ids, "carol")
    _join(ids, "dave")
    _as(ids, "dave")
    data = client.get("/users/me/events").json()
    assert [e["id"] for e in data["waitlisted"]] == [ids["event"]]
    assert data["waitlisted"][0]["waitlist_position"] == 2
    assert data["attending"] == []


def test_notifications_can_be_listed_and_marked_read():
    ids = _seed()
    _as(ids, "alice")
    client.delete(f"/events/{ids['event']}/register")

    _as(ids, "organizer")
    items = client.get("/users/me/notifications").json()
    assert len(items) == 1 and items[0]["read"] is False
    assert client.post("/users/me/notifications/read").status_code == 204
    assert client.get("/users/me/notifications").json()[0]["read"] is True

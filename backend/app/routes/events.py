from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

import csv
import io

from app.auth import get_current_user
from app.database import get_db
from app.models import Event, EventRegistration, Notification, User, WaitlistEntry
from app.schemas import EventCreate, EventPublic, EventUpdate, WaitlistEntryPublic

router = APIRouter(prefix="/events", tags=["events"])


def _event_query():
    return select(Event).options(joinedload(Event.organizer)).options(joinedload(Event.registrations)).options(joinedload(Event.waitlist))


def _event_or_404(db: Session, event_id: int) -> Event:
    event = db.execute(_event_query().where(Event.id == event_id)).unique().scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


def _order_clause(sort: str):
    if sort == "latest":
        return Event.start_time.desc().nulls_last()
    return Event.start_time.asc().nulls_last()


@router.get("", response_model=list[EventPublic])
def list_events(sort: str = Query("soonest", pattern="^(soonest|latest)$"), db: Session = Depends(get_db)):
    events = db.execute(_event_query().order_by(_order_clause(sort))).unique().scalars().all()
    return [_with_count(event) for event in events]


@router.get("/search", response_model=list[EventPublic])
def search_events(
    q: str = Query(min_length=1, max_length=100),
    sort: str = Query("soonest", pattern="^(soonest|latest)$"),
    db: Session = Depends(get_db),
):
    term = f"%{q.strip()}%"
    events = db.execute(
        _event_query().where(
            or_(Event.title.ilike(term), Event.description.ilike(term), Event.location.ilike(term))
        ).order_by(_order_clause(sort))
    ).unique().scalars().all()
    return [_with_count(event) for event in events]


@router.get("/{event_id}", response_model=EventPublic)
def get_event(event_id: int, db: Session = Depends(get_db)):
    return _with_count(_event_or_404(db, event_id))


@router.post("", response_model=EventPublic, status_code=status.HTTP_201_CREATED)
def create_event(data: EventCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    event = Event(**data.model_dump(), organizer_id=user.id)
    db.add(event)
    db.commit()
    db.refresh(event)
    return _with_count(_event_or_404(db, event.id))


@router.put("/{event_id}", response_model=EventPublic)
def update_event(
    event_id: int, data: EventUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    # Lock the row first so the capacity check and the save see the same registrations that register/cancel use.
    db.execute(select(Event.id).where(Event.id == event_id).with_for_update())
    event = _event_or_404(db, event_id)
    if event.organizer_id != user.id:
        raise HTTPException(status_code=403, detail="Only the organizer can update this event")
    updates = data.model_dump()
    if updates["capacity"] < len(event.registrations):
        raise HTTPException(status_code=400, detail="Capacity cannot be lower than current registrations")
    for field, value in updates.items():
        setattr(event, field, value)
    _promote_from_waitlist(db, event)
    db.commit()
    db.expire(event)
    return _with_count(_event_or_404(db, event_id))


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(event_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    event = _event_or_404(db, event_id)
    if event.organizer_id != user.id:
        raise HTTPException(status_code=403, detail="Only the organizer can delete this event")
    db.delete(event)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{event_id}/register", status_code=status.HTTP_201_CREATED)
def register_for_event(event_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    event = db.execute(select(Event).where(Event.id == event_id).with_for_update()).scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if db.scalar(select(EventRegistration.id).where(
        EventRegistration.event_id == event_id, EventRegistration.user_id == user.id
    )):
        raise HTTPException(status_code=409, detail="You are already registered for this event")
    count = db.scalar(select(func.count()).select_from(EventRegistration).where(EventRegistration.event_id == event_id))
    if count >= event.capacity:
        raise HTTPException(status_code=409, detail="This event is full")
    db.add(EventRegistration(event_id=event_id, user_id=user.id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="You are already registered for this event")
    return {"message": "Registration successful"}


@router.delete("/{event_id}/register", status_code=status.HTTP_204_NO_CONTENT)
def cancel_registration(event_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    registration = db.scalar(select(EventRegistration).where(
        EventRegistration.event_id == event_id, EventRegistration.user_id == user.id
    ))
    if not registration:
        raise HTTPException(status_code=404, detail="You are not registered for this event")
    event = db.execute(select(Event).where(Event.id == event_id).with_for_update()).scalar_one()
    was_full = _registration_count(db, event_id) >= event.capacity
    db.delete(registration)
    db.flush()
    if was_full:
        _promote_from_waitlist(db, event, freed_by=user)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{event_id}/waitlist", status_code=status.HTTP_201_CREATED)
def join_waitlist(event_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    event = db.execute(select(Event).where(Event.id == event_id).with_for_update()).scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if db.scalar(select(EventRegistration.id).where(
        EventRegistration.event_id == event_id, EventRegistration.user_id == user.id
    )):
        raise HTTPException(status_code=409, detail="You are already registered for this event")
    if _registration_count(db, event_id) < event.capacity:
        raise HTTPException(status_code=409, detail="This event still has spots; register instead")
    if db.scalar(select(WaitlistEntry.id).where(
        WaitlistEntry.event_id == event_id, WaitlistEntry.user_id == user.id
    )):
        raise HTTPException(status_code=409, detail="You are already on the waitlist for this event")
    db.add(WaitlistEntry(event_id=event_id, user_id=user.id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="You are already on the waitlist for this event")
    return {"message": "You joined the waitlist", "position": _waitlist_position(db, event_id, user.id)}


@router.delete("/{event_id}/waitlist", status_code=status.HTTP_204_NO_CONTENT)
def leave_waitlist(event_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    entry = db.scalar(select(WaitlistEntry).where(
        WaitlistEntry.event_id == event_id, WaitlistEntry.user_id == user.id
    ))
    if not entry:
        raise HTTPException(status_code=404, detail="You are not on the waitlist for this event")
    db.delete(entry)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{event_id}/waitlist", response_model=list[WaitlistEntryPublic])
def list_waitlist(event_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The waitlist in queue order. Restricted to the organizer."""
    event = _event_or_404(db, event_id)
    if event.organizer_id != user.id:
        raise HTTPException(status_code=403, detail="Only the organizer can view the waitlist")
    entries = db.execute(
        select(WaitlistEntry).options(joinedload(WaitlistEntry.user))
        .where(WaitlistEntry.event_id == event_id).order_by(WaitlistEntry.id)
    ).scalars().all()
    return [
        {"position": index, "user": entry.user, "joined_at": entry.joined_at}
        for index, entry in enumerate(entries, start=1)
    ]


@router.get("/{event_id}/registrations.csv")
def export_registrations_csv(
    event_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    """Export an event's attendee list as CSV. Restricted to the organizer."""
    event = _event_or_404(db, event_id)
    if event.organizer_id != user.id:
        raise HTTPException(status_code=403, detail="Only the organizer can export registrations")

    registrations = db.execute(
        select(EventRegistration)
        .options(joinedload(EventRegistration.user))
        .where(EventRegistration.event_id == event_id)
        .order_by(EventRegistration.registered_at)
    ).scalars().all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["user_id", "username", "email", "registered_at"])
    for registration in registrations:
        attendee = registration.user
        writer.writerow([
            registration.user_id,
            attendee.username if attendee else "",
            attendee.email if attendee else "",
            registration.registered_at.isoformat() if registration.registered_at else "",
        ])

    filename = f"event-{event_id}-registrations.csv"
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _registration_count(db: Session, event_id: int) -> int:
    return db.scalar(select(func.count()).select_from(EventRegistration).where(EventRegistration.event_id == event_id))


def _waitlist_position(db: Session, event_id: int, user_id: int) -> int | None:
    """1-based place in the queue, or None if the user is not waitlisted."""
    entry_id = db.scalar(select(WaitlistEntry.id).where(
        WaitlistEntry.event_id == event_id, WaitlistEntry.user_id == user_id
    ))
    if entry_id is None:
        return None
    return db.scalar(select(func.count()).select_from(WaitlistEntry).where(
        WaitlistEntry.event_id == event_id, WaitlistEntry.id <= entry_id
    ))


def _promote_from_waitlist(db: Session, event: Event, freed_by: User | None = None) -> None:
    """Fill open spots from the head of the waitlist and notify the people involved.

    Runs inside the caller's transaction (the event row is locked by the caller) and does not commit.
    """
    open_spots = event.capacity - _registration_count(db, event.id)
    if open_spots <= 0:
        return
    queue = db.scalars(
        select(WaitlistEntry).where(WaitlistEntry.event_id == event.id).order_by(WaitlistEntry.id).limit(open_spots)
    ).all()
    promoted = []
    for entry in queue:
        db.add(EventRegistration(event_id=event.id, user_id=entry.user_id))
        db.add(Notification(
            user_id=entry.user_id, event_id=event.id,
            message=f"A spot opened up and you're in! You were moved off the waitlist for \"{event.title}\".",
        ))
        promoted.append(db.get(User, entry.user_id))
        db.delete(entry)
    cause = f"{freed_by.username} cancelled" if freed_by else "Capacity was increased"
    if promoted:
        outcome = "Promoted from the waitlist: " + ", ".join(p.username for p in promoted) + "."
    else:
        outcome = "Nobody is on the waitlist, so the spot is open."
    db.add(Notification(
        user_id=event.organizer_id, event_id=event.id,
        message=f"A place opened up for \"{event.title}\". {cause}. {outcome}",
    ))


def _with_count(event: Event) -> dict:
    return {
        "id": event.id,
        "title": event.title,
        "description": event.description,
        "location": event.location,
        "start_time": event.start_time,
        "end_time": event.end_time,
        "capacity": event.capacity,
        "created_at": event.created_at,
        "organizer_id": event.organizer_id,
        "organizer": event.organizer,
        "attendee_count": len(event.registrations),
        "waitlist_count": len(event.waitlist),
    }

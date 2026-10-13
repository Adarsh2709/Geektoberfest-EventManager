from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

import csv
import io

from app.auth import get_current_user
from app.database import get_db
from app.models import Event, EventRegistration, User
from app.schemas import EventCreate, EventPublic, EventUpdate

router = APIRouter(prefix="/events", tags=["events"])


def _event_query():
    return select(Event).options(joinedload(Event.organizer)).options(joinedload(Event.registrations))


def _event_or_404(db: Session, event_id: int) -> Event:
    event = db.execute(_event_query().where(Event.id == event_id)).unique().scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.get("", response_model=list[EventPublic])
def list_events(db: Session = Depends(get_db)):
    events = db.execute(_event_query().order_by(Event.start_time)).unique().scalars().all()
    return [_with_count(event) for event in events]


@router.get("/search", response_model=list[EventPublic])
def search_events(q: str = Query(min_length=1, max_length=100), db: Session = Depends(get_db)):
    term = f"%{q.strip()}%"
    events = db.execute(
        _event_query().where(
            or_(Event.title.ilike(term), Event.description.ilike(term), Event.location.ilike(term))
        ).order_by(Event.start_time)
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
    db.commit()
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
    db.delete(registration)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    }

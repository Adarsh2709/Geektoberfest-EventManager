from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload

from app.auth import get_current_user
from app.database import get_db
from app.models import Event, EventRegistration, Notification, User, WaitlistEntry
from app.routes.events import _waitlist_position, _with_count
from app.schemas import NotificationPublic

router = APIRouter(prefix="/users", tags=["users"])


def _loaded(query):
    return query.options(
        joinedload(Event.organizer), joinedload(Event.registrations), joinedload(Event.waitlist)
    ).order_by(Event.start_time)


@router.get("/me/events")
def my_events(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    attending = db.execute(
        _loaded(select(Event).join(EventRegistration).where(EventRegistration.user_id == user.id))
    ).unique().scalars().all()
    organized = db.execute(_loaded(select(Event).where(Event.organizer_id == user.id))).unique().scalars().all()
    waitlisted = db.execute(
        _loaded(select(Event).join(WaitlistEntry).where(WaitlistEntry.user_id == user.id))
    ).unique().scalars().all()
    return {"attending": [_with_count(event) for event in attending],
            "organized": [_with_count(event) for event in organized],
            "waitlisted": [
                {**_with_count(event), "waitlist_position": _waitlist_position(db, event.id, user.id)}
                for event in waitlisted
            ]}


@router.get("/me/notifications", response_model=list[NotificationPublic])
def my_notifications(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.scalars(
        select(Notification).where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc()).limit(50)
    ).all()


@router.post("/me/notifications/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_notifications_read(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    db.execute(update(Notification).where(Notification.user_id == user.id, Notification.read.is_(False)).values(read=True))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

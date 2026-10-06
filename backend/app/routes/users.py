from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.auth import get_current_user
from app.database import get_db
from app.models import Event, EventRegistration, User
from app.routes.events import _with_count

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me/events")
def my_events(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    attending = db.execute(
        select(Event).join(EventRegistration).where(EventRegistration.user_id == user.id)
        .options(joinedload(Event.organizer), joinedload(Event.registrations)).order_by(Event.start_time)
    ).unique().scalars().all()
    organized = db.execute(
        select(Event).where(Event.organizer_id == user.id)
        .options(joinedload(Event.organizer), joinedload(Event.registrations)).order_by(Event.start_time)
    ).unique().scalars().all()
    return {"attending": [_with_count(event) for event in attending],
            "organized": [_with_count(event) for event in organized]}

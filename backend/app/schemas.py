from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class EventCreate(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    description: str = Field(min_length=1, max_length=10000)
    location: str = Field(min_length=2, max_length=200)
    start_time: datetime
    end_time: datetime
    capacity: int = Field(gt=0, le=100000)

    @field_validator("title", "location", mode="before")
    @classmethod
    def validate_non_blank(cls, value: str) -> str:
        if isinstance(value, str):
            value = value.strip()
            if len(value) < 2:
                raise ValueError("Must contain at least 2 non-whitespace characters")
        return value

    @model_validator(mode="after")
    def end_after_start(self):
        if self.end_time <= self.start_time:
            raise ValueError("End time must be after start time")
        return self


class EventUpdate(EventCreate):
    pass


class EventPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    location: str
    start_time: datetime
    end_time: datetime
    capacity: int
    created_at: datetime
    organizer_id: int
    organizer: UserPublic
    attendee_count: int
    waitlist_count: int = 0
    waitlist_position: int | None = None


class WaitlistEntryPublic(BaseModel):
    position: int
    user: UserPublic
    joined_at: datetime


class NotificationPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int | None
    message: str
    read: bool
    created_at: datetime


class MyEvents(BaseModel):
    attending: list[EventPublic]
    organized: list[EventPublic]
    waitlisted: list[EventPublic] = []

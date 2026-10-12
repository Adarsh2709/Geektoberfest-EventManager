# Event Hub

A simple event creation and registration platform built with FastAPI, PostgreSQL, SQLAlchemy, and React. Event Hub is a small open-source starter intended to be easy to run, read, and improve.

##Live Demo

Frontend: https://eventmanager-ivory.vercel.app

Backend API: https://eventmanager-oocc.onrender.com

API Documentation: https://eventmanager-oocc.onrender.com/docs

Health Check: https://eventmanager-oocc.onrender.com/health

## Features

- Create an account, log in, and log out with JWT authentication
- Browse upcoming events, search by title, description, or location, and view event details
- Create, update, and delete your own events
- Register for events, see your registrations, and cancel your spot
- Enforce event capacity and prevent duplicate registrations
- Join a waitlist when an event is full; the first person in line is moved in automatically when a spot opens, and the organizer is notified

## Tech stack

- FastAPI and Python
- PostgreSQL and SQLAlchemy
- Alembic migrations
- JWT authentication and Argon2 password hashing (`pwdlib`)
- React, Vite, and plain CSS

## Requirements

- Python 3.11+
- Node.js 18+
- PostgreSQL 14+

## Backend setup

Create a PostgreSQL database named `eventhub`, then:

```bash
cd backend
python -m venv .venv
```

Activate the virtual environment. On Windows:

```powershell
.venv\Scripts\activate
```

Install packages and configure environment variables:

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env` in the `backend` directory. Set `DATABASE_URL` to your local PostgreSQL credentials and replace `SECRET_KEY` with a long random value. Keep `.env` private.

Apply the database migration and start the API:

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

The API is at <http://localhost:8000>. Interactive API documentation is at <http://localhost:8000/docs>.

## Frontend setup

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Vite serves the app at <http://localhost:5173>. The frontend uses `http://localhost:8000` for the API by default. To use another API address, set `VITE_API_URL` in a `frontend/.env` file.

## API overview

| Method | Endpoint | Purpose |
| --- | --- | --- |
| POST | `/auth/register` | Create an account |
| POST | `/auth/login` | Get a JWT |
| GET | `/auth/me` | Get the signed-in user |
| GET | `/events` | Browse events |
| GET | `/events/search?q=...` | Search events |
| GET | `/events/{id}` | View an event |
| POST | `/events` | Create an event (signed in) |
| PUT | `/events/{id}` | Update your event |
| DELETE | `/events/{id}` | Delete your event |
| POST | `/events/{id}/register` | Register for an event |
| DELETE | `/events/{id}/register` | Cancel a registration |
| GET | `/events/{id}/registrations.csv` | Export attendees as CSV (organizer only) |
| POST | `/events/{id}/waitlist` | Join the waitlist (only when the event is full) |
| DELETE | `/events/{id}/waitlist` | Leave the waitlist |
| GET | `/events/{id}/waitlist` | View the waitlist in queue order (organizer only) |
| GET | `/users/me/events` | View events you're attending, hosting, and waitlisted for |
| GET | `/users/me/notifications` | View your notifications |
| POST | `/users/me/notifications/read` | Mark all your notifications as read |

### Waitlist

- A waitlist can only be joined while an event is at capacity, and only once per person. Registered attendees cannot join.
- The queue is first come, first served. Your position is shown on the event page and under "My events".
- When a registration is cancelled, or the organizer raises the capacity, waitlisted people are registered in queue order until the event is full again.
- The promoted attendee and the organizer each get an in-app notification (shown on "My events"). Existing databases need `alembic upgrade head` to add the new tables.

## Contributing

First contributions are welcome.Bug reports and feature suggestions can use the templates in `.github/ISSUE_TEMPLATE/`.

This project is intentionally a small MVP. Payments, notifications, external sign-in, and other larger ideas are left for future contributions.

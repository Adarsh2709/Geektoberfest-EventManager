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
| PUT | `/events/{id}` | Update your event (organizer only; capacity cannot go below current registrations) |
| DELETE | `/events/{id}` | Delete your event |
| POST | `/events/{id}/register` | Register for an event |
| DELETE | `/events/{id}/register` | Cancel a registration |
| GET | `/users/me/events` | View events you're attending and hosting |

## Contributing

First contributions are welcome.Bug reports and feature suggestions can use the templates in `.github/ISSUE_TEMPLATE/`.

This project is intentionally a small MVP. Payments, notifications, external sign-in, and other larger ideas are left for future contributions.

# TutorTrack AI

A student performance tracking web application for math teachers — built by adapting the CGST Guruvayoor **Guesthouse Booking** backend.

## Field Mapping (Guesthouse → TutorTrack AI)

| Guesthouse Field | TutorTrack AI Field | Notes |
|---|---|---|
| Guest Name | **Student Name** | Core identifying field |
| Check-in Date | **Test Date** | YYYY-MM-DD format |
| Room Price | **Marks Obtained** | 0.0 – 100.0 |

## Tech Stack

- **Backend**: Python 3.11 + FastAPI + Firebase Firestore
- **Frontend**: Vanilla HTML / CSS / JavaScript (no frameworks)
- **Auth**: JWT HS256, bcrypt password hashing
- **Database**: Firebase Firestore (same as Guesthouse)

## Project Structure

```
TutorTrack AI/
├── backend/
│   ├── main.py               ← FastAPI app entry point
│   ├── config.py             ← Settings (pydantic-settings)
│   ├── auth.py               ← JWT + bcrypt auth (reused from Guesthouse)
│   ├── database.py           ← Firestore helpers (collection: student_records)
│   ├── models.py             ← Pydantic models (StudentRecord, Grade, …)
│   ├── requirements.txt
│   ├── .env.example          ← Copy to .env and fill values
│   ├── firebase-service-account.json   ← (you provide this)
│   ├── routers/
│   │   ├── records.py        ← Student record CRUD endpoints
│   │   └── admin.py          ← Auth endpoints (login, change-password)
│   └── services/
│       ├── grade_service.py  ← Grade band calculation (replaces room_service)
│       └── date_utils.py     ← IST date formatting (reused from Guesthouse)
└── frontend/
    ├── index.html            ← Main page
    ├── style.css             ← Dark premium UI
    └── app.js                ← All frontend logic
```

## Setup

### 1. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Copy and fill in your environment variables
cp .env.example .env
# → Set ADMIN_ID, ADMIN_PASS_DEFAULT, JWT_SECRET, FIREBASE_PROJECT_ID
# → Place your firebase-service-account.json in backend/

uvicorn main:app --reload --port 8000
# API docs: http://localhost:8000/api/docs
```

### 2. Frontend

Open `frontend/index.html` with a Live Server (VS Code extension) or:

```bash
cd frontend
npx serve .
# → http://localhost:5500
```

> Make sure `API_BASE` in `frontend/app.js` points to `http://localhost:8000`.

## API Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/records` | No | Add a student record |
| `GET` | `/api/records/analytics` | No | Class summary stats |
| `GET` | `/api/records` | JWT | List all records |
| `GET` | `/api/records/{id}` | JWT | Get single record |
| `PATCH` | `/api/records/{id}/status` | JWT | Mark Reviewed / Archived |
| `DELETE` | `/api/records/{id}` | JWT | Delete record |
| `POST` | `/api/records/cleanup` | JWT | Remove old archives |
| `POST` | `/api/auth/login` | No | Get JWT token |
| `POST` | `/api/auth/change-password` | JWT | Change admin password |

## Grade Scale

| % Score | Grade |
|---|---|
| 90 – 100 | Outstanding |
| 75 – 89 | Excellent |
| 60 – 74 | Good |
| 40 – 59 | Average |
| 0 – 39 | Needs Work |

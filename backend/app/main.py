"""
Backend API for the microservices lab.

Responsibilities (per the lab spec):
- Accept text data from the frontend, append server-side date/time, store in Postgres.
- Return all stored entries (with their appended date/time) to the frontend on request.
- The frontend NEVER talks to the database directly -- only through this API.
"""

import os
import time
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Configuration (from environment variables -- set via `docker run -e` or
# Compose/pipeline, never hardcoded, per 12-factor app practice)
# ---------------------------------------------------------------------------
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "labdb")
DB_USER = os.environ.get("DB_USER", "labuser")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "labpassword")

# Allow the frontend's origin to call this API from the browser (CORS).
# In production, restrict this to your actual domain instead of "*".
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*").split(",")

app = FastAPI(title="MSA Lab Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Database connection helper
# ---------------------------------------------------------------------------
def get_connection(retries: int = 5, delay_seconds: float = 2.0):
    """
    Connect to Postgres, retrying briefly on failure.

    Why retries: on `docker compose up` / instance boot, the backend
    container can start before Postgres is fully ready to accept
    connections (see doc 03.7's note on `depends_on` only waiting for
    container start, not app readiness). A short retry loop here makes
    the backend resilient to that race instead of crash-looping.
    """
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                dbname=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
                connect_timeout=5,
            )
            return conn
        except psycopg2.OperationalError as exc:
            last_error = exc
            time.sleep(delay_seconds)
    raise last_error


def init_db():
    """Create the entries table if it doesn't already exist."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS entries (
                    id SERIAL PRIMARY KEY,
                    text_data TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL
                );
                """
            )
        conn.commit()
    finally:
        conn.close()


@app.on_event("startup")
def on_startup():
    init_db()


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------
class EntryCreate(BaseModel):
    text: str


class EntryOut(BaseModel):
    id: int
    text: str
    created_at: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    """Used by the ALB target group health check (see doc 05)."""
    return {"status": "ok"}


@app.post("/api/entries", response_model=EntryOut, status_code=201)
def create_entry(entry: EntryCreate):
    if not entry.text or not entry.text.strip():
        raise HTTPException(status_code=400, detail="text must not be empty")

    now = datetime.now(timezone.utc)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO entries (text_data, created_at) VALUES (%s, %s) RETURNING id;",
                (entry.text.strip(), now),
            )
            new_id = cur.fetchone()[0]
        conn.commit()
    finally:
        conn.close()

    return EntryOut(id=new_id, text=entry.text.strip(), created_at=now.isoformat())


@app.get("/api/entries", response_model=list[EntryOut])
def list_entries():
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, text_data, created_at FROM entries ORDER BY created_at DESC;"
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    return [
        EntryOut(id=row["id"], text=row["text_data"], created_at=row["created_at"].isoformat())
        for row in rows
    ]

"""SQLite-backed analysis session memory.

Phase 4 keeps a lightweight audit trail of what the analyst reviewed, asked,
and generated during a research session.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from src.utils.config import PROJECT_ROOT, get_settings


@dataclass
class AnalysisSession:
    """Saved analysis session metadata."""

    id: int
    name: str
    ticker: str
    created_at: str
    updated_at: str


@dataclass
class AnalysisEvent:
    """One saved event in an analysis session."""

    id: int
    session_id: int
    event_type: str
    document_name: str
    question: str
    content: str
    created_at: str


def get_database_path() -> Path:
    """Return configured SQLite database path."""

    path = PROJECT_ROOT / get_settings().sqlite_db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def connect() -> sqlite3.Connection:
    """Open a SQLite connection with row access by column name."""

    connection = sqlite3.connect(get_database_path())
    connection.row_factory = sqlite3.Row
    return connection


def initialize_session_store() -> None:
    """Create Phase 4 persistence tables."""

    with connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                ticker TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                document_name TEXT NOT NULL DEFAULT '',
                question TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES analysis_sessions(id)
            )
            """
        )


def utc_now() -> str:
    """Return an ISO timestamp."""

    return datetime.now(UTC).replace(microsecond=0).isoformat()


def create_analysis_session(name: str, ticker: str = "") -> int:
    """Create a new analysis session and return its ID."""

    timestamp = utc_now()
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO analysis_sessions (name, ticker, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (name.strip() or "Untitled Analysis Session", ticker.upper().strip(), timestamp, timestamp),
        )
        return int(cursor.lastrowid)


def list_analysis_sessions(limit: int = 20) -> list[AnalysisSession]:
    """Return recent analysis sessions."""

    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, name, ticker, created_at, updated_at
            FROM analysis_sessions
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [AnalysisSession(**dict(row)) for row in rows]


def save_analysis_event(
    session_id: int,
    event_type: str,
    content: str,
    document_name: str = "",
    question: str = "",
) -> int:
    """Save one session event."""

    timestamp = utc_now()
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO analysis_events
                (session_id, event_type, document_name, question, content, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session_id, event_type, document_name, question, content, timestamp),
        )
        connection.execute(
            "UPDATE analysis_sessions SET updated_at = ? WHERE id = ?",
            (timestamp, session_id),
        )
        return int(cursor.lastrowid)


def list_analysis_events(session_id: int, limit: int = 50) -> list[AnalysisEvent]:
    """Return events for one analysis session."""

    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, session_id, event_type, document_name, question, content, created_at
            FROM analysis_events
            WHERE session_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
    return [AnalysisEvent(**dict(row)) for row in rows]


def export_session_markdown(session_id: int) -> str:
    """Export one analysis session as Markdown."""

    sessions = [session for session in list_analysis_sessions(limit=100) if session.id == session_id]
    if not sessions:
        return "# Analysis Session\n\nSession not found."

    session = sessions[0]
    events = list(reversed(list_analysis_events(session_id=session_id, limit=200)))
    lines = [
        f"# {session.name}",
        "",
        f"- Ticker: {session.ticker or 'Not specified'}",
        f"- Created: {session.created_at}",
        f"- Updated: {session.updated_at}",
        "",
    ]
    for event in events:
        lines.extend(
            [
                f"## {event.event_type.replace('_', ' ').title()}",
                "",
                f"- Time: {event.created_at}",
                f"- Document: {event.document_name or 'Not specified'}",
            ]
        )
        if event.question:
            lines.append(f"- Question: {event.question}")
        lines.extend(["", event.content, ""])
    return "\n".join(lines)

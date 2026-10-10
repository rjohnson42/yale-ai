"""SQLite access for the SOM catalog and per-user chat."""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path

from models import Course

ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = ROOT / "data" / "yale_som.db"
ACCOUNTS_PATH = ROOT / "data" / "accounts.db"
_HASH_ROUNDS = 200_000

_ACCOUNT_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    role TEXT NOT NULL,
    text TEXT NOT NULL,
    tools_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS messages_user_id ON messages(user_id);
"""


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class _Connection(sqlite3.Connection):
    """Commit or roll back, then close. sqlite's own context manager leaves it open."""

    def __exit__(self, exc_type, exc_value, traceback) -> None:  # type: ignore[override]
        try:
            if exc_type is None:
                self.commit()
            else:
                self.rollback()
        finally:
            self.close()


def connect_catalog() -> sqlite3.Connection:
    if not CATALOG_PATH.is_file():
        raise FileNotFoundError(
            f"Missing course database {CATALOG_PATH}. Expected data/yale_som.db."
        )
    connection = sqlite3.connect(CATALOG_PATH, factory=_Connection)
    connection.row_factory = sqlite3.Row
    return connection


def connect_accounts() -> sqlite3.Connection:
    ACCOUNTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(ACCOUNTS_PATH, factory=_Connection)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(_ACCOUNT_SCHEMA)
    return connection


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def course_from_row(row: sqlite3.Row) -> Course:
    return Course.model_validate(
        {
            "Course ID": _text(row["course_id"]),
            "Course Number": _text(row["course_number"]),
            "Course Title": _text(row["course_title"]),
            "Course Category": _text(row["course_category"]),
            "Course Type": _text(row["course_type"]),
            "Course Session": _text(row["course_session"]),
            "Course Description": _text(row["course_description"]),
            "Faculty 1": _text(row["faculty_1"]),
            "Faculty 1 Email": _text(row["faculty_1_email"]),
            "faculty_bio": _text(row["faculty_bio"]),
            "Daytimes": _text(row["daytimes"]),
            "Timings Day": _text(row["timings_day"]),
            "Timings StartTime": _text(row["timings_start"]),
            "Timings EndTime": _text(row["timings_end"]),
            "Room": _text(row["room"]),
            "Section": _text(row["section"]),
            "Units": _text(row["units"]),
            "TermCode": _text(row["term_code"]),
            "Syllabus": _text(row["syllabus"]),
            "Old Syllabus": _text(row["old_syllabus"]),
        }
    )


def fetch_courses() -> list[Course]:
    """Read every row of the courses table, in catalog order."""
    with connect_catalog() as connection:
        rows = connection.execute(
            """
            SELECT course_id, course_number, course_title, course_category, course_type,
                   course_session, course_description, faculty_1, faculty_1_email, faculty_bio,
                   daytimes, timings_day, timings_start, timings_end, room, section, units,
                   term_code, syllabus, old_syllabus
            FROM courses
            ORDER BY id
            """
        ).fetchall()
    return [course_from_row(row) for row in rows]


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _HASH_ROUNDS)
    return f"pbkdf2_sha256${_HASH_ROUNDS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, rounds, salt_hex, digest_hex = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        check = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
            bytes.fromhex(salt_hex),
            int(rounds),
        )
    except (ValueError, TypeError):
        return False
    return secrets.compare_digest(check.hex(), digest_hex)


def _user_dict(row: sqlite3.Row) -> dict[str, object]:
    return {"id": row["id"], "email": row["email"], "name": row["name"]}


def create_user(email: str, password: str, name: str) -> dict[str, object]:
    cleaned = email.strip().lower()
    display = name.strip() or cleaned.split("@", 1)[0]
    with connect_accounts() as connection:
        try:
            cursor = connection.execute(
                """
                INSERT INTO users (email, name, password_hash, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (cleaned, display, hash_password(password), _now()),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("An account with that email already exists.") from exc
        row = connection.execute(
            "SELECT id, email, name FROM users WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
    if row is None:
        raise RuntimeError("Account was created but could not be read back.")
    return _user_dict(row)


def authenticate(email: str, password: str) -> dict[str, object] | None:
    with connect_accounts() as connection:
        row = connection.execute(
            "SELECT id, email, name, password_hash FROM users WHERE email = ?",
            (email.strip().lower(),),
        ).fetchone()
    if row is None or not verify_password(password, row["password_hash"]):
        return None
    return _user_dict(row)


def open_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with connect_accounts() as connection:
        connection.execute(
            "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
            (token, user_id, _now()),
        )
    return token


def user_for_token(token: str) -> dict[str, object] | None:
    if not token:
        return None
    with connect_accounts() as connection:
        row = connection.execute(
            """
            SELECT users.id, users.email, users.name
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token = ?
            """,
            (token,),
        ).fetchone()
    return _user_dict(row) if row else None


def close_session(token: str) -> None:
    with connect_accounts() as connection:
        connection.execute("DELETE FROM sessions WHERE token = ?", (token,))


def add_message(user_id: int, role: str, text: str, tools: list[str]) -> dict[str, object]:
    created = _now()
    payload = json.dumps(tools)
    with connect_accounts() as connection:
        cursor = connection.execute(
            """
            INSERT INTO messages (user_id, role, text, tools_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, role, text, payload, created),
        )
        message_id = cursor.lastrowid
    return {
        "id": message_id,
        "role": role,
        "text": text,
        "tools": tools,
        "created_at": created,
    }


def list_messages(user_id: int) -> list[dict[str, object]]:
    with connect_accounts() as connection:
        rows = connection.execute(
            """
            SELECT id, role, text, tools_json, created_at
            FROM messages
            WHERE user_id = ?
            ORDER BY id
            """,
            (user_id,),
        ).fetchall()
    messages: list[dict[str, object]] = []
    for row in rows:
        try:
            tools = json.loads(row["tools_json"])
        except json.JSONDecodeError:
            tools = []
        if not isinstance(tools, list):
            tools = []
        messages.append(
            {
                "id": row["id"],
                "role": row["role"],
                "text": row["text"],
                "tools": [str(tool) for tool in tools],
                "created_at": row["created_at"],
            }
        )
    return messages

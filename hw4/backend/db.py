"""SQLite access for Campus Customs accounts. Passwords never leave this module."""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from passwords import hash_password, verify_against_account

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "campus_customs.db"
SESSION_DAYS = 14

_SESSION_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL
);
"""


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _stamp(moment: datetime | None = None) -> str:
    return (moment or _now()).strftime("%Y-%m-%d %H:%M:%S")


def connect() -> sqlite3.Connection:
    if not DB_PATH.is_file():
        raise FileNotFoundError(f"Missing database {DB_PATH}.")
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def ensure_sessions() -> None:
    with connect() as connection:
        connection.executescript(_SESSION_SCHEMA)
        connection.commit()


def public_user(row: sqlite3.Row) -> dict[str, object]:
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "first_name": row["first_name"] or "",
        "last_name": row["last_name"] or "",
    }


def create_user(first_name: str, last_name: str, email: str, password: str) -> dict[str, object]:
    display = f"{first_name} {last_name}".strip()
    with connect() as connection:
        try:
            cursor = connection.execute(
                """
                INSERT INTO users (name, email, password_hash, first_name, last_name)
                VALUES (?, ?, ?, ?, ?)
                """,
                (display, email, hash_password(password), first_name, last_name),
            )
            connection.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError("That email already has an account. Try logging in.") from exc
        row = connection.execute(
            """
            SELECT id, email, name, first_name, last_name
            FROM users WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
    if row is None:
        raise RuntimeError("Account was created but could not be read back.")
    return public_user(row)


def authenticate(email: str, password: str) -> dict[str, object] | None:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT id, email, name, first_name, last_name, password_hash
            FROM users WHERE email = ?
            """,
            (email,),
        ).fetchone()
    stored = str(row["password_hash"]) if row is not None else None
    if not verify_against_account(password, stored) or row is None:
        return None
    return public_user(row)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def open_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with connect() as connection:
        connection.execute(
            "INSERT INTO sessions (token_hash, user_id, created_at) VALUES (?, ?, ?)",
            (_token_hash(token), user_id, _stamp()),
        )
        connection.commit()
    return token


def user_for_token(token: str) -> dict[str, object] | None:
    if not token:
        return None
    cutoff = _stamp(_now() - timedelta(days=SESSION_DAYS))
    with connect() as connection:
        connection.execute("DELETE FROM sessions WHERE created_at < ?", (cutoff,))
        row = connection.execute(
            """
            SELECT u.id, u.email, u.name, u.first_name, u.last_name
            FROM sessions AS s
            JOIN users AS u ON u.id = s.user_id
            WHERE s.token_hash = ?
            """,
            (_token_hash(token),),
        ).fetchone()
        connection.commit()
    if row is None:
        return None
    return public_user(row)


def close_session(token: str) -> None:
    if not token:
        return
    with connect() as connection:
        connection.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))
        connection.commit()


def list_messages(user_id: int) -> list[dict[str, object]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, role, content, products_json, created_at
            FROM chat_messages
            WHERE user_id = ?
            ORDER BY id
            """,
            (user_id,),
        ).fetchall()
    messages: list[dict[str, object]] = []
    for row in rows:
        try:
            products = json.loads(row["products_json"] or "[]")
        except json.JSONDecodeError:
            products = []
        if not isinstance(products, list):
            products = []
        messages.append(
            {
                "id": row["id"],
                "role": row["role"],
                "content": row["content"],
                "products": products,
                "created_at": row["created_at"],
            }
        )
    return messages


def add_message(user_id: int, role: str, content: str, products: list[dict[str, object]]) -> dict[str, object]:
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO chat_messages (user_id, role, content, products_json)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, role, content, json.dumps(products)),
        )
        connection.commit()
        row = connection.execute(
            """
            SELECT id, role, content, products_json, created_at
            FROM chat_messages WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
    if row is None:
        raise RuntimeError("Chat message was saved but could not be read back.")
    return {
        "id": row["id"],
        "role": row["role"],
        "content": row["content"],
        "products": products,
        "created_at": row["created_at"],
    }

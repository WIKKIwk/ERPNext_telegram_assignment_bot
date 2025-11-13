from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _utcnow() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


class AssignmentError(RuntimeError):
    """Raised when assignment constraints are violated."""


@dataclass(frozen=True)
class Candidate:
    telegram_id: int
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    started_at: str

    @property
    def display_label(self) -> str:
        name_parts = [part for part in (self.first_name, self.last_name) if part]
        if name_parts:
            return " ".join(name_parts)
        if self.username:
            return f"@{self.username}"
        return str(self.telegram_id)


class AssignmentStorage:
    """SQLite persistence for sales manager assignment bot."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        if self.db_path.parent and not self.db_path.parent.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialise_schema()

    @contextmanager
    def _connection(self) -> Iterable[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _initialise_schema(self) -> None:
        with self._connection() as conn:
            conn.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    started_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chats (
                    chat_id INTEGER PRIMARY KEY,
                    title TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS assignments (
                    chat_id INTEGER PRIMARY KEY,
                    user_id INTEGER UNIQUE NOT NULL,
                    assigned_at TEXT NOT NULL,
                    api_key TEXT,
                    api_secret TEXT,
                    credentials_status TEXT,
                    customer_docname TEXT,
                    FOREIGN KEY (chat_id) REFERENCES chats(chat_id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(telegram_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS item_drafts (
                    user_id INTEGER PRIMARY KEY,
                    state TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(telegram_id) ON DELETE CASCADE
                );
                """
            )
            self._ensure_assignment_columns(conn)

    def _ensure_assignment_columns(self, conn: sqlite3.Connection) -> None:
        """Upgrade helper to add new columns for credentials."""

        info = conn.execute("PRAGMA table_info(assignments)").fetchall()
        columns = {row["name"] for row in info}
        upgrades = []
        if "api_key" not in columns:
            upgrades.append("ALTER TABLE assignments ADD COLUMN api_key TEXT")
        if "api_secret" not in columns:
            upgrades.append("ALTER TABLE assignments ADD COLUMN api_secret TEXT")
        if "credentials_status" not in columns:
            upgrades.append("ALTER TABLE assignments ADD COLUMN credentials_status TEXT")
        if "customer_docname" not in columns:
            upgrades.append("ALTER TABLE assignments ADD COLUMN customer_docname TEXT")
        for statement in upgrades:
            conn.execute(statement)

    # ---------------------------------------------------------------- users
    def record_user(
        self,
        telegram_id: int,
        *,
        username: Optional[str],
        first_name: Optional[str],
        last_name: Optional[str],
    ) -> bool:
        """Register or update a user who interacted via private chat.

        Returns True when the user was created for the first time.
        """
        now = _utcnow()
        with self._lock, self._connection() as conn:
            row = conn.execute(
                "SELECT telegram_id FROM users WHERE telegram_id = ?",
                (telegram_id,),
            ).fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE users
                    SET username = ?, first_name = ?, last_name = ?, updated_at = ?
                    WHERE telegram_id = ?
                    """,
                    (username, first_name, last_name, now, telegram_id),
                )
                return False
            conn.execute(
                """
                INSERT INTO users (telegram_id, username, first_name, last_name, started_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (telegram_id, username, first_name, last_name, now, now),
            )
            return True

    def record_private_user(
        self,
        telegram_id: int,
        *,
        username: Optional[str],
        first_name: Optional[str],
        last_name: Optional[str],
    ) -> bool:
        """Backward-compatible wrapper for record_user."""

        return self.record_user(
            telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
        )

    def get_user(self, telegram_id: int) -> Optional[Candidate]:
        with self._lock, self._connection() as conn:
            row = conn.execute(
                """
                SELECT telegram_id, username, first_name, last_name, started_at
                FROM users
                WHERE telegram_id = ?
                """,
                (telegram_id,),
            ).fetchone()
            if not row:
                return None
            return Candidate(
                telegram_id=row["telegram_id"],
                username=row["username"],
                first_name=row["first_name"],
                last_name=row["last_name"],
                started_at=row["started_at"],
            )

    def list_unassigned_users(self, *, limit: int = 25) -> List[Candidate]:
        with self._lock, self._connection() as conn:
            rows = conn.execute(
                """
                SELECT u.telegram_id, u.username, u.first_name, u.last_name, u.started_at
                FROM users AS u
                LEFT JOIN assignments AS a ON a.user_id = u.telegram_id
                WHERE a.user_id IS NULL
                ORDER BY
                    COALESCE(NULLIF(TRIM(u.first_name || ' ' || IFNULL(u.last_name, '')), ''), u.username, u.telegram_id)
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        candidates: List[Candidate] = []
        for row in rows:
            candidates.append(
                Candidate(
                    telegram_id=row["telegram_id"],
                    username=row["username"],
                    first_name=row["first_name"],
                    last_name=row["last_name"],
                    started_at=row["started_at"],
                )
            )
        return candidates

    # ---------------------------------------------------------------- chats
    def record_group_chat(self, chat_id: int, *, title: Optional[str]) -> None:
        now = _utcnow()
        with self._lock, self._connection() as conn:
            existing = conn.execute(
                "SELECT chat_id FROM chats WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE chats
                    SET title = COALESCE(?, title), updated_at = ?
                    WHERE chat_id = ?
                    """,
                    (title, now, chat_id),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO chats (chat_id, title, created_at, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (chat_id, title, now, now),
                )

    def get_chat(self, chat_id: int) -> Optional[Dict[str, Optional[str]]]:
        with self._lock, self._connection() as conn:
            row = conn.execute(
                "SELECT chat_id, title, created_at, updated_at FROM chats WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
            if not row:
                return None
            return {
                "chat_id": row["chat_id"],
                "title": row["title"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }

    # --------------------------------------------------------------- assignment
    def get_group_assignment(self, chat_id: int) -> Optional[Dict[str, Optional[str]]]:
        with self._lock, self._connection() as conn:
            row = conn.execute(
                """
                SELECT
                    a.chat_id,
                    a.user_id,
                    a.assigned_at,
                    a.api_key,
                    a.api_secret,
                    a.credentials_status,
                    a.customer_docname,
                    c.title,
                    u.username,
                    u.first_name,
                    u.last_name
                FROM assignments AS a
                JOIN chats AS c ON c.chat_id = a.chat_id
                JOIN users AS u ON u.telegram_id = a.user_id
                WHERE a.chat_id = ?
                """,
                (chat_id,),
            ).fetchone()
            if not row:
                return None
            return {
                "chat_id": row["chat_id"],
                "user_id": row["user_id"],
                "assigned_at": row["assigned_at"],
                "api_key": row["api_key"],
                "api_secret": row["api_secret"],
                "credentials_status": row["credentials_status"],
                "customer_docname": row["customer_docname"],
                "title": row["title"],
                "username": row["username"],
                "first_name": row["first_name"],
                "last_name": row["last_name"],
            }

    def get_user_assignment(self, telegram_id: int) -> Optional[Dict[str, Optional[str]]]:
        with self._lock, self._connection() as conn:
            row = conn.execute(
                """
                SELECT
                    a.chat_id,
                    a.user_id,
                    a.assigned_at,
                    a.api_key,
                    a.api_secret,
                    a.credentials_status,
                    a.customer_docname,
                    c.title,
                    u.username,
                    u.first_name,
                    u.last_name
                FROM assignments AS a
                JOIN chats AS c ON c.chat_id = a.chat_id
                JOIN users AS u ON u.telegram_id = a.user_id
                WHERE a.user_id = ?
                """,
                (telegram_id,),
            ).fetchone()
            if not row:
                return None
            return {
                "chat_id": row["chat_id"],
                "user_id": row["user_id"],
                "assigned_at": row["assigned_at"],
                "api_key": row["api_key"],
                "api_secret": row["api_secret"],
                "credentials_status": row["credentials_status"],
                "customer_docname": row["customer_docname"],
                "title": row["title"],
                "username": row["username"],
                "first_name": row["first_name"],
                 "last_name": row["last_name"],
            }

    def assign_sales_manager(self, *, chat_id: int, user_id: int) -> None:
        now = _utcnow()
        with self._lock, self._connection() as conn:
            chat_row = conn.execute(
                "SELECT chat_id FROM chats WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
            if not chat_row:
                conn.execute(
                    """
                    INSERT INTO chats (chat_id, title, created_at, updated_at)
                    VALUES (?, NULL, ?, ?)
                    """,
                    (chat_id, now, now),
                )

            user_row = conn.execute(
                "SELECT telegram_id FROM users WHERE telegram_id = ?",
                (user_id,),
            ).fetchone()
            if not user_row:
                raise AssignmentError("Foydalanuvchi botga shaxsiy chatda /start yubormagan.")

            existing_group = conn.execute(
                "SELECT user_id FROM assignments WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
            if existing_group:
                raise AssignmentError("Bu guruh uchun sales manager allaqachon tanlangan.")

            existing_user = conn.execute(
                "SELECT chat_id FROM assignments WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if existing_user:
                raise AssignmentError("Bu foydalanuvchi boshqa guruhda sales manager sifatida tayinlangan.")

            conn.execute(
                """
                INSERT INTO assignments (chat_id, user_id, assigned_at, api_key, api_secret, credentials_status, customer_docname)
                VALUES (?, ?, ?, NULL, NULL, 'pending_key', NULL)
                """,
                (chat_id, user_id, now),
            )

    def store_api_key(self, user_id: int, api_key: str) -> None:
        with self._lock, self._connection() as conn:
            updated = conn.execute(
                """
                UPDATE assignments
                SET api_key = ?, credentials_status = 'pending_secret'
                WHERE user_id = ?
                """,
                (api_key, user_id),
            )
            if updated.rowcount == 0:
                raise AssignmentError("Foydalanuvchi sales manager sifatida topilmadi.")

    def store_api_secret(self, user_id: int, api_secret: str, *, verified: bool) -> None:
        status = "active" if verified else "pending_secret"
        with self._lock, self._connection() as conn:
            updated = conn.execute(
                """
                UPDATE assignments
                SET api_secret = ?, credentials_status = ?
                WHERE user_id = ?
                """,
                (api_secret, status, user_id),
            )
            if updated.rowcount == 0:
                raise AssignmentError("Foydalanuvchi sales manager sifatida topilmadi.")

    def reset_credentials(self, user_id: int) -> None:
        with self._lock, self._connection() as conn:
            updated = conn.execute(
                """
                UPDATE assignments
                SET api_key = NULL,
                    api_secret = NULL,
                    credentials_status = 'pending_key'
                WHERE user_id = ?
                """,
                (user_id,),
            )
            if updated.rowcount == 0:
                raise AssignmentError("Foydalanuvchi sales manager sifatida topilmadi.")

    def reset_all(self) -> None:
        """Dangerous helper used only for tests."""
        with self._lock, self._connection() as conn:
            conn.executescript(
                """
                DELETE FROM assignments;
                DELETE FROM chats;
                DELETE FROM users;
                """
            )

    def clear_all_assignments(self) -> None:
        """Remove all assignments and credential data, keeping user records."""

        with self._lock, self._connection() as conn:
            conn.executescript(
                """
                DELETE FROM assignments;
                """
            )

    # --------------------------------------------------------- item drafts
    def get_item_draft(self, user_id: int) -> Optional[Dict[str, Any]]:
        with self._lock, self._connection() as conn:
            row = conn.execute(
                "SELECT state FROM item_drafts WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not row:
                return None
            try:
                return json.loads(row["state"])
            except json.JSONDecodeError:
                return None

    def save_item_draft(self, user_id: int, state: Dict[str, Any]) -> None:
        payload = json.dumps(state)
        now = _utcnow()
        with self._lock, self._connection() as conn:
            conn.execute(
                """
                INSERT INTO item_drafts (user_id, state, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id)
                DO UPDATE SET state = excluded.state, updated_at = excluded.updated_at
                """,
                (user_id, payload, now),
            )

    def delete_item_draft(self, user_id: int) -> None:
        with self._lock, self._connection() as conn:
            conn.execute("DELETE FROM item_drafts WHERE user_id = ?", (user_id,))

    def store_customer_doc(self, chat_id: int, docname: str) -> None:
        with self._lock, self._connection() as conn:
            conn.execute(
                """
                UPDATE assignments
                SET customer_docname = ?
                WHERE chat_id = ?
                """,
                (docname, chat_id),
            )

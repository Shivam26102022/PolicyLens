from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from policylens.conversations.models import (
    ConversationSession,
    ConversationTurn,
    ConversationTurnPage,
    SessionPage,
    Workspace,
)
from policylens.settings import PROJECT_ROOT

# Serverless deployments have a read-only project directory; /tmp is the only writable path.
DEFAULT_CONVERSATION_DATABASE = (
    Path("/tmp/policylens_conversations.sqlite3")
    if os.environ.get("VERCEL")
    else PROJECT_ROOT / "data" / "indexes" / "policylens_conversations.sqlite3"
)


class ConversationNotFoundError(LookupError):
    """Raised when a session or turn is unavailable in the requested workspace."""


class ConversationStateError(ValueError):
    """Raised when a turn cannot make the requested state transition."""


class ConversationStore:
    def __init__(self, database_path: Path | str | None = None) -> None:
        self.database_path = Path(database_path or DEFAULT_CONVERSATION_DATABASE)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _transaction(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(
            self.database_path,
            timeout=30,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        try:
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._transaction(write=True) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS workspaces (
                    workspace_id TEXT PRIMARY KEY,
                    data_use_acknowledged INTEGER NOT NULL DEFAULT 1
                        CHECK (data_use_acknowledged IN (0, 1)),
                    data_use_acknowledged_at TEXT,
                    long_memory_enabled INTEGER NOT NULL DEFAULT 0
                        CHECK (long_memory_enabled IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (long_memory_enabled = 0 OR data_use_acknowledged = 1)
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id)
                        ON DELETE CASCADE,
                    title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 80),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS sessions_workspace_updated
                    ON sessions(workspace_id, updated_at DESC, session_id);

                CREATE TABLE IF NOT EXISTS turns (
                    turn_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(session_id)
                        ON DELETE CASCADE,
                    position INTEGER NOT NULL CHECK (position > 0),
                    user_content TEXT NOT NULL CHECK (length(user_content) BETWEEN 1 AND 4000),
                    assistant_content TEXT CHECK (
                        assistant_content IS NULL OR length(assistant_content) <= 12000
                    ),
                    answer_json TEXT,
                    status TEXT NOT NULL CHECK (
                        status IN ('in_progress', 'completed', 'failed')
                    ),
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    UNIQUE(session_id, position),
                    CHECK (
                        status != 'completed'
                        OR (assistant_content IS NOT NULL AND length(trim(assistant_content)) > 0)
                    )
                );
                CREATE INDEX IF NOT EXISTS turns_session_position
                    ON turns(session_id, position);
                """
            )

    def create_workspace(
        self,
        workspace_id: UUID,
        *,
        data_use_acknowledged: bool = True,
        long_memory_enabled: bool = False,
    ) -> Workspace:
        now = _timestamp()
        acknowledged = data_use_acknowledged or long_memory_enabled
        acknowledged_at = now if acknowledged else None
        with self._transaction(write=True) as connection:
            connection.execute(
                """
                INSERT INTO workspaces (
                    workspace_id, data_use_acknowledged, data_use_acknowledged_at,
                    long_memory_enabled, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(workspace_id) DO NOTHING
                """,
                (
                    str(workspace_id),
                    int(acknowledged),
                    acknowledged_at,
                    int(long_memory_enabled),
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM workspaces WHERE workspace_id = ?",
                (str(workspace_id),),
            ).fetchone()
        return _workspace_from_row(row)

    def get_workspace(self, workspace_id: UUID) -> Workspace | None:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM workspaces WHERE workspace_id = ?",
                (str(workspace_id),),
            ).fetchone()
        return _workspace_from_row(row) if row is not None else None

    def update_workspace_preferences(
        self,
        workspace_id: UUID,
        *,
        data_use_acknowledged: bool | None = None,
        long_memory_enabled: bool | None = None,
    ) -> Workspace:
        current = self.get_workspace(workspace_id)
        if current is None:
            current = self.create_workspace(workspace_id)
        acknowledged = (
            current.data_use_acknowledged
            if data_use_acknowledged is None
            else data_use_acknowledged
        )
        memory_enabled = (
            current.long_memory_enabled if long_memory_enabled is None else long_memory_enabled
        )
        # Older database schemas require the legacy flag when memory is enabled.
        # This is stored only for schema compatibility; it is never a chat gate.
        acknowledged = acknowledged or memory_enabled
        now = _timestamp()
        acknowledged_at = (
            now
            if acknowledged and not current.data_use_acknowledged
            else current.data_use_acknowledged_at
            if acknowledged
            else None
        )
        with self._transaction(write=True) as connection:
            connection.execute(
                """
                UPDATE workspaces
                SET data_use_acknowledged = ?, data_use_acknowledged_at = ?,
                    long_memory_enabled = ?, updated_at = ?
                WHERE workspace_id = ?
                """,
                (
                    int(acknowledged),
                    acknowledged_at,
                    int(memory_enabled),
                    now,
                    str(workspace_id),
                ),
            )
            row = connection.execute(
                "SELECT * FROM workspaces WHERE workspace_id = ?",
                (str(workspace_id),),
            ).fetchone()
        return _workspace_from_row(row)

    def create_session(
        self,
        workspace_id: UUID,
        *,
        title: str = "New conversation",
        session_id: UUID | None = None,
    ) -> ConversationSession:
        session = ConversationSession(
            session_id=session_id or uuid4(),
            workspace_id=workspace_id,
            title=title,
        )
        self.create_workspace(workspace_id)
        with self._transaction(write=True) as connection:
            connection.execute(
                """
                INSERT INTO sessions (session_id, workspace_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(session.session_id),
                    str(workspace_id),
                    session.title,
                    _to_iso(session.created_at),
                    _to_iso(session.updated_at),
                ),
            )
        return session

    def get_session(self, workspace_id: UUID, session_id: UUID) -> ConversationSession | None:
        with self._transaction() as connection:
            row = connection.execute(
                """
                SELECT * FROM sessions
                WHERE workspace_id = ? AND session_id = ?
                """,
                (str(workspace_id), str(session_id)),
            ).fetchone()
        return _session_from_row(row) if row is not None else None

    def count_turns(self, workspace_id: UUID, session_id: UUID) -> int:
        with self._transaction() as connection:
            _session_row(connection, workspace_id, session_id)
            row = connection.execute(
                """
                SELECT count(*) AS turn_count FROM turns
                WHERE session_id = ?
                """,
                (str(session_id),),
            ).fetchone()
        return int(row["turn_count"])

    def list_sessions(
        self,
        workspace_id: UUID,
        *,
        limit: int = 50,
        before_session_id: UUID | None = None,
    ) -> SessionPage:
        bounded_limit = _bounded_limit(limit, maximum=50)
        with self._transaction() as connection:
            cursor_row = None
            if before_session_id is not None:
                cursor_row = connection.execute(
                    """
                    SELECT updated_at, session_id FROM sessions
                    WHERE workspace_id = ? AND session_id = ?
                    """,
                    (str(workspace_id), str(before_session_id)),
                ).fetchone()
                if cursor_row is None:
                    return SessionPage(items=())
            if cursor_row is None:
                rows = connection.execute(
                    """
                    SELECT * FROM sessions WHERE workspace_id = ?
                    ORDER BY updated_at DESC, session_id DESC LIMIT ?
                    """,
                    (str(workspace_id), bounded_limit + 1),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM sessions
                    WHERE workspace_id = ?
                      AND (updated_at, session_id) < (?, ?)
                    ORDER BY updated_at DESC, session_id DESC LIMIT ?
                    """,
                    (
                        str(workspace_id),
                        cursor_row["updated_at"],
                        cursor_row["session_id"],
                        bounded_limit + 1,
                    ),
                ).fetchall()
        has_more = len(rows) > bounded_limit
        sessions = tuple(_session_from_row(row) for row in rows[:bounded_limit])
        next_cursor = str(sessions[-1].session_id) if has_more and sessions else None
        return SessionPage(items=sessions, next_cursor=next_cursor)

    def create_turn(
        self,
        workspace_id: UUID,
        session_id: UUID,
        user_content: str,
        *,
        turn_id: UUID | None = None,
    ) -> ConversationTurn:
        turn = ConversationTurn(
            turn_id=turn_id or uuid4(),
            session_id=session_id,
            position=1,
            user_content=user_content,
            status="in_progress",
        )
        now = _timestamp()
        with self._transaction(write=True) as connection:
            session_row = _session_row(connection, workspace_id, session_id)
            position = connection.execute(
                "SELECT COALESCE(MAX(position), 0) + 1 FROM turns WHERE session_id = ?",
                (str(session_id),),
            ).fetchone()[0]
            title = session_row["title"]
            if title == "New conversation":
                first_line = user_content.strip().splitlines()
                title = first_line[0][:80] if first_line else "New conversation"
            connection.execute(
                """
                INSERT INTO turns (
                    turn_id, session_id, position, user_content, assistant_content,
                    answer_json, status, created_at, completed_at
                )
                VALUES (?, ?, ?, ?, NULL, NULL, 'in_progress', ?, NULL)
                """,
                (str(turn.turn_id), str(session_id), position, user_content, now),
            )
            connection.execute(
                "UPDATE sessions SET title = ?, updated_at = ? WHERE session_id = ?",
                (title, now, str(session_id)),
            )
            row = connection.execute(
                "SELECT * FROM turns WHERE turn_id = ?",
                (str(turn.turn_id),),
            ).fetchone()
        return _turn_from_row(row)

    def complete_turn(
        self,
        workspace_id: UUID,
        session_id: UUID,
        turn_id: UUID,
        *,
        assistant_content: str,
        answer_json: dict[str, object] | None = None,
    ) -> ConversationTurn:
        if not assistant_content.strip():
            raise ValueError("assistant response must not be empty")
        now = _timestamp()
        serialized_answer = (
            json.dumps(answer_json, separators=(",", ":"), ensure_ascii=False)
            if answer_json is not None
            else None
        )
        with self._transaction(write=True) as connection:
            _session_row(connection, workspace_id, session_id)
            row = _turn_row(connection, session_id, turn_id)
            if row["status"] != "in_progress":
                raise ConversationStateError("only an in-progress turn can be completed")
            connection.execute(
                """
                UPDATE turns
                SET assistant_content = ?, answer_json = ?, status = 'completed', completed_at = ?
                WHERE turn_id = ? AND session_id = ?
                """,
                (
                    assistant_content,
                    serialized_answer,
                    now,
                    str(turn_id),
                    str(session_id),
                ),
            )
            connection.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                (now, str(session_id)),
            )
            updated = connection.execute(
                "SELECT * FROM turns WHERE turn_id = ?",
                (str(turn_id),),
            ).fetchone()
        return _turn_from_row(updated)

    def fail_turn(
        self,
        workspace_id: UUID,
        session_id: UUID,
        turn_id: UUID,
    ) -> ConversationTurn:
        now = _timestamp()
        with self._transaction(write=True) as connection:
            _session_row(connection, workspace_id, session_id)
            row = _turn_row(connection, session_id, turn_id)
            if row["status"] != "in_progress":
                raise ConversationStateError("only an in-progress turn can be failed")
            connection.execute(
                """
                UPDATE turns SET status = 'failed', completed_at = ?
                WHERE turn_id = ? AND session_id = ?
                """,
                (now, str(turn_id), str(session_id)),
            )
            updated = connection.execute(
                "SELECT * FROM turns WHERE turn_id = ?",
                (str(turn_id),),
            ).fetchone()
        return _turn_from_row(updated)

    def update_completed_turn_answer(
        self,
        workspace_id: UUID,
        session_id: UUID,
        turn_id: UUID,
        answer_json: dict[str, object],
    ) -> ConversationTurn:
        serialized_answer = json.dumps(
            answer_json,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        with self._transaction(write=True) as connection:
            _session_row(connection, workspace_id, session_id)
            row = _turn_row(connection, session_id, turn_id)
            if row["status"] != "completed":
                raise ConversationStateError(
                    "only a completed turn can receive its final answer metadata"
                )
            connection.execute(
                "UPDATE turns SET answer_json = ? WHERE turn_id = ? AND session_id = ?",
                (serialized_answer, str(turn_id), str(session_id)),
            )
            updated = connection.execute(
                "SELECT * FROM turns WHERE turn_id = ?",
                (str(turn_id),),
            ).fetchone()
        return _turn_from_row(updated)

    def get_recent_completed_turns(
        self,
        workspace_id: UUID,
        session_id: UUID,
        *,
        limit: int = 5,
    ) -> tuple[ConversationTurn, ...]:
        bounded_limit = _bounded_limit(limit, maximum=5)
        with self._transaction() as connection:
            _session_row(connection, workspace_id, session_id)
            rows = connection.execute(
                """
                SELECT turns.* FROM turns
                JOIN sessions USING (session_id)
                WHERE sessions.workspace_id = ? AND sessions.session_id = ?
                  AND turns.status = 'completed'
                  AND turns.assistant_content IS NOT NULL
                  AND length(trim(turns.assistant_content)) > 0
                ORDER BY turns.position DESC LIMIT ?
                """,
                (str(workspace_id), str(session_id), bounded_limit),
            ).fetchall()
        return tuple(_turn_from_row(row) for row in reversed(rows))

    def list_turns(
        self,
        workspace_id: UUID,
        session_id: UUID,
        *,
        limit: int = 100,
        before_turn_id: UUID | None = None,
    ) -> ConversationTurnPage:
        bounded_limit = _bounded_limit(limit, maximum=100)
        with self._transaction() as connection:
            _session_row(connection, workspace_id, session_id)
            before_position = None
            if before_turn_id is not None:
                cursor = connection.execute(
                    "SELECT position FROM turns WHERE session_id = ? AND turn_id = ?",
                    (str(session_id), str(before_turn_id)),
                ).fetchone()
                if cursor is None:
                    raise ConversationNotFoundError("conversation turn not found")
                before_position = cursor["position"]
            if before_position is None:
                rows = connection.execute(
                    """
                    SELECT * FROM turns WHERE session_id = ?
                    ORDER BY position DESC LIMIT ?
                    """,
                    (str(session_id), bounded_limit + 1),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM turns WHERE session_id = ? AND position < ?
                    ORDER BY position DESC LIMIT ?
                    """,
                    (str(session_id), before_position, bounded_limit + 1),
                ).fetchall()
        has_more = len(rows) > bounded_limit
        turns = tuple(_turn_from_row(row) for row in reversed(rows[:bounded_limit]))
        next_before_turn_id = turns[0].turn_id if has_more and turns else None
        return ConversationTurnPage(items=turns, next_before_turn_id=next_before_turn_id)

    def delete_session(self, workspace_id: UUID, session_id: UUID) -> bool:
        with self._transaction(write=True) as connection:
            cursor = connection.execute(
                "DELETE FROM sessions WHERE workspace_id = ? AND session_id = ?",
                (str(workspace_id), str(session_id)),
            )
        return cursor.rowcount == 1


def _session_row(
    connection: sqlite3.Connection,
    workspace_id: UUID,
    session_id: UUID,
) -> sqlite3.Row:
    row = connection.execute(
        "SELECT * FROM sessions WHERE workspace_id = ? AND session_id = ?",
        (str(workspace_id), str(session_id)),
    ).fetchone()
    if row is None:
        raise ConversationNotFoundError("conversation session not found")
    return row


def _turn_row(
    connection: sqlite3.Connection,
    session_id: UUID,
    turn_id: UUID,
) -> sqlite3.Row:
    row = connection.execute(
        "SELECT * FROM turns WHERE session_id = ? AND turn_id = ?",
        (str(session_id), str(turn_id)),
    ).fetchone()
    if row is None:
        raise ConversationNotFoundError("conversation turn not found")
    return row


def _bounded_limit(limit: int, *, maximum: int) -> int:
    if limit < 1:
        raise ValueError("limit must be at least one")
    return min(limit, maximum)


def _timestamp() -> str:
    return _to_iso(datetime.now(UTC))


def _to_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _from_iso(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


def _required_from_iso(value: str | None) -> datetime:
    timestamp = _from_iso(value)
    if timestamp is None:
        raise ValueError("required conversation timestamp is missing")
    return timestamp


def _workspace_from_row(row: sqlite3.Row) -> Workspace:
    return Workspace(
        workspace_id=UUID(row["workspace_id"]),
        data_use_acknowledged=bool(row["data_use_acknowledged"]),
        data_use_acknowledged_at=_from_iso(row["data_use_acknowledged_at"]),
        long_memory_enabled=bool(row["long_memory_enabled"]),
        created_at=_required_from_iso(row["created_at"]),
        updated_at=_required_from_iso(row["updated_at"]),
    )


def _session_from_row(row: sqlite3.Row) -> ConversationSession:
    return ConversationSession(
        session_id=UUID(row["session_id"]),
        workspace_id=UUID(row["workspace_id"]),
        title=row["title"],
        created_at=_required_from_iso(row["created_at"]),
        updated_at=_required_from_iso(row["updated_at"]),
    )


def _turn_from_row(row: sqlite3.Row) -> ConversationTurn:
    answer = json.loads(row["answer_json"]) if row["answer_json"] is not None else None
    return ConversationTurn(
        turn_id=UUID(row["turn_id"]),
        session_id=UUID(row["session_id"]),
        position=row["position"],
        user_content=row["user_content"],
        assistant_content=row["assistant_content"],
        answer_json=answer,
        status=row["status"],
        created_at=_required_from_iso(row["created_at"]),
        completed_at=_from_iso(row["completed_at"]),
    )

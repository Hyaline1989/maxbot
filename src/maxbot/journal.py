"""Тестовый SQLite-журнал и защита от повторов."""

from dataclasses import dataclass
from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Iterator


@dataclass(frozen=True, slots=True)
class JournalEntry:
    deal_id: str
    directed_at: str
    processed_at: str
    status: str
    prepared_message: str
    max_message_id: str | None = None
    error_description: str | None = None
    private_status: str | None = None
    private_max_message_id: str | None = None
    private_recipient_id: str | None = None


@dataclass(frozen=True, slots=True)
class PrivateDeliveryEntry:
    deal_id: str
    directed_at: str
    bitrix_user_id: str
    max_user_id: str | None
    status: str
    max_message_id: str | None = None
    error_description: str | None = None


class SQLiteJournal:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def initialize(self) -> None:
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS processing_journal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    deal_id TEXT NOT NULL,
                    directed_at TEXT NOT NULL,
                    processed_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    prepared_message TEXT NOT NULL,
                    max_message_id TEXT,
                    error_description TEXT,
                    private_status TEXT,
                    private_max_message_id TEXT,
                    private_recipient_id TEXT,
                    UNIQUE (deal_id, directed_at)
                )
                """
            )
            columns = {
                str(row[1])
                for row in connection.execute(
                    "PRAGMA table_info(processing_journal)"
                )
            }
            migrations = {
                "private_status": "TEXT",
                "private_max_message_id": "TEXT",
                "private_recipient_id": "TEXT",
            }
            for name, column_type in migrations.items():
                if name not in columns:
                    connection.execute(
                        f"ALTER TABLE processing_journal "
                        f"ADD COLUMN {name} {column_type}"
                    )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS private_delivery_journal (
                    deal_id TEXT NOT NULL,
                    directed_at TEXT NOT NULL,
                    bitrix_user_id TEXT NOT NULL,
                    max_user_id TEXT,
                    status TEXT NOT NULL,
                    max_message_id TEXT,
                    error_description TEXT,
                    PRIMARY KEY (deal_id, directed_at, bitrix_user_id)
                )
                """
            )

    def contains(self, deal_id: str, directed_at: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM processing_journal
                WHERE deal_id = ? AND directed_at = ?
                LIMIT 1
                """,
                (deal_id, directed_at),
            ).fetchone()
        return row is not None

    def add(self, entry: JournalEntry) -> bool:
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO processing_journal (
                        deal_id,
                        directed_at,
                        processed_at,
                        status,
                        prepared_message,
                        max_message_id,
                        error_description,
                        private_status,
                        private_max_message_id,
                        private_recipient_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry.deal_id,
                        entry.directed_at,
                        entry.processed_at,
                        entry.status,
                        entry.prepared_message,
                        entry.max_message_id,
                        entry.error_description,
                        entry.private_status,
                        entry.private_max_message_id,
                        entry.private_recipient_id,
                    ),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def count(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM processing_journal"
            ).fetchone()
        return int(row[0])

    def get(self, deal_id: str, directed_at: str) -> JournalEntry | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT deal_id, directed_at, processed_at, status,
                       prepared_message, max_message_id, error_description,
                       private_status, private_max_message_id,
                       private_recipient_id
                FROM processing_journal
                WHERE deal_id = ? AND directed_at = ?
                """,
                (deal_id, directed_at),
            ).fetchone()
        return JournalEntry(*row) if row else None

    def update_delivery(
        self,
        deal_id: str,
        directed_at: str,
        *,
        status: str,
        max_message_id: str | None = None,
        error_description: str | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE processing_journal
                SET status = ?, max_message_id = ?, error_description = ?
                WHERE deal_id = ? AND directed_at = ?
                """,
                (
                    status,
                    max_message_id,
                    error_description,
                    deal_id,
                    directed_at,
                ),
            )

    def update_private_delivery(
        self,
        deal_id: str,
        directed_at: str,
        *,
        private_status: str,
        private_max_message_id: str | None = None,
        private_recipient_id: str | None = None,
        error_description: str | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE processing_journal
                SET private_status = ?,
                    private_max_message_id = ?,
                    private_recipient_id = ?,
                    error_description = COALESCE(?, error_description)
                WHERE deal_id = ? AND directed_at = ?
                """,
                (
                    private_status,
                    private_max_message_id,
                    private_recipient_id,
                    error_description,
                    deal_id,
                    directed_at,
                ),
            )

    def get_private_delivery(
        self,
        deal_id: str,
        directed_at: str,
        bitrix_user_id: str,
    ) -> PrivateDeliveryEntry | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT deal_id, directed_at, bitrix_user_id, max_user_id,
                       status, max_message_id, error_description
                FROM private_delivery_journal
                WHERE deal_id = ? AND directed_at = ? AND bitrix_user_id = ?
                """,
                (deal_id, directed_at, bitrix_user_id),
            ).fetchone()
        return PrivateDeliveryEntry(*row) if row else None

    def upsert_private_delivery(
        self,
        entry: PrivateDeliveryEntry,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO private_delivery_journal (
                    deal_id, directed_at, bitrix_user_id, max_user_id,
                    status, max_message_id, error_description
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(deal_id, directed_at, bitrix_user_id)
                DO UPDATE SET
                    max_user_id = excluded.max_user_id,
                    status = excluded.status,
                    max_message_id = excluded.max_message_id,
                    error_description = excluded.error_description
                """,
                (
                    entry.deal_id,
                    entry.directed_at,
                    entry.bitrix_user_id,
                    entry.max_user_id,
                    entry.status,
                    entry.max_message_id,
                    entry.error_description,
                ),
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

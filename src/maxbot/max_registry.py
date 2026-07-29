"""Защищённый реестр сотрудников, запустивших MAX-бота."""

from dataclasses import dataclass
from contextlib import closing
from pathlib import Path
import secrets
import sqlite3


@dataclass(frozen=True, slots=True)
class RegisteredManager:
    user_id: str
    first_name: str
    last_name: str
    username: str
    registered_at: int
    bitrix_user_id: str = ""
    binding_code: str = ""


class MaxManagerRegistry:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS max_managers (
                    user_id TEXT PRIMARY KEY,
                    first_name TEXT NOT NULL,
                    last_name TEXT NOT NULL,
                    username TEXT NOT NULL,
                    registered_at INTEGER NOT NULL,
                    bitrix_user_id TEXT,
                    binding_code TEXT
                )
                """
            )
            columns = {
                str(row[1])
                for row in connection.execute(
                    "PRAGMA table_info(max_managers)"
                )
            }
            if "bitrix_user_id" not in columns:
                connection.execute(
                    "ALTER TABLE max_managers "
                    "ADD COLUMN bitrix_user_id TEXT"
                )
            if "binding_code" not in columns:
                connection.execute(
                    "ALTER TABLE max_managers "
                    "ADD COLUMN binding_code TEXT"
                )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                    idx_max_managers_bitrix_user_id
                ON max_managers(bitrix_user_id)
                WHERE bitrix_user_id IS NOT NULL
                  AND bitrix_user_id <> ''
                """
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                    idx_max_managers_binding_code
                ON max_managers(binding_code)
                WHERE binding_code IS NOT NULL
                  AND binding_code <> ''
                """
            )
            rows_without_code = connection.execute(
                """
                SELECT user_id FROM max_managers
                WHERE binding_code IS NULL OR binding_code = ''
                """
            ).fetchall()
            for (user_id,) in rows_without_code:
                connection.execute(
                    """
                    UPDATE max_managers SET binding_code = ?
                    WHERE user_id = ?
                    """,
                    (_new_binding_code(connection), user_id),
                )
            connection.commit()

    def register(self, manager: RegisteredManager) -> RegisteredManager:
        self.initialize()
        with closing(sqlite3.connect(self.path)) as connection:
            existing = connection.execute(
                "SELECT binding_code FROM max_managers WHERE user_id = ?",
                (manager.user_id,),
            ).fetchone()
            binding_code = (
                manager.binding_code
                or (str(existing[0]) if existing and existing[0] else "")
                or _new_binding_code(connection)
            )
            connection.execute(
                """
                INSERT INTO max_managers (
                    user_id, first_name, last_name, username, registered_at,
                    bitrix_user_id, binding_code
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    first_name = excluded.first_name,
                    last_name = excluded.last_name,
                    username = excluded.username,
                    registered_at = excluded.registered_at,
                    bitrix_user_id = CASE
                        WHEN excluded.bitrix_user_id <> ''
                            THEN excluded.bitrix_user_id
                        ELSE max_managers.bitrix_user_id
                    END,
                    binding_code = CASE
                        WHEN max_managers.binding_code IS NULL
                          OR max_managers.binding_code = ''
                            THEN excluded.binding_code
                        ELSE max_managers.binding_code
                    END
                """,
                (
                    manager.user_id,
                    manager.first_name,
                    manager.last_name,
                    manager.username,
                    manager.registered_at,
                    manager.bitrix_user_id,
                    binding_code,
                ),
            )
            connection.commit()
        registered = self.get(manager.user_id)
        if registered is None:
            raise RuntimeError("Регистрация не сохранилась.")
        return registered

    def get(self, user_id: str) -> RegisteredManager | None:
        self.initialize()
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute(
                """
                SELECT user_id, first_name, last_name, username, registered_at,
                       COALESCE(bitrix_user_id, ''),
                       COALESCE(binding_code, '')
                FROM max_managers WHERE user_id = ?
                """,
                (str(user_id),),
            ).fetchone()
        return RegisteredManager(*row) if row else None

    def bind_bitrix_user(self, bitrix_user_id: str, max_user_id: str) -> None:
        normalized_bitrix_id = str(bitrix_user_id).strip()
        normalized_max_id = str(max_user_id).strip()
        if not normalized_bitrix_id or not normalized_max_id:
            raise ValueError("Оба идентификатора обязательны.")
        self.initialize()
        with closing(sqlite3.connect(self.path)) as connection:
            cursor = connection.execute(
                """
                UPDATE max_managers
                SET bitrix_user_id = ?
                WHERE user_id = ?
                """,
                (normalized_bitrix_id, normalized_max_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("Сотрудник сначала должен запустить MAX-бота.")
            connection.commit()

    def get_by_bitrix_user_id(
        self,
        bitrix_user_id: str,
    ) -> RegisteredManager | None:
        self.initialize()
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute(
                """
                SELECT user_id, first_name, last_name, username, registered_at,
                       COALESCE(bitrix_user_id, ''),
                       COALESCE(binding_code, '')
                FROM max_managers
                WHERE bitrix_user_id = ?
                """,
                (str(bitrix_user_id).strip(),),
            ).fetchone()
        return RegisteredManager(*row) if row else None

    def bind_bitrix_user_by_code(
        self,
        bitrix_user_id: str,
        binding_code: str,
    ) -> RegisteredManager:
        normalized_code = str(binding_code).strip()
        self.initialize()
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute(
                """
                SELECT user_id FROM max_managers
                WHERE binding_code = ?
                """,
                (normalized_code,),
            ).fetchone()
        if not row:
            raise ValueError("Код регистрации не найден.")
        self.bind_bitrix_user(bitrix_user_id, str(row[0]))
        manager = self.get(str(row[0]))
        if manager is None:
            raise RuntimeError("Привязка не сохранилась.")
        return manager


def _new_binding_code(connection: sqlite3.Connection) -> str:
    for _ in range(100):
        code = f"{secrets.randbelow(900_000) + 100_000:06d}"
        exists = connection.execute(
            "SELECT 1 FROM max_managers WHERE binding_code = ?",
            (code,),
        ).fetchone()
        if not exists:
            return code
    raise RuntimeError("Не удалось создать уникальный код регистрации.")

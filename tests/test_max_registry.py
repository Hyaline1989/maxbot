from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from maxbot.max_registry import MaxManagerRegistry, RegisteredManager


class MaxManagerRegistryTests(unittest.TestCase):
    def test_existing_registry_receives_binding_codes(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "registry.sqlite3"
            connection = sqlite3.connect(path)
            try:
                connection.execute(
                    """
                    CREATE TABLE max_managers (
                        user_id TEXT PRIMARY KEY,
                        first_name TEXT NOT NULL,
                        last_name TEXT NOT NULL,
                        username TEXT NOT NULL,
                        registered_at INTEGER NOT NULL,
                        bitrix_user_id TEXT
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO max_managers VALUES
                    ('7', 'Иван', '', 'ivan', 100, '95713')
                    """
                )
                connection.commit()
            finally:
                connection.close()

            registry = MaxManagerRegistry(path)
            registry.initialize()
            manager = registry.get("7")

            self.assertRegex(manager.binding_code, r"^\d{6}$")
            self.assertEqual(manager.bitrix_user_id, "95713")

    def test_registration_is_saved_and_updated(self) -> None:
        with TemporaryDirectory() as directory:
            registry = MaxManagerRegistry(Path(directory) / "registry.sqlite3")
            registry.register(
                RegisteredManager("7", "Иван", "", "ivan", 100)
            )
            registry.register(
                RegisteredManager("7", "Иван", "Иванов", "ivan", 200)
            )

            manager = registry.get("7")

            self.assertEqual(manager.last_name, "Иванов")
            self.assertEqual(manager.registered_at, 200)
            self.assertRegex(manager.binding_code, r"^\d{6}$")

    def test_bitrix_employee_is_bound_to_registered_max_user(self) -> None:
        with TemporaryDirectory() as directory:
            registry = MaxManagerRegistry(Path(directory) / "registry.sqlite3")
            registry.register(
                RegisteredManager("7", "Иван", "Иванов", "ivan", 100)
            )

            registry.bind_bitrix_user("95713", "7")

            manager = registry.get_by_bitrix_user_id("95713")
            self.assertIsNotNone(manager)
            self.assertEqual(manager.user_id, "7")
            self.assertEqual(manager.bitrix_user_id, "95713")

    def test_reregistration_preserves_bitrix_binding(self) -> None:
        with TemporaryDirectory() as directory:
            registry = MaxManagerRegistry(Path(directory) / "registry.sqlite3")
            registry.register(
                RegisteredManager(
                    "7",
                    "Иван",
                    "",
                    "ivan",
                    100,
                    bitrix_user_id="95713",
                )
            )

            registry.register(
                RegisteredManager("7", "Иван", "Иванов", "ivan", 200)
            )

            manager = registry.get("7")
            self.assertEqual(manager.bitrix_user_id, "95713")

    def test_binding_code_is_stable_and_can_bind_employee(self) -> None:
        with TemporaryDirectory() as directory:
            registry = MaxManagerRegistry(Path(directory) / "registry.sqlite3")
            first = registry.register(
                RegisteredManager("7", "Иван", "", "ivan", 100)
            )
            second = registry.register(
                RegisteredManager("7", "Иван", "Иванов", "ivan", 200)
            )

            self.assertEqual(first.binding_code, second.binding_code)
            manager = registry.bind_bitrix_user_by_code(
                "95713",
                first.binding_code,
            )

            self.assertEqual(manager.user_id, "7")
            self.assertEqual(manager.bitrix_user_id, "95713")


class FakeDirectClient:
    def __init__(self) -> None:
        self.sent = []

    def send_text_to_user(self, user_id, text):
        self.sent.append((user_id, text))
        return "mid-1"

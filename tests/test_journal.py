from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from maxbot.journal import JournalEntry, SQLiteJournal


class JournalTests(unittest.TestCase):
    def test_initialize_migrates_existing_journal_for_private_delivery(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "journal.sqlite3"
            connection = sqlite3.connect(path)
            try:
                connection.execute(
                    """
                    CREATE TABLE processing_journal (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        deal_id TEXT NOT NULL,
                        directed_at TEXT NOT NULL,
                        processed_at TEXT NOT NULL,
                        status TEXT NOT NULL,
                        prepared_message TEXT NOT NULL,
                        max_message_id TEXT,
                        error_description TEXT,
                        UNIQUE (deal_id, directed_at)
                    )
                    """
                )
                connection.commit()
            finally:
                connection.close()

            journal = SQLiteJournal(path)
            journal.initialize()
            connection = sqlite3.connect(path)
            try:
                columns = {
                    row[1]
                    for row in connection.execute(
                        "PRAGMA table_info(processing_journal)"
                    )
                }
            finally:
                connection.close()

            self.assertIn("private_status", columns)
            self.assertIn("private_max_message_id", columns)
            self.assertIn("private_recipient_id", columns)

    def test_unique_deal_and_direction_date_blocks_duplicate(self) -> None:
        with TemporaryDirectory() as directory:
            journal = SQLiteJournal(Path(directory) / "journal.sqlite3")
            journal.initialize()
            entry = JournalEntry(
                deal_id="TEST-1",
                directed_at="2026-07-23T12:00:00+03:00",
                processed_at="2026-07-23T12:01:00+03:00",
                status="prepared",
                prepared_message="Тест",
            )

            self.assertTrue(journal.add(entry))
            self.assertFalse(journal.add(entry))
            self.assertEqual(journal.count(), 1)

    def test_changed_direction_date_is_new_event(self) -> None:
        with TemporaryDirectory() as directory:
            journal = SQLiteJournal(Path(directory) / "journal.sqlite3")
            journal.initialize()
            first = JournalEntry(
                "TEST-1",
                "2026-07-23T12:00:00+03:00",
                "2026-07-23T12:01:00+03:00",
                "prepared",
                "Первое",
            )
            second = JournalEntry(
                "TEST-1",
                "2026-07-24T12:00:00+03:00",
                "2026-07-24T12:01:00+03:00",
                "prepared",
                "Второе",
            )

            self.assertTrue(journal.add(first))
            self.assertTrue(journal.add(second))
            self.assertEqual(journal.count(), 2)


if __name__ == "__main__":
    unittest.main()

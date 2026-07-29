from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from maxbot.baseline import create_direction_baseline
from maxbot.journal import SQLiteJournal


class FakeClient:
    def list_recent_target_stage_deals(self, modified_since):
        return [
            {"ID": "1", "STAGE_ID": "3"},
            {"ID": "3", "STAGE_ID": "3"},
        ]


class BaselineTests(unittest.TestCase):
    def test_only_existing_direction_keys_are_added(self):
        with TemporaryDirectory() as directory:
            journal = SQLiteJournal(Path(directory) / "journal.sqlite3")

            result = create_direction_baseline(
                FakeClient(),
                journal,
                now=datetime(2026, 7, 27, 12, 0, 0),
            )

            self.assertEqual(result.scanned_count, 2)
            self.assertEqual(result.directed_count, 2)
            self.assertEqual(result.added_count, 2)
            self.assertEqual(
                journal.get("1", "stage:3").status,
                "baseline",
            )

    def test_rerun_does_not_duplicate_baseline(self):
        with TemporaryDirectory() as directory:
            journal = SQLiteJournal(Path(directory) / "journal.sqlite3")

            create_direction_baseline(FakeClient(), journal)
            result = create_direction_baseline(FakeClient(), journal)

            self.assertEqual(result.added_count, 0)
            self.assertEqual(journal.count(), 2)


if __name__ == "__main__":
    unittest.main()

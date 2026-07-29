from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from maxbot.journal import SQLiteJournal
from maxbot.service import ReferralProcessor
from tests.test_validation import complete_referral


class ServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.journal = SQLiteJournal(
            Path(self.directory.name) / "journal.sqlite3"
        )
        self.journal.initialize()
        self.processor = ReferralProcessor(
            self.journal,
            now=lambda: datetime(2026, 7, 23, 15, 0, 0),
        )

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_complete_referral_is_prepared_but_not_marked_sent(self) -> None:
        result = self.processor.process(complete_referral())

        self.assertEqual(result.status, "prepared")
        self.assertIsNotNone(result.message)
        self.assertEqual(self.journal.count(), 1)

    def test_same_deal_and_date_is_duplicate(self) -> None:
        referral = complete_referral()

        first = self.processor.process(referral)
        second = self.processor.process(referral)

        self.assertEqual(first.status, "prepared")
        self.assertEqual(second.status, "duplicate")
        self.assertIsNone(second.message)
        self.assertEqual(self.journal.count(), 1)

    def test_new_stage_entry_is_processed_again(self) -> None:
        first = self.processor.process(
            complete_referral(),
            event_key="stage:3:2026-07-23T12:00:00+03:00",
        )
        second = self.processor.process(
            complete_referral(),
            event_key="stage:3:2026-07-24T12:00:00+03:00",
        )

        self.assertEqual(first.status, "prepared")
        self.assertEqual(second.status, "prepared")
        self.assertEqual(self.journal.count(), 2)

    def test_missing_fields_prepare_error_instead_of_normal_message(self) -> None:
        result = self.processor.process(
            complete_referral(object_name="", planned_arrival="")
        )

        self.assertEqual(result.status, "validation_error_prepared")
        self.assertEqual(
            result.missing_fields,
            ("объект", "ориентировочная дата прибытия"),
        )
        self.assertNotIn("Вахтовик:", result.message or "")
        self.assertIn("Уведомление о направлении не отправлено.", result.message)

    def test_missing_deduplication_key_is_not_written_to_journal(self) -> None:
        result = self.processor.process(
            complete_referral(deal_id="", directed_at="")
        )

        self.assertEqual(result.status, "validation_error_prepared")
        self.assertEqual(self.journal.count(), 0)


if __name__ == "__main__":
    unittest.main()

from datetime import datetime, timedelta
import unittest

from maxbot.polling import DealPollingRunner


class FakeListClient:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.requested_since: list[datetime] = []

    def list_recent_target_stage_deals(
        self,
        modified_since: datetime,
    ) -> list[dict[str, object]]:
        self.requested_since.append(modified_since)
        return self.rows


class PollingTests(unittest.TestCase):
    def test_only_rows_returned_for_target_stage_are_processed(self) -> None:
        client = FakeListClient(
            [
                {
                    "ID": "43528",
                    "MOVED_TIME": "2026-07-23T12:00:01+03:00",
                    "STAGE_ID": "3",
                },
                {
                    "ID": "43529",
                    "MOVED_TIME": "2026-07-23T12:00:02+03:00",
                    "STAGE_ID": "3",
                },
            ]
        )
        processed: list[tuple[str, str]] = []
        current_time = datetime(2026, 7, 23, 12, 0, 0)
        runner = DealPollingRunner(
            client,  # type: ignore[arg-type]
            lambda deal_id, event_key: processed.append(
                (deal_id, event_key)
            ),
            now=lambda: current_time,
        )

        result = runner.poll_once()

        self.assertEqual(result.checked_count, 2)
        self.assertEqual(result.matched_count, 2)
        self.assertEqual(
            processed,
            [
                ("43528", "stage:3:2026-07-23T12:00:01+03:00"),
                ("43529", "stage:3:2026-07-23T12:00:02+03:00"),
            ],
        )

    def test_initial_scan_starts_at_process_start(self) -> None:
        current_time = datetime(2026, 7, 23, 12, 0, 0)
        client = FakeListClient([])
        runner = DealPollingRunner(
            client,  # type: ignore[arg-type]
            lambda deal_id, event_key: None,
            now=lambda: current_time,
        )

        runner.poll_once()

        self.assertEqual(
            client.requested_since,
            [current_time],
        )

    def test_next_scan_overlaps_five_seconds(self) -> None:
        times = iter(
            (
                datetime(2026, 7, 23, 12, 0, 0),
                datetime(2026, 7, 23, 12, 0, 10),
                datetime(2026, 7, 23, 12, 0, 20),
            )
        )
        client = FakeListClient([])
        runner = DealPollingRunner(
            client,  # type: ignore[arg-type]
            lambda deal_id, event_key: None,
            now=lambda: next(times),
        )

        runner.poll_once()
        runner.poll_once()

        self.assertEqual(
            client.requested_since[1],
            datetime(2026, 7, 23, 12, 0, 5),
        )

    def test_same_deal_version_is_not_processed_twice(self) -> None:
        client = FakeListClient(
            [
                {
                    "ID": "43528",
                    "MOVED_TIME": "2026-07-23T14:50:00+03:00",
                    "STAGE_ID": "3",
                }
            ]
        )
        processed: list[tuple[str, str]] = []
        runner = DealPollingRunner(
            client,  # type: ignore[arg-type]
            lambda deal_id, event_key: processed.append(
                (deal_id, event_key)
            ),
            now=lambda: datetime(2026, 7, 23, 12, 0, 0),
        )

        first = runner.poll_once()
        second = runner.poll_once()

        self.assertEqual(first.matched_count, 1)
        self.assertEqual(second.matched_count, 0)
        self.assertEqual(
            processed,
            [("43528", "stage:3:2026-07-23T14:50:00+03:00")],
        )

    def test_same_deal_is_processed_again_after_new_stage_entry(self) -> None:
        client = FakeListClient(
            [
                {
                    "ID": "43528",
                    "MOVED_TIME": "2026-07-23T14:50:00+03:00",
                    "STAGE_ID": "3",
                }
            ]
        )
        processed: list[tuple[str, str]] = []
        runner = DealPollingRunner(
            client,  # type: ignore[arg-type]
            lambda deal_id, event_key: processed.append(
                (deal_id, event_key)
            ),
            now=lambda: datetime(2026, 7, 23, 12, 0, 0),
        )

        runner.poll_once()
        client.rows = [
            {
                "ID": "43528",
                "MOVED_TIME": "2026-07-24T09:15:00+03:00",
                "STAGE_ID": "3",
            }
        ]
        runner.poll_once()

        self.assertEqual(len(processed), 2)
        self.assertNotEqual(processed[0][1], processed[1][1])

    def test_failed_transition_is_retried_without_advancing_cursor(self) -> None:
        times = iter(
            (
                datetime(2026, 7, 23, 12, 0, 0),
                datetime(2026, 7, 23, 12, 0, 10),
                datetime(2026, 7, 23, 12, 0, 20),
            )
        )
        client = FakeListClient(
            [
                {
                    "ID": "43528",
                    "MOVED_TIME": "2026-07-23T12:00:01+03:00",
                    "STAGE_ID": "3",
                }
            ]
        )
        attempts = 0

        def process(deal_id: str, event_key: str) -> bool:
            nonlocal attempts
            attempts += 1
            return attempts > 1

        runner = DealPollingRunner(
            client,  # type: ignore[arg-type]
            process,
            now=lambda: next(times),
        )
        initial_cursor = runner.cursor

        runner.poll_once()
        self.assertEqual(runner.cursor, initial_cursor)
        runner.poll_once()

        self.assertEqual(attempts, 2)
        self.assertNotEqual(runner.cursor, initial_cursor)


if __name__ == "__main__":
    unittest.main()

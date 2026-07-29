"""Начальная отметка существующих направлений без чтения персональных данных."""

from dataclasses import dataclass
from datetime import datetime, timezone

from .bitrix import BitrixReadClient
from .journal import JournalEntry, SQLiteJournal


@dataclass(frozen=True, slots=True)
class BaselineResult:
    scanned_count: int
    directed_count: int
    added_count: int


def create_direction_baseline(
    client: BitrixReadClient,
    journal: SQLiteJournal,
    *,
    now: datetime | None = None,
) -> BaselineResult:
    journal.initialize()
    rows = client.list_recent_target_stage_deals(
        datetime(1970, 1, 1, tzinfo=timezone.utc)
    )
    processed_at = (now or datetime.now().astimezone()).isoformat(
        timespec="seconds"
    )
    directed_count = 0
    added_count = 0
    for row in rows:
        deal_id = str(row.get("ID") or "").strip()
        if not deal_id:
            continue
        directed_count += 1
        if journal.add(
            JournalEntry(
                deal_id=deal_id,
                directed_at="stage:3",
                processed_at=processed_at,
                status="baseline",
                prepared_message="",
            )
        ):
            added_count += 1
    return BaselineResult(len(rows), directed_count, added_count)

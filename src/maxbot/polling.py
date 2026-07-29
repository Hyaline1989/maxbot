"""Периодический опрос недавно изменённых сделок."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from .bitrix import BitrixReadClient


@dataclass(frozen=True, slots=True)
class PollResult:
    checked_count: int
    matched_count: int
    processed_deal_ids: tuple[str, ...]


class DealPollingRunner:
    """Один безопасный шаг опроса только новых сделок."""

    def __init__(
        self,
        client: BitrixReadClient,
        process_deal: Callable[[str, str], bool | None],
        *,
        now: Callable[[], datetime] | None = None,
        initial_lookback: timedelta = timedelta(0),
        overlap: timedelta = timedelta(seconds=5),
    ) -> None:
        self.client = client
        self.process_deal = process_deal
        self.now = now or (lambda: datetime.now().astimezone())
        self.overlap = overlap
        self._cursor = self.now() - initial_lookback
        self._seen_transitions: set[tuple[str, str]] = set()

    @property
    def cursor(self) -> datetime:
        return self._cursor

    def poll_once(self) -> PollResult:
        started_at = self.now()
        rows = self.client.list_recent_target_stage_deals(self._cursor)
        processed: list[str] = []
        matched_count = 0
        had_failure = False

        for row in rows:
            deal_id = _text(row.get("ID"))
            moved_at = _text(row.get("MOVED_TIME"))
            if not deal_id or not moved_at:
                continue
            transition = (deal_id, moved_at)
            if transition in self._seen_transitions:
                continue
            matched_count += 1
            event_key = f"stage:3:{moved_at}"
            processed_successfully = self.process_deal(deal_id, event_key)
            if processed_successfully is not False:
                self._seen_transitions.add(transition)
            else:
                had_failure = True
            processed.append(deal_id)

        if not had_failure:
            self._cursor = started_at - self.overlap
        return PollResult(
            checked_count=len(rows),
            matched_count=matched_count,
            processed_deal_ids=tuple(processed),
        )


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()

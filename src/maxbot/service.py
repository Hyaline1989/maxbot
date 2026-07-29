"""Локальный сценарий обработки без настоящей отправки."""

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from .journal import JournalEntry, SQLiteJournal
from .messages import build_error_message, build_referral_message
from .models import Referral
from .validation import missing_fields


@dataclass(frozen=True, slots=True)
class ProcessingResult:
    status: str
    message: str | None
    missing_fields: tuple[str, ...] = ()


class ReferralProcessor:
    def __init__(
        self,
        journal: SQLiteJournal,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.journal = journal
        self.now = now or datetime.now

    def process(
        self,
        referral: Referral,
        *,
        retry_existing: bool = False,
        event_key: str = "stage:3",
    ) -> ProcessingResult:
        # Один ключ соответствует одному конкретному входу сделки в стадию.
        missing = missing_fields(referral)
        if not referral.deal_id or not event_key:
            return self._prepare_validation_error(
                referral,
                missing,
                record=False,
                event_key=event_key,
            )

        existing = self.journal.get(referral.deal_id, event_key)
        if existing:
            if (
                existing.status
                in {"sent", "validation_error_sent", "baseline"}
                or not retry_existing
            ):
                return ProcessingResult(status="duplicate", message=None)
            return ProcessingResult(
                status=existing.status,
                message=existing.prepared_message,
            )

        if missing:
            return self._prepare_validation_error(
                referral,
                missing,
                record=True,
                event_key=event_key,
            )

        prepared_at = self.now()
        message = build_referral_message(referral)
        inserted = self.journal.add(
            JournalEntry(
                deal_id=referral.deal_id,
                directed_at=event_key,
                processed_at=prepared_at.isoformat(timespec="seconds"),
                status="prepared",
                prepared_message=message,
            )
        )
        if not inserted:
            return ProcessingResult(status="duplicate", message=None)
        return ProcessingResult(status="prepared", message=message)

    def _prepare_validation_error(
        self,
        referral: Referral,
        missing: list[str],
        *,
        record: bool,
        event_key: str,
    ) -> ProcessingResult:
        prepared_at = self.now()
        message = build_error_message(referral, missing, prepared_at)
        if record:
            inserted = self.journal.add(
                JournalEntry(
                    deal_id=referral.deal_id,
                    directed_at=event_key,
                    processed_at=prepared_at.isoformat(timespec="seconds"),
                    status="validation_error_prepared",
                    prepared_message=message,
                    error_description=", ".join(missing),
                )
            )
            if not inserted:
                return ProcessingResult(status="duplicate", message=None)
        return ProcessingResult(
            status="validation_error_prepared",
            message=message,
            missing_fields=tuple(missing),
        )

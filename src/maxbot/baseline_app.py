"""Разовый безопасный запуск начальной отметки."""

import json

from .baseline import create_direction_baseline
from .bitrix import BitrixReadClient
from .config import Settings
from .journal import SQLiteJournal


def main() -> int:
    settings = Settings.from_environment()
    if not settings.bitrix_webhook_base_url:
        print(json.dumps({"status": "bitrix_not_configured"}))
        return 2
    client = BitrixReadClient(
        settings.bitrix_webhook_base_url,
        allowed_deal_ids=set(),
        discover_funnel_deals=True,
    )
    result = create_direction_baseline(
        client,
        SQLiteJournal(settings.journal_path),
    )
    print(
        json.dumps(
            {
                "status": "baseline_complete",
                "scanned_count": result.scanned_count,
                "directed_count": result.directed_count,
                "added_count": result.added_count,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

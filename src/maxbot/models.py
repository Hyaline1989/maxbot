"""Внутренняя модель направления, независимая от формата API."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Referral:
    deal_id: str
    candidate_title: str
    full_name: str
    birth_date: str
    phone: str
    object_name: str
    manager_name: str
    directed_at: str
    planned_arrival: str
    deal_url: str
    position_name: str = ""
    created_at: str = ""
    planned_arrival_at: str = ""
    object_manager_bitrix_id: str = ""
    additional_manager_bitrix_ids: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "Referral":
        def text(key: str) -> str:
            item = value.get(key, "")
            return "" if item is None else str(item).strip()

        def text_tuple(key: str) -> tuple[str, ...]:
            item = value.get(key, ())
            values = item if isinstance(item, (list, tuple)) else (item,)
            return tuple(
                str(part).strip()
                for part in values
                if part is not None and str(part).strip()
            )

        return cls(
            deal_id=text("deal_id"),
            created_at=text("created_at"),
            candidate_title=text("candidate_title"),
            full_name=text("full_name"),
            birth_date=text("birth_date"),
            phone=text("phone"),
            object_name=text("object_name"),
            manager_name=text("manager_name"),
            directed_at=text("directed_at"),
            planned_arrival=text("planned_arrival"),
            deal_url=text("deal_url"),
            position_name=text("position_name"),
            planned_arrival_at=text("planned_arrival_at"),
            object_manager_bitrix_id=text("object_manager_bitrix_id"),
            additional_manager_bitrix_ids=text_tuple(
                "additional_manager_bitrix_ids"
            ),
        )

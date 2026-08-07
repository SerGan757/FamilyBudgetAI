import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def parse_admin_telegram_ids(value: str | None) -> frozenset[int]:
    if not value:
        return frozenset()

    admin_ids: set[int] = set()
    for item in value.split(","):
        try:
            telegram_id = int(item.strip())
        except (TypeError, ValueError):
            continue
        if telegram_id > 0:
            admin_ids.add(telegram_id)
    return frozenset(admin_ids)


def get_admin_telegram_ids() -> frozenset[int]:
    return parse_admin_telegram_ids(os.getenv("ADMIN_TELEGRAM_IDS"))


def is_admin(telegram_id: int | None) -> bool:
    return telegram_id is not None and telegram_id in get_admin_telegram_ids()

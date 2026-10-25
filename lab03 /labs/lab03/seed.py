"""Початкове заповнення бази з data/seed.json.

Запуск із кореня репозиторію: ``python -m labs.lab03.seed``.
Дані перевіряються до запису, категорії та записи додаються в одній
транзакції; повторний запуск для непорожньої бази нічого не змінює.
"""

import json
import logging
import sqlite3
import sys
from pathlib import Path
from typing import Any

from . import repository
from .config import (
    CATEGORY_NAME_MAX,
    CATEGORY_NAME_MIN,
    CODE_MAX,
    CODE_MIN,
    SQLITE_MAX_INT,
    STATUSES,
    TITLE_MAX,
    TITLE_MIN,
    VALUE_MIN,
)
from .database import BASE_DIR, initialize_database

logger = logging.getLogger(__name__)

SEED_PATH = BASE_DIR / "data" / "seed.json"
CATEGORY_KEYS = {"id", "name"}
RECORD_KEYS = {"code", "title", "category_id", "value", "status"}

EXIT_OK = 0
EXIT_ERROR = 1


SeedParts = tuple[list[dict[str, Any]], list[dict[str, Any]]]  # (категорії, записи)


class SeedDataError(ValueError):
    """Початкові дані некоректні."""


def _is_int(value: object) -> bool:
    """Ціле число (bool у Python теж int, але тут він недопустимий)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _text(value: object, where: str, name: str, low: int, high: int) -> str:
    if not isinstance(value, str):
        raise SeedDataError(f"{where}: поле {name} має бути рядком")
    cleaned = value.strip()
    if not low <= len(cleaned) <= high:
        raise SeedDataError(f"{where}: довжина {name} має бути від {low} до {high}")
    return cleaned


def _object(item: object, where: str, keys: set[str]) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise SeedDataError(f"{where}: очікується JSON-об'єкт")
    if set(item) != keys:
        raise SeedDataError(f"{where}: потрібні рівно поля {sorted(keys)}")
    return item


def _array(data: dict[str, Any], key: str) -> list[Any]:
    items = data.get(key)
    if not isinstance(items, list) or not items:
        raise SeedDataError(f"'{key}' має бути непорожнім масивом")
    return items


def validate_seed(data: object) -> SeedParts:
    """Перевірити структуру й значення seed.json; повернути (категорії, записи)."""
    if not isinstance(data, dict) or set(data) != {"categories", "records"}:
        raise SeedDataError("JSON має бути об'єктом із полями categories та records")

    categories: list[dict[str, Any]] = []
    for index, raw in enumerate(_array(data, "categories"), start=1):
        where = f"categories[{index}]"
        item = _object(raw, where, CATEGORY_KEYS)
        if not _is_int(item["id"]) or not 0 < item["id"] <= SQLITE_MAX_INT:
            raise SeedDataError(f"{where}: id має бути додатним цілим числом")
        name = _text(item["name"], where, "name", CATEGORY_NAME_MIN, CATEGORY_NAME_MAX)
        categories.append({"id": item["id"], "name": name})

    category_ids = [item["id"] for item in categories]
    if len(set(category_ids)) != len(category_ids):
        raise SeedDataError("id категорій мають бути унікальними")
    names = [item["name"] for item in categories]
    if len(set(names)) != len(names):
        raise SeedDataError("назви категорій мають бути унікальними")

    records: list[dict[str, Any]] = []
    for index, raw in enumerate(_array(data, "records"), start=1):
        where = f"records[{index}]"
        item = _object(raw, where, RECORD_KEYS)
        code = _text(item["code"], where, "code", CODE_MIN, CODE_MAX)
        title = _text(item["title"], where, "title", TITLE_MIN, TITLE_MAX)
        if item["category_id"] not in category_ids or not _is_int(item["category_id"]):
            raise SeedDataError(
                f"{where}: category_id посилається на відсутню категорію"
            )
        value = item["value"]
        if not _is_int(value) or not VALUE_MIN <= value <= SQLITE_MAX_INT:
            raise SeedDataError(f"{where}: value має бути цілим числом не менше 0")
        if item["status"] not in STATUSES:
            raise SeedDataError(f"{where}: status має бути одним із {list(STATUSES)}")
        records.append(
            {
                "code": code,
                "title": title,
                "category_id": item["category_id"],
                "value": value,
                "status": item["status"],
            }
        )

    codes = [item["code"] for item in records]
    if len(set(codes)) != len(codes):
        raise SeedDataError("code записів мають бути унікальними")
    return categories, records


def load_seed(path: Path = SEED_PATH) -> SeedParts:
    """Прочитати JSON і перевірити його вміст."""
    with path.open(encoding="utf-8") as handle:
        return validate_seed(json.load(handle))


def main() -> int:
    """Створити таблиці (за потреби) та заповнити порожню базу."""
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    try:
        initialize_database()
        categories, records = load_seed()
        inserted = repository.seed_database(categories, records)
    except FileNotFoundError:
        print(f"Файл початкових даних не знайдено: {SEED_PATH}")
        return EXIT_ERROR
    except json.JSONDecodeError as error:
        print(f"seed.json не є коректним JSON: {error}")
        return EXIT_ERROR
    except SeedDataError as error:
        print(f"Початкові дані некоректні, базу не змінено: {error}")
        return EXIT_ERROR
    except repository.RepositoryError as error:
        print(f"Заповнення скасовано, базу не змінено: {error}")
        return EXIT_ERROR
    except sqlite3.Error:
        logger.exception("Помилка SQLite під час початкового заповнення")
        print("Помилка бази даних: заповнення скасовано (подробиці в журналі).")
        return EXIT_ERROR

    if not inserted:
        print("База вже містить дані: заповнення пропущено, нічого не змінено.")
        return EXIT_OK
    print(f"Додано категорій: {len(categories)}, записів: {len(records)}.")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

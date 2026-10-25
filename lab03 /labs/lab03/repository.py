"""Параметризовані SQL-запити до таблиць categories і records.

Модуль не залежить від FastAPI: про помилки він повідомляє власними
винятками, а в HTTP-відповіді їх перетворює шар API (main.py). З'єднання
відкривається й закривається всередині кожної операції; зміни даних
виконуються в одній транзакції (``with connection``).
"""

import logging
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import closing, contextmanager
from typing import Any

from .database import get_connection

logger = logging.getLogger(__name__)

Row = dict[str, Any]

RECORD_SELECT = """
    SELECT r.id, r.code, r.title, r.category_id, r.value, r.status,
           c.name AS category_name
    FROM records AS r
    JOIN categories AS c ON c.id = r.category_id
"""
INSERT_RECORD = """
    INSERT INTO records (code, title, category_id, value, status)
    VALUES (?, ?, ?, ?, ?)
"""
UPDATE_RECORD = """
    UPDATE records
    SET code = ?, title = ?, category_id = ?, value = ?, status = ?
    WHERE id = ?
"""


# --- Винятки шару доступу до даних -------------------------------------------
class RepositoryError(Exception):
    """Базовий виняток шару доступу до даних."""


class RecordNotFoundError(RepositoryError):
    """Запису з таким id немає."""


class CategoryNotFoundError(RepositoryError):
    """Категорії з таким id немає."""


class DuplicateError(RepositoryError):
    """Порушено унікальність code запису або назви категорії."""


class CategoryNotEmptyError(RepositoryError):
    """Категорію не можна видалити: у ній є записи."""


class DataConstraintError(RepositoryError):
    """Дані порушують обмеження бази, які не вдалося віднести до інших видів."""


# --- Допоміжні функції -------------------------------------------------------
@contextmanager
def _session() -> Iterator[sqlite3.Connection]:
    """З'єднання на час однієї операції; після неї воно завжди закривається."""
    with closing(get_connection()) as connection:
        connection.row_factory = sqlite3.Row
        yield connection


def _translate_integrity_error(error: sqlite3.IntegrityError) -> RepositoryError:
    """Перетворити помилку SQLite на виняток без SQL і службових подробиць."""
    message = str(error)
    if "UNIQUE constraint failed: records.code" in message:
        logger.info("Дублікат code: %s", message)
        return DuplicateError("Запис із таким code вже існує")
    if "UNIQUE constraint failed: categories.name" in message:
        logger.info("Дублікат назви категорії: %s", message)
        return DuplicateError("Категорія з такою назвою вже існує")
    if "UNIQUE constraint failed" in message:
        logger.info("Порушення унікальності: %s", message)
        return DuplicateError("Значення має бути унікальним")
    if "FOREIGN KEY constraint failed" in message:
        logger.info("Порушення зовнішнього ключа: %s", message)
        return CategoryNotFoundError("Категорію не знайдено")
    logger.warning("Непередбачене порушення обмеження: %s", message)
    return DataConstraintError("Дані порушують обмеження бази даних")


def _ensure_category_exists(connection: sqlite3.Connection, category_id: int) -> None:
    found = connection.execute(
        "SELECT 1 FROM categories WHERE id = ?",
        (category_id,),
    ).fetchone()
    if found is None:
        raise CategoryNotFoundError("Категорію не знайдено")


def _fetch_record(connection: sqlite3.Connection, record_id: int) -> Row:
    row = connection.execute(
        RECORD_SELECT + " WHERE r.id = ?",
        (record_id,),
    ).fetchone()
    if row is None:
        raise RecordNotFoundError("Запис не знайдено")
    return dict(row)


def _record_values(item: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        item["code"],
        item["title"],
        item["category_id"],
        item["value"],
        item["status"],
    )


# --- Категорії ---------------------------------------------------------------
def create_category(name: str) -> Row:
    """Створити категорію; повторна назва — DuplicateError."""
    with _session() as connection:
        try:
            with connection:
                cursor = connection.execute(
                    "INSERT INTO categories (name) VALUES (?)",
                    (name,),
                )
        except sqlite3.IntegrityError as error:
            raise _translate_integrity_error(error) from error
        return {"id": cursor.lastrowid, "name": name}


def list_categories() -> list[Row]:
    """Усі категорії за зростанням id."""
    with _session() as connection:
        rows = connection.execute(
            "SELECT id, name FROM categories ORDER BY id ASC",
        ).fetchall()
        return [dict(row) for row in rows]


def delete_category(category_id: int) -> None:
    """Видалити порожню категорію (RESTRICT не дає видалити непорожню)."""
    with _session() as connection:
        try:
            with connection:
                cursor = connection.execute(
                    "DELETE FROM categories WHERE id = ?",
                    (category_id,),
                )
        except sqlite3.IntegrityError as error:
            if "FOREIGN KEY constraint failed" in str(error):
                logger.info("Спроба видалити непорожню категорію %s", category_id)
                raise CategoryNotEmptyError(
                    "Категорія містить записи, її не можна видалити"
                ) from error
            raise _translate_integrity_error(error) from error
        if cursor.rowcount == 0:
            raise CategoryNotFoundError("Категорію не знайдено")


# --- Записи ------------------------------------------------------------------
def create_record(
    *, code: str, title: str, category_id: int, value: int, status: str
) -> Row:
    """Додати запис і повернути його разом з category_name."""
    item = {
        "code": code,
        "title": title,
        "category_id": category_id,
        "value": value,
        "status": status,
    }
    with _session() as connection:
        try:
            with connection:
                _ensure_category_exists(connection, category_id)
                cursor = connection.execute(INSERT_RECORD, _record_values(item))
                return _fetch_record(connection, int(cursor.lastrowid or 0))
        except sqlite3.IntegrityError as error:
            raise _translate_integrity_error(error) from error


def get_record(record_id: int) -> Row:
    """Один запис за id."""
    with _session() as connection:
        return _fetch_record(connection, record_id)


def list_records(
    *,
    category_id: int | None = None,
    status: str | None = None,
    min_value: int | None = None,
    q: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[Row]:
    """Записи з фільтрами (AND), сортуванням за id та поділом на сторінки.

    У SQL потрапляють лише наперед задані фрагменти умов; усі значення
    передаються окремим списком параметрів.
    """
    conditions: list[str] = []
    params: list[Any] = []
    if category_id is not None:
        conditions.append("r.category_id = ?")
        params.append(category_id)
    if status is not None:
        conditions.append("r.status = ?")
        params.append(status)
    if min_value is not None:
        conditions.append("r.value >= ?")
        params.append(min_value)
    if q is not None:
        # instr() шукає буквальний підрядок з урахуванням регістру: символи
        # % та _ тут не є шаблонами, а лапки й коментарі лишаються даними.
        conditions.append("instr(r.title, ?) > 0")
        params.append(q)

    sql = RECORD_SELECT
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY r.id ASC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with _session() as connection:
        rows = connection.execute(sql, params).fetchall()
        return [dict(row) for row in rows]


def replace_record(
    record_id: int,
    *,
    code: str,
    title: str,
    category_id: int,
    value: int,
    status: str,
) -> Row:
    """Повна заміна змінюваних полів запису; id лишається незмінним."""
    item = {
        "code": code,
        "title": title,
        "category_id": category_id,
        "value": value,
        "status": status,
    }
    with _session() as connection:
        try:
            with connection:
                _ensure_category_exists(connection, category_id)
                cursor = connection.execute(
                    UPDATE_RECORD,
                    (*_record_values(item), record_id),
                )
                if cursor.rowcount == 0:
                    raise RecordNotFoundError("Запис не знайдено")
                return _fetch_record(connection, record_id)
        except sqlite3.IntegrityError as error:
            raise _translate_integrity_error(error) from error


def delete_record(record_id: int) -> None:
    """Видалити запис; відсутній id — RecordNotFoundError."""
    with _session() as connection:
        with connection:
            cursor = connection.execute(
                "DELETE FROM records WHERE id = ?",
                (record_id,),
            )
        if cursor.rowcount == 0:
            raise RecordNotFoundError("Запис не знайдено")


def create_records_bulk(items: Sequence[Mapping[str, Any]]) -> list[Row]:
    """Додати пакет записів в ОДНІЙ транзакції: або всі, або жодного.

    Дублікат code (у базі чи всередині пакета) — DuplicateError, неіснуюча
    категорія — CategoryNotFoundError. Окремого commit() після елементів
    немає: підтвердження чи скасування виконує ``with connection``.
    """
    seen_codes: set[str] = set()
    for item in items:
        if item["code"] in seen_codes:
            raise DuplicateError(f"Код '{item['code']}' повторюється в пакеті")
        seen_codes.add(item["code"])

    with _session() as connection:
        try:
            with connection:
                for category_id in sorted({item["category_id"] for item in items}):
                    _ensure_category_exists(connection, category_id)
                new_ids: list[int] = []
                for item in items:
                    cursor = connection.execute(INSERT_RECORD, _record_values(item))
                    new_ids.append(int(cursor.lastrowid or 0))
                return [_fetch_record(connection, record_id) for record_id in new_ids]
        except sqlite3.IntegrityError as error:
            raise _translate_integrity_error(error) from error


# --- Початкове заповнення ----------------------------------------------------
def seed_database(
    categories: Sequence[Mapping[str, Any]],
    records: Sequence[Mapping[str, Any]],
) -> bool:
    """Заповнити порожню базу категоріями й записами в одній транзакції.

    Повертає False, якщо база вже містить дані (тоді нічого не змінюється).
    Категорії вставляються з id із JSON, id записів створює база.
    """
    with _session() as connection:
        categories_count, records_count = connection.execute(
            "SELECT (SELECT COUNT(*) FROM categories), (SELECT COUNT(*) FROM records)",
        ).fetchone()
        if categories_count or records_count:
            return False
        try:
            with connection:
                connection.executemany(
                    "INSERT INTO categories (id, name) VALUES (?, ?)",
                    [(item["id"], item["name"]) for item in categories],
                )
                connection.executemany(
                    INSERT_RECORD,
                    [_record_values(item) for item in records],
                )
        except sqlite3.IntegrityError as error:
            raise _translate_integrity_error(error) from error
    return True

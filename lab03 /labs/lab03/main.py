"""FastAPI-застосунок ЛР №3 (варіант 5): облік спрацювань засобів захисту.

Запуск із кореня репозиторію:
``uvicorn labs.lab03.main:app --reload --host 127.0.0.1 --port 8000``.
"""

import logging
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from shared.student import GROUP_NAME, STUDENT_NAME, VARIANT_NUMBER

from . import repository
from .config import CATEGORY_NAMES, THRESHOLD, UNIT, VARIANT_TITLE
from .database import initialize_database
from .routers import categories, records
from .schemas import PingRead, StudentRead

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

CATEGORY_LIST = ", ".join(f"`{name}`" for name in CATEGORY_NAMES)
DESCRIPTION = f"""
**{VARIANT_TITLE}** (варіант {VARIANT_NUMBER}).

Сервіс зберігає підсумки спрацювань засобів захисту за навчальні інтервали.
Категорія ({CATEGORY_LIST}) визначає джерело спрацювання, `value` —
кількість спрацювань (одиниця вимірювання: **{UNIT}**, ціле число не менше 0),
`status` — стан перевірки підсумкового запису (`new`, `in_progress`, `done`).
Навчальний поріг: **{THRESHOLD} {UNIT}** (фільтр `min_value={THRESHOLD}`).
"""

# Винятки шару доступу до даних -> HTTP-коди (SQLite не залежить від FastAPI).
ERROR_STATUS_CODES: tuple[tuple[type[repository.RepositoryError], int], ...] = (
    (repository.RecordNotFoundError, 404),
    (repository.CategoryNotFoundError, 404),
    (repository.DuplicateError, 409),
    (repository.CategoryNotEmptyError, 409),
    (repository.DataConstraintError, 422),
)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Під час запуску створити відсутні таблиці (дані не чіпати й не заповнювати)."""
    initialize_database()
    yield


app = FastAPI(
    title="Облік спрацювань засобів захисту",
    description=DESCRIPTION,
    version="1.0.0",
    lifespan=lifespan,
)
app.include_router(categories.router)
app.include_router(records.router)


@app.get("/ping", response_model=PingRead, tags=["service"], summary="Перевірка API")
def ping() -> dict[str, str]:
    """Перевірити доступність API."""
    return {"status": "ok"}


@app.get(
    "/student",
    response_model=StudentRead,
    tags=["service"],
    summary="Дані студента",
)
def student() -> dict[str, str | int]:
    """ПІБ, група та номер варіанта з shared/student.py."""
    return {
        "student_name": STUDENT_NAME,
        "group_name": GROUP_NAME,
        "variant_number": VARIANT_NUMBER,
    }


@app.exception_handler(repository.RepositoryError)
async def repository_error_handler(
    _request: Request, error: repository.RepositoryError
) -> JSONResponse:
    """404, 409 або 422 для очікуваних помилок; без SQL і службових подробиць."""
    for error_type, status_code in ERROR_STATUS_CODES:
        if isinstance(error, error_type):
            return JSONResponse(status_code=status_code, content={"detail": str(error)})
    logger.error("Невідома помилка шару даних: %s", error)
    return JSONResponse(
        status_code=500,
        content={"detail": "Внутрішня помилка сервера"},
    )


@app.exception_handler(sqlite3.Error)
async def sqlite_error_handler(_request: Request, error: sqlite3.Error) -> JSONResponse:
    """Технічні помилки SQLite: подробиці — в журнал, клієнту — загальне 500."""
    logger.error("Помилка SQLite: %s", error, exc_info=error)
    return JSONResponse(
        status_code=500,
        content={"detail": "Внутрішня помилка сервера"},
    )

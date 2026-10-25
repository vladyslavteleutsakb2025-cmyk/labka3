"""Маршрути ресурсу /records."""

from typing import Annotated

from fastapi import APIRouter, Body, Path, Query, Response
from fastapi import status as http_status

from .. import repository
from ..config import (
    DEFAULT_LIMIT,
    MAX_BATCH_SIZE,
    MAX_LIMIT,
    SEARCH_MAX,
    SEARCH_MIN,
    SQLITE_MAX_INT,
    VALUE_MIN,
    Status,
)
from ..schemas import ErrorDetail, RecordCreate, RecordRead, RecordReplace

router = APIRouter(prefix="/records", tags=["records"])

NOT_FOUND = {"model": ErrorDetail, "description": "Запис або категорію не знайдено"}
CONFLICT = {"model": ErrorDetail, "description": "Дублікат code"}

RecordId = Annotated[
    int,
    Path(
        gt=0,
        le=SQLITE_MAX_INT,
        description="Ідентифікатор запису (додатне ціле число)",
    ),
]


@router.get(
    "",
    response_model=list[RecordRead],
    summary="Список записів із фільтрами",
)
def list_records(
    category_id: Annotated[
        int | None,
        Query(gt=0, le=SQLITE_MAX_INT, description="Лише записи цієї категорії"),
    ] = None,
    status: Annotated[
        Status | None,
        Query(description="Лише записи з цим статусом"),
    ] = None,
    min_value: Annotated[
        int | None,
        Query(
            ge=VALUE_MIN,
            le=SQLITE_MAX_INT,
            description="Лише записи, де value >= min_value (кількість спрацювань)",
        ),
    ] = None,
    q: Annotated[
        str | None,
        Query(
            min_length=SEARCH_MIN,
            max_length=SEARCH_MAX,
            description="Буквальний підрядок у title (з урахуванням регістру)",
        ),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=MAX_LIMIT, description="Максимальна кількість записів"),
    ] = DEFAULT_LIMIT,
    offset: Annotated[
        int,
        Query(ge=0, le=SQLITE_MAX_INT, description="Скільки записів пропустити"),
    ] = 0,
) -> list[dict]:
    """Фільтри поєднуються через AND; сортування за id зростає."""
    return repository.list_records(
        category_id=category_id,
        status=status,
        min_value=min_value,
        q=q,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/bulk",
    status_code=http_status.HTTP_201_CREATED,
    response_model=list[RecordRead],
    summary="Пакетне створення записів",
    responses={404: NOT_FOUND, 409: CONFLICT},
)
def create_records_bulk(
    payload: Annotated[
        list[RecordCreate],
        Body(
            min_length=1,
            max_length=MAX_BATCH_SIZE,
            description="Від 1 до 100 записів; зберігаються всі або жоден",
        ),
    ],
) -> list[dict]:
    """Додати пакет в одній транзакції: помилка в будь-якому елементі скасовує все."""
    return repository.create_records_bulk([item.model_dump() for item in payload])


@router.get(
    "/{record_id}",
    response_model=RecordRead,
    summary="Один запис",
    responses={404: {"model": ErrorDetail, "description": "Запис не знайдено"}},
)
def get_record(record_id: RecordId) -> dict:
    """Запис за id разом з назвою категорії."""
    return repository.get_record(record_id)


@router.post(
    "",
    status_code=http_status.HTTP_201_CREATED,
    response_model=RecordRead,
    summary="Створити запис",
    responses={404: NOT_FOUND, 409: CONFLICT},
)
def create_record(payload: RecordCreate) -> dict:
    """Створити запис; id створює база, категорія має існувати."""
    return repository.create_record(**payload.model_dump())


@router.put(
    "/{record_id}",
    response_model=RecordRead,
    summary="Повністю замінити змінювані поля запису",
    responses={404: NOT_FOUND, 409: CONFLICT},
)
def replace_record(record_id: RecordId, payload: RecordReplace) -> dict:
    """Усі п'ять змінюваних полів обов'язкові; id лишається незмінним."""
    return repository.replace_record(record_id, **payload.model_dump())


@router.delete(
    "/{record_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Видалити запис",
    responses={404: {"model": ErrorDetail, "description": "Запис не знайдено"}},
)
def delete_record(record_id: RecordId) -> Response:
    """Видалити запис; успішна відповідь не має тіла."""
    repository.delete_record(record_id)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)

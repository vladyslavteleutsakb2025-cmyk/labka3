"""Маршрути ресурсу /categories."""

from typing import Annotated

from fastapi import APIRouter, Path, Response
from fastapi import status as http_status

from .. import repository
from ..config import SQLITE_MAX_INT
from ..schemas import CategoryCreate, CategoryRead, ErrorDetail

router = APIRouter(prefix="/categories", tags=["categories"])

CategoryId = Annotated[
    int,
    Path(
        gt=0,
        le=SQLITE_MAX_INT,
        description="Ідентифікатор категорії (додатне ціле число)",
    ),
]


@router.get(
    "",
    response_model=list[CategoryRead],
    summary="Список категорій",
)
def list_categories() -> list[dict]:
    """Усі категорії за зростанням id."""
    return repository.list_categories()


@router.post(
    "",
    status_code=http_status.HTTP_201_CREATED,
    response_model=CategoryRead,
    summary="Створити категорію",
    responses={409: {"model": ErrorDetail, "description": "Назва вже існує"}},
)
def create_category(payload: CategoryCreate) -> dict:
    """Створити категорію; назва має бути унікальною."""
    return repository.create_category(payload.name)


@router.delete(
    "/{category_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Видалити порожню категорію",
    responses={
        404: {"model": ErrorDetail, "description": "Категорію не знайдено"},
        409: {"model": ErrorDetail, "description": "Категорія містить записи"},
    },
)
def delete_category(category_id: CategoryId) -> Response:
    """Видалити категорію без записів; успішна відповідь не має тіла."""
    repository.delete_category(category_id)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)

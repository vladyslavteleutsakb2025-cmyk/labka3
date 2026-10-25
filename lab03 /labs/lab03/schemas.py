"""Pydantic-моделі запитів і відповідей (Pydantic 2)."""

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from .config import (
    CATEGORY_NAME_MAX,
    CATEGORY_NAME_MIN,
    CODE_MAX,
    CODE_MIN,
    SQLITE_MAX_INT,
    TITLE_MAX,
    TITLE_MIN,
    VALUE_MAX,
    VALUE_MIN,
    Status,
)


class CategoryCreate(BaseModel):
    """Тіло запиту для створення категорії."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(
        min_length=CATEGORY_NAME_MIN,
        max_length=CATEGORY_NAME_MAX,
        description="Унікальна назва категорії (джерело спрацювання)",
        examples=["firewall"],
    )


class CategoryRead(BaseModel):
    """Категорія у відповіді API."""

    id: int
    name: str


class RecordCreate(BaseModel):
    """Тіло запиту для створення запису; id задає база, а не клієнт."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    code: str = Field(
        min_length=CODE_MIN,
        max_length=CODE_MAX,
        description="Унікальний код запису",
        examples=["V05-TEST"],
    )
    title: str = Field(
        min_length=TITLE_MIN,
        max_length=TITLE_MAX,
        description="Назва запису",
        examples=["Підсумок спрацювань 09"],
    )
    category_id: StrictInt = Field(
        gt=0,
        le=SQLITE_MAX_INT,
        description="Ідентифікатор наявної категорії",
        examples=[1],
    )
    value: StrictInt = Field(
        ge=VALUE_MIN,
        le=VALUE_MAX,
        description="Кількість спрацювань (events): ціле число не менше 0",
        examples=[12],
    )
    status: Status = Field(description="Стан перевірки підсумкового запису")


class RecordReplace(RecordCreate):
    """Тіло PUT: усі змінювані поля обов'язкові, id змінити не можна."""


class RecordRead(RecordCreate):
    """Запис у відповіді API: змінювані поля, id та назва категорії."""

    id: int
    category_name: str


class PingRead(BaseModel):
    """Відповідь перевірки доступності."""

    status: str


class StudentRead(BaseModel):
    """Дані з shared/student.py."""

    student_name: str
    group_name: str
    variant_number: int


class ErrorDetail(BaseModel):
    """Тіло відповіді з помилкою (404, 409)."""

    detail: str

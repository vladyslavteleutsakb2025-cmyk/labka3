"""Параметри варіанта 5: облік спрацювань засобів захисту."""

from typing import Literal, get_args

# --- Предметна область -------------------------------------------------------
VARIANT_TITLE = "Облік спрацювань засобів захисту"
UNIT = "events"  # одиниця вимірювання value: кількість спрацювань
THRESHOLD = 15  # навчальний поріг: value >= 15 — підвищена активність
CATEGORY_NAMES = ("firewall", "ids", "antivirus")
RECORD_TITLE = "Підсумок спрацювань"

# --- Обмеження value (INTEGER у SQLite) -----------------------------------------
# Числа більші за 2**63 - 1 SQLite не збереже (OverflowError), тому це верхня
# межа value та ідентифікаторів: так замість 500 клієнт отримає 422.
SQLITE_MAX_INT = 2**63 - 1
VALUE_MIN = 0
VALUE_MAX = SQLITE_MAX_INT

# --- Статуси опрацювання -----------------------------------------------------
Status = Literal["new", "in_progress", "done"]
STATUSES: tuple[str, ...] = get_args(Status)

# --- Обмеження рядків (мають збігатися з CHECK у schema.sql) ----------------
CATEGORY_NAME_MIN = 2
CATEGORY_NAME_MAX = 40
CODE_MIN = 3
CODE_MAX = 40
TITLE_MIN = 3
TITLE_MAX = 120

# --- Параметри запитів -------------------------------------------------------
SEARCH_MIN = 1
SEARCH_MAX = 120
DEFAULT_LIMIT = 20
MAX_LIMIT = 100
MAX_BATCH_SIZE = 100

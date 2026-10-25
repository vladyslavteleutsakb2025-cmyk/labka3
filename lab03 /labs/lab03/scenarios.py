"""Виконання сценаріїв 2-13 Завдання 3 проти запущеного API.

Перед запуском потрібні свіжа база (``python -m labs.lab03.seed``) і сервер
(``uvicorn labs.lab03.main:app --host 127.0.0.1 --port 8000``). Запуск із
кореня репозиторію: ``python -m labs.lab03.scenarios``.

Для кожного кроку скрипт друкує запит, HTTP-код і відповідь та перевіряє
очікуваний результат. Після роботи база повертається до початкового стану
(3 категорії, 8 записів). Сценарії 1 (seed) і 14 (перезапуск сервера)
виконуються вручну — див. README. Використано лише стандартну бібліотеку.
"""

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from shared.student import GROUP_NAME, STUDENT_NAME, VARIANT_NUMBER

from .config import SQLITE_MAX_INT, THRESHOLD
from .database import BASE_DIR

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
SEED_PATH = BASE_DIR / "data" / "seed.json"
PREVIEW_LIMIT = 150

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_NO_SERVER = 2


class Runner:
    """Виконує HTTP-запити, друкує їх і рахує успішні та невдалі перевірки."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.checks = 0
        self.failures = 0

    def send(
        self, method: str, path: str, body: Any = None, expect: int | None = None
    ) -> Any:
        """Надіслати запит, вивести результат і (за потреби) перевірити код."""
        data = None
        headers: dict[str, str] = {}
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base_url + path, data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                status, raw = response.status, response.read()
        except urllib.error.HTTPError as error:
            status, raw = error.code, error.read()
        try:
            payload = json.loads(raw) if raw else None
        except ValueError:
            payload = raw.decode("utf-8", errors="replace")

        sent = f"  {method} {path}"
        if body is not None:
            sent += f"  {preview(body)}"
        print(sent)
        print(f"    <- {status} {preview(payload)}")
        if expect is not None:
            self.check(status == expect, f"код відповіді {expect}", status)
        return payload

    def check(self, condition: bool, label: str, actual: Any = None) -> None:
        self.checks += 1
        if condition:
            print(f"    PASS  {label}")
            return
        self.failures += 1
        suffix = f" (отримано: {actual})" if actual is not None else ""
        print(f"    FAIL  {label}{suffix}")

    def records(self) -> list[dict[str, Any]]:
        """Усі записи (одна сторінка з limit=100; у базі їх менше)."""
        payload = self.send("GET", "/records?limit=100")
        return payload if isinstance(payload, list) else []

    def codes(self, query: str = "") -> list[str]:
        payload = self.send("GET", "/records" + query)
        if not isinstance(payload, list):
            return []
        return [item["code"] for item in payload]


def preview(value: Any) -> str:
    """Короткий однорядковий JSON для виводу."""
    text = json.dumps(value, ensure_ascii=False)
    if len(text) > PREVIEW_LIMIT:
        return text[: PREVIEW_LIMIT - 3] + "..."
    return text


def title(number: int, text: str) -> None:
    print(f"\n== Сценарій {number}. {text} ==")


def new_record(code: str, **changes: Any) -> dict[str, Any]:
    record = {
        "code": code,
        "title": "Навчальний підсумок",
        "category_id": 1,
        "value": 12,
        "status": "new",
    }
    record.update(changes)
    return record


def expected_codes(seed: dict[str, Any], **conditions: Any) -> list[str]:
    """Коди записів із seed.json, що задовольняють умови (порядок як за id)."""
    category_id = conditions.get("category_id")
    status = conditions.get("status")
    min_value = conditions.get("min_value")
    return [
        record["code"]
        for record in seed["records"]
        if (category_id is None or record["category_id"] == category_id)
        and (status is None or record["status"] == status)
        and (min_value is None or record["value"] >= min_value)
    ]


def check_count(runner: Runner, expected: int) -> None:
    """Кількість записів у базі має дорівнювати очікуваній."""
    runner.check(
        len(runner.records()) == expected,
        f"кількість записів не змінилась ({expected})",
    )


def check_start_state(runner: Runner, seed: dict[str, Any]) -> bool:
    """Сценарії розраховані на свіжозаповнену базу."""
    categories = runner.send("GET", "/categories", expect=200)
    codes = runner.codes("?limit=100")
    ready = (
        isinstance(categories, list)
        and len(categories) == len(seed["categories"])
        and codes == [item["code"] for item in seed["records"]]
    )
    if not ready:
        print(
            "\nБаза не є свіжозаповненою. Зупиніть сервер, видаліть "
            "labs/lab03/data/lab3.sqlite3, виконайте `python -m labs.lab03.seed` "
            "і запустіть сервер знову."
        )
    return ready


def scenario_2(runner: Runner) -> None:
    title(2, "GET /ping, /student, /categories")
    ping = runner.send("GET", "/ping", expect=200)
    runner.check(ping == {"status": "ok"}, 'тіло {"status": "ok"}')
    student = runner.send("GET", "/student", expect=200)
    runner.check(
        student
        == {
            "student_name": STUDENT_NAME,
            "group_name": GROUP_NAME,
            "variant_number": VARIANT_NUMBER,
        },
        "ПІБ, група та варіант збігаються з shared/student.py",
    )
    categories = runner.send("GET", "/categories", expect=200)
    names = [item["name"] for item in categories]
    runner.check(
        names == ["firewall", "ids", "antivirus"], "3 категорії за зростанням id"
    )


def scenario_3(runner: Runner) -> None:
    title(3, "Повний цикл CRUD окремого запису")
    created = runner.send("POST", "/records", new_record("V05-TEST"), expect=201)
    record_id = created["id"]
    runner.check(created["category_name"] == "firewall", "category_name = firewall")
    fetched = runner.send("GET", f"/records/{record_id}", expect=200)
    runner.check(fetched == created, "GET повертає той самий запис")
    replacement = new_record(
        "V05-TEST",
        title="Оновлений підсумок",
        category_id=2,
        value=20,
        status="in_progress",
    )
    replaced = runner.send("PUT", f"/records/{record_id}", replacement, expect=200)
    runner.check(replaced["id"] == record_id, "id не змінився")
    runner.check(
        (replaced["category_name"], replaced["value"], replaced["status"])
        == ("ids", 20, "in_progress"),
        "поля замінено (category_name = ids)",
    )
    runner.send("DELETE", f"/records/{record_id}", expect=204)
    runner.send("GET", f"/records/{record_id}", expect=404)


def scenario_4(runner: Runner, seed: dict[str, Any]) -> None:
    title(4, "Фільтри, два фільтри одночасно, limit і offset")
    cases = (
        ("?category_id=1", expected_codes(seed, category_id=1)),
        ("?status=new", expected_codes(seed, status="new")),
        (
            "?category_id=1&status=new",
            expected_codes(seed, category_id=1, status="new"),
        ),
        (f"?min_value={THRESHOLD}", expected_codes(seed, min_value=THRESHOLD)),
        (
            f"?category_id=2&min_value={THRESHOLD}",
            expected_codes(seed, category_id=2, min_value=THRESHOLD),
        ),
    )
    for query, expected in cases:
        runner.check(runner.codes(query) == expected, f"{query} -> {expected}")
    all_codes = [item["code"] for item in seed["records"]]
    page = runner.codes("?limit=3&offset=3")
    runner.check(page == all_codes[3:6], "limit=3&offset=3 -> записи 4-6")
    tail = runner.codes("?limit=3&offset=6")
    runner.check(tail == all_codes[6:], "limit=3&offset=6 -> останні записи")
    query = urllib.parse.urlencode({"q": "спрацювань 03"})
    found = runner.codes(f"?{query}")
    runner.check(found == ["V05-03"], "q = буквальний підрядок у title")
    ids = [item["id"] for item in runner.records()]
    runner.check(ids == sorted(ids), "сортування за id зростає (стабільний порядок)")


def scenario_5(runner: Runner) -> None:
    title(5, "Некоректні дані -> 422, база не змінюється")
    before = len(runner.records())
    runner.send("POST", "/records", new_record("V05-BAD1", value=-1), expect=422)
    runner.send("POST", "/records", new_record("V05-BAD2", title="   "), expect=422)
    bad_status = new_record("V05-BAD3", status="unknown")
    runner.send("POST", "/records", bad_status, expect=422)
    with_id = {**new_record("V05-BAD4"), "id": 99}
    runner.send("POST", "/records", with_id, expect=422)
    runner.send("GET", "/records?limit=0", expect=422)
    check_count(runner, before)


def scenario_6(runner: Runner) -> None:
    title(6, "Лічильник: дробове число та значення поза межами -> 422")
    before = len(runner.records())
    runner.send("POST", "/records", new_record("V05-BAD5", value=1.5), expect=422)
    too_big = new_record("V05-BAD6", value=SQLITE_MAX_INT + 1)
    runner.send("POST", "/records", too_big, expect=422)
    runner.send("GET", "/records?min_value=1.5", expect=422)
    check_count(runner, before)


def scenario_7(runner: Runner) -> None:
    title(7, "Неіснуючі record_id та category_id -> 404")
    runner.send("GET", "/records/999999", expect=404)
    runner.send("PUT", "/records/999999", new_record("V05-NF1"), expect=404)
    runner.send("DELETE", "/records/999999", expect=404)
    no_category = new_record("V05-NF2", category_id=999999)
    runner.send("POST", "/records", no_category, expect=404)


def scenario_8(runner: Runner) -> None:
    title(8, "Повторний code і повторна назва категорії -> 409")
    before_records = runner.records()
    before_categories = runner.send("GET", "/categories", expect=200)
    runner.send("POST", "/records", new_record("V05-01"), expect=409)
    runner.send("POST", "/categories", {"name": "firewall"}, expect=409)
    runner.check(runner.records() == before_records, "записи не змінились")
    runner.check(
        runner.send("GET", "/categories") == before_categories, "категорії не змінились"
    )


def scenario_9(runner: Runner) -> None:
    title(9, "Видалення непорожньої та порожньої категорій")
    runner.send("DELETE", "/categories/1", expect=409)
    created = runner.send("POST", "/categories", {"name": "temp_cat"}, expect=201)
    runner.send("DELETE", f"/categories/{created['id']}", expect=204)
    categories = runner.send("GET", "/categories", expect=200)
    runner.check(len(categories) == 3, "залишилось 3 категорії, зв'язки не порушено")


def scenario_10(runner: Runner) -> list[int]:
    title(10, "Коректний пакет із двох нових записів")
    before = len(runner.records())
    batch = [
        new_record("V05-B1", title="Пакетний запис один"),
        new_record("V05-B2", title="Пакетний запис два", category_id=3, value=0),
    ]
    created = runner.send("POST", "/records/bulk", batch, expect=201)
    runner.check(isinstance(created, list) and len(created) == 2, "повернуто 2 записи")
    runner.check(len(runner.records()) == before + 2, "обидва записи збережено")
    return [item["id"] for item in created] if isinstance(created, list) else []


def rollback_checks(runner: Runner, before: int) -> None:
    check_count(runner, before)
    saved = "V05-ROLLBACK" in runner.codes("?limit=100")
    runner.check(not saved, "V05-ROLLBACK не збережено")


def scenario_11(runner: Runner) -> None:
    title(11, "Пакет: другий запис має code, що вже є в базі -> 409")
    before = len(runner.records())
    batch = [new_record("V05-ROLLBACK", title="Перший елемент"), new_record("V05-01")]
    runner.send("POST", "/records/bulk", batch, expect=409)
    rollback_checks(runner, before)


def scenario_12(runner: Runner) -> None:
    title(12, "Пакет: другий запис має неіснуючу категорію -> 404")
    before = len(runner.records())
    batch = [
        new_record("V05-ROLLBACK", title="Перший елемент"),
        new_record("V05-NEW2", category_id=999999),
    ]
    runner.send("POST", "/records/bulk", batch, expect=404)
    rollback_checks(runner, before)


def scenario_13(runner: Runner) -> None:
    title(13, "Пошук q=' OR 1=1 -- обробляється як дані")
    before_records = runner.records()
    before_categories = runner.send("GET", "/categories", expect=200)
    for text in ("' OR 1=1 --", "'; DROP TABLE records; --"):
        query = urllib.parse.urlencode({"q": text})
        found = runner.send("GET", f"/records?{query}", expect=200)
        runner.check(found == [], "рядок не є SQL: збігів немає")
    runner.check(runner.records() == before_records, "записи не змінились")
    categories = runner.send("GET", "/categories")
    runner.check(categories == before_categories, "категорії цілі")


def cleanup(runner: Runner, record_ids: list[int], expected_count: int) -> None:
    title(0, "Повернення бази до початкового стану")
    for record_id in record_ids:
        runner.send("DELETE", f"/records/{record_id}", expect=204)
    runner.check(
        len(runner.records()) == expected_count,
        f"у базі знову {expected_count} записів",
    )


def main(argv: list[str] | None = None) -> int:
    """Виконати сценарії; код 0 — усі перевірки пройдено."""
    parser = argparse.ArgumentParser(description="Сценарії Завдання 3 (варіант 5)")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="адреса API")
    args = parser.parse_args(argv)
    seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    runner = Runner(args.base_url)

    print(
        f"Сценарії Завдання 3 | {STUDENT_NAME} | {GROUP_NAME} | "
        f"варіант {VARIANT_NUMBER}"
    )
    try:
        if not check_start_state(runner, seed):
            return EXIT_FAILED
        scenario_2(runner)
        scenario_3(runner)
        scenario_4(runner, seed)
        scenario_5(runner)
        scenario_6(runner)
        scenario_7(runner)
        scenario_8(runner)
        scenario_9(runner)
        created_ids = scenario_10(runner)
        scenario_11(runner)
        scenario_12(runner)
        scenario_13(runner)
        cleanup(runner, created_ids, len(seed["records"]))
    except (urllib.error.URLError, ConnectionError, TimeoutError) as error:
        print(f"\nНе вдалося з'єднатися з API {args.base_url}: {error}")
        print("Запустіть сервер: uvicorn labs.lab03.main:app --port 8000")
        return EXIT_NO_SERVER

    passed = runner.checks - runner.failures
    print(f"\nПеревірок: {runner.checks}, успішно: {passed}")
    print(f"Невдало: {runner.failures}")
    print("Сценарії 1 (seed) і 14 (перезапуск сервера) виконайте вручну.")
    return EXIT_OK if runner.failures == 0 else EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())

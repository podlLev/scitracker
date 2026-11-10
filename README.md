# scitracker

Трекер наукових публікацій за темами. Сервіс збирає публікації з arXiv та Crossref за збереженими запитами користувачів, об'єднує дублікати за DOI та arXiv ID і дозволяє вести читацький список зі статусами й нотатками.

Курсовий проєкт з дисципліни «Python-програмування» (ДУІТЗ, спеціальність 122 «Комп'ютерні науки»), тема 17.

**Робоча версія:** _буде додано після розгортання_

## Статус

Проєкт у розробці. Реалізується поетапно, через pull request.

- [x] Каркас проєкту, інструменти якості, CI
- [x] Доменна модель і правила переходу статусів
- [x] Шар зберігання (PostgreSQL, міграції, seed-дані)
- [x] Клієнти arXiv і Crossref
- [x] Нормалізація та дедуплікація
- [x] REST API
- [x] Автентифікація, ролі, теми користувачів
- [x] Читацький список: статуси, історія, нотатки
- [x] Аналітика й стрічка
- [ ] CLI, експорт BibTeX, збір за розкладом
- [ ] Docker і розгортання

## Можливості (план)

- збір публікацій за запитами користувача з arXiv та Crossref;
- дедуплікація публікацій, знайдених в обох джерелах;
- пошук за назвою, автором і темою з серверною пагінацією;
- читацький список зі статусами `до читання → читаю → прочитано` та нотатками;
- експорт списку у BibTeX через CLI;
- аналітика: динаміка публікацій за темою, найпродуктивніші автори, статистика читання.

## Стек

| Компонент              | Інструмент                                             |
|------------------------|--------------------------------------------------------|
| Мова                   | Python 3.12+                                           |
| Керування залежностями | uv                                                     |
| База даних             | PostgreSQL (див. [ADR-002](docs/adr/0002-database.md)) |
| ORM і міграції         | SQLAlchemy 2.0, Alembic                                |
| HTTP-клієнт            | httpx, defusedxml (безпечний розбір XML)               |
| API                    | FastAPI, Pydantic                                      |
| Якість коду            | ruff, mypy (strict), pytest, import-linter             |
| CI                     | GitHub Actions                                         |
| Контейнеризація        | Docker, Docker Compose                                 |

Обґрунтування вибору інструментів і розглянуті альтернативи: [ADR-001](docs/adr/0001-technology-stack.md).
Не всі компоненти вже підключено: клієнти, API та автентифікація з'являться пізніше.

## Архітектура

Код поділено на шари. Залежності спрямовані до домену:

```
src/scitracker/
├── domain/     # моделі та правила предметної області
├── services/   # сценарії використання, порти, помилки, збір та дедуплікація
├── sources/    # адаптери arXiv та Crossref, HTTP-шар із retry
├── storage/    # моделі БД, репозиторії, міграції, seed
├── api/        # маршрути FastAPI, схеми, помилки
└── security/   # паролі (argon2id), JWT
```

Межі шарів перевіряються автоматично командою `lint-imports` (налаштування в `pyproject.toml`).
Архітектурні рішення зафіксовано в [docs/adr](docs/adr).

### Статуси читання

`до читання → читаю → прочитано`. Крок уперед або назад на один; пропуск статусу
відхиляється з поясненням. Повторний запит на той самий статус нічого не змінює
(дата завершення не перезаписується). Правила реалізовано в `domain/status.py`
і `domain/reading.py`.

## Розробка

Потрібні: Python 3.12+, [uv](https://docs.astral.sh/uv/), Git.

```powershell
uv sync
uv run pre-commit install --hook-type pre-commit --hook-type pre-push
```

### База даних

Потрібен запущений Docker.

```powershell
copy .env.example .env
docker compose up -d db
uv run --env-file .env alembic upgrade head
uv run --env-file .env python -m scitracker.storage.seed
```

База доступна на `127.0.0.1:5433` (порт 5433 обрано, щоб не конфліктувати з локальним PostgreSQL на 5432). Тестова база `scitracker_test` створюється автоматично під час першого запуску контейнера.

### Конфігурація

Змінні середовища задаються в `.env` (файл не потрапляє до репозиторію, шаблон: `.env.example`).

| Змінна              | Призначення                                                   |
|---------------------|---------------------------------------------------------------|
| `DATABASE_URL`      | підключення до PostgreSQL                                     |
| `TEST_DATABASE_URL` | тестова база (`scitracker_test`)                              |
| `CROSSREF_MAILTO`   | пошта для «polite pool» Crossref (стабільніші ліміти запитів) |
| `JWT_SECRET`        | секрет підпису токенів, мінімум 32 символи                    |

Згенерувати секрет:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Без `JWT_SECRET` застосунок не стартує.

### Перевірки

Мають проходити перед кожним PR:

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run lint-imports
uv run --env-file .env pytest
```

Ті самі перевірки виконує CI на кожен pull request (з сервісним контейнером PostgreSQL). Без запущеної бази тести storage локально пропускаються.

### Перевірка реальних API

Тести проти справжніх arXiv і Crossref за замовчуванням вимкнені (маркер `live`). Запуск вручну:

```powershell
uv run pytest -m live -s --no-cov
```

Також є ручний workflow GitHub Actions «Live API checks» (вкладка Actions).
`CROSSREF_MAILTO` у `.env` потрібна для «polite pool» Crossref (стабільніші ліміти запитів).

### Збір публікацій

```powershell
uv run --env-file .env python -m scitracker.collect
```

Для кожної теми запитує arXiv і Crossref паралельно, об'єднує дублікати за DOI та arXiv ID й виводить підсумок (створено, об'єднано, відхилено, збої джерел). Потрібна `CROSSREF_MAILTO` у `.env`.

### Запуск API

```powershell
uv run --env-file .env uvicorn scitracker.main:build_app --factory --reload
```

Документація Swagger: http://127.0.0.1:8000/docs, перевірка працездатності: `/healthz`.
Пошук: `GET /api/v1/publications?q=&author=&topic=&from=&cursor=&limit=`.
Помилки повертаються у форматі `application/problem+json` (RFC 9457).

### Адміністратор і автентифікація

```powershell
uv run --env-file .env python -m scitracker.create_admin
```

Реєстрація: `POST /api/v1/auth/register`, вхід: `POST /api/v1/auth/login` повертає токен (30 хв). У Swagger натисніть **Authorize** і вставте токен. Гість лише шукає публікації; користувач керує приватними темами (до 20); адміністратор створює й видаляє публічні.

### Читацький список

Усі запити потребують токена (`Authorize` у Swagger).

- `POST /api/v1/reading-list` `{publication_id}`: додати публікацію (повтор повертає наявний елемент)
- `PATCH /api/v1/reading-list/{id}` `{status}`: `to_read` → `reading` → `done`; пропуск статусу дає 409
- `GET /api/v1/reading-list?status=&cursor=&limit=`: мій список
- `GET /api/v1/reading-list/{id}/history`: історія змін статусу
- `POST` і `GET /api/v1/reading-list/{id}/notes`: приватні нотатки

### Стрічка й аналітика

Усі запити потребують токена.

- `GET /api/v1/feed?topic=&cursor=&limit=`: нові публікації в моїх і публічних темах
- `GET /api/v1/stats/by-topic?from=&to=&topic=`: публікації за темою по місяцях (за замовчуванням останні 12 місяців)
- `GET /api/v1/stats/top-authors?topic=&from=&to=&limit=`: найпродуктивніші автори теми
- `GET /api/v1/stats/reading?from=&to=`: моя статистика читання (за замовчуванням 30 днів)

## Процес роботи

- нова робота йде в окремій гілці (`feat/...`, `fix/...`, `chore/...`);
- зміни вливаються у `main` лише через pull request із зеленим CI;
- коміти невеликі й описують один логічний крок.

## Ліцензія

MIT, див. [LICENSE](LICENSE).

# Розгортання

Потрібні: Linux-сервер із Docker Engine і Compose v2, домен, A-запис якого вказує на IP сервера, відкриті порти 80 і 443.

## Перший запуск

```bash
sudo mkdir -p /opt/scitracker && cd /opt/scitracker
# нам потрібні лише ці файли (клонування репозиторію теж підходить)
git clone https://github.com/<owner>/scitracker.git .

cp .env.example .env && chmod 600 .env
```

У `.env` на сервері:

```
COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml
SCITRACKER_IMAGE=ghcr.io/<owner-lowercase>/scitracker:latest
DOMAIN=tracker.example.com
POSTGRES_PASSWORD=<python -c "import secrets; print(secrets.token_urlsafe(24))">
JWT_SECRET=<python -c "import secrets; print(secrets.token_urlsafe(48))">
CROSSREF_MAILTO=<ваша пошта>
LOG_FORMAT=json
```

```bash
docker compose pull
docker compose up -d
docker compose ps                      # api: healthy, migrate: exited (0)
docker compose run --rm api scitracker seed       # лише для демонстрації
docker compose run --rm api scitracker create-admin --email you@example.com
curl -i https://$DOMAIN/healthz
```

Caddy отримає сертифікат сам, перший запит може тривати кілька секунд.

## Оновлення

```bash
docker compose pull && docker compose up -d
```

Міграції виконує сервіс `migrate` перед стартом API. Відкат образу: вкажіть у `SCITRACKER_IMAGE` тег `sha-<коміт>` і повторіть `up -d`. Відкат міграцій робиться вручну (`alembic downgrade -1`), тому перед оновленням робіть копію (`scripts/backup.sh`).

## Перевірка після розгортання

- `https://<домен>/docs` відкривається, сертифікат дійсний;
- наскрізний сценарій: реєстрація, вхід, додавання публікації, зміна статусу;
- `docker compose logs api` містить JSON із `request_id`, без паролів і токенів.

## Варіант без власного сервера (PaaS)

Dockerfile працює без змін. На Render, Fly.io чи Railway: створіть керовану PostgreSQL і задайте `DATABASE_URL` (формат `postgresql+psycopg://...`), `JWT_SECRET`, `CROSSREF_MAILTO`. Команда міграцій `alembic upgrade head` запускається як pre-deploy/release-команда, `scitracker schedule` як окремий фоновий сервіс. HTTPS дає платформа, Caddy не потрібен. Умови безкоштовних тарифів змінюються, перевірте їх перед вибором.

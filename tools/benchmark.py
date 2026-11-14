"""Measurements for section 4.3 of the report. Runs on the TEST database.

    uv run --env-file .env python tools/benchmark.py ingest \
        --output docs/performance/ingest-before.txt
    uv run --env-file .env python tools/benchmark.py status \
        --output docs/performance/status-latency.txt

The ingestion run is rolled back; the status run commits for real (the commit is part of
the measured operation) and removes its rows afterwards.
"""

import argparse
import cProfile
import io
import os
import pstats
import random
import statistics
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import Engine, delete, event
from sqlalchemy.orm import Session, sessionmaker
from starlette.testclient import TestClient

from scitracker.api.app import create_app
from scitracker.cache.memory import InMemoryTtlCache, NullCache
from scitracker.domain.publication import Author, Publication
from scitracker.domain.status import ReadingStatus
from scitracker.domain.topic import Topic
from scitracker.domain.user import User
from scitracker.security.passwords import Argon2PasswordHasher
from scitracker.security.tokens import JwtTokenService
from scitracker.services.ingest import ingest_publication
from scitracker.services.ports import UnitOfWork
from scitracker.services.reading import change_status
from scitracker.storage.database import create_db_engine
from scitracker.storage.models import PublicationRow, UserRow
from scitracker.storage.repositories import (
    SqlPublicationRepository,
    SqlReadingListRepository,
    SqlTopicRepository,
    SqlUserRepository,
)
from scitracker.storage.unit_of_work import SqlUnitOfWork

WARMUP = 5


def make_publications(count: int, authors_per: int) -> list[Publication]:
    run = uuid4().hex[:8]
    rng = random.Random(1)  # noqa: S311 - reproducible benchmark data, not security
    pool = [f"Bench Author {n}" for n in range(300)]
    return [
        Publication(
            title=f"Benchmark paper {i}",
            authors=[Author(name) for name in rng.sample(pool, authors_per)],
            doi=f"10.7777/bench.{run}.{i}",
        )
        for i in range(count)
    ]


def bench_ingest(engine: Engine, count: int, authors_per: int) -> str:
    publications = make_publications(count, authors_per)
    statements = 0

    def on_execute(*_: object) -> None:
        nonlocal statements
        statements += 1

    event.listen(engine, "before_cursor_execute", on_execute)
    profiler = cProfile.Profile()
    try:
        with Session(engine) as session:
            repo = SqlPublicationRepository(session)
            started = time.perf_counter()
            profiler.enable()
            for publication in publications:
                ingest_publication(repo, publication)
            profiler.disable()
            elapsed = time.perf_counter() - started
            session.rollback()
    finally:
        event.remove(engine, "before_cursor_execute", on_execute)
    top = io.StringIO()
    pstats.Stats(profiler, stream=top).strip_dirs().sort_stats("cumulative").print_stats(12)
    return (
        f"records: {count}, authors per record: {authors_per}\n"
        f"total: {elapsed:.2f} s ({elapsed / count * 1000:.1f} ms per record)\n"
        f"SQL statements: {statements} ({statements / count:.1f} per record)\n\n"
        f"{top.getvalue()}"
    )


def bench_status(engine: Engine, iterations: int) -> str:
    run = uuid4().hex
    with Session(engine) as session, session.begin():
        user = SqlUserRepository(session).add(
            User(email=f"bench-{run}@example.com", password_hash="h")  # noqa: S106
        )
        publication = SqlPublicationRepository(session).add(
            Publication(title="Benchmark", authors=[], doi=f"10.7777/status.{run}")
        )
        assert user.id is not None
        assert publication.id is not None
        user_id, publication_id = user.id, publication.id
        item, _ = SqlReadingListRepository(session).add_if_absent(
            user_id, publication_id, datetime.now(UTC)
        )
        assert item.id is not None
        item_id = item.id
    timings: list[float] = []
    try:
        for n in range(iterations + WARMUP):
            target = ReadingStatus.READING if n % 2 == 0 else ReadingStatus.TO_READ
            started = time.perf_counter()
            with Session(engine) as session:  # a new session per call, like a request
                change_status(
                    SqlReadingListRepository(session), user_id, item_id, target, datetime.now(UTC)
                )
                session.commit()
            timings.append((time.perf_counter() - started) * 1000)
    finally:
        with Session(engine) as session, session.begin():
            session.execute(delete(UserRow).where(UserRow.id == user_id))  # cascades to the item
            session.execute(delete(PublicationRow).where(PublicationRow.id == publication_id))
    samples = timings[WARMUP:]
    p95 = statistics.quantiles(samples, n=20)[18]
    return (
        f"operation: change_status (row lock, update, history, commit), {len(samples)} calls\n"
        f"median: {statistics.median(samples):.2f} ms\n"
        f"p95:    {p95:.2f} ms\n"
        f"max:    {max(samples):.2f} ms\n"
        f"rate:   {1000 / statistics.mean(samples):.0f} calls/s (one at a time)\n"
    )


def _time_requests(
    client: TestClient, url: str, headers: dict[str, str], iterations: int
) -> tuple[list[float], int, float]:
    """Return (timings after warm-up in ms, number of cache hits, first request in ms)."""
    timings: list[float] = []
    hits = 0
    first = 0.0
    for n in range(iterations + WARMUP):
        started = time.perf_counter()
        response = client.get(url, headers=headers)
        elapsed = (time.perf_counter() - started) * 1000
        assert response.status_code == 200, response.text
        if n == 0:
            first = elapsed
        if n >= WARMUP:
            timings.append(elapsed)
            hits += response.headers.get("x-cache") == "HIT"
    return timings, hits, first


def _line(label: str, samples: list[float], hits: int, first: float) -> str:
    p95 = statistics.quantiles(samples, n=20)[18]
    return (
        f"{label}: median {statistics.median(samples):.2f} ms, p95 {p95:.2f} ms, "
        f"max {max(samples):.2f} ms, hits {hits}/{len(samples)}, first request {first:.2f} ms\n"
    )


def bench_cache(engine: Engine, iterations: int) -> str:
    session_factory = sessionmaker(engine)

    @contextmanager
    def scope() -> Iterator[UnitOfWork]:
        with session_factory() as session:
            yield SqlUnitOfWork(session)

    def ping() -> None:
        return None

    tokens = JwtTokenService("bench-secret-" + "x" * 40)
    run = uuid4().hex
    with Session(engine) as session, session.begin():
        user = SqlUserRepository(session).add(
            User(email=f"bench-cache-{run}@example.com", password_hash="h")  # noqa: S106
        )
        assert user.id is not None
        user_id = user.id
        topic = SqlTopicRepository(session).add(
            Topic(name=f"bench-{run}", query="bench", owner_id=user.id)
        )
        assert topic.id is not None
    headers = {"Authorization": f"Bearer {tokens.issue(user_id)}"}
    report = f"cache benchmark, {iterations} requests per mode, warm-up {WARMUP}\n\n"
    try:
        for label, cache in (
            ("cache off", NullCache()),
            ("cache on ", InMemoryTtlCache(ttl_seconds=3600)),
        ):
            app = create_app(
                scope=scope,
                ping=ping,
                hasher=Argon2PasswordHasher(),
                tokens=tokens,
                cache=cache,
            )
            with TestClient(app) as client:
                url = "/api/v1/stats/by-topic"
                report += "GET /stats/by-topic\n  " + _line(
                    label, *_time_requests(client, url, headers, iterations)
                )
                series = client.get(url, headers=headers).json()["series"]
                if series:
                    top = f"/api/v1/stats/top-authors?topic={series[0]['topic_id']}"
                    report += "GET /stats/top-authors\n  " + _line(
                        label, *_time_requests(client, top, headers, iterations)
                    )
            report += "\n"
    finally:
        with Session(engine) as session, session.begin():
            session.execute(delete(UserRow).where(UserRow.id == user_id))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--db-env", default="TEST_DATABASE_URL", help="env var with the database URL"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest")
    ingest.add_argument("--records", type=int, default=1000)
    ingest.add_argument("--authors", type=int, default=4)
    status = commands.add_parser("status")
    status.add_argument("--iterations", type=int, default=300)
    cache = commands.add_parser("cache")
    cache.add_argument("--iterations", type=int, default=200)
    for sub in (ingest, status, cache):
        sub.add_argument("--output", help="also write the report to this file (UTF-8)")
    args = parser.parse_args()
    engine = create_db_engine(os.environ[args.db_env])
    if args.command == "ingest":
        report = bench_ingest(engine, args.records, args.authors)
    elif args.command == "status":
        report = bench_status(engine, args.iterations)
    else:
        report = bench_cache(engine, args.iterations)
    sys.stdout.write(report)
    if args.output:
        Path(args.output).write_text(report, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()

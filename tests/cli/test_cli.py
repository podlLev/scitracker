import re
import threading
from datetime import UTC, date, datetime
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
from _pytest.monkeypatch import MonkeyPatch

from scitracker.cli import CliError, _prompt_password, _use_utf8, build_context, build_parser, main
from scitracker.config import ConfigError
from scitracker.domain.publication import Author, Publication
from scitracker.domain.user import Role, User
from scitracker.services.collection import CollectionReport, SourceReport
from scitracker.storage.database import SessionFactory
from scitracker.storage.repositories import (
    SqlPublicationRepository,
    SqlReadingListRepository,
    SqlUserRepository,
)
from tests.cli.helpers import PASSWORD, make_harness, no_prompt

NOW = datetime(2026, 11, 1, tzinfo=UTC)


def test_seed_fills_the_database_only_once(session_factory: SessionFactory) -> None:
    harness = make_harness(session_factory)
    assert harness.run("seed", "--publications", "30") == 0
    assert "Seeded 30 publications" in harness.out.getvalue()
    with session_factory() as session:
        assert SqlPublicationRepository(session).count() == 30
    assert harness.run("seed", "--publications", "30") == 0
    assert "nothing seeded" in harness.out.getvalue()


def test_collect_prints_a_summary_per_topic(session_factory: SessionFactory) -> None:
    reports = [CollectionReport("ML", [SourceReport("arxiv", fetched=3)], created=3)]
    harness = make_harness(session_factory, collect=lambda limit: reports)
    assert harness.run("collect") == 0
    assert "created=3" in harness.out.getvalue()


def test_collect_fails_when_every_source_is_down(session_factory: SessionFactory) -> None:
    down = CollectionReport(
        "ML", [SourceReport("crossref", error="x"), SourceReport("arxiv", error="y")]
    )
    harness = make_harness(session_factory, collect=lambda limit: [down])
    assert harness.run("collect") == 1
    assert "failed_sources=crossref, arxiv" in harness.out.getvalue()


def test_collect_passes_the_limit_and_copes_with_no_topics(session_factory: SessionFactory) -> None:
    seen: list[int] = []

    def collect(limit: int) -> list[CollectionReport]:
        seen.append(limit)
        return []

    harness = make_harness(session_factory, collect=collect)
    assert harness.run("collect", "--limit", "7") == 0
    assert seen == [7]
    assert "no topics" in harness.out.getvalue()


@pytest.mark.parametrize(
    "argv",
    [
        ["collect", "--limit", "0"],
        ["collect", "--limit", "x"],
        ["schedule", "--interval-minutes", "0"],
        [],
    ],
)
def test_invalid_arguments_exit_with_code_2(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as info:
        build_parser().parse_args(argv)
    assert info.value.code == 2


def test_schedule_stops_after_the_current_run(session_factory: SessionFactory) -> None:
    calls: list[int] = []
    holder: dict[str, object] = {}

    def collect(limit: int) -> list[CollectionReport]:
        calls.append(limit)
        harness = holder["harness"]
        assert hasattr(harness, "stop")
        harness.stop.set()  # a stop request arrives while the run is in progress
        return []

    harness = make_harness(session_factory, collect=collect)
    holder["harness"] = harness
    assert harness.run("schedule", "--interval-minutes", "1", "--limit", "9") == 0
    assert calls == [9]
    assert "Stopped after 1 run(s)" in harness.out.getvalue()


def test_create_admin_makes_an_administrator(session_factory: SessionFactory) -> None:
    harness = make_harness(session_factory)
    assert harness.run("create-admin", "--email", "Admin@Example.com") == 0
    with session_factory() as session:
        admin = SqlUserRepository(session).get_by_email("admin@example.com")
    assert admin is not None
    assert admin.role is Role.ADMIN
    assert harness.run("create-admin", "--email", "admin@example.com") == 1
    assert "already exists" in harness.err.getvalue()


def test_create_admin_can_take_the_password_from_the_environment(
    session_factory: SessionFactory,
) -> None:
    harness = make_harness(
        session_factory, prompt=no_prompt, env={"SCITRACKER_ADMIN_PASSWORD": PASSWORD}
    )
    assert harness.run("create-admin", "--email", "a@example.com") == 0


def test_create_admin_rejects_a_weak_password(session_factory: SessionFactory) -> None:
    harness = make_harness(session_factory, prompt=lambda: "short")
    assert harness.run("create-admin", "--email", "a@example.com") == 1
    assert "password" in harness.err.getvalue()


def _reading_list_of(session_factory: SessionFactory, email: str) -> None:
    with session_factory() as session, session.begin():
        user = SqlUserRepository(session).add(User(email=email, password_hash="h"))
        publication = SqlPublicationRepository(session).add(
            Publication(
                title="Deep Graph Networks",
                authors=[Author("Ann Lee")],
                doi="10.1000/x",
                published_on=date(2024, 1, 1),
            )
        )
        assert user.id is not None
        assert publication.id is not None
        SqlReadingListRepository(session).add_if_absent(user.id, publication.id, NOW)


def test_export_bibtex_to_stdout_and_to_a_file(
    session_factory: SessionFactory, tmp_path: Path
) -> None:
    _reading_list_of(session_factory, "a@example.com")
    harness = make_harness(session_factory)
    assert harness.run("export-bibtex", "--email", "A@example.com") == 0
    assert harness.out.getvalue().startswith("@misc{lee2024deep,")
    assert "doi = {10.1000/x}" in harness.out.getvalue()
    assert "Exported 1 entries" in harness.err.getvalue()
    target = tmp_path / "list.bib"
    assert harness.run("export-bibtex", "--email", "a@example.com", "--output", str(target)) == 0
    assert target.read_text(encoding="utf-8") == harness.out.getvalue()


def test_export_bibtex_filters_by_status(session_factory: SessionFactory) -> None:
    _reading_list_of(session_factory, "a@example.com")
    harness = make_harness(session_factory)
    assert harness.run("export-bibtex", "--email", "a@example.com", "--status", "done") == 0
    assert harness.out.getvalue() == ""
    assert "Exported 0 entries" in harness.err.getvalue()


def test_export_for_an_unknown_user_fails(session_factory: SessionFactory) -> None:
    harness = make_harness(session_factory)
    assert harness.run("export-bibtex", "--email", "nobody@example.com") == 1
    assert "not found" in harness.err.getvalue()


def test_report_shows_the_totals(session_factory: SessionFactory) -> None:
    harness = make_harness(session_factory)
    harness.run("seed", "--publications", "5")
    assert harness.run("report") == 0
    assert re.search(r"Publications:\s+5\b", harness.out.getvalue())
    assert "Public topics:" in harness.out.getvalue()


def test_prompt_password_mismatch(monkeypatch: MonkeyPatch) -> None:
    inputs = iter(["password123", "different123"])
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(inputs))
    with pytest.raises(CliError, match="passwords do not match"):
        _prompt_password()


def test_use_utf8_with_and_without_reconfigure() -> None:
    stream_with = StringIO()
    _use_utf8(stream_with)

    class DummyStream:
        def reconfigure(self, *, encoding: str) -> None:
            pass

    stream_without: Any = DummyStream()
    _use_utf8(stream_without)


def test_build_context_wires_properly(monkeypatch: MonkeyPatch) -> None:
    env = {"DATABASE_URL": "sqlite:///:memory:"}
    out, err = StringIO(), StringIO()
    ctx = build_context(env, out, err)

    assert ctx.env == env
    assert ctx.out is out
    assert ctx.err is err
    assert ctx.prompt_password is _prompt_password


def test_main_handles_config_error(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        "scitracker.cli.Settings.from_env",
        lambda env: (_ for _ in ()).throw(ConfigError("missing config")),
    )

    exit_code = main(["report"])
    assert exit_code == 1


def test_main_schedule_installs_stop_signals(
    monkeypatch: MonkeyPatch, session_factory: SessionFactory
) -> None:
    signals_installed: list[int] = []
    monkeypatch.setattr(
        "scitracker.cli.signal.signal",
        lambda sig, handler: signals_installed.append(sig),
    )

    class MockContext:
        def __init__(self) -> None:
            self.stop: threading.Event = threading.Event()

    monkeypatch.setattr("scitracker.cli.build_context", lambda env, out, err: MockContext())
    monkeypatch.setattr("scitracker.cli.execute", lambda ctx, args: 0)

    exit_code = main(["schedule", "--interval-minutes", "1"])
    assert exit_code == 0
    assert len(signals_installed) > 0

import argparse
import getpass
import os
import signal
import sys
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import TextIO

from scitracker.config import ConfigError, Settings
from scitracker.domain.errors import DomainError
from scitracker.domain.status import ReadingStatus
from scitracker.jobs import run_collection
from scitracker.observability.context import bind_request_id, new_run_id
from scitracker.observability.logs import LogSettings, configure_logging
from scitracker.scheduler import run_periodically
from scitracker.security.passwords import Argon2PasswordHasher
from scitracker.services.accounts import create_admin_user
from scitracker.services.bibtex import export_reading_list
from scitracker.services.collection import CollectionReport, run_failed
from scitracker.services.ports import PasswordHasher
from scitracker.services.report import format_overview
from scitracker.storage.database import SessionFactory, create_db_engine, create_session_factory
from scitracker.storage.repositories import SqlReadingListRepository, SqlUserRepository
from scitracker.storage.seed import seed
from scitracker.storage.stats import SqlStatsRepository

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


class CliError(Exception):
    """A problem to show to the operator (no traceback)."""


@dataclass(frozen=True, slots=True)
class Context:
    """
    Everything with side effects, injected:
    tests replace it, build_context wires the real one.
    """

    session_factory: SessionFactory
    collect: Callable[[int], list[CollectionReport]]
    hasher: PasswordHasher
    prompt_password: Callable[[], str]
    env: Mapping[str, str]
    out: TextIO
    err: TextIO
    stop: threading.Event


Handler = Callable[[Context, argparse.Namespace], int]


def _prompt_password() -> str:
    first = getpass.getpass("Password: ")
    if first != getpass.getpass("Repeat password: "):
        raise CliError("passwords do not match")
    return first


def build_context(env: Mapping[str, str], out: TextIO, err: TextIO) -> Context:
    settings = Settings.from_env(env)
    session_factory = create_session_factory(create_db_engine(settings.database_url))

    def collect(limit: int) -> list[CollectionReport]:
        return run_collection(session_factory, limit=limit, mailto=settings.crossref_mailto)

    return Context(
        session_factory=session_factory,
        collect=collect,
        hasher=Argon2PasswordHasher(),
        prompt_password=_prompt_password,
        env=env,
        out=out,
        err=err,
        stop=threading.Event(),
    )


def cmd_seed(ctx: Context, args: argparse.Namespace) -> int:
    with ctx.session_factory() as session, session.begin():
        created = seed(session, publications=args.publications)
    if created:
        ctx.out.write(f"Seeded {created} publications\n")
    else:
        ctx.out.write("The database already has publications: nothing seeded\n")
    return 0


def cmd_collect(ctx: Context, args: argparse.Namespace) -> int:
    with bind_request_id(new_run_id()):
        reports = ctx.collect(args.limit)
    if not reports:
        ctx.out.write("There are no topics to collect (run `scitracker seed` or create one).\n")
        return 0
    for report in reports:
        ctx.out.write(report.summary() + "\n")
    return 1 if run_failed(reports) else 0


def cmd_schedule(ctx: Context, args: argparse.Namespace) -> int:
    ctx.out.write(f"Collecting every {args.interval_minutes} min, Ctrl+C stops after the run.\n")
    ctx.out.flush()

    def job() -> None:
        with bind_request_id(new_run_id()):  # one id per scheduled run
            ctx.collect(args.limit)

    runs = run_periodically(job, interval_seconds=args.interval_minutes * 60, stop=ctx.stop)
    ctx.out.write(f"Stopped after {runs} run(s)\n")
    return 0


def cmd_create_admin(ctx: Context, args: argparse.Namespace) -> int:
    password = ctx.env.get("SCITRACKER_ADMIN_PASSWORD") or ctx.prompt_password()
    try:
        with ctx.session_factory() as session, session.begin():
            user = create_admin_user(
                SqlUserRepository(session), ctx.hasher, email=args.email, password=password
            )
    except DomainError as exc:
        raise CliError(str(exc)) from exc
    ctx.out.write(f"Administrator {user.email} created\n")
    return 0


def cmd_export_bibtex(ctx: Context, args: argparse.Namespace) -> int:
    status = ReadingStatus(args.status) if args.status else None
    with ctx.session_factory() as session:
        user = SqlUserRepository(session).get_by_email(args.email.strip().lower())
        if user is None or user.id is None:
            raise CliError(f"user {args.email} not found")
        export = export_reading_list(SqlReadingListRepository(session), user.id, status=status)
    if args.output:
        Path(args.output).write_text(export.text, encoding="utf-8", newline="\n")
    else:
        ctx.out.write(export.text)
    ctx.err.write(f"Exported {export.entries} entries\n")  # stdout stays clean for redirects
    return 0


def cmd_report(ctx: Context, args: argparse.Namespace) -> int:
    with ctx.session_factory() as session:
        overview = SqlStatsRepository(session).overview()
    ctx.out.write(format_overview(overview))
    return 0


def _bounded(low: int, high: int) -> Callable[[str], int]:
    def parse(raw: str) -> int:
        try:
            value = int(raw)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"{raw!r} is not a number") from exc
        if not low <= value <= high:
            raise argparse.ArgumentTypeError(f"must be between {low} and {high}")
        return value

    return parse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scitracker", description="Scientific publication tracker"
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="command")

    seed_parser = commands.add_parser("seed", help="fill an empty database with synthetic data")
    seed_parser.add_argument("--publications", type=_bounded(1, 100_000), default=250)
    seed_parser.set_defaults(handler=cmd_seed)

    collect_parser = commands.add_parser("collect", help="collect publications for all topics once")
    collect_parser.add_argument(
        "--limit", type=_bounded(1, 100), default=50, help="per source and topic"
    )
    collect_parser.set_defaults(handler=cmd_collect)

    schedule_parser = commands.add_parser("schedule", help="collect repeatedly until stopped")
    schedule_parser.add_argument("--interval-minutes", type=_bounded(1, 10_080), default=360)
    schedule_parser.add_argument("--limit", type=_bounded(1, 100), default=50)
    schedule_parser.set_defaults(handler=cmd_schedule)

    admin_parser = commands.add_parser("create-admin", help="create an administrator account")
    admin_parser.add_argument("--email", required=True)
    admin_parser.set_defaults(handler=cmd_create_admin)

    export_parser = commands.add_parser("export-bibtex", help="export a reading list as BibTeX")
    export_parser.add_argument("--email", required=True, help="owner of the reading list")
    export_parser.add_argument("--status", choices=[s.value for s in ReadingStatus])
    export_parser.add_argument("--output", help="file to write (UTF-8); stdout by default")
    export_parser.set_defaults(handler=cmd_export_bibtex)

    report_parser = commands.add_parser("report", help="print totals of the database")
    report_parser.set_defaults(handler=cmd_report)
    return parser


def execute(ctx: Context, args: argparse.Namespace) -> int:
    handler: Handler = args.handler
    try:
        return handler(ctx, args)
    except CliError as exc:
        ctx.err.write(f"error: {exc}\n")
        return 1


def _install_stop_signals(stop: threading.Event) -> None:
    def request_stop(signum: int, frame: FrameType | None) -> None:
        stop.set()

    for number in (signal.SIGINT, signal.SIGTERM):
        signal.signal(number, request_stop)


def _use_utf8(stream: TextIO) -> None:
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        log = LogSettings.from_env(os.environ)
    except ValueError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1
    configure_logging(log.level, log.format)
    _use_utf8(sys.stdout)
    try:
        ctx = build_context(os.environ, sys.stdout, sys.stderr)
    except ConfigError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1
    if args.command == "schedule":
        _install_stop_signals(ctx.stop)  # other commands stay interruptible by Ctrl+C
    return execute(ctx, args)

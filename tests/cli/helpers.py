import io
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from argon2 import PasswordHasher as Argon2

from scitracker.cli import Context, build_parser, execute
from scitracker.security.passwords import Argon2PasswordHasher
from scitracker.services.collection import CollectionReport
from scitracker.storage.database import SessionFactory

PASSWORD = "correct horse battery"


def no_collect(limit: int) -> list[CollectionReport]:
    raise AssertionError("collect must not run in this test")


def no_prompt() -> str:
    raise AssertionError("the password must not be requested in this test")


@dataclass
class Harness:
    ctx: Context
    out: io.StringIO
    err: io.StringIO
    stop: threading.Event

    def run(self, *argv: str) -> int:
        return execute(self.ctx, build_parser().parse_args(argv))


def make_harness(
    session_factory: SessionFactory,
    *,
    collect: Callable[[int], list[CollectionReport]] = no_collect,
    prompt: Callable[[], str] = lambda: PASSWORD,
    env: Mapping[str, str] | None = None,
) -> Harness:
    out, err, stop = io.StringIO(), io.StringIO(), threading.Event()
    ctx = Context(
        session_factory=session_factory,
        collect=collect,
        hasher=Argon2PasswordHasher(Argon2(time_cost=1, memory_cost=8, parallelism=1)),
        prompt_password=prompt,
        env=env or {},
        out=out,
        err=err,
        stop=stop,
    )
    return Harness(ctx, out, err, stop)

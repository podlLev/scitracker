import logging
import threading
import time

import pytest

from scitracker.scheduler import run_periodically


def test_job_runs_until_stopped() -> None:
    stop, calls = threading.Event(), []

    def job() -> None:
        calls.append(1)
        if len(calls) == 3:
            stop.set()

    assert run_periodically(job, interval_seconds=0, stop=stop) == 3


def test_failing_run_is_logged_and_the_schedule_continues(
    caplog: pytest.LogCaptureFixture,
) -> None:
    stop, calls = threading.Event(), []

    def job() -> None:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom")
        stop.set()

    with caplog.at_level(logging.ERROR, logger="scitracker.scheduler"):
        assert run_periodically(job, interval_seconds=0, stop=stop) == 2
    assert "scheduled run failed" in caplog.text


def test_stopping_interrupts_the_wait() -> None:
    stop = threading.Event()
    timer = threading.Timer(0.05, stop.set)
    timer.start()
    started = time.monotonic()
    assert run_periodically(lambda: None, interval_seconds=60, stop=stop) == 1
    assert time.monotonic() - started < 5
    timer.join()


def test_already_stopped_schedule_never_runs() -> None:
    stop = threading.Event()
    stop.set()
    assert run_periodically(lambda: pytest.fail("must not run"), interval_seconds=0, stop=stop) == 0

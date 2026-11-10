import logging
import threading
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)


def run_periodically(
    job: Callable[[], None],
    *,
    interval_seconds: float,
    stop: threading.Event,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    """Run `job` every `interval_seconds` (between starts) until `stop` is set.

    A failing run is logged and the schedule goes on. Returns the number of runs.
    """
    runs = 0
    while not stop.is_set():
        started = clock()
        runs += 1
        try:
            job()
        except Exception:
            logger.exception("scheduled run failed, the next one is in %.0f s", interval_seconds)
        if stop.wait(max(0.0, interval_seconds - (clock() - started))):
            break
    return runs

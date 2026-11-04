import tracemalloc
from collections.abc import Callable, Iterator

from scitracker.domain.publication import Author, Publication
from scitracker.services.ingest import ingest_stream

N = 10_000


class NullRepository:
    """Stores nothing: isolates the memory behaviour of the pipeline itself."""

    def add(self, publication: Publication) -> Publication:
        return publication

    def update(self, publication: Publication) -> Publication:
        return publication

    def get(self, publication_id: int) -> Publication | None:
        return None

    def find_all_by_identifiers(
        self, *, doi: str | None, arxiv_id: str | None
    ) -> list[Publication]:
        return []

    def link_topic(self, publication_id: int, topic_id: int) -> bool:
        return True

    def count(self) -> int:
        return 0


def records() -> Iterator[Publication]:
    for i in range(N):
        yield Publication(
            title=f"Paper {i}",
            authors=[Author(f"Author {i}")],
            doi=f"10.1000/{i}",
            abstract="x" * 200,
        )


def peak_kib(work: Callable[[], None]) -> float:
    tracemalloc.start()
    try:
        work()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return peak / 1024


def lazy() -> None:
    assert sum(1 for _ in ingest_stream(NullRepository(), records())) == N


def eager() -> None:
    assert len(list(ingest_stream(NullRepository(), list(records())))) == N


def test_lazy_pipeline_needs_far_less_memory_than_eager() -> None:
    lazy_peak, eager_peak = peak_kib(lazy), peak_kib(eager)
    print(f"\nlazy: {lazy_peak:,.0f} KiB, eager: {eager_peak:,.0f} KiB")  # noqa: T201
    assert lazy_peak * 10 < eager_peak

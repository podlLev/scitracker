import logging
import os
import random
from datetime import date, timedelta

from sqlalchemy.orm import Session

from scitracker.domain.publication import Author, Publication
from scitracker.domain.topic import Topic
from scitracker.storage.database import create_db_engine, create_session_factory
from scitracker.storage.repositories import SqlPublicationRepository, SqlTopicRepository

logger = logging.getLogger(__name__)

TOPICS = (
    ("Machine learning", "machine learning"),
    ("Graph neural networks", "graph neural networks"),
    ("Protein folding", "protein structure prediction"),
    ("Quantum computing", "quantum error correction"),
    ("Climate modelling", "climate model downscaling"),
    ("Natural language processing", "language models"),
)
FIRST_NAMES = ("Anna", "Ivan", "Olena", "Petro", "Maria", "John", "Wei", "Fatima", "Lars", "Sofia")
LAST_NAMES = (
    "Kovalenko",
    "Shevchenko",
    "Smith",
    "Zhang",
    "Garcia",
    "Muller",
    "Tanaka",
    "Ivanova",
    "Brown",
    "Rossi",
)
ADJECTIVES = ("Scalable", "Robust", "Efficient", "Bayesian", "Self-supervised", "Sparse")
SUBJECTS = tuple(query for _, query in TOPICS)
APPLICATIONS = ("small datasets", "noisy data", "edge devices", "large-scale systems")


def _make_publication(index: int, rng: random.Random, authors: list[Author]) -> Publication:
    # index % 3: 0 -> arXiv only, 1 -> DOI only, 2 -> both
    kind = index % 3
    year = 24 + index // 1200
    return Publication(
        title=(
            f"{rng.choice(ADJECTIVES)} {rng.choice(SUBJECTS)} "
            f"for {rng.choice(APPLICATIONS)} #{index}"
        ),
        authors=rng.sample(authors, k=rng.randint(1, 4)),
        doi=f"10.5555/seed.{index:04d}" if kind != 0 else None,
        arxiv_id=f"{year:02d}{index % 12 + 1:02d}.{index:05d}" if kind != 1 else None,
        abstract="Synthetic seed record used to exercise search and pagination.",
        published_on=date(2023, 1, 1) + timedelta(days=rng.randint(0, 1400)),
    )


def seed(session: Session, *, publications: int = 250, rng_seed: int = 42) -> int:
    """Fill an empty database with synthetic data. Returns the number of publications added."""
    repo = SqlPublicationRepository(session)
    if repo.count() > 0:
        return 0
    topics = SqlTopicRepository(session)
    if not topics.list_all():
        for name, query in TOPICS:
            topics.add(Topic(name=name, query=query))
    rng = random.Random(rng_seed)  # noqa: S311 - deterministic seed data, not security
    authors = [Author(f"{first} {last}") for first in FIRST_NAMES for last in LAST_NAMES]
    for index in range(publications):
        repo.add(_make_publication(index, rng, authors))
    return publications


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    engine = create_db_engine(os.environ["DATABASE_URL"])
    factory = create_session_factory(engine)
    with factory() as session, session.begin():
        created = seed(session)
    logger.info("seeded %d publications", created)


if __name__ == "__main__":
    main()

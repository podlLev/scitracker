from datetime import date

from sqlalchemy.orm import Session

from scitracker.domain.publication import Author, Publication
from scitracker.domain.topic import Topic
from scitracker.services.collection import FetchedTopic, SourceReport, store_topic
from scitracker.storage.repositories import SqlPublicationRepository, SqlTopicRepository


def make_topic(session: Session) -> Topic:
    return SqlTopicRepository(session).add(Topic(name="GNN", query="graph neural networks"))


def fetched(*batches: list[Publication]) -> FetchedTopic:
    return FetchedTopic([SourceReport("test", fetched=len(b)) for b in batches], list(batches))


def test_publication_found_in_both_sources_is_stored_once(session: Session) -> None:
    repo = SqlPublicationRepository(session)
    crossref = Publication(
        title="Attention Is All You Need",
        authors=[Author("Ashish Vaswani")],
        doi="10.5555/3295222.3295349",
        published_on=date(2017, 12, 4),
    )
    arxiv = Publication(
        title="Attention Is All You Need",
        authors=[Author("Ashish Vaswani"), Author("Noam Shazeer")],
        doi="10.5555/3295222.3295349",
        arxiv_id="1706.03762v7",
        abstract="The dominant sequence transduction models...",
    )
    report = store_topic(repo, make_topic(session), fetched([crossref], [arxiv]))
    assert repo.count() == 1
    assert (report.created, report.merged) == (1, 1)
    stored = repo.find_all_by_identifiers(doi=None, arxiv_id="1706.03762")[0]
    assert stored.published_on == date(2017, 12, 4)  # from Crossref
    assert stored.abstract is not None  # from arXiv
    assert [a.name for a in stored.authors] == ["Ashish Vaswani", "Noam Shazeer"]


def test_arxiv_doi_from_crossref_matches_the_arxiv_record(session: Session) -> None:
    repo = SqlPublicationRepository(session)
    arxiv = Publication(title="T", authors=[], arxiv_id="1706.03762")
    crossref = Publication(title="T", authors=[], doi="10.48550/arXiv.1706.03762")
    store_topic(repo, make_topic(session), fetched([arxiv], [crossref]))
    assert repo.count() == 1


def test_repeated_collection_creates_no_duplicates(session: Session) -> None:
    repo = SqlPublicationRepository(session)
    topic = make_topic(session)
    batch = fetched([Publication(title="T", authors=[Author("Ann Lee")], doi="10.1000/a")])
    store_topic(repo, topic, batch)
    second = store_topic(repo, topic, batch)
    assert repo.count() == 1
    assert (second.created, second.merged, second.new_links) == (0, 0, 0)


def test_conflicting_identifiers_are_skipped_and_counted(session: Session) -> None:
    repo = SqlPublicationRepository(session)
    repo.add(Publication(title="A", authors=[], doi="10.1000/x"))
    repo.add(Publication(title="B", authors=[], arxiv_id="2101.00001"))
    incoming = Publication(title="C", authors=[], doi="10.1000/x", arxiv_id="2101.00001")
    report = store_topic(repo, make_topic(session), fetched([incoming]))
    assert report.conflicts == 1
    assert repo.count() == 2

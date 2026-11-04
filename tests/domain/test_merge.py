from datetime import date

from scitracker.domain.merge import merge_publications
from scitracker.domain.publication import Author, Publication


def make(**overrides: object) -> Publication:
    fields: dict[str, object] = {"title": "Title", "authors": [], "doi": "10.1000/a"}
    fields.update(overrides)
    return Publication(**fields)  # type: ignore[arg-type]


def test_gaps_are_filled_from_the_other_record() -> None:
    base = make(abstract=None, published_on=None)
    other = make(
        arxiv_id="2101.00001", abstract="Abs", published_on=date(2021, 1, 1), url="https://x.test"
    )
    merged = merge_publications(base, other)
    assert merged.arxiv_id == "2101.00001"
    assert merged.abstract == "Abs"
    assert merged.published_on == date(2021, 1, 1)
    assert merged.url == "https://x.test"


def test_existing_values_win() -> None:
    base = make(title="Original", abstract="Mine")
    other = make(title="Other", abstract="Theirs")
    merged = merge_publications(base, other)
    assert (merged.title, merged.abstract) == ("Original", "Mine")


def test_longer_author_list_is_kept() -> None:
    base = make(authors=[Author("Ann Lee")])
    other = make(authors=[Author("Ann Lee"), Author("Bob Ray")])
    assert [a.name for a in merge_publications(base, other).authors] == ["Ann Lee", "Bob Ray"]


def test_identity_of_the_base_record_is_preserved() -> None:
    assert merge_publications(make(id=7), make()).id == 7

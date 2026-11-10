from datetime import UTC, date, datetime

from scitracker.domain.publication import Author, Publication
from scitracker.domain.status import ReadingStatus
from scitracker.services.bibtex import escape, export_reading_list, to_bibtex
from scitracker.services.reading import change_status
from tests.services.fakes import InMemoryReadingListRepository

T0 = datetime(2026, 11, 1, 12, tzinfo=UTC)


def make(title: str = "Attention Is All You Need", **overrides: object) -> Publication:
    base: dict[str, object] = {
        "authors": [Author("Ashish Vaswani"), Author("Noam Shazeer")],
        "doi": "10.5555/3295222.3295349",
        "arxiv_id": "1706.03762",
        "published_on": date(2017, 6, 12),
        "url": "https://arxiv.org/abs/1706.03762",
    }
    base.update(overrides)
    return Publication(title=title, **base)  # type: ignore[arg-type]


def test_entry_contains_all_known_fields() -> None:
    text = to_bibtex([make()])
    assert text.startswith("@misc{vaswani2017attention,\n")
    assert "  author = {Ashish Vaswani and Noam Shazeer}," in text
    assert "  title = {{Attention Is All You Need}}," in text
    assert "  year = {2017}," in text
    assert "  doi = {10.5555/3295222.3295349}," in text
    assert "  eprint = {1706.03762}," in text
    assert "  archivePrefix = {arXiv}," in text
    assert text.endswith("  url = {https://arxiv.org/abs/1706.03762}\n}\n")


def test_arxiv_only_record_has_no_doi_field() -> None:
    text = to_bibtex([make(doi=None, url=None)])
    assert "doi" not in text
    assert "eprint = {1706.03762}" in text


def test_special_characters_are_escaped_once() -> None:
    assert escape(r"R&D 100% of $5_x #1 {a}\b~^") == (
        r"R\&D 100\% of \$5\_x \#1 \{a\}\textbackslash{}b\textasciitilde{}\textasciicircum{}"
    )


def test_organisation_with_and_stays_one_author() -> None:
    text = to_bibtex([make(authors=[Author("Research and Development Group")])])
    assert "author = {{Research and Development Group}}" in text


def test_braces_in_urls_cannot_break_the_entry() -> None:
    assert "url = {https://x.test/%7Ba%7D}" in to_bibtex([make(url="https://x.test/{a}")])


def test_duplicate_keys_get_a_suffix() -> None:
    text = to_bibtex([make(doi="10.1000/a"), make(doi="10.1000/b", arxiv_id="1706.03763")])
    assert "@misc{vaswani2017attention,\n" in text
    assert "@misc{vaswani2017attention_2,\n" in text


def test_key_falls_back_when_nothing_can_be_transliterated() -> None:
    bare = Publication(title="A", authors=[Author("Олена Коваленко")], arxiv_id="2101.00001", id=7)
    assert to_bibtex([bare]).startswith("@misc{pub7,\n")
    dated = Publication(
        title="Квантові коди",
        authors=[Author("Олена Коваленко")],
        arxiv_id="2101.00001",
        published_on=date(2024, 1, 1),
    )
    assert to_bibtex([dated]).startswith("@misc{2024,\n")


def test_no_publications_give_an_empty_file() -> None:
    assert to_bibtex([]) == ""


def test_export_follows_the_status_filter() -> None:
    publications = {
        10: make("Alpha Study", doi="10.1000/a", id=10),
        11: make("Beta Study", doi="10.1000/b", arxiv_id=None, id=11),
    }
    repo = InMemoryReadingListRepository(publications)
    first, _ = repo.add_if_absent(1, 10, T0)
    repo.add_if_absent(1, 11, T0)
    repo.add_if_absent(2, 10, T0)  # another user's list is never exported
    assert first.id is not None
    change_status(repo, 1, first.id, ReadingStatus.READING, T0)
    everything = export_reading_list(repo, 1)
    reading = export_reading_list(repo, 1, status=ReadingStatus.READING)
    assert (everything.entries, reading.entries) == (2, 1)
    assert "Alpha Study" in reading.text
    assert "Beta Study" not in reading.text

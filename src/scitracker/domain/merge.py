from scitracker.domain.publication import Publication


def merge_publications(base: Publication, other: Publication) -> Publication:
    """Combine two records of the same work.

    Values already present in `base` win; gaps are filled from `other`.
    The longer author list is kept (a source may truncate it).
    """
    return Publication(
        id=base.id,
        title=base.title,
        authors=base.authors if len(base.authors) >= len(other.authors) else other.authors,
        doi=base.doi or other.doi,
        arxiv_id=base.arxiv_id or other.arxiv_id,
        abstract=base.abstract or other.abstract,
        published_on=base.published_on or other.published_on,
        url=base.url or other.url,
    )

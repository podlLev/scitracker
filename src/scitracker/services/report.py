from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TopicTotal:
    name: str
    publications: int


@dataclass(frozen=True, slots=True)
class Overview:
    publications: int
    without_doi: int
    authors: int
    users: int
    reading_items: int
    private_topics: int
    topics: list[TopicTotal]  # public topics only


def format_overview(overview: Overview) -> str:
    lines = [
        f"Publications:    {overview.publications} (without DOI: {overview.without_doi})",
        f"Authors:         {overview.authors}",
        f"Users:           {overview.users}",
        f"Reading items:   {overview.reading_items}",
        f"Private topics:  {overview.private_topics}",
        "",
        "Public topics:" if overview.topics else "Public topics: none",
    ]
    width = max((len(topic.name) for topic in overview.topics), default=0)
    lines += [f"  {topic.name.ljust(width)}  {topic.publications}" for topic in overview.topics]
    return "\n".join(lines) + "\n"

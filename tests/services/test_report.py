from scitracker.services.report import Overview, TopicTotal, format_overview


def test_overview_is_aligned_and_lists_public_topics() -> None:
    text = format_overview(
        Overview(250, 83, 100, 3, 12, 4, [TopicTotal("ML", 48), TopicTotal("Quantum computing", 7)])
    )
    assert "Publications:    250 (without DOI: 83)" in text
    assert "  ML                 48\n" in text
    assert "  Quantum computing  7\n" in text


def test_overview_without_topics() -> None:
    assert "Public topics: none" in format_overview(Overview(0, 0, 0, 0, 0, 0, []))

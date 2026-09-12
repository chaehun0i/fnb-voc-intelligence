from src.dashboard.app import overview_sections, page_config


def test_dashboard_page_configuration() -> None:
    assert page_config() == {"page_title": "F&B VOC Dashboard", "layout": "wide"}


def test_overview_has_coherent_empty_and_data_states() -> None:
    assert overview_sections(1) == ["Summary", "Filters", "Analysis", "Review explorer"]
    assert overview_sections(0)[-1] == "Empty state"

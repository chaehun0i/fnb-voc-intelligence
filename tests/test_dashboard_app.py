from src.dashboard.app import dashboard_message, overview_sections, page_config


def test_dashboard_page_configuration() -> None:
    assert page_config() == {"page_title": "F&B VOC Dashboard", "layout": "wide"}


def test_overview_has_coherent_empty_and_data_states() -> None:
    assert overview_sections(1) == ["Summary", "Filters", "Analysis", "Review explorer"]
    assert overview_sections(0)[-1] == "Empty state"


def test_dashboard_messages_are_user_readable() -> None:
    assert "리뷰가 없습니다" in dashboard_message(0)
    assert "설정" in dashboard_message(1, RuntimeError("secret"))

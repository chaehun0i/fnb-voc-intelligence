from src.dashboard.app import page_config


def test_dashboard_page_configuration() -> None:
    assert page_config() == {"page_title": "F&B VOC Dashboard", "layout": "wide"}

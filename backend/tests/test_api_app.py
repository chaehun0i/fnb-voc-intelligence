from src.api.app import create_app


def test_health() -> None:
    app = create_app()
    assert app.url_path_for("health") == "/api/v1/health"

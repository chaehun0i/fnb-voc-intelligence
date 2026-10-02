import pytest

from src.dashboard.models import DashboardQuery


def test_dashboard_query_validates_rating_range() -> None:
    assert DashboardQuery(category="beverage", rating_min=2, rating_max=4).category == "beverage"
    for query in (
        lambda: DashboardQuery(rating_min=0),
        lambda: DashboardQuery(rating_min=5, rating_max=1),
    ):
        with pytest.raises(ValueError):
            query()

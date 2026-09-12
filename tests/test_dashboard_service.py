from src.dashboard.models import DashboardQuery, DashboardReview
from src.dashboard.service import filter_options, summarize_reviews


def test_dashboard_summary_aggregates_and_filters() -> None:
    rows=[DashboardReview("R1","P1","음료","beverage",2,"비싸요",["price"]),DashboardReview("R2","P2","과자","snack",5,"좋아요",[])]
    summary=summarize_reviews(rows, DashboardQuery(category="beverage"))
    assert summary.review_total == 1 and summary.average_rating == 2 and summary.pain_point_counts == {"price":1}


def test_filter_options_derive_available_business_values() -> None:
    rows=[DashboardReview("R1","P1","음료","beverage",2,"비싸요",["price"])]
    assert filter_options(rows) == {"products":["P1"],"categories":["beverage"],"ratings":[2],"pain_points":["price"]}

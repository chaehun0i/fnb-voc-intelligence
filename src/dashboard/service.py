"""Dashboard-ready aggregation isolated from Streamlit."""
from collections import Counter

from .models import DashboardQuery, DashboardReview, DashboardSummary


def summarize_reviews(rows: list[DashboardReview], query: DashboardQuery | None = None) -> DashboardSummary:
    query = query or DashboardQuery()
    filtered = [r for r in rows if (not query.product_id or r.product_id == query.product_id) and (not query.category or r.category == query.category) and (query.rating_min is None or r.rating >= query.rating_min) and (query.rating_max is None or r.rating <= query.rating_max) and (not query.pain_point or query.pain_point in r.pain_points)]
    ratings = Counter(r.rating for r in filtered)
    return DashboardSummary(len(filtered), sum(r.rating for r in filtered) / len(filtered) if filtered else None, dict(ratings), dict(Counter(r.product_name for r in filtered)), dict(Counter(r.category for r in filtered)), dict(Counter(p for r in filtered for p in r.pain_points)), filtered)


def filter_options(rows: list[DashboardReview]) -> dict[str, list[str | int]]:
    return {"products": sorted({row.product_id for row in rows}), "categories": sorted({row.category for row in rows}), "ratings": sorted({row.rating for row in rows}), "pain_points": sorted({point for row in rows for point in row.pain_points})}


def kpis(summary: DashboardSummary) -> dict[str, float | int | str | None]:
    total = summary.review_total
    classified = sum(summary.pain_point_counts.values())
    return {"total_reviews": total, "average_rating": summary.average_rating, "low_rating_ratio": sum(count for rating, count in summary.rating_distribution.items() if rating <= 2) / total if total else 0.0, "top_pain_point": max(summary.pain_point_counts, key=summary.pain_point_counts.get) if summary.pain_point_counts else None, "unclassified_ratio": (total - classified) / total if total else 0.0}


def chart_rows(counts: dict[str | int, int], total: int) -> list[dict[str, float | int | str]]:
    return [{"label": str(label), "count": count, "percentage": count / total * 100 if total else 0.0} for label, count in sorted(counts.items(), key=lambda item: (-item[1], str(item[0])))]

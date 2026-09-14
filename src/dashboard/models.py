"""Typed dashboard query and result contracts."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DashboardQuery:
    product_id: str | None = None
    category: str | None = None
    rating_min: int | None = None
    rating_max: int | None = None
    pain_point: str | None = None

    def __post_init__(self) -> None:
        if self.rating_min is not None and not 1 <= self.rating_min <= 5: raise ValueError("rating_min must be 1..5")
        if self.rating_max is not None and not 1 <= self.rating_max <= 5: raise ValueError("rating_max must be 1..5")
        if self.rating_min and self.rating_max and self.rating_min > self.rating_max: raise ValueError("rating range is invalid")


@dataclass(frozen=True)
class DashboardReview:
    review_id: str; product_id: str; product_name: str; category: str; rating: int; review_text: str; pain_points: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DashboardSummary:
    review_total: int; average_rating: float | None; rating_distribution: dict[int, int]; product_counts: dict[str, int]; category_counts: dict[str, int]; pain_point_counts: dict[str, int]; reviews: list[DashboardReview]

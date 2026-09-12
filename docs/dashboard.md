# Day 9 VOC Dashboard

Install dependencies and run Streamlit locally:

```bash
python -m pip install -e ".[dev]"
streamlit run src/dashboard/app.py
```

The dashboard domain layer is UI-independent. `DashboardQuery` combines product,
category, rating range, and Pain Point filters. The aggregation service returns
filtered review evidence, summary totals, rating/product/category distributions, and
Pain Point counts.

The overview is organized as Summary, Filters, Analysis, and Review explorer. Empty
results and connection failures have user-readable states. Active filters apply to
KPIs, chart data, and review rows together.

KPIs include total reviews, average rating, low-rating ratio, top Pain Point, and
unclassified ratio. Chart rows expose count and percentage for Pain Points and rating
distribution. Review evidence includes product/category, rating, Pain Points, and
text for drill-down without adding RAG behavior.

The initial Streamlit entry point is intentionally lightweight; production database
service initialization and authentication are not included. Charts use native
Streamlit-friendly row data and do not add a chart dependency.

```bash
ruff check .
pytest
```

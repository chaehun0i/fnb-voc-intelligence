"""Runnable Streamlit entry point; business logic stays in dashboard.service."""


def page_config() -> dict[str, str]:
    return {"page_title": "F&B VOC Dashboard", "layout": "wide"}


def overview_sections(review_total: int) -> list[str]:
    sections = ["Summary", "Filters", "Analysis", "Review explorer"]
    return sections if review_total else ["Summary", "Filters", "Empty state"]


def dashboard_message(review_total: int, error: Exception | None = None) -> str | None:
    if error is not None:
        return "데이터를 불러오지 못했습니다. 설정과 연결 상태를 확인하세요."
    if not review_total:
        return "선택한 조건에 맞는 리뷰가 없습니다. 필터를 재설정하세요."
    return None


def main() -> None:
    import streamlit as st

    st.set_page_config(**page_config())
    st.title("F&B VOC Dashboard")
    st.caption("Configure a dashboard data source to begin analysis.")


if __name__ == "__main__":
    main()

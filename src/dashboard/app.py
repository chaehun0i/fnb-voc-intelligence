"""Runnable Streamlit entry point; business logic stays in dashboard.service."""


def page_config() -> dict[str, str]:
    return {"page_title": "F&B VOC Dashboard", "layout": "wide"}


def main() -> None:
    import streamlit as st

    st.set_page_config(**page_config())
    st.title("F&B VOC Dashboard")
    st.caption("Configure a dashboard data source to begin analysis.")


if __name__ == "__main__":
    main()

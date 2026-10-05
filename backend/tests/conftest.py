"""History Vertical Slice의 결정적 실행 입력을 공유합니다."""
import pytest


@pytest.fixture
def history_setup():
    from tests.test_history_application import setup_history
    return setup_history()

"""backend 폴더에서 FastAPI CLI로 실행하는 진입점입니다."""

from src.api.app import app

__all__ = ["app"]
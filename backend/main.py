"""backend 폴더에서 FastAPI CLI로 실행하는 진입점입니다."""

from pathlib import Path

from dotenv import load_dotenv

# 실행 위치에 관계없이 로컬 설정을 읽되 이미 지정한 환경변수는 덮어쓰지 않습니다.
load_dotenv(Path(__file__).with_name(".env"), override=False)

from src.api.app import app

__all__ = ["app"]

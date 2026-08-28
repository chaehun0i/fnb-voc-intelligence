# fnb-voc-intelligence

식음료 고객의 VOC 데이터를 수집·정리·분석하기 위한 프로젝트입니다.

## 시작하기

Python 3.12 환경에서 의존성을 설치한 뒤 검증 명령을 실행합니다.

```bash
python -m pip install -e ".[dev]"
ruff check .
pytest
```

## 디렉터리

- `data/raw`: 원본 데이터
- `data/interim`: 중간 처리 데이터
- `data/processed`: 처리 완료 데이터
- `src`: 애플리케이션 코드
- `tests`: 테스트
- `docs`: 프로젝트 문서

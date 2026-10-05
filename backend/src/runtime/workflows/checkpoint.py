"""Checkpoint는 JSON 기본 타입만 복원하며 임의 클래스 역직렬화를 허용하지 않습니다."""
import json
from contextlib import contextmanager

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres import PostgresSaver


class SafeJsonSerializer:
    def dumps_typed(self, value):
        return "json", json.dumps(value, ensure_ascii=False, allow_nan=False).encode()

    def loads_typed(self, value):
        kind, data = value
        if kind != "json":
            raise ValueError("알 수 없는 Checkpoint 직렬화 형식입니다.")
        return json.loads(data)


def memory_checkpoint():
    return InMemorySaver(serde=SafeJsonSerializer())


@contextmanager
def postgres_checkpoint(dsn):
    with PostgresSaver.from_conn_string(dsn) as saver:
        saver.serde = SafeJsonSerializer()
        saver.setup()
        yield saver

"""Checkpoint는 JSON 기본 타입만 복원하며 임의 클래스 역직렬화를 허용하지 않습니다."""
import json
from contextlib import contextmanager

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Interrupt


class SafeJsonSerializer:
    def dumps_typed(self, value):
        def encode(item):
            # SDK의 고정 Interrupt 한 타입만 허용합니다. pickle/동적 클래스 import는 금지합니다.
            if isinstance(item, Interrupt) and item.response_schema is None:
                return {"__serviq_interrupt__": {"id": item.id, "value": item.value}}
            raise TypeError("지원하지 않는 Checkpoint 값입니다.")
        return "json", json.dumps(value, ensure_ascii=False, allow_nan=False, default=encode).encode()

    def loads_typed(self, value):
        kind, data = value
        if kind != "json":
            raise ValueError("알 수 없는 Checkpoint 직렬화 형식입니다.")
        def decode(item):
            if set(item) == {"__serviq_interrupt__"}:
                safe = item["__serviq_interrupt__"]
                if not isinstance(safe, dict) or set(safe) != {"id", "value"} or not isinstance(safe["id"], str):
                    raise ValueError("유효한 승인 중단 Checkpoint가 아닙니다.")
                return Interrupt(id=safe["id"], value=safe["value"])
            return item
        return json.loads(data, object_hook=decode)


def memory_checkpoint():
    return InMemorySaver(serde=SafeJsonSerializer())


@contextmanager
def postgres_checkpoint(dsn):
    with PostgresSaver.from_conn_string(dsn) as saver:
        saver.serde = SafeJsonSerializer()
        saver.setup()
        yield saver

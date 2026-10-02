"""Deterministic normalization and source-aware de-duplication."""

from hashlib import sha256


def deduplicate[T](records: list[T], key: object) -> tuple[list[T], int]:
    seen: set[str] = set()
    unique: list[T] = []
    for record in records:
        value = str(key(record))
        digest = sha256(value.strip().lower().encode()).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        unique.append(record)
    return unique, len(records) - len(unique)

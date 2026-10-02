"""UTF-8 CSV loaders with schema and relationship validation."""

import csv
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from .models import Product, Review

Model = TypeVar("Model", bound=BaseModel)


class DataValidationError(ValueError):
    """A readable validation error for a CSV dataset."""


def _load(path: Path, model: type[Model]) -> list[Model]:  # noqa: UP047
    if not path.is_file():
        raise DataValidationError(f"file not found: {path}")
    with path.open(encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames:
            raise DataValidationError(f"empty file: {path}")
        missing = set(model.model_fields) - set(reader.fieldnames)
        if missing:
            raise DataValidationError(f"missing columns: {', '.join(sorted(missing))}")
        rows = list(reader)
    if not rows:
        raise DataValidationError(f"empty file: {path}")
    records: list[Model] = []
    for row_number, row in enumerate(rows, start=2):
        try:
            records.append(model.model_validate(row))
        except ValidationError as error:
            raise DataValidationError(f"row {row_number}: {error}") from error
    return records


def load_products(path: str | Path) -> list[Product]:
    return _load(Path(path), Product)


def load_reviews(path: str | Path, products: list[Product]) -> list[Review]:
    reviews = _load(Path(path), Review)
    product_ids = {product.product_id for product in products}
    orphans = [review.product_id for review in reviews if review.product_id not in product_ids]
    if orphans:
        raise DataValidationError(f"orphan product_id: {orphans[0]}")
    return reviews

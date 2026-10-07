"""Template·Mapping·Validation의 단일 정의. 실제 지원 Observation만 포함합니다."""
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class IntakeCommandResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["STORE", "IMPORT"]
    identifier: str = Field(min_length=1, max_length=128)
    store: str = Field(min_length=1, max_length=100)


@dataclass(frozen=True)
class Column:
    field: str
    label: str
    type: str
    required: bool
    example: str | int
    aliases: tuple[str, ...] = ()


STORE = Column("store", "매장명", "text", True, "체험 매장", ("지점", "지점명", "store_name", "store"))
SOURCE = Column("source_id", "자료ID", "identifier", True, "voc-001", ("id", "source_id", "번호"))
DATE = Column("observed_at", "발생일시", "datetime", True, "2026-10-07T09:00:00+09:00", ("접수일", "일자", "날짜", "observed_at", "date"))
SCHEMAS = {
    "매장": (STORE,),
    "VOC": (STORE, SOURCE, DATE,
        Column("text", "VOC 내용", "text", True, "품질 문제로 같은 메뉴 환불이 반복되었습니다.", ("고객의견", "내용", "review_text", "voc", "text")),
        Column("rating", "평점", "integer", True, 1, ("별점", "rating", "score")),
        Column("product", "제품명", "text", False, "체험 메뉴", ("메뉴", "상품명", "product", "product_name"))),
    "판매_거래": (STORE, SOURCE, DATE,
        Column("signal", "관측코드", "signal", True, "REFUND_SIGNAL", ("신호", "signal", "코드"))),
    "재고": (STORE, SOURCE, DATE,
        Column("signal", "관측코드", "signal", True, "STOCK_SHORTAGE", ("신호", "signal", "코드"))),
}


def schema_document():
    return {name: [{"field": c.field, "label": c.label, "type": c.type,
        "required": c.required, "example": c.example} for c in columns] for name, columns in SCHEMAS.items()}


def column_mapping(kind, headers, overrides=None):
    overrides = overrides or {}
    columns = SCHEMAS[kind]
    fields = {c.field for c in columns}
    if any(k not in headers for k in overrides) or any(v is not None and v not in fields for v in overrides.values()):
        raise ValueError("매핑할 원본 컬럼과 ServIQ 필드를 확인해 주세요.")
    def normalize(value):
        return re.sub(r"[\s_]", "", value).casefold()
    result = []
    for header in headers:
        matches = [c for c in columns if normalize(header) in {normalize(x) for x in (c.field, c.label, *c.aliases)}]
        target = overrides[header] if header in overrides else matches[0].field if len(matches) == 1 else None
        column = next((c for c in columns if c.field == target), None)
        result.append({"source": header, "target": target, "inferred_type": column.type if column else "unknown",
            "confidence": 1.0 if header in overrides or (column and header in (column.field, column.label)) else .9 if column else 0,
            "required": column.required if column else False, "warning": None if column else "미매핑: 가져오지 않습니다."})
    for item in result:
        if item["target"] and sum(other["target"] == item["target"] for other in result) > 1:
            target = item["target"]
            for other in result:
                if other["target"] == target:
                    other.update(target=None, confidence=0, warning="중복 후보입니다. 사용할 컬럼 하나를 직접 선택해 주세요.")
    return result


def validate_tables(tables, *, store, kind="VOC", mappings=None):
    """원본 source와 위치는 보존하되 오류에 입력 값을 복제하지 않습니다."""
    records, sheets, errors, warnings = [], [], [], []
    mappings = mappings or {}
    if len(mappings) > 5 or any(len(m) > 20 for m in mappings.values()):
        raise ValueError("매핑 범위를 초과했습니다.")
    for sheet, rows in tables:
        selected = sheet if sheet in SCHEMAS else kind
        if selected not in SCHEMAS:
            raise ValueError("지원하는 데이터 종류를 선택해 주세요.")
        columns, headers = SCHEMAS[selected], rows[0]
        mapping = column_mapping(selected, headers, mappings.get(sheet))
        targets = {m["target"] for m in mapping if m["target"]}
        sheet_errors, good, previews = [], 0, []
        for c in columns:
            if c.required and c.field not in targets:
                sheet_errors.append({"location": sheet+"!1", "code": "REQUIRED_COLUMN", "message": c.label+" 필수 컬럼을 연결해 주세요."})
        for row_number, row in enumerate(rows[1:], start=2):
            if not any(str(v).strip() for v in row):
                continue
            values = {m["target"]: row[i] if i < len(row) else "" for i, m in enumerate(mapping) if m["target"]}
            item, row_errors = {}, []
            for c in columns:
                value = values.get(c.field, "")
                position = next((i for i, m in enumerate(mapping) if m["target"] == c.field), 0)
                location = f"{sheet}!{chr(65+position)}{row_number}"
                try:
                    text = str(value).strip()
                    if not text:
                        if c.required:
                            raise ValueError("비어 있을 수 없습니다.")
                        item[c.field] = "입력 제품" if c.field == "product" else ""
                        continue
                    if text.startswith(("=", "+", "-", "@")) or any(ord(ch) < 32 and ch not in "\n\r\t" for ch in text):
                        raise ValueError("수식/제어 문자를 제거하고 값으로 입력해 주세요.")
                    if c.type == "identifier":
                        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", text):
                            raise ValueError("영문/숫자/._:- 1~64자로 입력해 주세요.")
                        item[c.field] = text
                    elif c.type == "datetime":
                        if isinstance(value, datetime):
                            parsed = value.replace(tzinfo=UTC) if value.tzinfo is None else value
                        elif isinstance(value, date) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
                            parsed = datetime.fromisoformat(text).replace(tzinfo=UTC)
                        else:
                            parsed = datetime.fromisoformat(text)
                            if parsed.utcoffset() is None:
                                raise ValueError()
                        item[c.field] = parsed.astimezone(UTC).isoformat()
                    elif c.type == "integer":
                        if not re.fullmatch(r"[1-5]", text):
                            raise ValueError("1~5 정수로 입력해 주세요.")
                        item[c.field] = int(text)
                    elif c.type == "signal":
                        allowed = {"REFUND_SIGNAL", "CANCEL_SIGNAL"} if selected == "판매_거래" else {"STOCK_SHORTAGE", "STOCK_ADJUSTMENT"}
                        if text not in allowed:
                            raise ValueError("지원하는 관측코드를 입력해 주세요: "+" / ".join(sorted(allowed)))
                        item[c.field] = text
                    else:
                        if len(text) > (2000 if c.field == "text" else 100) or (c.field == "text" and len(text) < 2):
                            raise ValueError("입력 길이를 줄여 주세요.")
                        item[c.field] = text
                    if c.field == "store" and item[c.field] != store:
                        raise ValueError("선택한 대상 매장과 동일해야 합니다.")
                except (ValueError, OverflowError):
                    row_errors.append({"location": location, "code": "INVALID_VALUE", "message": c.label+" 값/형식을 확인해 주세요."})
            if row_errors:
                sheet_errors.extend(row_errors)
            elif not any(e["code"] == "REQUIRED_COLUMN" for e in sheet_errors):
                good += 1
                records.append({"kind": selected, **item})
                if len(previews) < 5:
                    previews.append({key: ("[VOC 본문 미리보기 숨김]" if key == "text" else value) for key, value in item.items()})
        for m in mapping:
            if m["warning"]:
                warnings.append({"sheet": sheet, "column": m["source"], "message": m["warning"]})
        errors.extend(sheet_errors)
        sheets.append({"sheet": sheet, "kind": selected, "row_count": sum(any(str(v).strip() for v in r) for r in rows[1:]),
            "valid_rows": good, "error_rows": len({e["location"] for e in sheet_errors}), "mapping": mapping,
            "fields": [{"field": c.field, "label": c.label} for c in columns], "preview_rows": previews})
    identities = [(r["kind"], r.get("source_id", r["store"])) for r in records]
    if len(identities) != len(set(identities)):
        errors.append({"location": "Workbook", "code": "DUPLICATE_SOURCE", "message": "동일 종류의 자료ID가 중복되었습니다."})
    return {"sheets": sheets, "errors": errors[:100], "warnings": warnings[:100], "valid": not errors, "records": records}

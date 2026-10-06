"""파일 입력과 첫 실행 조회. 저장소 구현은 Application/UoW 뒤에 둡니다."""
import json

import psycopg
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from src.api.dependencies.auth import request_context
from src.api.errors import error_response
from src.application.data_intake import DataIntake
from src.application.intake_schema import schema_document
from src.application.ports.repositories import IncidentConflict
from src.application.security.authorization import require
from src.infrastructure.intake_workbook import (
    MAX_BYTES,
    IntakeFileError,
    parse_file,
    template_bytes,
)

router = APIRouter(prefix="/api/v1/data", tags=["data-intake"])


def service(request):
    return DataIntake(request.app.state.access_persistence, request_context(request))


@router.get("/onboarding")
def status(request: Request):
    try:
        return service(request).status()
    except psycopg.Error:
        return error_response(request, 503, "DATA_UNAVAILABLE", "입력 데이터 상태를 불러오지 못했습니다.")


class StoreInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    store: str = Field(min_length=1, max_length=100, pattern=r"^[^\x00-\x1f/\\]+$")


@router.post("/stores")
def add_store(body: StoreInput, request: Request):
    try:
        return service(request).add_store(body.store)
    except psycopg.Error:
        return error_response(request, 503, "DATA_UNAVAILABLE", "입력 저장소를 사용할 수 없습니다.")


class SampleInput(StoreInput):
    confirmed: bool = Field(strict=True)


class ConsentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: bool = Field(strict=True)


class AnalysisInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    topic: str = Field(min_length=2, max_length=100, pattern=r"^[^\x00-\x1f]+$")


@router.post("/initialize-runtime")
def initialize_runtime(body: ConsentInput, request: Request):
    if not body.confirmed:
        return error_response(request, 422, "CONFIRMATION_REQUIRED", "초기 설정 내용을 확인해 주세요.")
    return service(request).initialize_runtime()


@router.post("/imports/{import_id}/analysis")
def analyze(import_id: str, body: AnalysisInput, request: Request):
    try:
        return service(request).analyze(import_id, body.topic)
    except psycopg.Error:
        return error_response(request, 503, "DATA_UNAVAILABLE", "조사 저장소를 사용할 수 없습니다.")


@router.post("/sample")
def sample(body: SampleInput, request: Request):
    if not body.confirmed:
        return error_response(request, 422, "CONFIRMATION_REQUIRED", "Demo 데이터 추가 내용을 확인해 주세요.")
    try:
        return service(request).sample(body.store)
    except psycopg.Error:
        return error_response(request, 503, "DATA_UNAVAILABLE", "입력 저장소를 사용할 수 없습니다.")


@router.get("/schema")
def schema(request: Request):
    require(request_context(request).principal, "read")
    return {"version": "intake-1", "sheets": schema_document()}


@router.get("/template")
def template(request: Request):
    require(request_context(request).principal, "read")
    return Response(template_bytes(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="ServIQ-template-v1.xlsx"', "Cache-Control": "no-store"})


@router.post("/preview")
async def preview(request: Request):
    intake = service(request)
    require(intake.context.principal, "operate")
    content = bytearray()
    async for chunk in request.stream():
        if len(content)+len(chunk) > MAX_BYTES+20000:
            raise HTTPException(413, "파일 업로드 최대 크기는 2MB입니다.")
        content.extend(chunk)
    async def stream():
        yield bytes(content)
    try:
        form = await MultiPartParser(request.headers, stream(), max_files=1, max_fields=4, max_part_size=MAX_BYTES).parse()
        try:
            if len(form.multi_items()) != len(form) or set(form) - {"file", "store", "kind", "mappings"}:
                raise IntakeFileError("업로드 필드를 확인해 주세요.")
            file = form.get("file")
            if not isinstance(file, UploadFile):
                raise IntakeFileError("파일을 선택해 주세요.")
            store = StoreInput(store=form.get("store", "")).store
            mappings = json.loads(form.get("mappings", "{}"))
            if not isinstance(mappings, dict) or any(not isinstance(v, dict) for v in mappings.values()):
                raise IntakeFileError("컬럼 매핑 형식을 확인해 주세요.")
            kind = form.get("kind", "VOC")
            tables = parse_file(file.filename, await file.read(MAX_BYTES+1), file.content_type, kind)
            return intake.preview(tables, store, kind=kind, mappings=mappings)
        finally:
            await form.close()
    except (ValueError, MultiPartException, TypeError, AttributeError) as error:
        message = str(error) if isinstance(error, IntakeFileError) else "파일과 컬럼 매핑 형식을 확인해 주세요."
        return error_response(request, 422, "IMPORT_VALIDATION_ERROR", message)
    except psycopg.Error:
        return error_response(request, 503, "DATA_UNAVAILABLE", "입력 저장소를 사용할 수 없습니다.")


class ConfirmInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirmed: bool = Field(strict=True)


@router.post("/imports/{preview_id}/confirm")
def confirm(preview_id: str, body: ConfirmInput, request: Request):
    if not body.confirmed:
        return error_response(request, 422, "CONFIRMATION_REQUIRED", "매핑과 미리보기를 확인한 뒤 Import해 주세요.")
    try:
        return service(request).confirm(preview_id, body.digest)
    except IncidentConflict:
        raise
    except psycopg.Error:
        return error_response(request, 503, "DATA_UNAVAILABLE", "입력 저장소를 사용할 수 없습니다.")
    except ValueError:
        return error_response(request, 422, "IMPORT_VALIDATION_ERROR", "입력 행을 다시 확인해 주세요.")

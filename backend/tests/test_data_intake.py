"""입력 전후 서버 상태와 조직/매장 경계를 검증합니다."""
import json
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from src.api.app import create_app
from src.application.security.principal import Principal, Role
from src.infrastructure.auth.local_identity_provider import LocalIdentityProvider
from src.infrastructure.repositories.in_memory_incident_repository import (
    InMemoryIncidentRepository,
)


def client():
    identity = LocalIdentityProvider({
        "admin": Principal("admin", "a", frozenset({Role.HQ_ADMIN})),
        "other": Principal("other", "b", frozenset({Role.HQ_ADMIN})),
        "store": Principal("store", "a", frozenset({Role.STORE_MANAGER}), frozenset({"허용 매장"})),
        "reader": Principal("reader", "a", frozenset({Role.AUDITOR})),
    })
    return TestClient(create_app(InMemoryIncidentRepository(), identity_provider=identity))


def headers(token="admin", key="intake-one"):
    return {"Authorization": "Bearer "+token, "Idempotency-Key": key}


def test_onboarding_uses_server_stores_and_preserves_empty_data_status():
    c = client()
    assert c.get("/api/v1/data/onboarding", headers=headers()).json()["first_run"]
    for _ in range(2):
        assert c.post("/api/v1/data/stores", json={"store": "허용 매장"}, headers=headers()).status_code == 200
    status = c.get("/api/v1/data/onboarding", headers=headers()).json()
    assert status["stores"] == ["허용 매장"] and not status["has_data"]
    assert not c.get("/api/v1/data/onboarding", headers=headers("other")).json()["stores"]


def test_store_scope_role_and_extra_tenant_are_rejected():
    c = client()
    for token in ("reader", "store"):
        assert c.post("/api/v1/data/stores", json={"store": "다른 매장"}, headers=headers(token)).status_code == 403
    assert c.post("/api/v1/data/stores", json={"store": "허용 매장", "tenant": "b"}, headers=headers()).status_code == 422
    assert c.post("/api/v1/data/stores", json={"store": "../escape"}, headers=headers()).status_code == 422


def test_template_headers_examples_and_validation_share_one_schema():
    from src.application.intake_schema import SCHEMAS, validate_tables
    from src.infrastructure.intake_workbook import parse_file
    c = client()
    response = c.get("/api/v1/data/template", headers=headers())
    assert response.status_code == 200
    tables = parse_file("template.xlsx", response.content, response.headers["content-type"])
    assert {name for name, _ in tables} == set(SCHEMAS)
    assert validate_tables(tables, store="체험 매장")["valid"]
    for name, rows in tables:
        assert rows[0] == [col.label for col in SCHEMAS[name]]


CSV = "매장명,자료ID,발생일시,VOC 내용,평점\n허용 매장,voc-1,2026-10-07,품질 문제가 반복됩니다.,1\n"


def registered():
    c = client()
    assert c.post("/api/v1/data/stores", json={"store": "허용 매장"}, headers=headers()).status_code == 200
    return c


def upload(c, content=CSV, *, filename="voc.csv", mime="text/csv", token="admin", mapping=None):
    return c.post("/api/v1/data/preview", headers=headers(token),
        data={"store": "허용 매장", "kind": "VOC", "mappings": json.dumps(mapping or {})},
        files={"file": (filename, content.encode() if isinstance(content, str) else content, mime)})


def test_preview_is_not_canonical_and_confirm_is_atomic_idempotent():
    c = registered()
    preview = upload(c).json()
    assert preview["valid"] and preview["row_count"] == 1
    assert not c.get("/api/v1/data/onboarding", headers=headers()).json()["has_data"]
    with c.app.state.access_persistence.transaction("a") as uow:
        assert uow.intake.list("SOURCE") == []
    path = "/api/v1/data/imports/"+preview["preview_id"]+"/confirm"
    body = {"digest": preview["digest"], "confirmed": True}
    first = c.post(path, json=body, headers=headers(key="confirm"))
    assert first.status_code == 200 and first.json()["row_count"] == 1
    assert c.post(path, json=body, headers=headers(key="confirm")).json() == first.json()
    assert c.post(path, json={**body, "digest": "a"*64}, headers=headers(key="confirm")).status_code == 409
    assert c.get("/api/v1/data/onboarding", headers=headers()).json()["has_data"]
    assert "품질 문제가" not in first.text
    with c.app.state.access_persistence.transaction("a") as uow:
        assert len(uow.intake.list("SOURCE")) == 1 and not uow.intake.list("PREVIEW")


@pytest.mark.parametrize("content,filename,mime", [
    (b"", "empty.csv", "text/csv"), (b"bad", "bad.xls", "application/octet-stream"),
    (b"not a workbook", "bad.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    (b"PK\x03\x04bad", "bad.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    (b"abc", "../bad.csv", "text/csv"), (b"x"*2_000_001, "large.csv", "text/csv"),
    ("매장명,매장명\n허용 매장,허용 매장".encode(), "duplicate.csv", "text/csv"),
], ids=["empty", "unsupported", "signature", "malformed-zip", "path", "oversized", "duplicate-header"])
def test_malformed_unsupported_or_oversized_files_are_safe(content, filename, mime):
    c = registered()
    assert upload(c, content, filename=filename, mime=mime).status_code in {413, 422}
    assert not c.get("/api/v1/data/onboarding", headers=headers()).json()["has_data"]


@pytest.mark.parametrize("content,code", [(CSV.replace("2026-10-07", "invalid-date"), "INVALID_VALUE"),
    (CSV.replace(".,1", ".,7"), "INVALID_VALUE"),
    (CSV.replace("VOC 내용", "알수없는필드"), "REQUIRED_COLUMN"),
    (CSV.replace("품질 문제가 반복됩니다.", "=WEBSERVICE(\"https://example.com\")"), "INVALID_VALUE")])
def test_row_validation_prevents_partial_import(content, code):
    c = registered()
    response = upload(c, content)
    assert response.status_code == 200
    result = response.json()
    assert not result["valid"] and any(e["code"] == code for e in result["errors"])
    assert not c.get("/api/v1/data/onboarding", headers=headers()).json()["has_data"]


def test_user_corrected_mapping_and_scope_enforcement():
    c = registered()
    raw = CSV.replace("VOC 내용", "담당메모")
    assert not upload(c, raw).json()["valid"]
    corrected = upload(c, raw, mapping={"VOC": {"담당메모": "text"}}).json()
    assert corrected["valid"]
    path = "/api/v1/data/imports/"+corrected["preview_id"]+"/confirm"
    body = {"digest": corrected["digest"], "confirmed": True}
    assert c.post(path, json=body, headers=headers("other")).status_code == 404
    assert c.post(path, json=body, headers=headers("reader")).status_code == 403
    assert c.post(path, json=body, headers=headers("store")).status_code == 403  # different owner
    assert upload(c, CSV, token="reader").status_code == 403


def test_formula_workbook_rejected_without_execution():
    book = Workbook()
    sheet = book.active
    sheet.title = "VOC"
    sheet.append(["매장명", "자료ID", "발생일시", "VOC 내용", "평점"])
    sheet.append(["허용 매장", "id", "2026-10-07", '=HYPERLINK("https://example.com")', 1])
    output = BytesIO()
    book.save(output)
    assert upload(registered(), output.getvalue(), filename="formula.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet").status_code == 422


def test_sample_is_tenant_scoped_marked_and_version_idempotent():
    c = registered()
    body = {"store": "허용 매장", "confirmed": True}
    first = c.post("/api/v1/data/sample", json=body, headers=headers(key="demo-1"))
    assert first.status_code == 200 and first.json()["sample"] and first.json()["row_count"] == 4
    assert c.post("/api/v1/data/sample", json=body, headers=headers(key="demo-2")).json() == first.json()
    assert c.post("/api/v1/data/sample", json=body, headers=headers("other")).status_code == 404
    assert c.post("/api/v1/data/sample", json=body, headers=headers("reader")).status_code == 403
    assert c.post("/api/v1/data/sample", json={**body, "confirmed": False}, headers=headers()).status_code == 422
    with c.app.state.access_persistence.transaction("a") as uow:
        rows = uow.intake.list("SOURCE")
        assert len(rows) == 4 and all(r["sample"] for r in rows)


def test_first_analysis_uses_real_commands_jev_and_persistent_job():
    c = registered()
    receipt = c.post("/api/v1/data/sample", json={"store": "허용 매장", "confirmed": True}, headers=headers(key="sample")).json()
    path = "/api/v1/data/imports/"+receipt["import_id"]+"/analysis"
    assert c.post(path, json={"topic": "품질"}, headers=headers(key="analysis")).status_code == 409
    assert c.post("/api/v1/data/initialize-runtime", json={"confirmed": True}, headers=headers(key="init")).status_code == 200
    first = c.post(path, json={"topic": "품질"}, headers=headers(key="analysis"))
    assert first.status_code == 200, first.text
    assert c.post(path, json={"topic": "품질"}, headers=headers(key="analysis")).json() == first.json()
    assert c.post(path, json={"topic": "다른 주제"}, headers=headers(key="analysis")).status_code == 409
    assert c.post(path, json={"topic": "품질"}, headers=headers("other")).status_code == 404
    status = c.get("/api/v1/data/onboarding", headers=headers()).json()
    assert status["checklist"]["incident"] and status["analysis_configured"]
    assert status["imports"][0]["incident_id"] == first.json()["incident_id"]
    assert not status["can_initialize_runtime"]
    with c.app.state.access_persistence.transaction("a") as uow:
        job = uow.jobs.get(first.json()["job_id"])
        assert job.job_type == "incident.history_investigation" and job.delegated_principal_id == "admin"
        assert uow.decisions.get(job.payload_ref).incident_id == first.json()["incident_id"]
        assert not uow.configs.current().config.hosted_ai_allowed


def test_source_conflict_rolls_back_without_overwriting_existing_data():
    c = registered()
    def confirm(preview, key):
        return c.post("/api/v1/data/imports/"+preview["preview_id"]+"/confirm", headers=headers(key=key),
            json={"digest": preview["digest"], "confirmed": True})
    assert confirm(upload(c).json(), "one").status_code == 200
    changed = upload(c, CSV.replace("품질 문제가 반복됩니다.", "다른 내용으로 변경")).json()
    assert confirm(changed, "two").status_code == 409
    with c.app.state.access_persistence.transaction("a") as uow:
        assert len(uow.intake.list("SOURCE")) == 1
        assert uow.intake.list("SOURCE")[0]["text"] == "품질 문제가 반복됩니다."


def test_ambiguous_columns_require_explicit_mapping_and_store_cannot_be_forged():
    c = registered()
    ambiguous = CSV.replace("VOC 내용,평점", "VOC 내용,고객의견,평점").replace("반복됩니다.,1", "반복됩니다.,다른 의견,1")
    result = upload(c, ambiguous).json()
    assert not result["valid"] and any(m["warning"] for m in result["sheets"][0]["mapping"])
    assert upload(c, ambiguous, mapping={"VOC": {"VOC 내용": "text", "고객의견": None}}).json()["valid"]
    assert not upload(c, CSV.replace("허용 매장", "비허용 매장")).json()["valid"]


def test_external_link_and_macro_archives_are_rejected():
    from zipfile import ZIP_DEFLATED, ZipFile
    for path in ("xl/externalLinks/externalLink1.xml", "xl/vbaProject.bin", "../traversal.xml"):
        output = BytesIO()
        with ZipFile(output, "w", ZIP_DEFLATED) as archive:
            archive.writestr(path, "untrusted")
        assert upload(registered(), output.getvalue(), filename="unsafe.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet").status_code == 422


def test_demo_and_operational_imports_cannot_be_mixed_in_one_store():
    c = registered()
    assert c.post("/api/v1/data/sample", headers=headers(key="sample"),
        json={"store": "허용 매장", "confirmed": True}).status_code == 200
    preview = upload(c).json()
    assert c.post("/api/v1/data/imports/"+preview["preview_id"]+"/confirm", headers=headers(key="confirm"),
        json={"digest": preview["digest"], "confirmed": True}).status_code == 409
    with c.app.state.access_persistence.transaction("a") as uow:
        assert len(uow.intake.list("SOURCE")) == 4 and all(r["sample"] for r in uow.intake.list("SOURCE"))
    real = registered()
    preview = upload(real).json()
    assert real.post("/api/v1/data/imports/"+preview["preview_id"]+"/confirm", headers=headers(key="confirm"),
        json={"digest": preview["digest"], "confirmed": True}).status_code == 200
    assert real.post("/api/v1/data/sample", headers=headers(key="sample"),
        json={"store": "허용 매장", "confirmed": True}).status_code == 409

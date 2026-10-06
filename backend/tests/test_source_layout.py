"""폴더 통합 뒤에도 책임 경계와 실제 실행 위치를 유지합니다."""
import ast
import importlib
import re
from pathlib import Path

ROOT = Path(__file__).parents[2]
SOURCE = ROOT / "backend/src"


def imports(path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            yield node.module or ""


def test_obsolete_package_locations_have_no_source():
    for obsolete in ("decision", "runtime", "application/commands",
                     "infrastructure/queue", "infrastructure/outbox",
                     "domain/workflows", "application/workflows", "infrastructure/workflows",
                     "domain/decisions", "application/decisions", "application/llm"):
        assert not list((SOURCE / obsolete).rglob("*.py")), obsolete


def test_domain_is_independent_of_application_and_execution_technology():
    files = list((SOURCE / "domain").rglob("*.py"))
    files += [SOURCE / f"agents/{name}.py" for name in
              ("models", "safe", "policy", "sufficiency", "verification_contracts", "verification_rules")]
    files += [SOURCE / f"routing/{name}.py" for name in ("models", "engine", "profiles", "rules")]
    assert files and (SOURCE / "routing/engine.py").is_file()
    forbidden = ("src.api", "src.application", "src.infrastructure",
                 "langgraph", "psycopg", "google", "ollama", "src.llm.providers",
                 "src.agents.graph", "src.agents.checkpoint", "src.agents.processor",
                 "src.agents.capa_commands", "src.agents.verification_commands",
                 "src.routing.context", "src.routing.queries", "src.routing.shadow")
    for path in files:
        assert not any(module.startswith(forbidden) for module in imports(path)), path


def test_workflow_nodes_do_not_import_graph_or_provider_adapters():
    for name in ("history_node", "rca_node", "capa_node"):
        path = SOURCE / f"agents/{name}.py"
        assert path.is_file()
        assert not any(module.startswith(("langgraph", "src.infrastructure",
            "src.llm.providers", "google", "ollama")) for module in imports(path)), path
    for name in ("graph", "checkpoint", "processor"):
        assert (SOURCE / f"agents/{name}.py").is_file()


def test_llm_contracts_do_not_import_provider_sdk_or_runtime_wiring():
    for name in ("contracts", "errors"):
        path = SOURCE / f"llm/{name}.py"
        assert path.is_file()
        assert not any(module.startswith(("google", "ollama", "src.llm.providers",
            "src.llm.runtime", "src.llm.service", "psycopg")) for module in imports(path)), path
    for name in ("runtime", "config", "service", "queries"):
        assert (SOURCE / f"llm/{name}.py").is_file()
    assert not (SOURCE / "infrastructure/llm_runtime.py").exists()
    assert not (SOURCE / "infrastructure/llm_config.py").exists()


def test_compose_worker_uses_real_consolidated_entrypoint():
    module = importlib.import_module("src.infrastructure.jobs.runtime")
    assert callable(module.main)
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert '"src.infrastructure.jobs.runtime"' in compose


def test_frontend_connection_settings_are_not_owned_by_incident_adapter():
    api = ROOT / "frontend/src/api"
    assert (api / "client.ts").is_file() and not (api / "auth.ts").exists()
    for path in (ROOT / "frontend/src").rglob("*"):
        if path.suffix not in {".ts", ".tsx"}:
            continue
        text = path.read_text(encoding="utf-8")
        assert not re.search(r'from\s*["\'][^"\']*(?:api/auth|\.\./auth)["\']', text), path
        for names in re.findall(r'import\s*\{([^}]+)\}\s*from\s*["\'][^"\']*incidents["\']', text):
            assert "apiMode" not in names and "apiBaseUrl" not in names, path

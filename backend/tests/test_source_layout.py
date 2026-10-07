"""파일 이름 대신 실제 정의와 import/call 방향으로 안전 경계를 검사합니다."""
import ast
from pathlib import Path

import pytest

SOURCE = Path(__file__).parents[1] / "src"
SDK = ("google", "ollama")
PURE = ("fastapi", "psycopg", "langgraph", "src.api", "src.infrastructure",
        "src.application", "src.ai.intelligence.service", "src.ai.workflow.runtime",
        "src.ai.execution.service", "src.ai.decision.service", *SDK)
ROLES = {
    "decision": {"DecisionContext", "DecisionResult", "JevEngine", "safety_and_risk", "select_profile", "build_context"},
    "contracts": {"WorkflowState", "SafeModel", "VerificationCandidate", "LLMIntent", "LLMProvider", "LLMError", "AgentDefinition", "AgentContextPack", "InvestigationResult", "LoopPolicy", "AgentRunManifest", "HarnessIntent", "HarnessDecision", "RuntimeEvent", "ToolContract", "ToolInput", "ToolResult", "ToolCall", "ToolError", "ToolExecutionContext", "PromptContract", "PromptReference"},
    "nodes": {"HistoryInvestigation", "RCAInvestigation", "CAPAInvestigation", "OperationalInvestigation", "ToolInvestigation"},
}


def imported_symbols(path, node):
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if not isinstance(node, ast.ImportFrom):
        return []
    module = node.module or ""
    if node.level:
        package = ("src", *path.relative_to(SOURCE).parent.parts)
        anchor = package[:len(package) - node.level + 1]
        module = ".".join((*anchor, *module.split("."))) if module else ".".join(anchor)
    return [module + "." + alias.name for alias in node.names]


def modules():
    for path in SOURCE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        definitions = {node.name for node in tree.body if isinstance(node,
            (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))}
        imports = []
        for node in ast.walk(tree):
            imports.extend(imported_symbols(path, node))
        yield path, tree, definitions, imports


@pytest.mark.parametrize("role", tuple(ROLES))
def test_runtime_role_dependency_direction(role):
    found = set()
    forbidden = PURE if role != "nodes" else (
        "src.infrastructure.repositories", "src.ai.intelligence.providers",
        "src.ai.execution.service", "mcp", "langgraph", *SDK)
    for path, tree, definitions, imports in modules():
        matched = definitions & ROLES[role]
        if not matched:
            continue
        found |= matched
        assert not any(name.startswith(forbidden) for name in imports), path
        if role == "decision":
            assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"transaction", "save", "generate", "invoke", "call_tool"}
                for node in ast.walk(tree)), path
    assert found == ROLES[role], (role, ROLES[role] - found)


def test_domain_and_shared_contracts_do_not_import_execution_technology():
    for path, _, _, imports in modules():
        if path.relative_to(SOURCE).parts[0] == "domain":
            assert not any(name.startswith(PURE) for name in imports), path


def test_api_and_workflow_do_not_import_repository_implementations():
    for path, _, _, imports in modules():
        parts = path.relative_to(SOURCE).parts
        if parts[:2] == ("api", "routes") or parts[:2] == ("ai", "workflow"):
            assert not any(name.startswith("src.infrastructure.repositories") for name in imports), path


def test_sdk_is_only_used_in_provider_adapters():
    for path, _, _, imports in modules():
        if "providers" not in path.relative_to(SOURCE).parts:
            assert not any(name.startswith(SDK) for name in imports), path


def test_ax_projection_is_read_only_and_does_not_execute_ai_or_domain_commands():
    pure_ax = {"models.py", "projector.py", "actions.py", "explanations.py", "releases.py"}
    for path, tree, _, imports in modules():
        if path.relative_to(SOURCE).parts[:2] != ("ai", "ax") or path.name not in pure_ax:
            continue
        assert not any(name.startswith(("src.infrastructure", "src.api", "fastapi", "psycopg", "langgraph",
            "src.ai.intelligence.service", "src.ai.execution.runtime", *SDK)) for name in imports), path
        assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"save", "transaction", "approve", "reject", "execute", "invoke", "call_tool"}
            for node in ast.walk(tree)), path


def test_intelligence_cannot_mutate_incident_or_authorize_tools():
    for path, tree, _, imports in modules():
        if path.relative_to(SOURCE).parts[:2] != ("ai", "intelligence"):
            continue
        assert not any(name.endswith((".IncidentService", ".IncidentCommands", ".Incident"))
            for name in imports), path
        assert not any(isinstance(node, (ast.Assign, ast.AnnAssign)) and any(
            isinstance(target, ast.Attribute) and target.attr == "status"
            for target in (node.targets if isinstance(node, ast.Assign) else [node.target]))
            for node in ast.walk(tree)), path


def test_execution_does_not_bypass_application_or_open_external_transport():
    for path, _, _, imports in modules():
        if path.relative_to(SOURCE).parts[:2] == ("ai", "execution"):
            assert not any(name.startswith(("src.infrastructure.repositories", "httpx", "requests",
                "subprocess", "google", "ollama", "mcp")) for name in imports), path


def test_ai_modules_have_no_dependency_cycle():
    graph = {}
    for path, _, _, imports in modules():
        if path.relative_to(SOURCE).parts[0] != "ai":
            continue
        module = "src." + ".".join(path.relative_to(SOURCE).with_suffix("").parts)
        graph[module] = imports
    assert graph
    edges = {module: {target for target in graph if any(
        name == target or name.startswith(target + ".") for name in imports)} - {module}
        for module, imports in graph.items()}

    def visit(module, chain):
        assert module not in chain, " → ".join((*chain, module))
        for target in edges[module]:
            visit(target, (*chain, module))
    for module in graph:
        visit(module, ())


@pytest.mark.parametrize("statement, expected", [
    ("from ..intelligence.providers import gemini", "src.ai.intelligence.providers.gemini"),
    ("from ...infrastructure import repositories", "src.infrastructure.repositories"),
    ("from . import models", "src.ai.workflow.models"),
    ("import google.genai as sdk", "google.genai"),
])
def test_dependency_rules_cannot_be_bypassed_with_relative_imports_or_aliases(statement, expected):
    path = SOURCE / "ai" / "workflow" / "example.py"
    assert imported_symbols(path, ast.parse(statement).body[0]) == [expected]

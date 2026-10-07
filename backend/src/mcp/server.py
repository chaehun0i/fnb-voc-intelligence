"""Official SDK adapter bound to an already-authorized runtime session.

No HTTP route, authentication substitute, shell or transport-provided principal.
"""
import json
from functools import partial

import anyio
from mcp import Client
from mcp.server import MCPServer
from mcp.types import CallToolResult, TextContent, Tool, ToolAnnotations

from src.ai.execution.tools import (
    READ_TOOLS,
    ToolFailure,
    ToolInput,
    ToolResult,
    tool_error,
)
from src.application.incidents.service import IncidentNotFound
from src.application.security.principal import AccessError


class ReadToolServer(MCPServer):
    def __init__(self, harness):
        super().__init__(name="ServIQ read business tools", version=READ_TOOLS.version, log_level="ERROR")
        self.harness = harness

    async def list_tools(self):
        return [Tool(name=t.name, description=t.description,
            input_schema=json.loads(t.input_schema_json), output_schema=json.loads(t.output_schema_json),
            annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False,
                idempotent_hint=True, open_world_hint=False),
            meta={"version": t.version, "bundle": READ_TOOLS.version,
                "when_to_use": t.when_to_use, "when_not_to_use": t.when_not_to_use,
                "preconditions": list(t.preconditions), "common_errors": list(t.common_errors),
                "retry_guidance": t.retry_guidance}) for t in READ_TOOLS.contracts()]

    async def call_tool(self, name, arguments, context=None):
        try:
            contract = READ_TOOLS.resolve(name)
            validated = ToolInput.model_validate(arguments)
            with anyio.fail_after(contract.timeout_seconds):
                result = await anyio.to_thread.run_sync(partial(self.harness.execute,
                    name, validated.model_dump()), abandon_on_cancel=True)
            value, failed = ToolResult.model_validate(result.model_dump()).model_dump(mode="json"), False
        except ToolFailure as error:
            value, failed = error.error.model_dump(mode="json"), True
        except AccessError:
            value, failed = tool_error("ACCESS_DENIED").model_dump(mode="json"), True
        except IncidentNotFound:
            value, failed = tool_error("NO_DATA").model_dump(mode="json"), True
        except ValueError:
            value, failed = tool_error("INVALID_CONTRACT").model_dump(mode="json"), True
        except TimeoutError:
            value, failed = tool_error("SOURCE_TIMEOUT").model_dump(mode="json"), True
        except Exception:  # noqa: BLE001 -- final protocol boundary must not disclose vendor exceptions.
            # Vendor messages, stack traces and credentials never cross the protocol.
            value, failed = tool_error("OUTCOME_UNKNOWN").model_dump(mode="json"), True
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(value, ensure_ascii=False))],
            structured_content=value, is_error=failed)


async def call_in_memory(harness, name, arguments):
    async with Client(ReadToolServer(harness), read_timeout_seconds=12) as client:
        result = await client.call_tool(name, arguments)
    if result.is_error:
        from src.ai.execution.tools import ToolError
        raise ToolFailure(ToolError.model_validate(result.structured_content))
    return ToolResult.model_validate(result.structured_content)

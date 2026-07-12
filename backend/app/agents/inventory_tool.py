import logging

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from backend.app.logging.agent_logger import log_agent_interaction

logger = logging.getLogger(__name__)

INVENTORY_AGENT_ID = "inventory"
QUERY_INVENTORY_TOOL_NAME = "query_inventory"

INVENTORY_TOOL_DESCRIPTION = (
    "Query the system inventory database (ChromaDB) for servers, hosts, VMs, "
    "network devices, and other infrastructure assets. "
    "Use this when you need asset information to answer the user's question."
)

INVENTORY_TOOL_PROMPT_HINT = (
    "You have access to the query_inventory tool for looking up system inventory "
    "(servers, hosts, VMs, network devices) stored in ChromaDB. "
    "Use it when the question involves infrastructure assets or when host/server details are needed."
)


class InventoryQueryInput(BaseModel):
    query: str = Field(
        description="Natural-language question about system inventory assets",
        min_length=1,
    )


async def _run_inventory_query(query: str, *, caller_agent_id: str | None = None) -> str:
    from backend.app.services.inventory import get_inventory_service

    service = get_inventory_service()
    result = await service.query(query)

    log_input = query
    if caller_agent_id:
        log_input = f"[caller={caller_agent_id}] {query}"

    log_agent_interaction(
        agent_id=INVENTORY_AGENT_ID,
        input_message=log_input,
        output_message=result.content,
        tools_used=[],
    )
    logger.info(
        "Inventory queried via tool (caller=%s, query=%s)",
        caller_agent_id or "unknown",
        query[:120],
    )
    return result.content


def create_inventory_tool(*, caller_agent_id: str | None = None) -> StructuredTool:
    async def _query_inventory(query: str) -> str:
        return await _run_inventory_query(query, caller_agent_id=caller_agent_id)

    return StructuredTool.from_function(
        coroutine=_query_inventory,
        name=QUERY_INVENTORY_TOOL_NAME,
        description=INVENTORY_TOOL_DESCRIPTION,
        args_schema=InventoryQueryInput,
    )

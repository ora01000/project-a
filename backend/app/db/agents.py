from dataclasses import dataclass
from pathlib import Path

from backend.app.agents.base import AgentDefinition
from backend.app.db.database import get_connection


@dataclass(frozen=True)
class StoredAgent:
    idx: int
    agent_id: str
    name: str
    role: str
    system_prompt: str
    mcp_server_keys: list[str]


def encode_mcp_server_keys(keys: list[str]) -> str:
    return ",".join(keys)


def decode_mcp_server_keys(value: str) -> list[str]:
    if not value.strip():
        return []
    return [key.strip() for key in value.split(",") if key.strip()]


def _row_to_stored_agent(row) -> StoredAgent:
    return StoredAgent(
        idx=int(row["idx"]),
        agent_id=str(row["agent_id"]),
        name=str(row["name"]),
        role=str(row["role"]),
        system_prompt=str(row["system_prompt"]),
        mcp_server_keys=decode_mcp_server_keys(str(row["mcp_server_keys"])),
    )


def to_agent_definition(agent: StoredAgent) -> AgentDefinition:
    return AgentDefinition(
        agent_id=agent.agent_id,
        name=agent.name,
        role=agent.role,
        mcp_server_keys=list(agent.mcp_server_keys),
        system_prompt=agent.system_prompt,
    )


def list_stored_agents(database_path: str | Path) -> list[StoredAgent]:
    with get_connection(database_path) as connection:
        rows = connection.execute(
            """
            SELECT idx, agent_id, name, role, system_prompt, mcp_server_keys
            FROM agents
            ORDER BY idx
            """
        ).fetchall()
    return [_row_to_stored_agent(row) for row in rows]


def list_agent_definitions(database_path: str | Path) -> list[AgentDefinition]:
    return [to_agent_definition(agent) for agent in list_stored_agents(database_path)]


def get_stored_agent_by_idx(database_path: str | Path, idx: int) -> StoredAgent | None:
    with get_connection(database_path) as connection:
        row = connection.execute(
            """
            SELECT idx, agent_id, name, role, system_prompt, mcp_server_keys
            FROM agents
            WHERE idx = ?
            """,
            (idx,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_stored_agent(row)


def get_stored_agent_by_id(database_path: str | Path, agent_id: str) -> StoredAgent | None:
    with get_connection(database_path) as connection:
        row = connection.execute(
            """
            SELECT idx, agent_id, name, role, system_prompt, mcp_server_keys
            FROM agents
            WHERE agent_id = ?
            """,
            (agent_id,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_stored_agent(row)


def get_agent_definition_by_id(database_path: str | Path, agent_id: str) -> AgentDefinition | None:
    stored_agent = get_stored_agent_by_id(database_path, agent_id)
    if stored_agent is None:
        return None
    return to_agent_definition(stored_agent)


def create_agent(
    database_path: str | Path,
    *,
    agent_id: str,
    name: str,
    role: str,
    system_prompt: str,
    mcp_server_keys: list[str],
) -> StoredAgent:
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO agents (agent_id, name, role, system_prompt, mcp_server_keys)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                agent_id.strip(),
                name.strip(),
                role.strip(),
                system_prompt,
                encode_mcp_server_keys(mcp_server_keys),
            ),
        )
        connection.commit()
        idx = int(cursor.lastrowid)

    agent = get_stored_agent_by_idx(database_path, idx)
    if agent is None:
        raise RuntimeError("Failed to load created agent")
    return agent


def update_agent(
    database_path: str | Path,
    idx: int,
    *,
    agent_id: str,
    name: str,
    role: str,
    system_prompt: str,
    mcp_server_keys: list[str],
) -> StoredAgent | None:
    with get_connection(database_path) as connection:
        connection.execute(
            """
            UPDATE agents
            SET agent_id = ?, name = ?, role = ?, system_prompt = ?, mcp_server_keys = ?
            WHERE idx = ?
            """,
            (
                agent_id.strip(),
                name.strip(),
                role.strip(),
                system_prompt,
                encode_mcp_server_keys(mcp_server_keys),
                idx,
            ),
        )
        connection.commit()

    return get_stored_agent_by_idx(database_path, idx)


def delete_agents(database_path: str | Path, idx_list: list[int]) -> int:
    if not idx_list:
        return 0

    placeholders = ", ".join("?" for _ in idx_list)
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            f"DELETE FROM agents WHERE idx IN ({placeholders})",
            idx_list,
        )
        connection.commit()
        return int(cursor.rowcount)

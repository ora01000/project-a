"""Legacy local inventory_api helpers (metadata moved to remote inventory-api)."""

from __future__ import annotations


def ensure_inventory_api_table(connection) -> None:
    """Drop legacy local inventory_api table."""
    connection.execute("DROP TABLE IF EXISTS inventory_api CASCADE")

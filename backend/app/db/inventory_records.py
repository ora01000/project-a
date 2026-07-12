from dataclasses import dataclass
from pathlib import Path

from backend.app.db.database import get_connection

CHUNK_TYPE_ROW = 1
CHUNK_TYPE_CUSTOM = 2

MODIFIED_EMBEDDED = 0
MODIFIED_NEEDS_EMBED = 1


@dataclass(frozen=True)
class StoredInventory:
    idx: int
    inventory_name: str
    inventory_file: str
    file_ext: str
    chunk_type: int
    chunk_size: int
    modified: int


def _row_to_stored_inventory(row) -> StoredInventory:
    return StoredInventory(
        idx=int(row["idx"]),
        inventory_name=str(row["inventory_name"]),
        inventory_file=str(row["inventory_file"]),
        file_ext=str(row["file_ext"]),
        chunk_type=int(row["chunk_type"]),
        chunk_size=int(row["chunk_size"]),
        modified=int(row["modified"]),
    )


def extract_file_ext(filename: str) -> str:
    extension = Path(filename).suffix.removeprefix(".")
    return extension.lower()


def list_stored_inventory(database_path: str | Path) -> list[StoredInventory]:
    with get_connection(database_path) as connection:
        rows = connection.execute(
            """
            SELECT idx, inventory_name, inventory_file, file_ext, chunk_type, chunk_size, modified
            FROM inventory
            ORDER BY idx
            """
        ).fetchall()
    return [_row_to_stored_inventory(row) for row in rows]


def get_stored_inventory_by_idx(database_path: str | Path, idx: int) -> StoredInventory | None:
    with get_connection(database_path) as connection:
        row = connection.execute(
            """
            SELECT idx, inventory_name, inventory_file, file_ext, chunk_type, chunk_size, modified
            FROM inventory
            WHERE idx = ?
            """,
            (idx,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_stored_inventory(row)


def create_inventory_record(
    database_path: str | Path,
    *,
    inventory_name: str,
    inventory_file: str,
    file_ext: str,
    chunk_type: int,
    chunk_size: int,
    modified: int = MODIFIED_NEEDS_EMBED,
) -> StoredInventory:
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO inventory (inventory_name, inventory_file, file_ext, chunk_type, chunk_size, modified)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                inventory_name.strip(),
                inventory_file.strip(),
                file_ext.strip(),
                chunk_type,
                chunk_size,
                modified,
            ),
        )
        connection.commit()
        idx = int(cursor.lastrowid)

    record = get_stored_inventory_by_idx(database_path, idx)
    if record is None:
        raise RuntimeError("Failed to load created inventory record")
    return record


def update_inventory_record(
    database_path: str | Path,
    idx: int,
    *,
    inventory_name: str,
    inventory_file: str | None = None,
    file_ext: str | None = None,
    chunk_type: int | None = None,
    chunk_size: int | None = None,
    modified: int | None = None,
) -> StoredInventory | None:
    existing = get_stored_inventory_by_idx(database_path, idx)
    if existing is None:
        return None

    next_inventory_file = inventory_file if inventory_file is not None else existing.inventory_file
    next_file_ext = file_ext if file_ext is not None else existing.file_ext
    next_chunk_type = chunk_type if chunk_type is not None else existing.chunk_type
    next_chunk_size = chunk_size if chunk_size is not None else existing.chunk_size
    next_modified = modified if modified is not None else existing.modified

    with get_connection(database_path) as connection:
        connection.execute(
            """
            UPDATE inventory
            SET inventory_name = ?, inventory_file = ?, file_ext = ?, chunk_type = ?, chunk_size = ?, modified = ?
            WHERE idx = ?
            """,
            (
                inventory_name.strip(),
                next_inventory_file.strip(),
                next_file_ext.strip(),
                next_chunk_type,
                next_chunk_size,
                next_modified,
                idx,
            ),
        )
        connection.commit()

    return get_stored_inventory_by_idx(database_path, idx)


def update_inventory_modified(database_path: str | Path, idx: int, modified: int) -> StoredInventory | None:
    with get_connection(database_path) as connection:
        connection.execute(
            "UPDATE inventory SET modified = ? WHERE idx = ?",
            (modified, idx),
        )
        connection.commit()
    return get_stored_inventory_by_idx(database_path, idx)


def delete_inventory_records(database_path: str | Path, idx_list: list[int]) -> list[StoredInventory]:
    if not idx_list:
        return []

    placeholders = ", ".join("?" for _ in idx_list)
    with get_connection(database_path) as connection:
        rows = connection.execute(
            f"""
            SELECT idx, inventory_name, inventory_file, file_ext, chunk_type, chunk_size, modified
            FROM inventory
            WHERE idx IN ({placeholders})
            """,
            idx_list,
        ).fetchall()
        deleted_records = [_row_to_stored_inventory(row) for row in rows]
        connection.execute(
            f"DELETE FROM inventory WHERE idx IN ({placeholders})",
            idx_list,
        )
        connection.commit()
    return deleted_records

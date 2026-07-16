from dataclasses import dataclass
from pathlib import Path

from backend.app.db.database import get_connection

CHUNK_TYPE_ROW = 1
CHUNK_TYPE_CUSTOM = 2

MODIFIED_EMBEDDED = 0
MODIFIED_NEEDS_EMBED = 1

DEFAULT_CHUNK_OVERLAP = 50
DEFAULT_N_RESULTS = 100

DB_TYPE_TABLE = "table"
DB_TYPE_VECTOR = "vector"


@dataclass(frozen=True)
class StoredInventory:
    idx: int
    inventory_name: str
    inventory_file: str
    file_ext: str
    chunk_type: int
    chunk_size: int
    chunk_overlap: int
    n_results: int
    db_type: str | None
    modified: int

    @property
    def effective_db_type(self) -> str:
        """Null/empty db_type is treated as vector for backward compatibility."""
        value = (self.db_type or "").strip().lower()
        if value == DB_TYPE_TABLE:
            return DB_TYPE_TABLE
        return DB_TYPE_VECTOR


def _row_keys(row) -> set[str]:
    return set(row.keys())


def _row_to_stored_inventory(row) -> StoredInventory:
    keys = _row_keys(row)
    raw_db_type = row["db_type"] if "db_type" in keys else None
    db_type = None if raw_db_type is None else str(raw_db_type).strip() or None
    return StoredInventory(
        idx=int(row["idx"]),
        inventory_name=str(row["inventory_name"]),
        inventory_file=str(row["inventory_file"]),
        file_ext=str(row["file_ext"]),
        chunk_type=int(row["chunk_type"]),
        chunk_size=int(row["chunk_size"]),
        chunk_overlap=int(row["chunk_overlap"]) if "chunk_overlap" in keys else DEFAULT_CHUNK_OVERLAP,
        n_results=int(row["n_results"]) if "n_results" in keys else DEFAULT_N_RESULTS,
        db_type=db_type,
        modified=int(row["modified"]),
    )


def extract_file_ext(filename: str) -> str:
    extension = Path(filename).suffix.removeprefix(".")
    return extension.lower()


_INVENTORY_SELECT = (
    "idx, inventory_name, inventory_file, file_ext, chunk_type, chunk_size, "
    "chunk_overlap, n_results, db_type, modified"
)


def list_stored_inventory(database_path: str | Path) -> list[StoredInventory]:
    with get_connection(database_path) as connection:
        rows = connection.execute(
            f"""
            SELECT {_INVENTORY_SELECT}
            FROM inventory
            ORDER BY idx
            """
        ).fetchall()
    return [_row_to_stored_inventory(row) for row in rows]


def get_stored_inventory_by_idx(database_path: str | Path, idx: int) -> StoredInventory | None:
    with get_connection(database_path) as connection:
        row = connection.execute(
            f"""
            SELECT {_INVENTORY_SELECT}
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
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    n_results: int = DEFAULT_N_RESULTS,
    db_type: str = DB_TYPE_VECTOR,
    modified: int = MODIFIED_NEEDS_EMBED,
) -> StoredInventory:
    with get_connection(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO inventory (
                inventory_name, inventory_file, file_ext, chunk_type, chunk_size,
                chunk_overlap, n_results, db_type, modified
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                inventory_name.strip(),
                inventory_file.strip(),
                file_ext.strip(),
                chunk_type,
                chunk_size,
                chunk_overlap,
                n_results,
                db_type,
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
    chunk_overlap: int | None = None,
    n_results: int | None = None,
    db_type: str | None = None,
    modified: int | None = None,
) -> StoredInventory | None:
    existing = get_stored_inventory_by_idx(database_path, idx)
    if existing is None:
        return None

    next_inventory_file = inventory_file if inventory_file is not None else existing.inventory_file
    next_file_ext = file_ext if file_ext is not None else existing.file_ext
    next_chunk_type = chunk_type if chunk_type is not None else existing.chunk_type
    next_chunk_size = chunk_size if chunk_size is not None else existing.chunk_size
    next_chunk_overlap = chunk_overlap if chunk_overlap is not None else existing.chunk_overlap
    next_n_results = n_results if n_results is not None else existing.n_results
    next_db_type = db_type if db_type is not None else existing.db_type
    next_modified = modified if modified is not None else existing.modified

    with get_connection(database_path) as connection:
        connection.execute(
            """
            UPDATE inventory
            SET inventory_name = ?, inventory_file = ?, file_ext = ?, chunk_type = ?,
                chunk_size = ?, chunk_overlap = ?, n_results = ?, db_type = ?, modified = ?
            WHERE idx = ?
            """,
            (
                inventory_name.strip(),
                next_inventory_file.strip(),
                next_file_ext.strip(),
                next_chunk_type,
                next_chunk_size,
                next_chunk_overlap,
                next_n_results,
                next_db_type,
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
            SELECT {_INVENTORY_SELECT}
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

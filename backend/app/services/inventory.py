import csv
import hashlib
import logging
from pathlib import Path
from typing import Any

import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from chromadb.config import Settings as ChromaSettings
from langchain_core.messages import HumanMessage, SystemMessage

from backend.app.agents.base import AgentInvokeResult, extract_token_usage_from_text
from backend.app.agents.inventory_agent import INVENTORY_AGENT
from backend.app.agents.inventory_tool import INVENTORY_AGENT_ID
from backend.app.config import InventorySettings, PROJECT_ROOT, load_inventory_settings
from backend.app.llm.factory import get_llm
from backend.app.logging.prompt_debug import wrap_llm_for_prompt_debug

logger = logging.getLogger(__name__)

COLLECTION_NAME = "system_inventory"
EMBEDDING_DIMENSION = 384
# ChromaDB enforces a max batch size (~5461); stay safely below it.
CHROMA_ADD_BATCH_SIZE = 5000
DEFAULT_N_RESULTS = 100


class LocalHashEmbeddingFunction(EmbeddingFunction[Documents]):
    """Offline-friendly embedding function that avoids external model downloads."""

    def __init__(self, dimension: int = EMBEDDING_DIMENSION) -> None:
        self.dimension = dimension

    def __call__(self, input: Documents) -> Embeddings:
        embeddings: Embeddings = []
        for text in input:
            vector = [0.0] * self.dimension
            for token in text.lower().split():
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                for index, value in enumerate(digest):
                    vector[index % self.dimension] += (value - 128) / 128.0
            norm = sum(value * value for value in vector) ** 0.5 or 1.0
            embeddings.append([value / norm for value in vector])
        return embeddings


CLASSIFICATION_SYSTEM_PROMPT = (
    "You classify user questions for the Inventory agent. "
    "Respond with exactly one word: INVENTORY if the question is about servers, hosts, VMs, "
    "network devices, system inventory, infrastructure assets, or similar resource lookup. "
    "Respond GENERAL for greetings, unrelated questions, or non-inventory topics."
)

ANSWER_SYSTEM_PROMPT = (
    "You are the Inventory system agent. Answer the user's question using only the provided "
    "inventory context from ChromaDB. If the context is insufficient, say so clearly. "
    "Respond in Korean when possible. Be concise and structured."
)

TABLE_SQL_SYSTEM_PROMPT = (
    "You are a SQLite expert for inventory lookup. "
    "Given registered inventory table schemas and a user question, write one read-only SQLite query. "
    "Respond with valid JSON only (no markdown) with keys: sql (string), rationale (string). "
    "Rules: use only SELECT or WITH ... SELECT; query only the listed tables/columns; "
    "quote identifiers with double quotes; prefer LIMIT <= 200; never modify data. "
    "Builtin Kubernetes tables (k8s_cluster, k8s_namespaces, k8s_deployments, "
    "k8s_nodes, k8s_pods, k8s_pvcs) may be used even when no inventory CSV is registered; "
    "join them using the documented foreign keys when needed. "
    "Never use SELECT * or SELECT ALL. "
    "Select at most 10 columns: prioritize columns that show key resource identity/attributes "
    "(e.g. hostname, host name, IP/address, OS/operating system, type, status, owner, "
    "environment, location, asset/id/code, cluster_name, namespace, node_name, pod name) "
    "when present in the schema, "
    "and always include every column used in WHERE/JOIN comparisons. "
    "If fewer than 10 useful columns exist, select only those; do not invent column names. "
    "When the user question includes search terms for string matching "
    "(names, codes, hosts, IPs, keywords, etc.), the SQL MUST include those exact terms "
    "in WHERE filters (prefer LIKE '%term%' for partial match, or = for exact match). "
    "Do not omit user-provided search parameters, invent unrelated filters, or return an "
    "unfiltered SELECT when the question clearly asks to find/filter by a value."
)

COMBINED_ANSWER_SYSTEM_PROMPT = (
    "You are the Inventory system agent. Answer the user's question using only the provided "
    "inventory contexts (SQL query results and/or vector search hits). "
    "If the context is insufficient, say so clearly. "
    "Respond in Korean when possible. Be concise and structured."
)


def _resolve_path(path: str) -> Path:
    resolved = Path(path)
    if not resolved.is_absolute():
        return PROJECT_ROOT / resolved
    return resolved


def _row_to_document(row: dict[str, str]) -> str:
    parts = [f"{key}: {value}" for key, value in row.items() if value.strip()]
    return " | ".join(parts)


def _chunk_text(text: str, chunk_size: int, chunk_overlap: int = 0) -> list[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0 for custom chunking")
    if chunk_overlap < 0:
        raise ValueError("chunk_overlap must be greater than or equal to 0")
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be less than chunk_size")

    step = chunk_size - chunk_overlap
    chunks: list[str] = []
    for index in range(0, len(text), step):
        chunk = text[index : index + chunk_size]
        if chunk.strip():
            chunks.append(chunk)
        if index + chunk_size >= len(text):
            break
    return chunks


class InventoryService:
    def __init__(
        self,
        settings: InventorySettings,
        *,
        database_path: str | Path | None = None,
    ) -> None:
        self.settings = settings
        self.database_path = _resolve_path(str(database_path)) if database_path is not None else None
        self.chroma_path = _resolve_path(settings.chroma_data_path)
        self.csv_path = _resolve_path(settings.csv_path)
        self.upload_path = _resolve_path(settings.upload_path)
        self._client: chromadb.ClientAPI | None = None
        self._collection: chromadb.Collection | None = None
        self._status = "uninitialized"
        self._error: str | None = None
        self._document_count = 0

    @property
    def status(self) -> str:
        return self._status

    @property
    def error(self) -> str | None:
        return self._error

    @property
    def document_count(self) -> int:
        return self._document_count

    def initialize(self) -> None:
        try:
            self.chroma_path.mkdir(parents=True, exist_ok=True)
            self.upload_path.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=str(self.chroma_path),
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            embedding_function = LocalHashEmbeddingFunction()
            self._collection = self._client.get_or_create_collection(
                name=COLLECTION_NAME,
                embedding_function=embedding_function,
            )
            self._document_count = self._collection.count()

            if self._document_count == 0:
                loaded = self._load_csv_embeddings()
                if loaded == 0 and not self.csv_path.exists():
                    self._status = "waiting_for_csv"
                    self._error = f"CSV file not found: {self.csv_path}"
                    logger.warning("Inventory CSV not found at %s", self.csv_path)
                    return

            self._status = "ready"
            self._error = None
            logger.info(
                "Inventory service ready (documents=%s, chroma=%s)",
                self._document_count,
                self.chroma_path,
            )
        except Exception as exc:
            self._status = "error"
            self._error = str(exc)
            logger.exception("Failed to initialize inventory service: %s", exc)

    def resolve_uploaded_file_path(self, filename: str) -> Path:
        return self.upload_path / Path(filename).name

    def save_uploaded_file(self, *, filename: str, content: bytes) -> str:
        safe_filename = Path(filename).name
        if not safe_filename:
            raise ValueError("A valid filename is required")

        self.upload_path.mkdir(parents=True, exist_ok=True)
        target_path = self.upload_path / safe_filename
        target_path.write_bytes(content)
        return safe_filename

    def delete_uploaded_file(self, filename: str) -> None:
        file_path = self.resolve_uploaded_file_path(filename)
        if file_path.exists():
            file_path.unlink()

    def _ensure_collection(self) -> chromadb.Collection:
        if self._collection is None:
            raise RuntimeError("Inventory service is not initialized")
        return self._collection

    def _add_documents_to_collection(
        self,
        collection: chromadb.Collection,
        *,
        documents: list[str],
        metadatas: list[dict[str, str]],
        ids: list[str],
        context: str = "",
    ) -> None:
        total = len(documents)
        for start in range(0, total, CHROMA_ADD_BATCH_SIZE):
            end = min(start + CHROMA_ADD_BATCH_SIZE, total)
            logger.info(
                "Chroma add batch context=%s documents=%s/%s range=%s-%s",
                context or "-",
                end - start,
                total,
                start,
                end,
            )
            collection.add(
                documents=documents[start:end],
                metadatas=metadatas[start:end],
                ids=ids[start:end],
            )

    def _delete_embeddings_for_idx(self, inventory_idx: int) -> None:
        collection = self._ensure_collection()
        collection.delete(where={"inventory_idx": str(inventory_idx)})
        self._document_count = collection.count()

    def delete_inventory_embeddings(self, inventory_idx: int) -> None:
        self._delete_embeddings_for_idx(inventory_idx)

    def _build_row_documents(
        self,
        *,
        inventory_idx: int,
        file_path: Path,
        filename: str,
    ) -> tuple[list[str], list[dict[str, str]], list[str]]:
        documents: list[str] = []
        metadatas: list[dict[str, str]] = []
        ids: list[str] = []

        with file_path.open(encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            for index, row in enumerate(reader):
                normalized = {key: (value or "").strip() for key, value in row.items() if key}
                if not any(normalized.values()):
                    continue
                doc_id = (
                    normalized.get("id")
                    or normalized.get("host_id")
                    or normalized.get("hostname")
                    or f"row-{index}"
                )
                documents.append(_row_to_document(normalized))
                metadatas.append(
                    {
                        **normalized,
                        "inventory_idx": str(inventory_idx),
                        "inventory_file": filename,
                    }
                )
                ids.append(f"inv-{inventory_idx}-row-{index}-{doc_id}")

        return documents, metadatas, ids

    def _build_custom_documents(
        self,
        *,
        inventory_idx: int,
        file_path: Path,
        filename: str,
        chunk_size: int,
        chunk_overlap: int,
    ) -> tuple[list[str], list[dict[str, str]], list[str]]:
        text = file_path.read_text(encoding="utf-8-sig")
        if not text.strip():
            return [], [], []

        documents: list[str] = []
        metadatas: list[dict[str, str]] = []
        ids: list[str] = []

        for index, chunk in enumerate(_chunk_text(text, chunk_size, chunk_overlap)):
            if not chunk.strip():
                continue
            documents.append(chunk)
            metadatas.append(
                {
                    "inventory_idx": str(inventory_idx),
                    "inventory_file": filename,
                    "chunk_index": str(index),
                    "chunk_overlap": str(chunk_overlap),
                }
            )
            ids.append(f"inv-{inventory_idx}-chunk-{index}")

        return documents, metadatas, ids

    def embed_inventory_record(
        self,
        *,
        inventory_idx: int,
        filename: str,
        chunk_type: int,
        chunk_size: int,
        chunk_overlap: int = 50,
    ) -> int:
        from backend.app.db.inventory_records import CHUNK_TYPE_CUSTOM, CHUNK_TYPE_ROW

        file_path = self.resolve_uploaded_file_path(filename)
        file_size = file_path.stat().st_size if file_path.exists() else None
        logger.info(
            "Inventory embed start idx=%s file=%s chunk_type=%s chunk_size=%s chunk_overlap=%s "
            "file_path=%s file_exists=%s file_size=%s service_status=%s chroma_path=%s",
            inventory_idx,
            filename,
            chunk_type,
            chunk_size,
            chunk_overlap,
            file_path,
            file_path.exists(),
            file_size,
            self._status,
            self.chroma_path,
        )

        collection = self._ensure_collection()
        if not file_path.exists():
            logger.error(
                "Inventory embed uploaded file missing idx=%s file=%s resolved_path=%s upload_path=%s",
                inventory_idx,
                filename,
                file_path,
                self.upload_path,
            )
            raise FileNotFoundError(f"Uploaded inventory file not found: {file_path}")

        try:
            self._delete_embeddings_for_idx(inventory_idx)
        except Exception as exc:
            logger.exception(
                "Inventory embed failed while deleting existing embeddings idx=%s file=%s",
                inventory_idx,
                filename,
            )
            raise RuntimeError(f"Failed to delete existing embeddings for idx={inventory_idx}: {exc}") from exc

        try:
            if chunk_type == CHUNK_TYPE_ROW:
                documents, metadatas, ids = self._build_row_documents(
                    inventory_idx=inventory_idx,
                    file_path=file_path,
                    filename=filename,
                )
            elif chunk_type == CHUNK_TYPE_CUSTOM:
                documents, metadatas, ids = self._build_custom_documents(
                    inventory_idx=inventory_idx,
                    file_path=file_path,
                    filename=filename,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                )
            else:
                raise ValueError(f"Unsupported chunk_type: {chunk_type}")
        except UnicodeDecodeError as exc:
            logger.error(
                "Inventory embed file encoding error idx=%s file=%s encoding=%s detail=%s",
                inventory_idx,
                filename,
                exc.encoding,
                exc,
            )
            raise ValueError(
                "업로드 파일 인코딩을 UTF-8로 읽을 수 없습니다. UTF-8 CSV/TXT 파일인지 확인해 주세요."
            ) from exc
        except csv.Error as exc:
            logger.error(
                "Inventory embed CSV parse error idx=%s file=%s detail=%s",
                inventory_idx,
                filename,
                exc,
            )
            raise ValueError(f"CSV 파싱에 실패했습니다: {exc}") from exc

        if not documents:
            logger.warning(
                "Inventory embed no embeddable content idx=%s file=%s chunk_type=%s chunk_size=%s file_size=%s",
                inventory_idx,
                filename,
                chunk_type,
                chunk_size,
                file_size,
            )
            raise ValueError("No embeddable content found in the uploaded file")

        duplicate_ids = {doc_id for doc_id in ids if ids.count(doc_id) > 1}
        if duplicate_ids:
            sample = sorted(duplicate_ids)[:5]
            logger.error(
                "Inventory embed duplicate document ids idx=%s file=%s duplicate_count=%s sample=%s",
                inventory_idx,
                filename,
                len(duplicate_ids),
                sample,
            )
            raise ValueError(
                "임베딩 ID가 중복되었습니다. CSV의 id/host_id/hostname 값이 고유한지 확인해 주세요."
            )

        logger.info(
            "Inventory embed adding to Chroma idx=%s file=%s documents=%s ids_sample=%s",
            inventory_idx,
            filename,
            len(documents),
            ids[:3],
        )

        try:
            self._add_documents_to_collection(
                collection,
                documents=documents,
                metadatas=metadatas,
                ids=ids,
                context=f"idx={inventory_idx} file={filename}",
            )
        except Exception as exc:
            logger.exception(
                "Inventory embed Chroma add failed idx=%s file=%s documents=%s chroma_path=%s",
                inventory_idx,
                filename,
                len(documents),
                self.chroma_path,
            )
            raise RuntimeError(f"ChromaDB add failed: {exc}") from exc

        self._document_count = collection.count()
        self._status = "ready"
        self._error = None
        logger.info(
            "Embedded inventory idx=%s file=%s documents=%s document_count=%s",
            inventory_idx,
            filename,
            len(documents),
            self._document_count,
        )
        return len(documents)

    def refresh_document_count(self) -> int:
        collection = self._ensure_collection()
        self._document_count = collection.count()
        return self._document_count

    def reload_csv(self) -> int:
        if self._collection is None:
            raise RuntimeError("Inventory service is not initialized")

        existing_ids = self._collection.get(include=[])["ids"]
        if existing_ids:
            self._collection.delete(ids=existing_ids)

        loaded = self._load_csv_embeddings()
        self._status = "ready" if loaded > 0 or self.csv_path.exists() else "waiting_for_csv"
        self._error = None if loaded > 0 else self._error
        return loaded

    def _load_csv_embeddings(self) -> int:
        if self._collection is None:
            return 0
        if not self.csv_path.exists():
            return 0

        documents: list[str] = []
        metadatas: list[dict[str, str]] = []
        ids: list[str] = []

        with self.csv_path.open(encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            for index, row in enumerate(reader):
                normalized = {key: (value or "").strip() for key, value in row.items() if key}
                if not any(normalized.values()):
                    continue
                doc_id = normalized.get("id") or normalized.get("host_id") or normalized.get("hostname") or f"row-{index}"
                documents.append(_row_to_document(normalized))
                metadatas.append(normalized)
                ids.append(str(doc_id))

        if not documents:
            logger.warning("Inventory CSV has no embeddable rows: %s", self.csv_path)
            return 0

        self._add_documents_to_collection(
            self._collection,
            documents=documents,
            metadatas=metadatas,
            ids=ids,
            context=f"csv={self.csv_path.name}",
        )
        self._document_count = self._collection.count()
        logger.info("Loaded %s inventory rows from %s", len(documents), self.csv_path)
        return len(documents)

    async def _is_inventory_query(self, message: str) -> bool:
        llm = wrap_llm_for_prompt_debug(
            get_llm(),
            agent_id=INVENTORY_AGENT_ID,
            agent_name=INVENTORY_AGENT.name,
        )
        response = await llm.ainvoke(
            [
                SystemMessage(content=CLASSIFICATION_SYSTEM_PROMPT),
                HumanMessage(content=message),
            ],
        )
        content = str(response.content).strip().upper()
        return content.startswith("INVENTORY")

    def _query_collection(
        self,
        collection: chromadb.Collection,
        query: str,
        *,
        n_results: int,
        where: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        requested = max(n_results, 1)

        while requested >= 1:
            query_kwargs: dict[str, Any] = {
                "query_texts": [query],
                "n_results": min(requested, max(self._document_count, 1)),
            }
            if where is not None:
                query_kwargs["where"] = where

            try:
                results = collection.query(**query_kwargs)
            except Exception as exc:
                if requested <= 1:
                    logger.warning(
                        "Chroma query failed n_results=%s where=%s error=%s",
                        requested,
                        where,
                        exc,
                    )
                    return []
                requested = requested // 2
                continue

            hits: list[dict[str, Any]] = []
            documents = results.get("documents") or [[]]
            metadatas = results.get("metadatas") or [[]]
            distances = results.get("distances") or [[]]

            for document, metadata, distance in zip(
                documents[0], metadatas[0], distances[0], strict=False
            ):
                hits.append(
                    {
                        "document": document,
                        "metadata": metadata or {},
                        "distance": distance,
                    }
                )
            return hits

        return []

    def _search(self, query: str) -> list[dict[str, Any]]:
        if self._collection is None or self._document_count == 0:
            return []

        collection = self._ensure_collection()
        hits: list[dict[str, Any]] = []

        records: list[Any] = []
        if self.database_path is not None:
            try:
                from backend.app.db.inventory_records import DB_TYPE_TABLE, list_stored_inventory

                records = [
                    record
                    for record in list_stored_inventory(self.database_path)
                    if record.effective_db_type != DB_TYPE_TABLE
                ]
            except Exception:
                logger.exception(
                    "Failed to load inventory records for Chroma search (database_path=%s)",
                    self.database_path,
                )

        if records:
            for record in records:
                n_results = max(int(getattr(record, "n_results", DEFAULT_N_RESULTS)), 1)
                try:
                    file_hits = self._query_collection(
                        collection,
                        query,
                        n_results=n_results,
                        where={"inventory_idx": str(record.idx)},
                    )
                except Exception:
                    logger.exception(
                        "Chroma query failed for inventory_idx=%s n_results=%s",
                        record.idx,
                        n_results,
                    )
                    continue
                logger.info(
                    "Chroma search inventory_idx=%s file=%s n_results=%s hits=%s",
                    record.idx,
                    record.inventory_file,
                    n_results,
                    len(file_hits),
                )
                hits.extend(file_hits)

            hits.sort(key=lambda item: float(item.get("distance") or 0.0))
            if hits:
                return hits

        return self._query_collection(collection, query, n_results=DEFAULT_N_RESULTS)

    async def _generate_inventory_sql(
        self,
        message: str,
        schemas_text: str,
    ) -> tuple[str, str]:
        from backend.app.db.inventory_table_query import extract_sql_from_llm_response

        prompt = (
            f"User question:\n{message}\n\n"
            f"Available inventory tables:\n{schemas_text}\n\n"
            "Do not use SELECT *. Pick up to 10 columns: key resource fields "
            "(hostname, ip, OS, etc. when available) plus any columns used in WHERE filters.\n"
            "If the user question contains string search parameters, include them in the SQL "
            "WHERE clause (e.g. LIKE '%value%' or = 'value') using the same terms from the question.\n"
            "Return JSON: {\"sql\": \"SELECT ...\", \"rationale\": \"...\"}"
        )
        llm = wrap_llm_for_prompt_debug(
            get_llm(),
            agent_id=INVENTORY_AGENT_ID,
            agent_name=INVENTORY_AGENT.name,
        )
        response = await llm.ainvoke(
            [
                SystemMessage(content=TABLE_SQL_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ],
        )
        content = response.content if isinstance(response.content, str) else str(response.content)
        return extract_sql_from_llm_response(content)

    async def _query_table_inventories(self, message: str) -> str | None:
        if self.database_path is None:
            return None

        from backend.app.db.inventory_table_query import (
            execute_inventory_sql,
            format_table_query_result,
            list_inventory_table_schemas,
            schemas_to_prompt_text,
        )

        schemas = list_inventory_table_schemas(self.database_path)
        if not schemas:
            return None

        schemas_text = schemas_to_prompt_text(schemas)
        allowed_tables = {schema.table_name for schema in schemas}
        logger.info(
            "Inventory table SQL routing tables=%s question_chars=%s",
            sorted(allowed_tables),
            len(message),
        )

        try:
            sql, rationale = await self._generate_inventory_sql(message, schemas_text)
            result = execute_inventory_sql(
                self.database_path,
                sql,
                allowed_tables=allowed_tables,
            )
            if rationale:
                from dataclasses import replace

                result = replace(result, rationale=rationale)
            formatted = format_table_query_result(result)
            logger.info(
                "Inventory table SQL executed rows=%s truncated=%s sql=%s",
                len(result.rows),
                result.truncated,
                result.sql.replace("\n", " ")[:300],
            )
            return formatted
        except Exception as exc:
            logger.exception("Inventory table SQL query failed: %s", exc)
            return (
                "table 타입 인벤토리 SQL 조회에 실패했습니다. "
                f"원인: {exc}"
            )

    async def query(self, message: str) -> AgentInvokeResult:
        if self._status == "error":
            content = f"인벤토리 서비스 오류: {self._error}"
            input_tokens, output_tokens = extract_token_usage_from_text(message, content)
            return AgentInvokeResult(content=content, tools_used=[], input_tokens=input_tokens, output_tokens=output_tokens)

        is_inventory_query = await self._is_inventory_query(message)
        if not is_inventory_query:
            content = "인벤토리와 관련 없는 질문입니다. 서버, 호스트, VM, 네트워크 장비 등 인프라 자산에 대해 질문해 주세요."
            input_tokens, output_tokens = extract_token_usage_from_text(message, content)
            return AgentInvokeResult(content=content, tools_used=[], input_tokens=input_tokens, output_tokens=output_tokens)

        table_context = await self._query_table_inventories(message)

        vector_hits: list[dict[str, Any]] = []
        if self._collection is not None and self._document_count > 0:
            vector_hits = self._search(message)
        elif self._status == "waiting_for_csv" and not table_context:
            content = (
                f"인벤토리 CSV 파일을 찾을 수 없습니다. "
                f"INVENTORY_CSV_PATH 환경변수로 경로를 설정해 주세요. (현재: {self.csv_path})"
            )
            input_tokens, output_tokens = extract_token_usage_from_text(message, content)
            return AgentInvokeResult(
                content=content,
                tools_used=[],
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        if not table_context and not vector_hits:
            content = (
                "인벤토리 DB에 조회 가능한 데이터가 없습니다. "
                "table/vector 인벤토리 등록 및 Embedding 상태를 확인해 주세요."
            )
            input_tokens, output_tokens = extract_token_usage_from_text(message, content)
            return AgentInvokeResult(content=content, tools_used=[], input_tokens=input_tokens, output_tokens=output_tokens)

        # table-only: return SQL execution result directly.
        if table_context and not vector_hits:
            input_tokens, output_tokens = extract_token_usage_from_text(message, table_context)
            return AgentInvokeResult(
                content=table_context,
                tools_used=[],
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        context_sections: list[str] = []
        if table_context:
            context_sections.append(f"[table SQL 결과]\n{table_context}")
        if vector_hits:
            vector_lines = []
            for index, hit in enumerate(vector_hits, start=1):
                metadata = hit.get("metadata") or {}
                metadata_text = ", ".join(f"{key}={value}" for key, value in metadata.items())
                vector_lines.append(f"[{index}] {hit['document']} ({metadata_text})")
            context_sections.append("[vector 검색 결과]\n" + "\n".join(vector_lines))

        context = "\n\n".join(context_sections)
        llm = wrap_llm_for_prompt_debug(
            get_llm(),
            agent_id=INVENTORY_AGENT_ID,
            agent_name=INVENTORY_AGENT.name,
        )
        response = await llm.ainvoke(
            [
                SystemMessage(
                    content=COMBINED_ANSWER_SYSTEM_PROMPT if table_context else ANSWER_SYSTEM_PROMPT
                ),
                HumanMessage(content=f"질문: {message}\n\n인벤토리 컨텍스트:\n{context}"),
            ],
        )
        content = str(response.content)
        input_tokens, output_tokens = extract_token_usage_from_text(f"{message}\n{context}", content)
        return AgentInvokeResult(content=content, tools_used=[], input_tokens=input_tokens, output_tokens=output_tokens)

    def get_status_info(self) -> dict[str, Any]:
        return {
            "agent_id": INVENTORY_AGENT_ID,
            "status": self._status,
            "error": self._error,
            "document_count": self._document_count,
            "chroma_data_path": str(self.chroma_path),
            "csv_path": str(self.csv_path),
            "upload_path": str(self.upload_path),
        }


_inventory_service: InventoryService | None = None


def get_inventory_service() -> InventoryService:
    if _inventory_service is None:
        raise RuntimeError("Inventory service is not initialized")
    return _inventory_service


def initialize_inventory_service(
    settings: InventorySettings | None = None,
    *,
    database_path: str | Path | None = None,
) -> InventoryService:
    global _inventory_service
    service = InventoryService(
        settings or load_inventory_settings(),
        database_path=database_path,
    )
    service.initialize()
    _inventory_service = service
    return service

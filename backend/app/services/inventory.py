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


def _resolve_path(path: str) -> Path:
    resolved = Path(path)
    if not resolved.is_absolute():
        return PROJECT_ROOT / resolved
    return resolved


def _row_to_document(row: dict[str, str]) -> str:
    parts = [f"{key}: {value}" for key, value in row.items() if value.strip()]
    return " | ".join(parts)


def _chunk_text(text: str, chunk_size: int) -> list[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0 for custom chunking")
    return [text[index : index + chunk_size] for index in range(0, len(text), chunk_size)]


class InventoryService:
    def __init__(self, settings: InventorySettings) -> None:
        self.settings = settings
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
    ) -> tuple[list[str], list[dict[str, str]], list[str]]:
        text = file_path.read_text(encoding="utf-8-sig")
        if not text.strip():
            return [], [], []

        documents: list[str] = []
        metadatas: list[dict[str, str]] = []
        ids: list[str] = []

        for index, chunk in enumerate(_chunk_text(text, chunk_size)):
            if not chunk.strip():
                continue
            documents.append(chunk)
            metadatas.append(
                {
                    "inventory_idx": str(inventory_idx),
                    "inventory_file": filename,
                    "chunk_index": str(index),
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
    ) -> int:
        from backend.app.db.inventory_records import CHUNK_TYPE_CUSTOM, CHUNK_TYPE_ROW

        collection = self._ensure_collection()
        file_path = self.resolve_uploaded_file_path(filename)
        if not file_path.exists():
            raise FileNotFoundError(f"Uploaded inventory file not found: {file_path}")

        self._delete_embeddings_for_idx(inventory_idx)

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
            )
        else:
            raise ValueError(f"Unsupported chunk_type: {chunk_type}")

        if not documents:
            raise ValueError("No embeddable content found in the uploaded file")

        collection.add(documents=documents, metadatas=metadatas, ids=ids)
        self._document_count = collection.count()
        self._status = "ready"
        self._error = None
        logger.info(
            "Embedded inventory idx=%s file=%s documents=%s",
            inventory_idx,
            filename,
            len(documents),
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

        self._collection.add(documents=documents, metadatas=metadatas, ids=ids)
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

    def _search(self, query: str, *, n_results: int = 5) -> list[dict[str, Any]]:
        if self._collection is None or self._document_count == 0:
            return []

        results = self._collection.query(query_texts=[query], n_results=min(n_results, self._document_count))
        hits: list[dict[str, Any]] = []
        documents = results.get("documents") or [[]]
        metadatas = results.get("metadatas") or [[]]
        distances = results.get("distances") or [[]]

        for document, metadata, distance in zip(documents[0], metadatas[0], distances[0], strict=False):
            hits.append(
                {
                    "document": document,
                    "metadata": metadata or {},
                    "distance": distance,
                }
            )
        return hits

    async def query(self, message: str) -> AgentInvokeResult:
        if self._status == "error":
            content = f"인벤토리 서비스 오류: {self._error}"
            input_tokens, output_tokens = extract_token_usage_from_text(message, content)
            return AgentInvokeResult(content=content, tools_used=[], input_tokens=input_tokens, output_tokens=output_tokens)

        if self._status == "waiting_for_csv":
            content = (
                f"인벤토리 CSV 파일을 찾을 수 없습니다. "
                f"INVENTORY_CSV_PATH 환경변수로 경로를 설정해 주세요. (현재: {self.csv_path})"
            )
            input_tokens, output_tokens = extract_token_usage_from_text(message, content)
            return AgentInvokeResult(content=content, tools_used=[], input_tokens=input_tokens, output_tokens=output_tokens)

        is_inventory_query = await self._is_inventory_query(message)
        if not is_inventory_query:
            content = "인벤토리와 관련 없는 질문입니다. 서버, 호스트, VM, 네트워크 장비 등 인프라 자산에 대해 질문해 주세요."
            input_tokens, output_tokens = extract_token_usage_from_text(message, content)
            return AgentInvokeResult(content=content, tools_used=[], input_tokens=input_tokens, output_tokens=output_tokens)

        hits = self._search(message)
        if not hits:
            content = "인벤토리 DB에 조회 가능한 데이터가 없습니다. CSV 파일을 확인하거나 reload를 실행해 주세요."
            input_tokens, output_tokens = extract_token_usage_from_text(message, content)
            return AgentInvokeResult(content=content, tools_used=[], input_tokens=input_tokens, output_tokens=output_tokens)

        context_lines = []
        for index, hit in enumerate(hits, start=1):
            metadata = hit.get("metadata") or {}
            metadata_text = ", ".join(f"{key}={value}" for key, value in metadata.items())
            context_lines.append(f"[{index}] {hit['document']} ({metadata_text})")

        context = "\n".join(context_lines)
        llm = wrap_llm_for_prompt_debug(
            get_llm(),
            agent_id=INVENTORY_AGENT_ID,
            agent_name=INVENTORY_AGENT.name,
        )
        response = await llm.ainvoke(
            [
                SystemMessage(content=ANSWER_SYSTEM_PROMPT),
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


def initialize_inventory_service(settings: InventorySettings | None = None) -> InventoryService:
    global _inventory_service
    service = InventoryService(settings or load_inventory_settings())
    service.initialize()
    _inventory_service = service
    return service

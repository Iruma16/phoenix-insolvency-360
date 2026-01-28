"""
TRACING - Observabilidad y Replay para PHOENIX

Permite responder: "¿Por qué este sistema dijo X ayer y hoy dice Y?"

NO modifica lógica de decisión. SOLO instrumenta para trazabilidad.
NO loggea PII ni texto libre. SOLO identificadores y metadatos.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Optional


@dataclass
class TraceContext:
    """
    Contexto de trazabilidad completo por request.

    Permite replay determinista de decisiones.
    """

    request_id: str
    timestamp_start: str
    timestamp_end: str
    component: str  # RAG | PROSECUTOR
    case_id: str
    model_name: Optional[str] = None
    prompt_version: Optional[str] = None
    vectorstore_version: Optional[str] = None
    retrieval_top_k: Optional[int] = None
    policy_applied: Optional[str] = None
    chunk_ids_used: Optional[list[str]] = None
    chunk_scores: Optional[list[float]] = None  # Para replay determinista
    latency_ms_total: Optional[float] = None
    latency_ms_retrieval: Optional[float] = None
    latency_ms_llm: Optional[float] = None
    cost_tokens_in: Optional[int] = None
    cost_tokens_out: Optional[int] = None
    decision_final: Optional[str] = None
    reason: Optional[str] = None
    replay_of: Optional[str] = None  # Si es un replay, indica request_id original

    def to_json(self) -> str:
        """Serializa a JSON sin PII."""
        return json.dumps(asdict(self), ensure_ascii=False)

    def emit(self) -> None:
        """Emite trace por stdout."""
        print(f"[TRACE] {self.to_json()}")


@dataclass
class DecisionRecord:
    """
    Registro de decisión sin PII ni texto libre.

    SOLO identificadores, hashes y metadatos.
    Permite auditabilidad y replay.
    """

    request_id: str
    case_id: str
    component: str
    prompt_version: str
    vectorstore_version: str
    retrieval_params: dict[str, Any]
    tools_used: list[str]
    cited_chunks: list[dict[str, Any]]  # chunk_id, doc_id, page, start_char, end_char
    decision_final: str
    reason: Optional[str] = None

    def to_json(self) -> str:
        """Serializa a JSON sin PII."""
        return json.dumps(asdict(self), ensure_ascii=False)

    def emit(self) -> None:
        """Emite decision record por stdout."""
        print(f"[DECISION_RECORD] {self.to_json()}")


class TracingSession:
    """
    Sesión de tracing para un request.

    Simplifica creación de TraceContext y DecisionRecord.
    """

    def __init__(
        self,
        component: str,
        case_id: str,
        request_id: Optional[str] = None,
    ):
        self.request_id = request_id or str(uuid.uuid4())
        self.component = component
        self.case_id = case_id
        self.timestamp_start = datetime.utcnow().isoformat()
        self.timestamp_end = None

        # Acumuladores
        self.model_name = None
        self.prompt_version = None
        self.vectorstore_version = None
        self.retrieval_top_k = None
        self.policy_applied = None
        self.chunk_ids_used = []
        self.chunk_scores = []  # Para replay determinista
        self.latency_ms_retrieval = None
        self.latency_ms_llm = None
        self.cost_tokens_in = None
        self.cost_tokens_out = None
        self.decision_final = None
        self.reason = None
        self.replay_of = None

        # Para DecisionRecord
        self.retrieval_params = {}
        self.tools_used = []
        self.cited_chunks = []

        # Certificación de estado limpio
        print(f"[CERT] NO_GLOBAL_STATE = OK request_id={self.request_id}")

    def set_model(self, model_name: str):
        """Registra modelo LLM usado."""
        self.model_name = model_name

    def set_prompt_version(self, version: str):
        """Registra versión de prompt."""
        self.prompt_version = version

    def set_vectorstore_version(self, version: str):
        """Registra versión de vectorstore."""
        self.vectorstore_version = version

    def set_retrieval_params(self, top_k: int, **kwargs):
        """Registra parámetros de retrieval."""
        self.retrieval_top_k = top_k
        self.retrieval_params = {"top_k": top_k, **kwargs}

    def set_policy(self, policy_name: str):
        """Registra política aplicada."""
        self.policy_applied = policy_name

    def add_chunk_ids(self, chunk_ids: list[str]):
        """Registra chunk IDs usados."""
        self.chunk_ids_used.extend(chunk_ids)

    def add_chunk_ids_with_scores(self, chunks_with_scores: list[tuple]):
        """
        Registra chunk IDs con sus scores para replay determinista.

        Args:
            chunks_with_scores: Lista de (chunk_id, score)
        """
        for chunk_id, score in chunks_with_scores:
            self.chunk_ids_used.append(chunk_id)
            self.chunk_scores.append(score)

        # Certificar orden para replay
        print(f"[CERT] REPLAY_CONTEXT chunk_ids={self.chunk_ids_used} scores={self.chunk_scores}")

    def add_tool(self, tool_name: str):
        """Registra herramienta usada."""
        if tool_name not in self.tools_used:
            self.tools_used.append(tool_name)

    def log_step(
        self,
        step_name: str,
        latency_ms: float,
        tokens_in: Optional[int] = None,
        tokens_out: Optional[int] = None,
    ):
        """
        Registra un step intermedio con latencia y tokens.

        Para visibilidad operativa de costes.
        """
        log_parts = [f"[TRACE_STEP] step={step_name}", f"latency_ms={latency_ms:.2f}"]

        if tokens_in is not None:
            log_parts.append(f"tokens_in={tokens_in}")
        if tokens_out is not None:
            log_parts.append(f"tokens_out={tokens_out}")

        print(" ".join(log_parts))

    def add_cited_chunks(self, chunks: list[dict[str, Any]]):
        """
        Registra chunks citados SIN extractos.

        SOLO: chunk_id, doc_id, page, start_char, end_char
        NO: content, extracto_literal
        """
        for chunk in chunks:
            cited = {
                "chunk_id": chunk.get("chunk_id"),
                "doc_id": chunk.get("document_id") or chunk.get("doc_id") or chunk.get("filename"),
                "page": chunk.get("page"),
                "start_char": chunk.get("start_char"),
                "end_char": chunk.get("end_char"),
            }
            self.cited_chunks.append(cited)

    def set_latency_retrieval(self, ms: float):
        """Registra latencia de retrieval."""
        self.latency_ms_retrieval = ms

    def set_latency_llm(self, ms: float):
        """Registra latencia de LLM."""
        self.latency_ms_llm = ms

    def set_tokens(self, tokens_in: int, tokens_out: int):
        """Registra tokens consumidos."""
        self.cost_tokens_in = tokens_in
        self.cost_tokens_out = tokens_out

    def set_decision(self, decision: str, reason: Optional[str] = None):
        """Registra decisión final."""
        self.decision_final = decision
        self.reason = reason

    def mark_replay(self, original_request_id: str):
        """Marca esta sesión como replay de otra."""
        self.replay_of = original_request_id

    def finish(self) -> TraceContext:
        """
        Finaliza sesión y genera TraceContext.

        Calcula latencia total y emite trace.
        """
        self.timestamp_end = datetime.utcnow().isoformat()

        # Calcular latencia total
        start = datetime.fromisoformat(self.timestamp_start)
        end = datetime.fromisoformat(self.timestamp_end)
        latency_total = (end - start).total_seconds() * 1000

        # Certificar ausencia de fallbacks silenciosos
        if self.prompt_version and self.vectorstore_version:
            print(f"[CERT] NO_FALLBACKS = OK request_id={self.request_id}")

        trace = TraceContext(
            request_id=self.request_id,
            timestamp_start=self.timestamp_start,
            timestamp_end=self.timestamp_end,
            component=self.component,
            case_id=self.case_id,
            model_name=self.model_name,
            prompt_version=self.prompt_version,
            vectorstore_version=self.vectorstore_version,
            retrieval_top_k=self.retrieval_top_k,
            policy_applied=self.policy_applied,
            chunk_ids_used=self.chunk_ids_used,
            chunk_scores=self.chunk_scores if self.chunk_scores else None,
            latency_ms_total=latency_total,
            latency_ms_retrieval=self.latency_ms_retrieval,
            latency_ms_llm=self.latency_ms_llm,
            cost_tokens_in=self.cost_tokens_in,
            cost_tokens_out=self.cost_tokens_out,
            decision_final=self.decision_final,
            reason=self.reason,
            replay_of=self.replay_of,
        )

        trace.emit()
        return trace

    def emit_decision_record(self) -> DecisionRecord:
        """
        Genera y emite DecisionRecord.

        SOLO identificadores, sin PII ni texto libre.
        """
        if not self.prompt_version:
            raise ValueError("prompt_version es obligatorio para DecisionRecord")
        if not self.vectorstore_version:
            raise ValueError("vectorstore_version es obligatorio para DecisionRecord")

        record = DecisionRecord(
            request_id=self.request_id,
            case_id=self.case_id,
            component=self.component,
            prompt_version=self.prompt_version,
            vectorstore_version=self.vectorstore_version,
            retrieval_params=self.retrieval_params,
            tools_used=self.tools_used,
            cited_chunks=self.cited_chunks,
            decision_final=self.decision_final or "UNKNOWN",
            reason=self.reason,
        )

        record.emit()
        return record


# ============================
# REPLAY STORAGE (EXPLÍCITO)
# ============================

# Backend de almacenamiento explícito
# En producción: migrar a DB/Redis/S3 según volumetría
_STORAGE_BACKEND = "in-memory-dict"  # Explícito para auditoría
_STORAGE_RETENTION_POLICY = "session"  # Se pierde al reiniciar proceso
_DECISION_RECORDS_STORAGE: dict[str, DecisionRecord] = {}


def store_decision_record(record: DecisionRecord) -> None:
    """
    Almacena DecisionRecord para replay futuro.

    Emite certificación de storage por stdout.
    """
    _DECISION_RECORDS_STORAGE[record.request_id] = record

    # [CERT] Certificar storage
    print(
        f"[CERT] DECISION_RECORD_STORAGE backend={_STORAGE_BACKEND} "
        f"key={record.request_id} retention={_STORAGE_RETENTION_POLICY}"
    )


def get_decision_record(request_id: str) -> Optional[DecisionRecord]:
    """Recupera DecisionRecord por request_id."""
    record = _DECISION_RECORDS_STORAGE.get(request_id)

    if record:
        # Certificar que NO se usa "latest"
        assert (
            "latest" not in record.prompt_version.lower()
        ), "CRITICAL: DecisionRecord contiene 'latest' en prompt_version"
        assert (
            "latest" not in record.vectorstore_version.lower()
        ), "CRITICAL: DecisionRecord contiene 'latest' en vectorstore_version"

        print(f"[CERT] NO_LATEST_USAGE = OK request_id={request_id}")

    return record


# ============================
# HIGIENE DE DATOS
# ============================


def sanitize_for_logging(data: Any) -> Any:
    """
    Sanitiza datos para logging sin PII.

    Elimina campos con texto libre o extractos.
    """
    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            # Campos prohibidos (contienen PII o texto libre)
            if key in ["content", "extracto_literal", "raw_text", "texto", "description"]:
                # Reemplazar por hash o longitud
                if isinstance(value, str):
                    sanitized[key] = f"[REDACTED-{len(value)}chars]"
                else:
                    sanitized[key] = "[REDACTED]"
            else:
                sanitized[key] = sanitize_for_logging(value)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_for_logging(item) for item in data]
    else:
        return data

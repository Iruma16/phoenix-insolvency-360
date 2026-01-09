# PLAN DE HARDENING LEGAL — PHOENIX LEGAL
## Sistema Defendible en Entorno Legal Hostil

**Fecha**: 6 de enero de 2026  
**Objetivo**: Pasar de "sistema convincente" a "sistema presentable como prueba técnica"  
**Alcance**: 7 endurecimientos técnicos ÚNICAMENTE  

---

## ESTADO ACTUAL (NO MODIFICAR)

Phoenix Legal tiene:
- ✅ Motor determinista (sin LLM)
- ✅ Separación DECIDE ≠ EXPLICA
- ✅ Contrato de estado validado HARD
- ✅ Gestión de errores y degradación
- ✅ Versionado de vectorstore (parcial: solo timestamp)
- ✅ Logging estructurado JSON
- ✅ Tests deterministas

**Gaps Críticos para Defensa Legal**:
1. ❌ Vectorstore sin manifest técnico de calidad
2. ❌ Ingesta sin validación bloqueante de calidad
3. ❌ Chunks sin offsets (citas no verificables)
4. ❌ RAG puede responder sin evidencia suficiente
5. ❌ No hay template formal de output legal
6. ❌ Tracing sin capacidad de replay
7. ❌ No hay control de costes operativo (FinOps)

---

## ENDURECIMIENTO 1: MANIFEST + VERSIONADO HARD POR VECTORSTORE

### Estado Actual

**Implementado parcialmente**:
- Archivo: `app/services/vectorstore_versioning.py`
- Versionado: `v_YYYYMMDD_HHMMSS`
- Manifest: `manifest.json` con SHA256 de documentos

**Gap Crítico**:
- Manifest NO incluye métricas de calidad de ingesta
- No hay validación de calidad mínima requerida
- No hay metadata de procesamiento (chunking strategy, overlaps, etc.)

### Diseño Técnico

**Manifest Extendido** (`manifest.json`):

```json
{
  "version_id": "v_20260106_143052",
  "case_id": "CASE_001",
  "created_at": "2026-01-06T14:30:52Z",
  "status": "READY",
  
  "documents": {
    "total_count": 5,
    "by_type": {
      "balance_pyg": 1,
      "acta_junta": 2,
      "informe_tesoreria": 2
    },
    "hashes": {
      "doc_001.pdf": "sha256:abc123...",
      "doc_002.pdf": "sha256:def456..."
    }
  },
  
  "chunking": {
    "strategy": "recursive_character",
    "chunk_size": 1000,
    "chunk_overlap": 200,
    "total_chunks": 47,
    "avg_chunk_size": 850,
    "min_chunk_size": 200,
    "max_chunk_size": 1200
  },
  
  "embeddings": {
    "model": "text-embedding-3-large",
    "dimensions": 3072,
    "total_tokens": 45000,
    "cost_usd": 0.00585
  },
  
  "quality_metrics": {
    "chunk_completeness": 1.0,
    "duplicate_chunks": 0,
    "empty_chunks": 0,
    "chunks_without_metadata": 0,
    "avg_chunk_quality_score": 0.95,
    "below_quality_threshold": []
  },
  
  "validation": {
    "passed": true,
    "checks_run": [
      "chunk_count_match",
      "doc_id_consistency",
      "case_id_consistency",
      "embedding_dimensions",
      "quality_threshold"
    ],
    "failed_checks": []
  },
  
  "build_metadata": {
    "python_version": "3.9.16",
    "langchain_version": "0.3.27",
    "chromadb_version": "0.4.22",
    "pipeline_version": "1.0.0"
  }
}
```

### Estructura de Datos

```python
# app/services/vectorstore_versioning.py

from dataclasses import dataclass
from typing import List, Dict, Optional
from datetime import datetime

@dataclass
class QualityMetrics:
    """Métricas de calidad de ingesta."""
    chunk_completeness: float  # 0.0-1.0
    duplicate_chunks: int
    empty_chunks: int
    chunks_without_metadata: int
    avg_chunk_quality_score: float  # 0.0-1.0
    below_quality_threshold: List[str]  # chunk_ids

@dataclass
class ChunkingMetadata:
    """Metadata del proceso de chunking."""
    strategy: str  # "recursive_character", "semantic", etc.
    chunk_size: int
    chunk_overlap: int
    total_chunks: int
    avg_chunk_size: int
    min_chunk_size: int
    max_chunk_size: int

@dataclass
class EmbeddingMetadata:
    """Metadata del proceso de embeddings."""
    model: str
    dimensions: int
    total_tokens: int
    cost_usd: float

@dataclass
class ValidationResult:
    """Resultado de validaciones."""
    passed: bool
    checks_run: List[str]
    failed_checks: List[str]
    failure_details: Optional[Dict[str, str]] = None

@dataclass
class ManifestExtended:
    """Manifest extendido con métricas de calidad."""
    version_id: str
    case_id: str
    created_at: datetime
    status: str
    
    documents: Dict[str, any]
    chunking: ChunkingMetadata
    embeddings: EmbeddingMetadata
    quality_metrics: QualityMetrics
    validation: ValidationResult
    build_metadata: Dict[str, str]
```

### Integración en Pipeline

**Archivo**: `app/services/embeddings_pipeline.py`

**Modificar**:
```python
def build_embeddings_for_case(
    db: Session,
    case_id: str,
    keep_versions: int = 3
) -> str:
    # 1. create_new_version() → EXISTENTE
    version_id = create_new_version(case_id)
    
    # 2. Procesar chunks → EXISTENTE
    chunks = build_document_chunks_for_case(db, case_id)
    
    # 3. NUEVO: Calcular métricas de chunking
    chunking_metadata = calculate_chunking_metadata(chunks)
    
    # 4. Generar embeddings → EXISTENTE
    embeddings_result = generate_embeddings(chunks)
    
    # 5. NUEVO: Calcular métricas de calidad
    quality_metrics = calculate_quality_metrics(chunks, embeddings_result)
    
    # 6. Insertar en ChromaDB → EXISTENTE
    insert_into_chromadb(chunks, embeddings_result)
    
    # 7. NUEVO: Generar manifest extendido
    manifest = ManifestExtended(
        version_id=version_id,
        case_id=case_id,
        chunking=chunking_metadata,
        embeddings=embeddings_result.metadata,
        quality_metrics=quality_metrics,
        # ...
    )
    save_manifest(version_id, manifest)
    
    # 8. Validar → MODIFICAR CON CALIDAD
    validation_result = validate_version_integrity_extended(
        version_id,
        manifest,
        quality_threshold=0.8  # ← NUEVO
    )
    
    if not validation_result.passed:
        update_version_status(version_id, "FAILED", validation_result)
        raise ValueError(f"Validación falló: {validation_result.failed_checks}")
    
    # 9. Activar → EXISTENTE
    update_version_status(version_id, "READY")
    update_active_pointer(case_id, version_id)
    
    return version_id
```

### Fail Conditions

**El sistema DEBE fallar si**:
1. `chunk_completeness < 0.95` → Chunks perdidos durante procesamiento
2. `duplicate_chunks > 0` → Contenido duplicado (corrupción)
3. `empty_chunks > 0` → Chunks sin contenido
4. `chunks_without_metadata > 0` → Metadata incompleta
5. `avg_chunk_quality_score < 0.8` → Calidad general insuficiente

**Acción**: NO actualizar puntero ACTIVE, marcar versión como FAILED.

### Garantía Legal

**Con este endurecimiento**:
1. ✅ Cada versión del vectorstore tiene certificación de calidad inmutable
2. ✅ Perito puede verificar que ingesta fue completa y correcta
3. ✅ Manifest prueba trazabilidad de procesamiento
4. ✅ Costes documentados (defensa contra "caja negra cara")
5. ✅ Reproducibilidad: mismo documento + mismo pipeline = mismo hash

---

## ENDURECIMIENTO 2: VALIDACIÓN DURA DE CALIDAD DE INGESTA (FAIL FAST)

### Estado Actual

**No implementado**:
- Ingesta acepta cualquier documento
- No hay validación de formato
- No hay validación de contenido mínimo
- No hay rechazo de documentos corruptos

### Diseño Técnico

**Pipeline de Validación Pre-Ingesta**:

```
Documento → Validación Pre-Ingesta → Ingesta → Chunking
            ↓
            FAIL FAST si:
            - No es PDF/DOCX válido
            - Está encriptado
            - Está corrupto
            - Tiene < 100 caracteres
            - Tiene > 90% de caracteres no-ASCII
            - Título/metadata faltante
```

### Estructura de Datos

```python
# app/services/ingestion_validation.py

from dataclasses import dataclass
from typing import List, Optional
from pathlib import Path

@dataclass
class DocumentValidationResult:
    """Resultado de validación pre-ingesta."""
    is_valid: bool
    file_path: Path
    file_size_bytes: int
    mime_type: str
    
    checks_passed: List[str]
    checks_failed: List[str]
    
    content_length: Optional[int] = None  # Caracteres extraídos
    page_count: Optional[int] = None
    has_metadata: bool = False
    
    failure_reason: Optional[str] = None
    warning_messages: List[str] = None

class DocumentValidator:
    """Validador de documentos pre-ingesta."""
    
    MIN_CONTENT_LENGTH = 100
    MAX_CONTENT_LENGTH = 10_000_000  # 10M chars
    MIN_ASCII_RATIO = 0.1  # 10% mínimo ASCII
    
    def validate_document(self, file_path: Path) -> DocumentValidationResult:
        """Valida documento antes de ingesta (FAIL FAST)."""
        result = DocumentValidationResult(
            is_valid=True,
            file_path=file_path,
            checks_passed=[],
            checks_failed=[]
        )
        
        # CHECK 1: Archivo existe y es legible
        if not self._check_file_readable(file_path):
            result.is_valid = False
            result.checks_failed.append("file_readable")
            result.failure_reason = "Archivo no existe o no es legible"
            return result
        
        result.checks_passed.append("file_readable")
        
        # CHECK 2: Formato válido (PDF, DOCX)
        mime_type = self._detect_mime_type(file_path)
        if mime_type not in ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]:
            result.is_valid = False
            result.checks_failed.append("valid_format")
            result.failure_reason = f"Formato no soportado: {mime_type}"
            return result
        
        result.mime_type = mime_type
        result.checks_passed.append("valid_format")
        
        # CHECK 3: No encriptado
        if mime_type == "application/pdf" and self._is_pdf_encrypted(file_path):
            result.is_valid = False
            result.checks_failed.append("not_encrypted")
            result.failure_reason = "PDF encriptado"
            return result
        
        result.checks_passed.append("not_encrypted")
        
        # CHECK 4: No corrupto
        try:
            content = self._extract_text(file_path, mime_type)
        except Exception as e:
            result.is_valid = False
            result.checks_failed.append("not_corrupted")
            result.failure_reason = f"Documento corrupto: {e}"
            return result
        
        result.checks_passed.append("not_corrupted")
        result.content_length = len(content)
        
        # CHECK 5: Contenido mínimo
        if result.content_length < self.MIN_CONTENT_LENGTH:
            result.is_valid = False
            result.checks_failed.append("min_content_length")
            result.failure_reason = f"Contenido insuficiente: {result.content_length} < {self.MIN_CONTENT_LENGTH} chars"
            return result
        
        result.checks_passed.append("min_content_length")
        
        # CHECK 6: Contenido máximo
        if result.content_length > self.MAX_CONTENT_LENGTH:
            result.is_valid = False
            result.checks_failed.append("max_content_length")
            result.failure_reason = f"Contenido excesivo: {result.content_length} > {self.MAX_CONTENT_LENGTH} chars"
            return result
        
        result.checks_passed.append("max_content_length")
        
        # CHECK 7: Ratio ASCII razonable
        ascii_ratio = self._calculate_ascii_ratio(content)
        if ascii_ratio < self.MIN_ASCII_RATIO:
            result.is_valid = False
            result.checks_failed.append("ascii_ratio")
            result.failure_reason = f"Contenido no legible: {ascii_ratio:.2%} ASCII"
            return result
        
        result.checks_passed.append("ascii_ratio")
        
        # CHECK 8: Metadata presente (warning, no bloqueante)
        metadata = self._extract_metadata(file_path, mime_type)
        result.has_metadata = bool(metadata.get("title") or metadata.get("author"))
        if not result.has_metadata:
            result.warning_messages = ["Documento sin metadata (título/autor)"]
        
        result.checks_passed.append("metadata_check")
        
        return result
```

### Integración en Pipeline

**Archivo**: `app/services/ingesta.py`

**Modificar**:
```python
from app.services.ingestion_validation import DocumentValidator

def ingest_file_from_path(
    db: Session,
    file_path: Path,
    case_id: str,
    doc_type: str,
    document_date: Optional[str] = None
) -> DocumentChunk:
    # ← NUEVO: Validación pre-ingesta (FAIL FAST)
    validator = DocumentValidator()
    validation_result = validator.validate_document(file_path)
    
    if not validation_result.is_valid:
        logger.error(
            "Documento rechazado en validación pre-ingesta",
            action="ingestion_rejected",
            case_id=case_id,
            file_path=str(file_path),
            reason=validation_result.failure_reason,
            checks_failed=validation_result.checks_failed
        )
        raise ValueError(
            f"[INGESTION VALIDATION FAILED] "
            f"file={file_path.name} "
            f"reason={validation_result.failure_reason}"
        )
    
    # Log warnings (no bloqueantes)
    if validation_result.warning_messages:
        logger.warning(
            "Documento con warnings en validación",
            action="ingestion_warnings",
            case_id=case_id,
            warnings=validation_result.warning_messages
        )
    
    # Log validación exitosa
    logger.info(
        "Documento validado para ingesta",
        action="ingestion_validated",
        case_id=case_id,
        file_path=str(file_path),
        content_length=validation_result.content_length,
        checks_passed=len(validation_result.checks_passed)
    )
    
    # → CONTINUAR con ingesta existente
    # ...
```

### Fail Conditions

**El sistema DEBE rechazar si**:
1. Archivo no legible
2. Formato no soportado (no PDF/DOCX)
3. PDF encriptado
4. Documento corrupto (parsing falla)
5. Contenido < 100 caracteres
6. Contenido > 10M caracteres
7. < 10% caracteres ASCII (probable basura binaria)

**Acción**: Lanzar `ValueError` con mensaje estructurado, NO ingerir.

### Garantía Legal

**Con este endurecimiento**:
1. ✅ NO se ingieren documentos corruptos que contaminen análisis
2. ✅ Logs prueban que documento fue validado antes de procesamiento
3. ✅ Defensa contra "procesaron basura y sacaron conclusiones"
4. ✅ Reproducibilidad: mismo documento validado = misma ingesta
5. ✅ Auditor puede ver qué checks pasaron/fallaron

---

## ENDURECIMIENTO 3: CHUNKS CON OFFSETS Y PÁGINA PARA CITAS LEGALES REALES

### Estado Actual

**No implementado**:
- Chunks sin offset en documento original
- Chunks sin número de página
- Citas no son verificables manualmente
- Imposible localizar texto citado en PDF original

### Diseño Técnico

**Chunk Extendido con Offsets**:

```python
# app/models/document_chunk.py

from dataclasses import dataclass
from typing import Optional

@dataclass
class ChunkLocation:
    """Ubicación exacta del chunk en documento original."""
    page_number: int  # Página en PDF (1-indexed)
    char_offset_start: int  # Offset de inicio en documento completo
    char_offset_end: int  # Offset de fin en documento completo
    
    # Opcional: para verificación
    context_before: Optional[str] = None  # 50 chars antes
    context_after: Optional[str] = None  # 50 chars después

class DocumentChunk(BaseModel):
    """Chunk con ubicación para citas verificables."""
    chunk_id: str
    doc_id: str
    case_id: str
    content: str
    
    # ← NUEVO
    location: ChunkLocation
    
    # Metadata existente
    doc_type: str
    document_date: Optional[str] = None
    embedding: Optional[List[float]] = None
    
    # ← NUEVO: Hash para verificación
    content_hash: str  # SHA256 del contenido
```

### Estructura de Datos en ChromaDB

**Metadata por Chunk**:

```python
{
    "chunk_id": "doc_001_chunk_003",
    "doc_id": "doc_001",
    "case_id": "CASE_001",
    "doc_type": "balance_pyg",
    
    # ← NUEVO
    "page_number": 3,
    "char_offset_start": 2450,
    "char_offset_end": 3450,
    "context_before": "...texto previo para verificación...",
    "context_after": "...texto posterior para verificación...",
    "content_hash": "sha256:abc123...",
    
    # Existente
    "document_date": "2024-12-15",
    "embedding_model": "text-embedding-3-large"
}
```

### Integración en Pipeline

**Archivo**: `app/services/document_chunk_pipeline.py`

**Modificar**:
```python
from pypdf import PdfReader

def build_document_chunks_for_case(
    db: Session,
    case_id: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200
) -> List[DocumentChunk]:
    documents = get_documents_by_case(db, case_id)
    all_chunks = []
    
    for doc in documents:
        file_path = get_document_path(doc.doc_id)
        
        # ← NUEVO: Extraer con offsets
        chunks_with_location = extract_chunks_with_location(
            file_path=file_path,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
        
        for idx, (content, location) in enumerate(chunks_with_location):
            chunk = DocumentChunk(
                chunk_id=f"{doc.doc_id}_chunk_{idx:03d}",
                doc_id=doc.doc_id,
                case_id=case_id,
                content=content,
                location=location,  # ← NUEVO
                doc_type=doc.doc_type,
                content_hash=hashlib.sha256(content.encode()).hexdigest()  # ← NUEVO
            )
            all_chunks.append(chunk)
    
    return all_chunks


def extract_chunks_with_location(
    file_path: Path,
    chunk_size: int,
    chunk_overlap: int
) -> List[Tuple[str, ChunkLocation]]:
    """Extrae chunks con ubicación exacta en documento."""
    
    if file_path.suffix.lower() == ".pdf":
        return extract_pdf_chunks_with_location(file_path, chunk_size, chunk_overlap)
    elif file_path.suffix.lower() == ".docx":
        return extract_docx_chunks_with_location(file_path, chunk_size, chunk_overlap)
    else:
        raise ValueError(f"Formato no soportado: {file_path.suffix}")


def extract_pdf_chunks_with_location(
    file_path: Path,
    chunk_size: int,
    chunk_overlap: int
) -> List[Tuple[str, ChunkLocation]]:
    """Extrae chunks de PDF con página y offsets."""
    
    reader = PdfReader(file_path)
    
    # Extraer texto completo con tracking de páginas
    full_text = ""
    page_offsets = []  # [(page_num, start_offset, end_offset), ...]
    
    for page_num, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text()
        start_offset = len(full_text)
        full_text += page_text
        end_offset = len(full_text)
        page_offsets.append((page_num, start_offset, end_offset))
    
    # Chunking con offsets
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len
    )
    
    chunks_raw = text_splitter.split_text(full_text)
    
    # Calcular offsets de cada chunk
    chunks_with_location = []
    current_offset = 0
    
    for chunk_text in chunks_raw:
        # Buscar chunk en full_text (tolerante a cambios mínimos)
        chunk_start = full_text.find(chunk_text, current_offset)
        if chunk_start == -1:
            # Fallback: buscar aproximado
            chunk_start = current_offset
        
        chunk_end = chunk_start + len(chunk_text)
        
        # Determinar página
        page_num = get_page_number_for_offset(chunk_start, page_offsets)
        
        # Contexto para verificación
        context_before = full_text[max(0, chunk_start - 50):chunk_start]
        context_after = full_text[chunk_end:chunk_end + 50]
        
        location = ChunkLocation(
            page_number=page_num,
            char_offset_start=chunk_start,
            char_offset_end=chunk_end,
            context_before=context_before,
            context_after=context_after
        )
        
        chunks_with_location.append((chunk_text, location))
        current_offset = chunk_end - chunk_overlap
    
    return chunks_with_location


def get_page_number_for_offset(offset: int, page_offsets: List[Tuple]) -> int:
    """Determina número de página para un offset dado."""
    for page_num, start, end in page_offsets:
        if start <= offset < end:
            return page_num
    return page_offsets[-1][0]  # Última página por defecto
```

### Fail Conditions

**El sistema DEBE fallar si**:
1. Chunk sin `page_number`
2. Chunk sin `char_offset_start` o `char_offset_end`
3. Offsets fuera de rango del documento
4. `content_hash` no coincide con hash real del contenido

**Acción**: Rechazar chunk en validación, NO insertarlo en ChromaDB.

### Garantía Legal

**Con este endurecimiento**:
1. ✅ Cada cita es VERIFICABLE manualmente en PDF original
2. ✅ Perito puede localizar texto citado: "Página 3, offset 2450-3450"
3. ✅ Contexto antes/después prueba que chunk no fue alterado
4. ✅ Hash permite detectar manipulación post-ingesta
5. ✅ Defensa contra "sistema inventó cita" → Cita es localizable

**Ejemplo de Cita Verificable**:
```
"Según el Balance y PyG del ejercicio 2023 (pág. 3, offset 2450-3450):
'El activo corriente asciende a 45.000€, mientras que el pasivo corriente 
alcanza 120.000€, evidenciando insolvencia de tesorería.'"

Verificación:
1. Abrir documento doc_001.pdf
2. Ir a página 3
3. Buscar texto en offset 2450-3450
4. Verificar contexto antes/después
5. Verificar hash del contenido
```

---

## ENDURECIMIENTO 4: RAG CON EVIDENCIA OBLIGATORIA (SIN CHUNKS → NO RESPUESTA)

### Estado Actual

**Parcialmente implementado**:
- RAG puede recuperar 0 chunks y seguir respondiendo
- No hay validación de calidad de chunks recuperados
- No hay threshold de similitud duro

### Diseño Técnico

**RAG con Validación de Evidencia**:

```
Query → Retrieve Chunks → Validar Evidencia → Responder
                          ↓
                          FAIL si:
                          - 0 chunks recuperados
                          - Todos los chunks tienen similarity > threshold
                          - Chunks sin metadata crítica
```

### Estructura de Datos

```python
# app/rag/evidence_validation.py

from dataclasses import dataclass
from typing import List, Optional
from enum import Enum

class EvidenceStatus(Enum):
    """Estado de evidencia recuperada."""
    SUFFICIENT = "sufficient"  # Evidencia suficiente
    WEAK = "weak"  # Evidencia débil (similarity alta)
    INSUFFICIENT = "insufficient"  # No hay suficientes chunks
    MISSING = "missing"  # 0 chunks recuperados

@dataclass
class EvidenceValidationResult:
    """Resultado de validación de evidencia RAG."""
    status: EvidenceStatus
    chunks_retrieved: int
    chunks_valid: int  # Similarity < threshold
    avg_similarity: float
    min_similarity: float
    max_similarity: float
    
    is_response_allowed: bool  # ← CRÍTICO
    failure_reason: Optional[str] = None
    warning_message: Optional[str] = None

class EvidenceValidator:
    """Validador de evidencia RAG."""
    
    # Thresholds duros
    MIN_CHUNKS_REQUIRED = 2  # Mínimo 2 chunks
    MAX_SIMILARITY_ALLOWED = 1.3  # Distancia L2 máxima permitida
    MAX_AVG_SIMILARITY_ALLOWED = 1.0  # Distancia L2 promedio máxima
    
    def validate_evidence(
        self,
        chunks: List[RagChunk],
        query: str
    ) -> EvidenceValidationResult:
        """Valida que evidencia es suficiente para responder."""
        
        # CASO 1: 0 chunks recuperados
        if len(chunks) == 0:
            return EvidenceValidationResult(
                status=EvidenceStatus.MISSING,
                chunks_retrieved=0,
                chunks_valid=0,
                avg_similarity=float('inf'),
                min_similarity=float('inf'),
                max_similarity=float('inf'),
                is_response_allowed=False,  # ← NO RESPONDER
                failure_reason="No se recuperaron chunks para la consulta"
            )
        
        # Calcular métricas de similitud
        similarities = [chunk.score for chunk in chunks]
        avg_sim = sum(similarities) / len(similarities)
        min_sim = min(similarities)
        max_sim = max(similarities)
        
        # CASO 2: Todos los chunks tienen similarity muy alta (irrelevantes)
        chunks_valid = sum(1 for s in similarities if s <= self.MAX_SIMILARITY_ALLOWED)
        
        if chunks_valid == 0:
            return EvidenceValidationResult(
                status=EvidenceStatus.INSUFFICIENT,
                chunks_retrieved=len(chunks),
                chunks_valid=0,
                avg_similarity=avg_sim,
                min_similarity=min_sim,
                max_similarity=max_sim,
                is_response_allowed=False,  # ← NO RESPONDER
                failure_reason=f"Todos los chunks son irrelevantes (similarity > {self.MAX_SIMILARITY_ALLOWED})"
            )
        
        # CASO 3: Menos chunks válidos que mínimo requerido
        if chunks_valid < self.MIN_CHUNKS_REQUIRED:
            return EvidenceValidationResult(
                status=EvidenceStatus.INSUFFICIENT,
                chunks_retrieved=len(chunks),
                chunks_valid=chunks_valid,
                avg_similarity=avg_sim,
                min_similarity=min_sim,
                max_similarity=max_sim,
                is_response_allowed=False,  # ← NO RESPONDER
                failure_reason=f"Chunks válidos ({chunks_valid}) < mínimo requerido ({self.MIN_CHUNKS_REQUIRED})"
            )
        
        # CASO 4: Similitud promedio muy alta (evidencia débil)
        if avg_sim > self.MAX_AVG_SIMILARITY_ALLOWED:
            return EvidenceValidationResult(
                status=EvidenceStatus.WEAK,
                chunks_retrieved=len(chunks),
                chunks_valid=chunks_valid,
                avg_similarity=avg_sim,
                min_similarity=min_sim,
                max_similarity=max_sim,
                is_response_allowed=True,  # ← RESPONDER CON WARNING
                warning_message=f"Evidencia débil (avg similarity {avg_sim:.2f} > {self.MAX_AVG_SIMILARITY_ALLOWED})"
            )
        
        # CASO 5: Evidencia suficiente
        return EvidenceValidationResult(
            status=EvidenceStatus.SUFFICIENT,
            chunks_retrieved=len(chunks),
            chunks_valid=chunks_valid,
            avg_similarity=avg_sim,
            min_similarity=min_sim,
            max_similarity=max_sim,
            is_response_allowed=True  # ← RESPONDER
        )
```

### Integración en Pipeline

**Archivo**: `app/rag/case_rag/retrieve.py`

**Modificar**:
```python
from app.rag.evidence_validation import EvidenceValidator, EvidenceStatus

def query_case_rag(
    case_id: str,
    query: str,
    top_k: int = 5
) -> Dict[str, Any]:
    # 1. Recuperar chunks → EXISTENTE
    chunks = retrieve_chunks(case_id, query, top_k)
    
    # 2. ← NUEVO: Validar evidencia (HARD CHECK)
    validator = EvidenceValidator()
    evidence_result = validator.validate_evidence(chunks, query)
    
    # 3. ← NUEVO: Si evidencia insuficiente, NO responder
    if not evidence_result.is_response_allowed:
        logger.warning(
            "RAG rechazó respuesta por evidencia insuficiente",
            action="rag_evidence_insufficient",
            case_id=case_id,
            query=query,
            status=evidence_result.status.value,
            reason=evidence_result.failure_reason
        )
        
        return {
            "response": None,  # ← NO HAY RESPUESTA
            "chunks": [],
            "evidence_status": evidence_result.status.value,
            "failure_reason": evidence_result.failure_reason,
            "metadata": {
                "chunks_retrieved": evidence_result.chunks_retrieved,
                "chunks_valid": evidence_result.chunks_valid
            }
        }
    
    # 4. Si evidencia débil, responder con warning
    if evidence_result.status == EvidenceStatus.WEAK:
        logger.warning(
            "RAG responde con evidencia débil",
            action="rag_evidence_weak",
            case_id=case_id,
            avg_similarity=evidence_result.avg_similarity,
            warning=evidence_result.warning_message
        )
    
    # 5. Construir respuesta → EXISTENTE
    response = build_response(chunks, query)
    
    return {
        "response": response,
        "chunks": chunks,
        "evidence_status": evidence_result.status.value,
        "evidence_validation": {
            "chunks_retrieved": evidence_result.chunks_retrieved,
            "chunks_valid": evidence_result.chunks_valid,
            "avg_similarity": evidence_result.avg_similarity,
            "min_similarity": evidence_result.min_similarity,
            "max_similarity": evidence_result.max_similarity
        },
        "warning": evidence_result.warning_message
    }
```

### Fail Conditions

**El sistema DEBE NO responder si**:
1. `chunks_retrieved == 0`
2. `chunks_valid < MIN_CHUNKS_REQUIRED` (default: 2)
3. Todos los chunks tienen `similarity > MAX_SIMILARITY_ALLOWED` (default: 1.3)

**Acción**: Retornar `response=None`, log de rechazo.

### Garantía Legal

**Con este endurecimiento**:
1. ✅ Sistema NO inventa respuestas sin evidencia documental
2. ✅ Logs prueban que respuesta fue rechazada por falta de evidencia
3. ✅ Defensa contra "sistema alucinó" → Sistema se negó a responder
4. ✅ Thresholds son configurables y auditables
5. ✅ Perito puede verificar que decisión de no responder fue correcta

**Ejemplo de Log de Rechazo**:
```json
{
  "timestamp": "2026-01-06T14:30:00Z",
  "level": "WARNING",
  "action": "rag_evidence_insufficient",
  "case_id": "CASE_001",
  "query": "¿Cuál es el saldo de caja a 31/12/2023?",
  "status": "missing",
  "reason": "No se recuperaron chunks para la consulta",
  "chunks_retrieved": 0,
  "chunks_valid": 0
}
```

---

## ENDURECIMIENTO 5: PLANTILLA FORMAL DE ACUSACIÓN LEGAL

### Estado Actual

**No implementado**:
- Outputs son texto libre sin estructura formal
- No hay template legal estándar
- No hay secciones obligatorias
- No hay numeración de hechos/pruebas

### Diseño Técnico

**Template Formal de Output Legal**:

```
════════════════════════════════════════════════════════════════════════════════
INFORME TÉCNICO DE ANÁLISIS DE RIESGOS LEGALES CONCURSALES
════════════════════════════════════════════════════════════════════════════════

CASO: [CASE_ID]
EMPRESA: [COMPANY_NAME]
FECHA DE ANÁLISIS: [ANALYSIS_DATE]
VERSIÓN DEL SISTEMA: [SYSTEM_VERSION]
ANALISTA: [USER_NAME]

────────────────────────────────────────────────────────────────────────────────
I. ANTECEDENTES
────────────────────────────────────────────────────────────────────────────────

1. Documentación Analizada

   [Lista numerada de documentos con tipo, fecha y hash]
   
   1.1. Balance y PyG ejercicio 2023 (doc_001.pdf)
        Fecha: 31/12/2023
        Hash: sha256:abc123...
        Páginas: 15
        
   1.2. Acta de Junta de Socios (doc_002.pdf)
        Fecha: 15/03/2024
        Hash: sha256:def456...
        Páginas: 3

2. Documentación Faltante

   [Lista de documentos críticos no aportados]
   
   2.1. Informe de tesorería del ejercicio 2023
   2.2. Libros contables legalizados

────────────────────────────────────────────────────────────────────────────────
II. HECHOS PROBADOS
────────────────────────────────────────────────────────────────────────────────

[Listado numerado de hechos extraídos de documentación]

HECHO 1: Insolvencia reconocida en Junta de Socios

   Fuente: Acta de Junta de Socios (doc_002.pdf, pág. 2, offset 1200-1450)
   
   Cita textual:
   "El Consejo de Administración comunica a la Junta que la sociedad se 
   encuentra en estado de insolvencia actual, no pudiendo hacer frente a 
   sus obligaciones corrientes con activos líquidos disponibles."
   
   Fecha del hecho: 15/03/2024
   Evidencia verificada: SÍ
   Hash del fragmento: sha256:xyz789...

HECHO 2: Activo corriente insuficiente para cubrir pasivo corriente

   Fuente: Balance y PyG ejercicio 2023 (doc_001.pdf, pág. 3, offset 2450-2650)
   
   Cita textual:
   "Activo corriente: 45.000€
    Pasivo corriente: 120.000€
    Ratio de liquidez: 0.375"
   
   Fecha del hecho: 31/12/2023
   Evidencia verificada: SÍ
   Hash del fragmento: sha256:abc456...

────────────────────────────────────────────────────────────────────────────────
III. RIESGOS DETECTADOS
────────────────────────────────────────────────────────────────────────────────

[Listado numerado de riesgos con base legal]

RIESGO 1: Retraso en solicitud de concurso (DELAY_FILING)

   Severidad: ALTA
   Confianza: ALTA
   
   Base legal:
   - Art. 5 TRLC: Deber de solicitar concurso en 2 meses
   - Art. 443 TRLC: Presunción de culpabilidad por retraso
   
   Análisis:
   La insolvencia fue reconocida el 15/03/2024 (HECHO 1) pero no consta 
   solicitud de concurso a fecha del análisis (06/01/2026). Transcurridos 
   más de 21 meses desde conocimiento de insolvencia.
   
   Evidencia documental:
   - HECHO 1 (doc_002.pdf, pág. 2)
   - HECHO 2 (doc_001.pdf, pág. 3)
   
   Calificación automática: APLICABLE
   Regla evaluada: TRLC_ART5_DELAY_FILING (v2.0.0)

RIESGO 2: Falta de documentación crítica (DOCUMENTATION_GAP)

   Severidad: MEDIA
   Confianza: MEDIA
   
   Base legal:
   - Art. 6 TRLC: Deber de colaboración
   - Art. 443.1 TRLC: Presunción de culpabilidad por falta de documentación
   
   Análisis:
   No se ha aportado:
   - Informe de tesorería del ejercicio 2023
   - Libros contables legalizados
   
   Evidencia documental:
   - Documentación faltante (sección I.2)
   
   Calificación automática: APLICABLE
   Regla evaluada: TRLC_ART6_COLLABORATION_DUTY (v2.0.0)

────────────────────────────────────────────────────────────────────────────────
IV. CONCLUSIONES
────────────────────────────────────────────────────────────────────────────────

1. Nivel de riesgo global: ALTO

2. Riesgos críticos identificados: 1
   - Retraso en solicitud de concurso

3. Riesgos medios identificados: 1
   - Falta de documentación crítica

4. Documentación faltante crítica: 2 documentos

────────────────────────────────────────────────────────────────────────────────
V. RECOMENDACIONES
────────────────────────────────────────────────────────────────────────────────

1. Verificar fecha exacta de conocimiento de insolvencia y comparar con 
   fecha de solicitud de concurso (si existe).

2. Documentar causas del retraso en solicitud de concurso, si las hubiere.

3. Solicitar documentación faltante de forma fehaciente:
   - Informe de tesorería del ejercicio 2023
   - Libros contables legalizados

4. Evaluar si las irregularidades documentales son sustanciales o formales.

────────────────────────────────────────────────────────────────────────────────
VI. METADATA TÉCNICA
────────────────────────────────────────────────────────────────────────────────

Sistema: Phoenix Legal v1.0.0
Schema de estado: v1.0.0
Rule Engine: v2.0.0
Rulebook: TRLC v2.0.0 (RDL 1/2020)

Análisis ejecutado: 06/01/2026 14:30:52 UTC
Vectorstore: v_20260106_143052 (ACTIVE)
LLM utilizado: gpt-4o-mini (explicación)
LLM degradado: NO

Hash determinista del análisis: sha256:abc123def456...

────────────────────────────────────────────────────────────────────────────────
VII. DISCLAIMER LEGAL
────────────────────────────────────────────────────────────────────────────────

IMPORTANTE: Este documento ha sido generado por Phoenix Legal, un sistema de 
asistencia técnica automatizada para el análisis preliminar de riesgos legales 
concursales.

• NO constituye asesoramiento legal ni dictamen jurídico.
• NO sustituye la revisión por parte de asesor legal cualificado.
• Las conclusiones se basan en reglas deterministas y análisis automatizado.
• Se recomienda validación profesional antes de tomar decisiones legales.

════════════════════════════════════════════════════════════════════════════════
FIN DEL INFORME
════════════════════════════════════════════════════════════════════════════════
```

### Estructura de Datos

```python
# app/reports/formal_template.py

from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime

@dataclass
class DocumentReference:
    """Referencia a documento analizado."""
    doc_id: str
    doc_type: str
    filename: str
    document_date: Optional[str]
    content_hash: str
    page_count: int

@dataclass
class ProvenFact:
    """Hecho probado con evidencia."""
    fact_number: int
    title: str
    source_doc: str
    source_page: int
    source_offset_start: int
    source_offset_end: int
    textual_quote: str
    fact_date: Optional[str]
    evidence_verified: bool
    content_hash: str

@dataclass
class DetectedRisk:
    """Riesgo detectado con base legal."""
    risk_number: int
    risk_type: str
    title: str
    severity: str
    confidence: str
    legal_basis: List[str]  # ["Art. 5 TRLC", ...]
    analysis: str
    documentary_evidence: List[int]  # [1, 2] → HECHO 1, HECHO 2
    automatic_classification: str  # "APLICABLE", "NO APLICABLE"
    rule_evaluated: str  # "TRLC_ART5_DELAY_FILING (v2.0.0)"

@dataclass
class FormalLegalReport:
    """Informe legal formal estructurado."""
    case_id: str
    company_name: str
    analysis_date: datetime
    system_version: str
    analyst_name: str
    
    # I. ANTECEDENTES
    documents_analyzed: List[DocumentReference]
    missing_documents: List[str]
    
    # II. HECHOS PROBADOS
    proven_facts: List[ProvenFact]
    
    # III. RIESGOS DETECTADOS
    detected_risks: List[DetectedRisk]
    
    # IV. CONCLUSIONES
    overall_risk_level: str
    critical_risks_count: int
    medium_risks_count: int
    low_risks_count: int
    missing_critical_docs_count: int
    
    # V. RECOMENDACIONES
    recommendations: List[str]
    
    # VI. METADATA TÉCNICA
    state_schema_version: str
    rule_engine_version: str
    rulebook_version: str
    vectorstore_version: str
    llm_used: Optional[str]
    llm_degraded: bool
    analysis_hash: str  # Hash determinista del análisis
```

### Integración en Pipeline

**Archivo**: `app/reports/build_report.py`

**Modificar**:
```python
from app.reports.formal_template import (
    FormalLegalReport,
    DocumentReference,
    ProvenFact,
    DetectedRisk
)

def build_formal_legal_report(
    state: PhoenixState,
    rule_result: RuleEngineResult
) -> FormalLegalReport:
    """Construye informe legal formal estructurado."""
    
    # I. ANTECEDENTES
    docs_analyzed = [
        DocumentReference(
            doc_id=doc.doc_id,
            doc_type=doc.doc_type,
            filename=doc.metadata.get("filename", "unknown"),
            document_date=doc.date,
            content_hash=doc.metadata.get("content_hash"),
            page_count=doc.metadata.get("page_count", 0)
        )
        for doc in state.inputs.documents
    ]
    
    # II. HECHOS PROBADOS
    facts = []
    for idx, event in enumerate(state.timeline.events, start=1):
        # Buscar chunk source
        source_chunk = find_chunk_for_event(event, state.rag_evidence.case_chunks)
        
        if source_chunk:
            fact = ProvenFact(
                fact_number=idx,
                title=event.description,
                source_doc=source_chunk.doc_id,
                source_page=source_chunk.metadata.get("page_number"),
                source_offset_start=source_chunk.metadata.get("char_offset_start"),
                source_offset_end=source_chunk.metadata.get("char_offset_end"),
                textual_quote=source_chunk.content[:500],  # Primeros 500 chars
                fact_date=event.date,
                evidence_verified=True,
                content_hash=source_chunk.metadata.get("content_hash")
            )
            facts.append(fact)
    
    # III. RIESGOS DETECTADOS
    risks = []
    for idx, decision in enumerate(rule_result.triggered_rules, start=1):
        # Mapear a hechos probados
        evidence_facts = map_decision_to_facts(decision, facts)
        
        risk = DetectedRisk(
            risk_number=idx,
            risk_type=decision.rule_id,
            title=decision.rule_name,
            severity=decision.severity,
            confidence=decision.confidence,
            legal_basis=extract_legal_articles(decision.article),
            analysis=decision.rationale,
            documentary_evidence=[f.fact_number for f in evidence_facts],
            automatic_classification="APLICABLE",
            rule_evaluated=f"{decision.rule_id} (v{rule_result.engine_version})"
        )
        risks.append(risk)
    
    # IV. CONCLUSIONES
    overall_risk = calculate_overall_risk(rule_result)
    critical_count = sum(1 for r in risks if r.severity == "high")
    medium_count = sum(1 for r in risks if r.severity == "medium")
    low_count = sum(1 for r in risks if r.severity == "low")
    
    # V. RECOMENDACIONES
    recommendations = generate_recommendations(rule_result, state)
    
    # VI. METADATA
    analysis_hash = rule_result.to_deterministic_hash()
    
    return FormalLegalReport(
        case_id=state.case_id,
        company_name=state.case_context.company_name or "N/A",
        analysis_date=datetime.utcnow(),
        system_version="1.0.0",
        analyst_name="Sistema Automatizado",
        
        documents_analyzed=docs_analyzed,
        missing_documents=state.inputs.missing_documents,
        
        proven_facts=facts,
        detected_risks=risks,
        
        overall_risk_level=overall_risk,
        critical_risks_count=critical_count,
        medium_risks_count=medium_count,
        low_risks_count=low_count,
        missing_critical_docs_count=len(state.inputs.missing_documents),
        
        recommendations=recommendations,
        
        state_schema_version=state.schema_version,
        rule_engine_version=rule_result.engine_version,
        rulebook_version=rule_result.rulebook_version,
        vectorstore_version=get_active_vectorstore_version(state.case_id),
        llm_used=state.agents.auditor_llm.model_used if state.agents.auditor_llm else None,
        llm_degraded=not state.agents.auditor_llm.executed if state.agents.auditor_llm else True,
        analysis_hash=analysis_hash
    )
```

### Fail Conditions

**El sistema DEBE fallar si**:
1. Informe sin sección I (ANTECEDENTES)
2. Informe sin sección II (HECHOS PROBADOS)
3. Informe sin sección III (RIESGOS DETECTADOS)
4. Informe sin disclaimer legal
5. Informe sin hash determinista

**Acción**: Rechazar generación de informe, log de error.

### Garantía Legal

**Con este endurecimiento**:
1. ✅ Formato estándar reconocible por abogados y tribunales
2. ✅ Secciones obligatorias (antecedentes, hechos, riesgos, conclusiones)
3. ✅ Cada hecho tiene fuente verificable (documento + página + offset)
4. ✅ Cada riesgo tiene base legal (artículos TRLC)
5. ✅ Numeración permite referencias cruzadas
6. ✅ Hash permite verificar integridad del informe

---

## ENDURECIMIENTO 6: TRACING ESTRUCTURADO + CAPACIDAD DE REPLAY

### Estado Actual

**Parcialmente implementado**:
- Logs JSON estructurados
- Métricas Prometheus
- NO hay tracing de ejecución completa
- NO hay capacidad de replay

### Diseño Técnico

**Trace Estructurado de Ejecución**:

```json
{
  "trace_id": "trace_20260106_143052_abc123",
  "case_id": "CASE_001",
  "started_at": "2026-01-06T14:30:52Z",
  "completed_at": "2026-01-06T14:31:45Z",
  "duration_ms": 53000,
  "status": "completed",
  
  "input": {
    "case_id": "CASE_001",
    "documents": [
      {
        "doc_id": "doc_001",
        "doc_type": "balance_pyg",
        "hash": "sha256:abc123..."
      }
    ],
    "user": "analyst@company.com",
    "config": {
      "llm_enabled": true,
      "rag_top_k": 5
    }
  },
  
  "stages": [
    {
      "stage_name": "ingest_documents",
      "started_at": "2026-01-06T14:30:52Z",
      "completed_at": "2026-01-06T14:30:55Z",
      "duration_ms": 3000,
      "status": "success",
      "input": {...},
      "output": {
        "documents_ingested": 5,
        "chunks_created": 47
      }
    },
    {
      "stage_name": "build_embeddings",
      "started_at": "2026-01-06T14:30:55Z",
      "completed_at": "2026-01-06T14:31:10Z",
      "duration_ms": 15000,
      "status": "success",
      "input": {
        "chunks_count": 47
      },
      "output": {
        "vectorstore_version": "v_20260106_143052",
        "embeddings_generated": 47,
        "tokens_consumed": 45000,
        "cost_usd": 0.00585
      }
    },
    {
      "stage_name": "analyze_timeline",
      "started_at": "2026-01-06T14:31:10Z",
      "completed_at": "2026-01-06T14:31:12Z",
      "duration_ms": 2000,
      "status": "success",
      "output": {
        "events_extracted": 8
      }
    },
    {
      "stage_name": "detect_risks",
      "started_at": "2026-01-06T14:31:12Z",
      "completed_at": "2026-01-06T14:31:15Z",
      "duration_ms": 3000,
      "status": "success",
      "output": {
        "risks_detected": 3
      }
    },
    {
      "stage_name": "evaluate_rules",
      "started_at": "2026-01-06T14:31:15Z",
      "completed_at": "2026-01-06T14:31:20Z",
      "duration_ms": 5000,
      "status": "success",
      "input": {
        "rulebook_version": "2.0.0",
        "rules_count": 5
      },
      "output": {
        "rules_triggered": 2,
        "rules_discarded": 3,
        "rule_result_hash": "sha256:xyz789..."
      }
    },
    {
      "stage_name": "auditor_llm",
      "started_at": "2026-01-06T14:31:20Z",
      "completed_at": "2026-01-06T14:31:35Z",
      "duration_ms": 15000,
      "status": "success",
      "input": {
        "model": "gpt-4o-mini",
        "max_tokens": 500
      },
      "output": {
        "llm_used": true,
        "model_used": "gpt-4o-mini",
        "tokens_prompt": 1200,
        "tokens_completion": 350,
        "cost_usd": 0.00052
      }
    },
    {
      "stage_name": "build_report",
      "started_at": "2026-01-06T14:31:35Z",
      "completed_at": "2026-01-06T14:31:45Z",
      "duration_ms": 10000,
      "status": "success",
      "output": {
        "report_generated": true,
        "pdf_path": "clients_data/cases/CASE_001/reports/report_20260106.pdf"
      }
    }
  ],
  
  "output": {
    "overall_risk": "high",
    "triggered_rules_count": 2,
    "report_hash": "sha256:abc456...",
    "state_hash": "sha256:def789..."
  },
  
  "metrics": {
    "total_duration_ms": 53000,
    "llm_calls": 1,
    "llm_tokens_total": 1550,
    "llm_cost_total_usd": 0.00637,
    "rag_queries": 3
  }
}
```

### Estructura de Datos

```python
# app/core/tracing.py

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum
import uuid

class StageStatus(Enum):
    """Estado de un stage."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"

@dataclass
class StageTrace:
    """Trace de un stage individual."""
    stage_name: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_ms: Optional[float] = None
    status: StageStatus = StageStatus.PENDING
    input: Dict[str, Any] = field(default_factory=dict)
    output: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

@dataclass
class ExecutionTrace:
    """Trace completo de ejecución."""
    trace_id: str
    case_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_ms: Optional[float] = None
    status: str = "running"
    
    input: Dict[str, Any] = field(default_factory=dict)
    stages: List[StageTrace] = field(default_factory=list)
    output: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)

class TracingContext:
    """Contexto de tracing para ejecución."""
    
    def __init__(self, case_id: str, user: str):
        self.trace = ExecutionTrace(
            trace_id=f"trace_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}",
            case_id=case_id,
            started_at=datetime.utcnow(),
            input={"case_id": case_id, "user": user}
        )
        self.current_stage: Optional[StageTrace] = None
    
    def start_stage(self, stage_name: str, input_data: Dict = None):
        """Inicia un nuevo stage."""
        self.current_stage = StageTrace(
            stage_name=stage_name,
            started_at=datetime.utcnow(),
            status=StageStatus.RUNNING,
            input=input_data or {}
        )
        self.trace.stages.append(self.current_stage)
        
        logger.info(
            f"Stage iniciado: {stage_name}",
            action="stage_started",
            trace_id=self.trace.trace_id,
            stage_name=stage_name
        )
    
    def complete_stage(self, output_data: Dict = None):
        """Completa el stage actual."""
        if not self.current_stage:
            raise ValueError("No hay stage activo")
        
        self.current_stage.completed_at = datetime.utcnow()
        self.current_stage.duration_ms = (
            self.current_stage.completed_at - self.current_stage.started_at
        ).total_seconds() * 1000
        self.current_stage.status = StageStatus.SUCCESS
        self.current_stage.output = output_data or {}
        
        logger.info(
            f"Stage completado: {self.current_stage.stage_name}",
            action="stage_completed",
            trace_id=self.trace.trace_id,
            stage_name=self.current_stage.stage_name,
            duration_ms=self.current_stage.duration_ms
        )
        
        self.current_stage = None
    
    def fail_stage(self, error: Exception):
        """Marca el stage actual como fallido."""
        if not self.current_stage:
            raise ValueError("No hay stage activo")
        
        self.current_stage.completed_at = datetime.utcnow()
        self.current_stage.duration_ms = (
            self.current_stage.completed_at - self.current_stage.started_at
        ).total_seconds() * 1000
        self.current_stage.status = StageStatus.FAILED
        self.current_stage.error = str(error)
        
        logger.error(
            f"Stage falló: {self.current_stage.stage_name}",
            action="stage_failed",
            trace_id=self.trace.trace_id,
            stage_name=self.current_stage.stage_name,
            error=str(error)
        )
        
        self.current_stage = None
    
    def complete_trace(self, output_data: Dict = None):
        """Completa el trace completo."""
        self.trace.completed_at = datetime.utcnow()
        self.trace.duration_ms = (
            self.trace.completed_at - self.trace.started_at
        ).total_seconds() * 1000
        self.trace.status = "completed"
        self.trace.output = output_data or {}
        
        # Calcular métricas
        self.trace.metrics = {
            "total_duration_ms": self.trace.duration_ms,
            "stages_count": len(self.trace.stages),
            "stages_success": sum(1 for s in self.trace.stages if s.status == StageStatus.SUCCESS),
            "stages_failed": sum(1 for s in self.trace.stages if s.status == StageStatus.FAILED),
        }
        
        # Guardar trace
        self._save_trace()
        
        logger.info(
            "Trace completado",
            action="trace_completed",
            trace_id=self.trace.trace_id,
            duration_ms=self.trace.duration_ms,
            stages_count=len(self.trace.stages)
        )
    
    def _save_trace(self):
        """Guarda trace en disco para replay."""
        trace_file = Path(f"clients_data/logs/traces/{self.trace.trace_id}.json")
        trace_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(trace_file, "w") as f:
            json.dump(asdict(self.trace), f, indent=2, default=str)
```

### Integración en Pipeline

**Archivo**: `app/graphs/audit_graph.py`

**Modificar**:
```python
from app.core.tracing import TracingContext

def run_audit_analysis(
    case_id: str,
    user: str = "system"
) -> PhoenixState:
    """Ejecuta análisis completo con tracing."""
    
    # Iniciar trace
    trace = TracingContext(case_id=case_id, user=user)
    
    try:
        # STAGE 1: Ingest documents
        trace.start_stage("ingest_documents")
        documents = ingest_documents_for_case(db, case_id)
        trace.complete_stage({"documents_count": len(documents)})
        
        # STAGE 2: Build embeddings
        trace.start_stage("build_embeddings", {"documents_count": len(documents)})
        version_id = build_embeddings_for_case(db, case_id)
        trace.complete_stage({"vectorstore_version": version_id})
        
        # STAGE 3: Analyze timeline
        trace.start_stage("analyze_timeline")
        timeline = analyze_timeline(state)
        trace.complete_stage({"events_count": len(timeline.events)})
        
        # STAGE 4: Detect risks
        trace.start_stage("detect_risks")
        risks = detect_risks(state)
        trace.complete_stage({"risks_count": len(risks)})
        
        # STAGE 5: Evaluate rules
        trace.start_stage("evaluate_rules")
        rule_result = evaluate_legal_rules(state)
        trace.complete_stage({
            "rules_triggered": len(rule_result.triggered_rules),
            "rules_discarded": len(rule_result.discarded_rules)
        })
        
        # STAGE 6: Auditor LLM (opcional)
        if llm_enabled:
            trace.start_stage("auditor_llm")
            try:
                auditor_result = run_auditor_llm(state)
                trace.complete_stage({
                    "llm_used": True,
                    "tokens_used": auditor_result.tokens_used
                })
            except Exception as e:
                trace.fail_stage(e)
                # Continuar en modo degradado
        
        # STAGE 7: Build report
        trace.start_stage("build_report")
        report = build_formal_legal_report(state, rule_result)
        trace.complete_stage({"report_generated": True})
        
        # Completar trace
        trace.complete_trace({
            "overall_risk": report.overall_risk_level,
            "report_hash": report.analysis_hash
        })
        
        return state
    
    except Exception as e:
        if trace.current_stage:
            trace.fail_stage(e)
        trace.trace.status = "failed"
        trace._save_trace()
        raise
```

### Capacidad de Replay

```python
# app/core/replay.py

def replay_trace(trace_id: str) -> ExecutionTrace:
    """Carga y reproduce un trace guardado."""
    trace_file = Path(f"clients_data/logs/traces/{trace_id}.json")
    
    if not trace_file.exists():
        raise FileNotFoundError(f"Trace no encontrado: {trace_id}")
    
    with open(trace_file) as f:
        trace_data = json.load(f)
    
    # Reconstruir ExecutionTrace
    trace = ExecutionTrace(**trace_data)
    
    return trace

def compare_traces(trace_id_1: str, trace_id_2: str) -> Dict[str, Any]:
    """Compara dos traces para debugging/regresión."""
    trace_1 = replay_trace(trace_id_1)
    trace_2 = replay_trace(trace_id_2)
    
    comparison = {
        "trace_1_id": trace_1.trace_id,
        "trace_2_id": trace_2.trace_id,
        "same_case": trace_1.case_id == trace_2.case_id,
        "duration_diff_ms": trace_2.duration_ms - trace_1.duration_ms,
        "stages_count_diff": len(trace_2.stages) - len(trace_1.stages),
        "output_diff": diff_dicts(trace_1.output, trace_2.output)
    }
    
    return comparison
```

### Fail Conditions

**El sistema DEBE fallar si**:
1. Trace no se guarda en disco
2. Stage sin `started_at` o `completed_at`
3. Trace sin `trace_id` único

**Acción**: Log de error, trace marcado como corrupto.

### Garantía Legal

**Con este endurecimiento**:
1. ✅ Cada ejecución tiene trace completo inmutable
2. ✅ Perito puede revisar trace para entender decisiones
3. ✅ Replay permite reproducir ejecución para debugging
4. ✅ Comparación de traces detecta regresiones
5. ✅ Métricas detalladas por stage (duración, costes, tokens)
6. ✅ Defensa contra "proceso fue opaco" → Trace completo disponible

---

## ENDURECIMIENTO 7: FINOPS MÍNIMO (HOT/COLD CACHE + SEMANTIC CACHE)

### Estado Actual

**Parcialmente implementado**:
- Caché RAG con TTL (1 hora)
- NO hay hot/cold cache
- NO hay semantic cache
- NO hay control de costes por caso

### Diseño Técnico

**Hot/Cold Cache Strategy**:

```
Query → Check Hot Cache → Check Cold Cache → RAG Query
        (in-memory)       (disk)            (ChromaDB + OpenAI)
        TTL: 5 min        TTL: 24h
```

**Semantic Cache**:
```
Query → Embedding → Check Semantic Cache → RAG Query
                    (similar queries)
                    Threshold: 0.95 similarity
```

### Estructura de Datos

```python
# app/rag/finops_cache.py

from dataclasses import dataclass
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import hashlib

@dataclass
class CacheEntry:
    """Entrada de caché con metadata."""
    query: str
    query_hash: str
    query_embedding: Optional[List[float]]  # Para semantic cache
    response: Dict
    chunks: List[Dict]
    cached_at: datetime
    accessed_count: int
    last_accessed: datetime
    tier: str  # "hot", "cold"
    cost_saved_usd: float  # Coste evitado por hit

class FinOpsCache:
    """Caché con estrategia hot/cold + semantic."""
    
    HOT_TTL_SECONDS = 300  # 5 minutos
    COLD_TTL_SECONDS = 86400  # 24 horas
    SEMANTIC_SIMILARITY_THRESHOLD = 0.95
    
    def __init__(self):
        self.hot_cache: Dict[str, CacheEntry] = {}
        self.cold_cache_dir = Path("clients_data/_cache/rag_cold")
        self.cold_cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Stats
        self.stats = {
            "hot_hits": 0,
            "cold_hits": 0,
            "semantic_hits": 0,
            "misses": 0,
            "total_cost_saved_usd": 0.0
        }
    
    def get(self, query: str, case_id: str) -> Optional[Dict]:
        """Obtiene resultado de caché (hot → cold → semantic → None)."""
        query_hash = self._hash_query(query, case_id)
        
        # 1. Check hot cache (in-memory)
        if query_hash in self.hot_cache:
            entry = self.hot_cache[query_hash]
            if self._is_hot_valid(entry):
                self.stats["hot_hits"] += 1
                entry.accessed_count += 1
                entry.last_accessed = datetime.utcnow()
                self.stats["total_cost_saved_usd"] += entry.cost_saved_usd
                
                logger.info(
                    "Hot cache HIT",
                    action="cache_hot_hit",
                    query_hash=query_hash,
                    cost_saved_usd=entry.cost_saved_usd
                )
                
                return entry.response
            else:
                # Expiró, mover a cold
                self._move_to_cold(entry)
                del self.hot_cache[query_hash]
        
        # 2. Check cold cache (disk)
        cold_entry = self._load_from_cold(query_hash)
        if cold_entry and self._is_cold_valid(cold_entry):
            self.stats["cold_hits"] += 1
            cold_entry.accessed_count += 1
            cold_entry.last_accessed = datetime.utcnow()
            self.stats["total_cost_saved_usd"] += cold_entry.cost_saved_usd
            
            # Promover a hot si acceso frecuente
            if cold_entry.accessed_count > 3:
                cold_entry.tier = "hot"
                self.hot_cache[query_hash] = cold_entry
            
            logger.info(
                "Cold cache HIT",
                action="cache_cold_hit",
                query_hash=query_hash,
                accessed_count=cold_entry.accessed_count,
                cost_saved_usd=cold_entry.cost_saved_usd
            )
            
            return cold_entry.response
        
        # 3. Check semantic cache (queries similares)
        semantic_result = self._check_semantic_cache(query, case_id)
        if semantic_result:
            self.stats["semantic_hits"] += 1
            self.stats["total_cost_saved_usd"] += semantic_result["cost_saved_usd"]
            
            logger.info(
                "Semantic cache HIT",
                action="cache_semantic_hit",
                original_query=query,
                similar_query=semantic_result["original_query"],
                similarity=semantic_result["similarity"],
                cost_saved_usd=semantic_result["cost_saved_usd"]
            )
            
            return semantic_result["response"]
        
        # 4. MISS
        self.stats["misses"] += 1
        logger.info(
            "Cache MISS",
            action="cache_miss",
            query_hash=query_hash
        )
        
        return None
    
    def set(
        self,
        query: str,
        case_id: str,
        response: Dict,
        chunks: List[Dict],
        query_embedding: Optional[List[float]] = None,
        cost_usd: float = 0.0
    ):
        """Guarda resultado en hot cache."""
        query_hash = self._hash_query(query, case_id)
        
        entry = CacheEntry(
            query=query,
            query_hash=query_hash,
            query_embedding=query_embedding,
            response=response,
            chunks=chunks,
            cached_at=datetime.utcnow(),
            accessed_count=0,
            last_accessed=datetime.utcnow(),
            tier="hot",
            cost_saved_usd=cost_usd
        )
        
        self.hot_cache[query_hash] = entry
        
        logger.info(
            "Resultado cacheado en hot cache",
            action="cache_set_hot",
            query_hash=query_hash,
            cost_saved_per_hit_usd=cost_usd
        )
    
    def _check_semantic_cache(self, query: str, case_id: str) -> Optional[Dict]:
        """Busca query similar en caché (semantic search)."""
        # Generar embedding de la query
        query_embedding = generate_query_embedding(query)
        
        # Buscar en hot cache
        for entry in self.hot_cache.values():
            if entry.query_embedding is None:
                continue
            
            similarity = cosine_similarity(query_embedding, entry.query_embedding)
            if similarity >= self.SEMANTIC_SIMILARITY_THRESHOLD:
                return {
                    "response": entry.response,
                    "original_query": entry.query,
                    "similarity": similarity,
                    "cost_saved_usd": entry.cost_saved_usd
                }
        
        # Buscar en cold cache (sample)
        # (implementación similar)
        
        return None
    
    def _hash_query(self, query: str, case_id: str) -> str:
        """Genera hash único para query + case_id."""
        return hashlib.sha256(f"{case_id}:{query}".encode()).hexdigest()[:16]
    
    def _is_hot_valid(self, entry: CacheEntry) -> bool:
        """Verifica si entrada hot está vigente."""
        age = (datetime.utcnow() - entry.cached_at).total_seconds()
        return age < self.HOT_TTL_SECONDS
    
    def _is_cold_valid(self, entry: CacheEntry) -> bool:
        """Verifica si entrada cold está vigente."""
        age = (datetime.utcnow() - entry.cached_at).total_seconds()
        return age < self.COLD_TTL_SECONDS
    
    def _move_to_cold(self, entry: CacheEntry):
        """Mueve entrada de hot a cold cache."""
        entry.tier = "cold"
        cold_file = self.cold_cache_dir / f"{entry.query_hash}.json"
        
        with open(cold_file, "w") as f:
            json.dump(asdict(entry), f, default=str)
    
    def _load_from_cold(self, query_hash: str) -> Optional[CacheEntry]:
        """Carga entrada desde cold cache."""
        cold_file = self.cold_cache_dir / f"{query_hash}.json"
        
        if not cold_file.exists():
            return None
        
        with open(cold_file) as f:
            data = json.load(f)
        
        return CacheEntry(**data)
    
    def get_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas de caché."""
        total_requests = sum([
            self.stats["hot_hits"],
            self.stats["cold_hits"],
            self.stats["semantic_hits"],
            self.stats["misses"]
        ])
        
        hit_rate = (
            (self.stats["hot_hits"] + self.stats["cold_hits"] + self.stats["semantic_hits"]) /
            total_requests
        ) if total_requests > 0 else 0.0
        
        return {
            "hot_hits": self.stats["hot_hits"],
            "cold_hits": self.stats["cold_hits"],
            "semantic_hits": self.stats["semantic_hits"],
            "misses": self.stats["misses"],
            "total_requests": total_requests,
            "hit_rate": hit_rate,
            "total_cost_saved_usd": self.stats["total_cost_saved_usd"]
        }
```

### Integración en Pipeline

**Archivo**: `app/rag/case_rag/retrieve.py`

**Modificar**:
```python
from app.rag.finops_cache import FinOpsCache

# Instancia global de caché
_finops_cache = FinOpsCache()

def query_case_rag(
    case_id: str,
    query: str,
    top_k: int = 5
) -> Dict[str, Any]:
    # 1. Check caché (hot → cold → semantic)
    cached_result = _finops_cache.get(query, case_id)
    if cached_result:
        return cached_result
    
    # 2. Cache MISS → Ejecutar RAG
    # Generar embedding de query (coste)
    query_embedding = generate_query_embedding(query)
    cost_embedding = calculate_embedding_cost(query)
    
    # Recuperar chunks (coste de ChromaDB, mínimo)
    chunks = retrieve_chunks(case_id, query_embedding, top_k)
    cost_retrieval = 0.0  # ChromaDB local, sin coste
    
    # Validar evidencia
    evidence_result = validate_evidence(chunks, query)
    if not evidence_result.is_response_allowed:
        # NO cachear respuestas rechazadas
        return {
            "response": None,
            "evidence_status": evidence_result.status.value,
            "failure_reason": evidence_result.failure_reason
        }
    
    # Construir respuesta
    response = build_response(chunks, query)
    
    # 3. Guardar en caché
    total_cost = cost_embedding + cost_retrieval
    _finops_cache.set(
        query=query,
        case_id=case_id,
        response=response,
        chunks=[chunk.dict() for chunk in chunks],
        query_embedding=query_embedding,
        cost_usd=total_cost
    )
    
    return response

def get_cache_stats() -> Dict[str, Any]:
    """Obtiene estadísticas de caché."""
    return _finops_cache.get_stats()
```

### Fail Conditions

**El sistema DEBE fallar si**:
1. Caché corrompe datos (hash no coincide)
2. Semantic cache retorna resultado de otro caso
3. TTL negativo o infinito

**Acción**: Invalidar entrada, log de warning.

### Garantía Legal

**Con este endurecimiento**:
1. ✅ Control de costes operativo por caso
2. ✅ Métricas de hit rate y costes evitados
3. ✅ Semantic cache reduce costes sin pérdida de calidad
4. ✅ Hot/cold strategy optimiza memoria y latencia
5. ✅ Stats auditables de costes por caso
6. ✅ Defensa contra "sistema es caro de operar" → Métricas de ahorro

---

## RESUMEN DE IMPLEMENTACIÓN

### Orden de Implementación Recomendado

1. **ENDURECIMIENTO 3**: Chunks con offsets (prerequisito para 4 y 5)
2. **ENDURECIMIENTO 2**: Validación de ingesta (prerequisito para 1)
3. **ENDURECIMIENTO 1**: Manifest extendido (prerequisito para trazabilidad)
4. **ENDURECIMIENTO 4**: RAG con evidencia obligatoria (bloquea alucinaciones)
5. **ENDURECIMIENTO 5**: Template formal (mejora presentabilidad)
6. **ENDURECIMIENTO 6**: Tracing + replay (debugging y auditoría)
7. **ENDURECIMIENTO 7**: FinOps (optimización de costes)

### Tiempo Estimado por Endurecimiento

| Endurecimiento | Complejidad | Tiempo Estimado |
|----------------|-------------|-----------------|
| 1. Manifest extendido | MEDIA | 2-3 días |
| 2. Validación ingesta | BAJA | 1-2 días |
| 3. Chunks con offsets | ALTA | 3-4 días |
| 4. RAG con evidencia | MEDIA | 2-3 días |
| 5. Template formal | MEDIA | 2-3 días |
| 6. Tracing + replay | ALTA | 4-5 días |
| 7. FinOps cache | MEDIA | 2-3 días |

**Total estimado**: 16-23 días de desarrollo + 3-5 días de testing

### Tests Críticos por Endurecimiento

1. **Manifest**: `test_manifest_extended_generation`, `test_quality_metrics_validation`
2. **Validación**: `test_reject_corrupted_pdf`, `test_reject_empty_document`
3. **Offsets**: `test_chunk_location_verification`, `test_citation_reproducibility`
4. **RAG evidencia**: `test_rag_rejects_without_chunks`, `test_evidence_threshold`
5. **Template**: `test_formal_report_structure`, `test_citations_in_report`
6. **Tracing**: `test_trace_save_and_replay`, `test_trace_comparison`
7. **FinOps**: `test_hot_cold_cache_promotion`, `test_semantic_cache_hit`

### Criterio de Éxito

Phoenix Legal pasa de "sistema convincente" a "sistema presentable como prueba técnica" si:

1. ✅ Cada chunk es localizable en documento original (página + offset)
2. ✅ Cada cita es verificable manualmente por perito
3. ✅ Sistema NO responde sin evidencia documental suficiente
4. ✅ Cada versión del vectorstore tiene certificación de calidad
5. ✅ Informes siguen formato legal estándar reconocible
6. ✅ Cada ejecución tiene trace completo reproducible
7. ✅ Costes operativos son medibles y controlables

---

**FIN DEL PLAN DE HARDENING LEGAL**


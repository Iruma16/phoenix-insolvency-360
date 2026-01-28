"""
Variables de configuración del sistema (LEGACY).

⚠️ DEPRECADO: Este módulo se mantiene por compatibilidad.
   Nuevos desarrollos deben usar app.core.config.Settings

Migración en progreso hacia app.core.config.
"""
from pathlib import Path
from app.core.config import settings

# =========================================================
# RUTAS Y DIRECTORIOS
# =========================================================

# Ruta raíz donde se guardan los archivos de los clientes
DATA = settings.data_dir

# Vectorstores para casos (embeddings) — NO es evidencia legal, es derivado y regenerable
# Estructura: clients_data/cases/<case_id>/vectorstore/
CASES_VECTORSTORE_BASE = DATA / "cases"

# Vectorstores para contenido legal (ley concursal y jurisprudencia)
# Estructura: clients_data/_vectorstore/legal/<tipo>/
LEGAL_VECTORSTORE_BASE = settings.vectorstore_dir / "legal"
LEGAL_LEY_VECTORSTORE = LEGAL_VECTORSTORE_BASE / "ley_concursal"
LEGAL_JURISPRUDENCIA_VECTORSTORE = LEGAL_VECTORSTORE_BASE / "jurisprudencia"

# =========================================================
# CONFIG EMBEDDINGS
# =========================================================
EMBEDDING_MODEL = settings.embedding_model
EMBEDDING_BATCH_SIZE = settings.embedding_batch_size

# =========================================================
# RAG / LLM
# =========================================================
RAG_LLM_MODEL = settings.primary_model
RAG_TEMPERATURE = 0.0
RAG_TOP_K_DEFAULT = settings.rag_top_k
RAG_AUTO_BUILD_EMBEDDINGS = settings.rag_auto_build_embeddings

# Score mínimo de similitud (distancia máxima permitida)
# ChromaDB usa distancia L2: menor = más similar
# Valores típicos: 0.5-1.0 (muy estricto), 1.0-1.5 (moderado), 1.5+ (permitivo)
RAG_MIN_SIMILARITY_SCORE = settings.rag_min_similarity_score

# Umbrales para determinar si la respuesta es débil
RAG_WEAK_RESPONSE_MAX_DISTANCE = settings.rag_weak_response_max_distance
RAG_HALLUCINATION_RISK_THRESHOLD = settings.rag_hallucination_risk_threshold

# =========================================================
# CALIDAD DOCUMENTAL Y RIESGO LEGAL
# =========================================================
# Umbrales de calidad para bloqueo de conclusiones automáticas
LEGAL_QUALITY_SCORE_BLOCK_THRESHOLD = settings.legal_quality_score_block_threshold
LEGAL_QUALITY_SCORE_WARNING_THRESHOLD = settings.legal_quality_score_warning_threshold

# Documentos críticos desde perspectiva legal (requieren embeddings)
CRITICAL_DOCUMENT_TYPES = {
    "contrato",
    "acta",
    "acuerdo_societario",
    "poder",
    "balance",
    "pyg",
    "extracto_bancario",
}

# =========================================================
# ENDURECIMIENTO OPERACIONAL RAG (EVIDENCIA OBLIGATORIA)
# =========================================================
# REGLA 4: Umbral mínimo de contexto
RAG_MIN_CHUNKS_REQUIRED = 1  # Mínimo de chunks con buena similitud para responder

# REGLA 6: Decisión trazable (habilitar logging detallado)
RAG_TRACE_DECISIONS = True  # Mostrar decisiones por stdout

# =========================================================
# CAPA DE PRODUCTO RAG (SCORING + POLÍTICAS + PHRASING)
# =========================================================
# REGLA 2: Política activa de no respuesta
RAG_ACTIVE_POLICY = "estandar"  # "conservadora" | "estandar" | "exploratoria"

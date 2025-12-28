"""
Service layer para consultar el RAG legal (Ley Concursal y Jurisprudencia).

Proporciona acceso simplificado al corpus legal para uso en agentes.
"""
from __future__ import annotations

from typing import List, Dict, Any, Optional, Literal
from pathlib import Path
from functools import lru_cache
import hashlib
import json

import chromadb
from openai import OpenAI
import os
from dotenv import load_dotenv

from app.core.variables import (
    LEGAL_LEY_VECTORSTORE,
    LEGAL_JURISPRUDENCIA_VECTORSTORE,
    EMBEDDING_MODEL,
    RAG_TOP_K_DEFAULT,
)

load_dotenv()


# =========================================================
# CLIENTE OPENAI REUTILIZABLE
# =========================================================

_openai_client: Optional[OpenAI] = None


def _get_openai_client() -> OpenAI:
    """Obtiene o crea el cliente OpenAI reutilizable."""
    global _openai_client
    if _openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY no definida en entorno")
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client


# =========================================================
# CACHÉ DE CONSULTAS LEGALES
# =========================================================

_legal_cache: Dict[str, List[Dict[str, Any]]] = {}


def _get_cache_key(query: str, include_ley: bool, include_jurisprudencia: bool) -> str:
    """Genera una clave única para el caché basada en los parámetros de consulta."""
    key_data = f"{query}::{include_ley}::{include_jurisprudencia}"
    return hashlib.md5(key_data.encode()).hexdigest()


def _get_cached_result(cache_key: str) -> Optional[List[Dict[str, Any]]]:
    """Obtiene un resultado del caché si existe."""
    return _legal_cache.get(cache_key)


def _cache_result(cache_key: str, result: List[Dict[str, Any]]) -> None:
    """Almacena un resultado en el caché."""
    _legal_cache[cache_key] = result


# =========================================================
# INTERPRETACIÓN DE SCORES
# =========================================================

RelevanceLevel = Literal["alta", "media", "baja"]


def _distance_to_relevance(distance: float) -> RelevanceLevel:
    """
    Convierte distancia de ChromaDB a nivel de relevancia semántica.
    
    ChromaDB usa distancia L2 (euclidiana):
    - Menor distancia = mayor similitud
    - Valores típicos: 0.0-0.5 (muy similar), 0.5-1.0 (similar), 1.0-1.5 (moderado), 1.5+ (diferente)
    
    Returns:
        "alta": distance < 0.8 (muy relevante)
        "media": 0.8 <= distance < 1.3 (relevante)
        "baja": distance >= 1.3 (poco relevante)
    """
    if distance < 0.8:
        return "alta"
    elif distance < 1.3:
        return "media"
    else:
        return "baja"


# =========================================================
# TIPOS Y NORMALIZACIÓN
# =========================================================

AuthorityLevel = Literal["norma", "jurisprudencia"]


class LegalResult:
    """Resultado legal normalizado para uso en agentes."""
    
    def __init__(
        self,
        citation: str,
        text: str,
        source: Literal["ley", "jurisprudencia"],
        authority_level: AuthorityLevel,
        relevance: RelevanceLevel,
        article: Optional[str] = None,
        law: Optional[str] = None,
        court: Optional[str] = None,
        date: Optional[str] = None,
        raw_score: Optional[float] = None,
    ):
        self.citation = citation
        self.text = text
        self.source = source
        self.authority_level = authority_level
        self.relevance = relevance
        self.article = article
        self.law = law
        self.court = court
        self.date = date
        self.raw_score = raw_score
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte el resultado a diccionario para serialización."""
        return {
            "citation": self.citation,
            "text": self.text,
            "source": self.source,
            "authority_level": self.authority_level,
            "relevance": self.relevance,
            "article": self.article,
            "law": self.law,
            "court": self.court,
            "date": self.date,
        }


def _normalize_legal_result(
    raw_result: Dict[str, Any],
    source: Literal["ley", "jurisprudencia"],
) -> LegalResult:
    """
    Normaliza un resultado raw del vectorstore en formato legal claro.
    
    Args:
        raw_result: Diccionario con datos del vectorstore (content, metadata, score)
        source: "ley" o "jurisprudencia"
    """
    content = raw_result.get("content", "")
    metadata = raw_result.get("metadata", {})
    score = raw_result.get("score", 0.0)
    
    # Determinar authority_level
    authority_level: AuthorityLevel = "norma" if source == "ley" else "jurisprudencia"
    
    # Calcular relevancia
    relevance = _distance_to_relevance(score)
    
    # Construir citation
    citation = ""
    if source == "ley":
        article = metadata.get("article")
        law = metadata.get("law", "Ley Concursal")
        if article:
            citation = f"Art. {article} {law}"
        else:
            citation = law
    else:  # jurisprudencia
        court = metadata.get("court", "Tribunal")
        date = metadata.get("date", "")
        if date:
            citation = f"{court} {date}"
        else:
            citation = court
    
    return LegalResult(
        citation=citation,
        text=content,
        source=source,
        authority_level=authority_level,
        relevance=relevance,
        article=metadata.get("article"),
        law=metadata.get("law"),
        court=metadata.get("court"),
        date=metadata.get("date"),
        raw_score=score,
    )


# =========================================================
# EXPLICACIÓN LEGAL HUMANA
# =========================================================

def _build_legal_summary(results: List[LegalResult]) -> Optional[str]:
    """
    Construye una explicación legal humana a partir de los resultados.
    
    Returns:
        String con explicación legal clara o None si no hay resultados relevantes.
    """
    if not results:
        return None
    
    # Filtrar solo resultados con relevancia alta o media
    relevant_results = [r for r in results if r.relevance in ("alta", "media")]
    if not relevant_results:
        return None
    
    # Separar normas y jurisprudencia
    normas = [r for r in relevant_results if r.authority_level == "norma"]
    jurisprudencia = [r for r in relevant_results if r.authority_level == "jurisprudencia"]
    
    parts = []
    
    if normas:
        citations = [n.citation for n in normas[:3]]  # Máximo 3
        if len(citations) == 1:
            parts.append(f"Este riesgo se fundamenta principalmente en {citations[0]}")
        else:
            parts.append(f"Este riesgo se fundamenta principalmente en {', '.join(citations[:-1])} y {citations[-1]}")
    
    if jurisprudencia:
        citations = [j.citation for j in jurisprudencia[:2]]  # Máximo 2
        if normas:
            parts.append(f"y ha sido confirmado por jurisprudencia reciente ({', '.join(citations)})")
        else:
            parts.append(f"Jurisprudencia reciente ({', '.join(citations)}) ha establecido criterios relevantes")
    
    if parts:
        return ". ".join(parts) + "."
    
    return None


# =========================================================
# FUNCIÓN PRINCIPAL
# =========================================================

def query_legal_rag(
    query: str,
    top_k: int = RAG_TOP_K_DEFAULT,
    include_ley: bool = True,
    include_jurisprudencia: bool = True,
) -> List[Dict[str, Any]]:
    """
    Consulta el RAG legal y devuelve resultados relevantes de ley y/o jurisprudencia.
    
    Args:
        query: Consulta o pregunta sobre fundamento legal
        top_k: Número máximo de resultados a devolver por fuente
        include_ley: Si True, incluye resultados de Ley Concursal
        include_jurisprudencia: Si True, incluye resultados de Jurisprudencia
    
    Returns:
        Lista de diccionarios con resultados normalizados. Cada diccionario contiene:
        - citation: Cita legal clara (ej: "Art. 165 LC", "TS 15/01/2023")
        - text: Texto del fragmento relevante
        - source: "ley" o "jurisprudencia"
        - authority_level: "norma" o "jurisprudencia"
        - relevance: "alta", "media" o "baja"
        - article: Número de artículo (si es ley)
        - law: Nombre de la ley
        - court: Órgano jurisdiccional (si es jurisprudencia)
        - date: Fecha relevante
    """
    # Verificar caché
    cache_key = _get_cache_key(query, include_ley, include_jurisprudencia)
    cached = _get_cached_result(cache_key)
    if cached is not None:
        return cached
    
    # Generar embedding
    openai_client = _get_openai_client()
    response = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=query,
    )
    query_embedding = response.data[0].embedding
    
    # Recopilar resultados raw
    raw_results: List[Dict[str, Any]] = []
    
    # Consultar Ley Concursal
    if include_ley:
        try:
            collection = _get_legal_collection(LEGAL_LEY_VECTORSTORE, "chunks")
            
            if collection.count() > 0:
                db_results = collection.query(
                    query_embeddings=[query_embedding],
                    n_results=top_k,
                    include=["documents", "metadatas", "distances"],
                )
                
                if db_results["ids"] and len(db_results["ids"][0]) > 0:
                    for doc_id, doc_text, metadata, distance in zip(
                        db_results["ids"][0],
                        db_results["documents"][0],
                        db_results["metadatas"][0],
                        db_results["distances"][0],
                    ):
                        raw_results.append({
                            "content": doc_text,
                            "metadata": metadata,
                            "score": float(distance),
                            "source": "ley",
                        })
        except Exception:
            # Si falla la consulta, continuar sin ley (no es crítico)
            pass
    
    # Consultar Jurisprudencia
    if include_jurisprudencia:
        try:
            collection = _get_legal_collection(LEGAL_JURISPRUDENCIA_VECTORSTORE, "chunks")
            
            if collection.count() > 0:
                db_results = collection.query(
                    query_embeddings=[query_embedding],
                    n_results=top_k,
                    include=["documents", "metadatas", "distances"],
                )
                
                if db_results["ids"] and len(db_results["ids"][0]) > 0:
                    for doc_id, doc_text, metadata, distance in zip(
                        db_results["ids"][0],
                        db_results["documents"][0],
                        db_results["metadatas"][0],
                        db_results["distances"][0],
                    ):
                        raw_results.append({
                            "content": doc_text,
                            "metadata": metadata,
                            "score": float(distance),
                            "source": "jurisprudencia",
                        })
        except Exception:
            # Si falla la consulta, continuar sin jurisprudencia (no es crítico)
            pass
    
    # Normalizar resultados
    normalized_results: List[LegalResult] = []
    for raw in raw_results:
        source = raw["source"]
        normalized = _normalize_legal_result(raw, source)
        normalized_results.append(normalized)
    
    # Ordenar por relevancia (alta > media > baja) y luego por score
    normalized_results.sort(key=lambda r: (
        {"alta": 0, "media": 1, "baja": 2}[r.relevance],
        r.raw_score or float('inf')
    ))
    
    # Construir resultado final
    result_dicts = [r.to_dict() for r in normalized_results]
    
    # Construir explicación legal si hay resultados relevantes
    legal_summary = _build_legal_summary(normalized_results)
    if legal_summary and result_dicts:
        # Añadir el summary solo al primer resultado para evitar duplicación
        result_dicts[0]["legal_summary"] = legal_summary
    
    # Almacenar en caché
    _cache_result(cache_key, result_dicts)
    
    return result_dicts


def _get_legal_collection(vectorstore_path: Path, collection_name: str = "chunks"):
    """Obtiene o crea una colección de ChromaDB para contenido legal."""
    # Crear el directorio si no existe
    vectorstore_path.mkdir(parents=True, exist_ok=True)
    
    client = chromadb.PersistentClient(path=str(vectorstore_path))
    
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"type": "legal"},
    )
    
    return collection

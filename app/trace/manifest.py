"""
MANIFEST HARD (FASE 6 - ENDURECIMIENTO 6).

PRINCIPIO: El manifest actúa como CERTIFICADO TÉCNICO del sistema.

Certifica:
- Integridad del trace
- Coherencia de versiones de schema
- Límites explícitos del sistema
- Snapshot de FinOps (si existe)

El manifest es el artefacto final de auditoría.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

from app.trace.models import ExecutionTrace, TRACE_SCHEMA_VERSION


MANIFEST_VERSION = "1.0.0"


class SchemaVersions(BaseModel):
    """
    Versiones de schemas utilizados en la ejecución.
    
    Permite verificar compatibilidad en auditoría.
    """
    chunk_schema: str = Field(..., description="Versión del schema de DocumentChunk")
    rag_schema: str = Field(..., description="Versión del schema de RAG")
    legal_output_schema: str = Field(..., description="Versión del schema de LegalReport")
    trace_schema: str = Field(..., description="Versión del schema de Trace")
    
    model_config = {"extra": "forbid"}


class ExecutionLimits(BaseModel):
    """
    Límites explícitos del sistema.
    
    Declara QUÉ NO HACE el sistema para evitar expectativas incorrectas.
    """
    cannot_process_without_documents: bool = Field(
        default=True,
        description="El sistema NO puede responder sin documentos"
    )
    cannot_generate_without_evidence: bool = Field(
        default=True,
        description="El sistema NO puede generar respuestas sin evidencia"
    )
    cannot_guarantee_legal_validity: bool = Field(
        default=True,
        description="El sistema NO garantiza validez legal (solo técnica)"
    )
    requires_human_review: bool = Field(
        default=True,
        description="El sistema REQUIERE revisión humana antes de uso legal"
    )
    
    model_config = {"extra": "forbid"}


class FinOpsSnapshot(BaseModel):
    """
    Snapshot de costes de la ejecución (si FinOps está activado).
    """
    total_cost_usd: Optional[float] = Field(None, description="Coste total en USD")
    llm_calls: int = Field(0, description="Número de llamadas LLM")
    embedding_calls: int = Field(0, description="Número de llamadas embedding")
    tokens_used: int = Field(0, description="Tokens totales consumidos")
    
    model_config = {"extra": "forbid"}


class HardManifest(BaseModel):
    """
    Manifest HARD: certificado técnico de una ejecución.
    
    CONTRATO DURO:
    - Debe incluir integrity_hash del trace
    - Debe declarar schema_versions
    - Debe explicitar execution_limits
    - Es INMUTABLE después de creado
    
    El manifest permite:
    - Auditoría técnica completa
    - Verificación de integridad
    - Certificación de límites
    - Trazabilidad de costes
    """
    manifest_version: str = Field(
        default=MANIFEST_VERSION,
        description="Versión del manifest"
    )
    
    trace_id: str = Field(
        ...,
        description="ID del trace asociado",
        min_length=1
    )
    
    case_id: str = Field(
        ...,
        description="ID del caso analizado",
        min_length=1
    )
    
    schema_versions: SchemaVersions = Field(
        ...,
        description="Versiones de schemas utilizados"
    )
    
    integrity_hash: str = Field(
        ...,
        description="Hash SHA256 del trace completo",
        min_length=64,
        max_length=64
    )
    
    execution_limits: ExecutionLimits = Field(
        default_factory=ExecutionLimits,
        description="Límites explícitos del sistema"
    )
    
    finops_snapshot: Optional[FinOpsSnapshot] = Field(
        None,
        description="Snapshot de costes (si FinOps activo)"
    )
    
    signed_at: datetime = Field(
        ...,
        description="Timestamp de firma del manifest"
    )
    
    system_version: str = Field(
        ...,
        description="Versión del sistema que generó el manifest"
    )
    
    model_config = {"extra": "forbid", "frozen": True}  # INMUTABLE
    
    def verify_integrity(self, trace: ExecutionTrace) -> bool:
        """
        Verifica que el hash de integridad coincide con el trace.
        
        Args:
            trace: ExecutionTrace a verificar
            
        Returns:
            True si la integridad es válida, False si no coincide
        """
        computed_hash = trace.compute_integrity_hash()
        return computed_hash == self.integrity_hash
    
    def to_certificate_dict(self) -> Dict[str, Any]:
        """
        Serializa el manifest como certificado técnico.
        
        Returns:
            Dict con estructura de certificado
        """
        return {
            "certificate_type": "phoenix_legal_execution_manifest",
            "manifest_version": self.manifest_version,
            "trace_id": self.trace_id,
            "case_id": self.case_id,
            "integrity_hash": self.integrity_hash,
            "signed_at": self.signed_at.isoformat(),
            "system_version": self.system_version,
            "schemas": {
                "chunk": self.schema_versions.chunk_schema,
                "rag": self.schema_versions.rag_schema,
                "legal_output": self.schema_versions.legal_output_schema,
                "trace": self.schema_versions.trace_schema,
            },
            "limits": {
                "cannot_process_without_documents": self.execution_limits.cannot_process_without_documents,
                "cannot_generate_without_evidence": self.execution_limits.cannot_generate_without_evidence,
                "cannot_guarantee_legal_validity": self.execution_limits.cannot_guarantee_legal_validity,
                "requires_human_review": self.execution_limits.requires_human_review,
            },
            "finops": self.finops_snapshot.dict() if self.finops_snapshot else None,
        }


def create_manifest(
    trace: ExecutionTrace,
    system_version: str,
    chunk_schema_version: str = "1.0.0",
    rag_schema_version: str = "1.0.0",
    legal_output_schema_version: str = "1.0.0",
    finops_snapshot: Optional[FinOpsSnapshot] = None,
) -> HardManifest:
    """
    Crea un HardManifest para un trace dado.
    
    Args:
        trace: ExecutionTrace a certificar
        system_version: Versión del sistema
        chunk_schema_version: Versión del schema de chunk
        rag_schema_version: Versión del schema de RAG
        legal_output_schema_version: Versión del schema de legal output
        finops_snapshot: Snapshot de costes (opcional)
        
    Returns:
        HardManifest certificado e inmutable
        
    Raises:
        ValueError: Si trace es inválido
    """
    # Calcular hash de integridad
    integrity_hash = trace.compute_integrity_hash()
    
    # Construir schema versions
    schema_versions = SchemaVersions(
        chunk_schema=chunk_schema_version,
        rag_schema=rag_schema_version,
        legal_output_schema=legal_output_schema_version,
        trace_schema=TRACE_SCHEMA_VERSION,
    )
    
    # Construir manifest
    manifest = HardManifest(
        trace_id=trace.trace_id,
        case_id=trace.case_id,
        schema_versions=schema_versions,
        integrity_hash=integrity_hash,
        finops_snapshot=finops_snapshot,
        signed_at=datetime.utcnow(),
        system_version=system_version,
    )
    
    return manifest


def verify_manifest(manifest: HardManifest, trace: ExecutionTrace) -> bool:
    """
    Verifica que un manifest es válido para un trace.
    
    Args:
        manifest: HardManifest a verificar
        trace: ExecutionTrace asociado
        
    Returns:
        True si el manifest es válido, False si no
    """
    # Verificar trace_id coincide
    if manifest.trace_id != trace.trace_id:
        return False
    
    # Verificar case_id coincide
    if manifest.case_id != trace.case_id:
        return False
    
    # Verificar integridad
    if not manifest.verify_integrity(trace):
        return False
    
    return True


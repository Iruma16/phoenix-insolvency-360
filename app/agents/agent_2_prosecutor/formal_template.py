"""
PLANTILLA FORMAL DE ACUSACIÓN LEGAL

Gap Actual: Outputs son texto libre sin estructura.
Solución: Template con secciones obligatorias:
  I. ANTECEDENTES (documentos + hashes)
  II. HECHOS PROBADOS (numerados con fuentes verificables)
  III. RIESGOS DETECTADOS (con base legal TRLC)

PRINCIPIO: Toda acusación formal debe seguir estructura judicial estándar.
"""
from __future__ import annotations

from typing import List, Dict
from datetime import datetime
from pydantic import BaseModel, Field
import hashlib


# ============================
# I. ANTECEDENTES
# ============================

class DocumentoAntecedente(BaseModel):
    """Documento con hash SHA256 para trazabilidad forense."""
    
    doc_id: str = Field(..., description="ID único del documento")
    nombre_documento: str = Field(..., description="Nombre descriptivo del documento")
    fecha_documento: str | None = Field(None, description="Fecha del documento (si consta)")
    hash_sha256: str = Field(..., description="Hash SHA256 del contenido del documento")
    paginas_relevantes: List[int] = Field(
        default_factory=list,
        description="Páginas específicas citadas en la acusación"
    )
    descripcion: str = Field(..., description="Breve descripción del contenido relevante")


class SeccionAntecedentes(BaseModel):
    """
    SECCIÓN I: ANTECEDENTES
    
    Enumera TODOS los documentos analizados con hashes verificables.
    """
    fecha_generacion: datetime = Field(
        default_factory=datetime.now,
        description="Fecha y hora de generación del informe"
    )
    
    case_id: str = Field(..., description="Identificador único del caso")
    
    documentos: List[DocumentoAntecedente] = Field(
        ...,
        min_items=1,
        description="Lista completa de documentos analizados (mínimo 1)"
    )
    
    total_documentos: int = Field(..., description="Número total de documentos")
    total_paginas_analizadas: int = Field(..., description="Total de páginas analizadas")
    
    observaciones_preliminares: str | None = Field(
        None,
        description="Observaciones sobre la completitud documental"
    )


# ============================
# II. HECHOS PROBADOS
# ============================

class FuenteVerificable(BaseModel):
    """Fuente documental específica que respalda un hecho probado."""
    
    doc_id: str = Field(..., description="ID del documento fuente")
    chunk_id: str = Field(..., description="Chunk ID específico")
    pagina: int | None = Field(None, description="Número de página")
    extracto_literal: str = Field(
        ...,
        max_length=500,
        description="Extracto LITERAL del documento (máx. 500 caracteres)"
    )
    ubicacion_exacta: str = Field(
        ...,
        description="Ubicación exacta en formato 'chars X-Y' o 'página N'"
    )


class HechoProbado(BaseModel):
    """
    Hecho probado enumerado con fuentes verificables.
    
    REQUISITO: Todo hecho debe tener AL MENOS una fuente documental.
    """
    numero: int = Field(..., description="Número secuencial del hecho (1, 2, 3...)")
    
    descripcion_factica: str = Field(
        ...,
        description="Descripción OBJETIVA del hecho (sin adjetivos ni valoraciones)"
    )
    
    fuentes: List[FuenteVerificable] = Field(
        ...,
        min_items=1,
        description="Fuentes documentales que prueban el hecho (mínimo 1)"
    )
    
    fecha_hecho: str | None = Field(
        None,
        description="Fecha en que ocurrió el hecho (si es determinable)"
    )
    
    nivel_certeza: str = Field(
        ...,
        description="Nivel de certeza: 'PROBADO' | 'ALTAMENTE_PROBABLE' | 'INDICIARIO'"
    )


class SeccionHechosProbados(BaseModel):
    """
    SECCIÓN II: HECHOS PROBADOS
    
    Enumeración estructurada de hechos con fuentes verificables.
    """
    hechos: List[HechoProbado] = Field(
        ...,
        min_items=1,
        description="Lista numerada de hechos probados (mínimo 1)"
    )
    
    total_hechos: int = Field(..., description="Número total de hechos probados")
    
    resumen_cronologico: str | None = Field(
        None,
        description="Breve resumen cronológico de los hechos (opcional)"
    )


# ============================
# III. RIESGOS DETECTADOS
# ============================

class BaseLegalTRLC(BaseModel):
    """Base legal específica del TRLC (Texto Refundido de la Ley Concursal)."""
    
    articulo: str = Field(..., description="Artículo del TRLC (ej: 'Art. 164.2.3')")
    texto_articulo: str = Field(..., description="Texto literal del artículo")
    tipo_infraccion: str = Field(
        ...,
        description="Tipo: 'CULPABILIDAD' | 'RESPONSABILIDAD' | 'SANCION_ADMINISTRATIVA'"
    )


class RiesgoDetectado(BaseModel):
    """
    Riesgo legal detectado con base legal TRLC.
    
    REQUISITO: Todo riesgo debe estar fundamentado en artículo concreto del TRLC.
    """
    numero: int = Field(..., description="Número secuencial del riesgo")
    
    titulo_riesgo: str = Field(
        ...,
        max_length=100,
        description="Título descriptivo del riesgo (máx. 100 caracteres)"
    )
    
    descripcion_riesgo: str = Field(
        ...,
        description="Descripción detallada del riesgo legal"
    )
    
    severidad: str = Field(
        ...,
        description="Severidad: 'BAJA' | 'MEDIA' | 'ALTA' | 'CRITICA'"
    )
    
    base_legal: BaseLegalTRLC = Field(
        ...,
        description="Fundamentación en artículo específico del TRLC"
    )
    
    hechos_relacionados: List[int] = Field(
        ...,
        min_items=1,
        description="Números de hechos probados que sustentan este riesgo"
    )
    
    consecuencias_juridicas: str = Field(
        ...,
        description="Consecuencias jurídicas potenciales"
    )
    
    nivel_confianza: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Nivel de confianza en la evaluación (0.0-1.0)"
    )


class SeccionRiesgosDetectados(BaseModel):
    """
    SECCIÓN III: RIESGOS DETECTADOS
    
    Análisis legal con base en TRLC.
    """
    riesgos: List[RiesgoDetectado] = Field(
        ...,
        min_items=1,
        description="Lista de riesgos detectados (mínimo 1)"
    )
    
    total_riesgos: int = Field(..., description="Número total de riesgos")
    
    distribucion_severidad: Dict[str, int] = Field(
        ...,
        description="Distribución de riesgos por severidad (BAJA, MEDIA, ALTA, CRITICA)"
    )
    
    calificacion_concursal_sugerida: str = Field(
        ...,
        description="Calificación sugerida: 'FORTUITO' | 'CULPABLE_SIMPLE' | 'CULPABLE_AGRAVADO'"
    )
    
    fundamento_calificacion: str = Field(
        ...,
        description="Fundamentación de la calificación sugerida"
    )


# ============================
# PLANTILLA COMPLETA
# ============================

class PlantillaFormalAcusacion(BaseModel):
    """
    PLANTILLA FORMAL DE ACUSACIÓN LEGAL
    
    Estructura obligatoria con 3 secciones:
    - I. ANTECEDENTES
    - II. HECHOS PROBADOS
    - III. RIESGOS DETECTADOS
    
    PROHIBIDO: Saltar secciones, usar texto libre sin estructura.
    """
    
    # METADATA
    version_plantilla: str = Field(
        default="1.0.0",
        description="Versión de la plantilla formal"
    )
    
    generado_por: str = Field(
        default="Phoenix Insolvency 360 - Prosecutor Agent",
        description="Sistema que generó el documento"
    )
    
    # SECCIONES OBLIGATORIAS
    seccion_i_antecedentes: SeccionAntecedentes = Field(
        ...,
        description="SECCIÓN I: ANTECEDENTES (documentos + hashes)"
    )
    
    seccion_ii_hechos_probados: SeccionHechosProbados = Field(
        ...,
        description="SECCIÓN II: HECHOS PROBADOS (numerados con fuentes)"
    )
    
    seccion_iii_riesgos_detectados: SeccionRiesgosDetectados = Field(
        ...,
        description="SECCIÓN III: RIESGOS DETECTADOS (con base legal TRLC)"
    )
    
    # VALIDACIÓN DE INTEGRIDAD
    certificacion_estructural: str = Field(
        default="ESTRUCTURA_VALIDADA",
        description="Certificación de que la estructura es conforme"
    )


# ============================
# UTILIDADES
# ============================

def generar_hash_documento(contenido: str | bytes) -> str:
    """
    Genera hash SHA256 de un documento para trazabilidad forense.
    
    Args:
        contenido: Contenido del documento (str o bytes)
        
    Returns:
        Hash SHA256 en formato hexadecimal
    """
    if isinstance(contenido, str):
        contenido = contenido.encode('utf-8')
    
    return hashlib.sha256(contenido).hexdigest()


def validar_estructura_obligatoria(plantilla: PlantillaFormalAcusacion) -> tuple[bool, List[str]]:
    """
    Valida que la plantilla cumpla TODOS los requisitos estructurales.
    
    Returns:
        (es_valida, lista_de_errores)
    """
    errores = []
    
    # Validar Sección I: ANTECEDENTES
    if not plantilla.seccion_i_antecedentes.documentos:
        errores.append("SECCIÓN I: Falta lista de documentos")
    
    for doc in plantilla.seccion_i_antecedentes.documentos:
        if not doc.hash_sha256 or len(doc.hash_sha256) != 64:
            errores.append(f"SECCIÓN I: Hash inválido para documento {doc.doc_id}")
    
    # Validar Sección II: HECHOS PROBADOS
    if not plantilla.seccion_ii_hechos_probados.hechos:
        errores.append("SECCIÓN II: Falta lista de hechos probados")
    
    for hecho in plantilla.seccion_ii_hechos_probados.hechos:
        if not hecho.fuentes:
            errores.append(f"SECCIÓN II: Hecho #{hecho.numero} sin fuentes verificables")
        
        # Validar que no contiene narrativa especulativa
        palabras_prohibidas = ["parece", "podría", "posiblemente", "probablemente"]
        if any(palabra in hecho.descripcion_factica.lower() for palabra in palabras_prohibidas):
            errores.append(f"SECCIÓN II: Hecho #{hecho.numero} contiene narrativa especulativa")
    
    # Validar Sección III: RIESGOS DETECTADOS
    if not plantilla.seccion_iii_riesgos_detectados.riesgos:
        errores.append("SECCIÓN III: Falta lista de riesgos")
    
    for riesgo in plantilla.seccion_iii_riesgos_detectados.riesgos:
        if not riesgo.base_legal or not riesgo.base_legal.articulo:
            errores.append(f"SECCIÓN III: Riesgo #{riesgo.numero} sin base legal TRLC")
        
        if not riesgo.hechos_relacionados:
            errores.append(f"SECCIÓN III: Riesgo #{riesgo.numero} sin hechos relacionados")
    
    # Validar cross-references
    numeros_hechos = {h.numero for h in plantilla.seccion_ii_hechos_probados.hechos}
    for riesgo in plantilla.seccion_iii_riesgos_detectados.riesgos:
        for num_hecho in riesgo.hechos_relacionados:
            if num_hecho not in numeros_hechos:
                errores.append(
                    f"SECCIÓN III: Riesgo #{riesgo.numero} referencia hecho inexistente #{num_hecho}"
                )
    
    return len(errores) == 0, errores


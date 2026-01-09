"""
GENERADOR DE PLANTILLA FORMAL DE ACUSACIÓN

Convierte ProsecutorResult (estructura interna) a PlantillaFormalAcusacion (estructura judicial).

PRINCIPIO: 
- Trazabilidad 1:1 desde evidencias hasta hechos probados
- Base legal TRLC obligatoria para cada riesgo
- Hashes verificables para cada documento
"""
from __future__ import annotations

from typing import List, Dict, Set
from datetime import datetime
from sqlalchemy.orm import Session

from app.core.database import get_session_factory
from app.models.document import Document

from .schema import ProsecutorResult, AcusacionProbatoria
from .formal_template import (
    PlantillaFormalAcusacion,
    SeccionAntecedentes,
    SeccionHechosProbados,
    SeccionRiesgosDetectados,
    DocumentoAntecedente,
    HechoProbado,
    FuenteVerificable,
    RiesgoDetectado,
    BaseLegalTRLC,
    generar_hash_documento,
    validar_estructura_obligatoria,
)


# ============================
# MAPEO DE SEVERIDAD A CALIFICACIÓN
# ============================

SEVERIDAD_TO_CALIFICACION = {
    "CRITICA": "CULPABLE_AGRAVADO",
    "ALTA": "CULPABLE_SIMPLE",
    "MEDIA": "CULPABLE_SIMPLE",
    "BAJA": "FORTUITO",
}


# ============================
# MAPEO DE GROUNDS A TÍTULOS LEGALES
# ============================

GROUND_TO_TITULO = {
    "retraso_concurso": "Retraso en la Solicitud de Concurso",
    "alzamiento_bienes": "Alzamiento de Bienes o Reducción Patrimonial",
    "pagos_preferentes": "Pagos Preferentes a Acreedores No Privilegiados",
}

GROUND_TO_CONSECUENCIAS = {
    "retraso_concurso": (
        "Calificación del concurso como culpable. "
        "Inhabilitación del administrador (2-15 años). "
        "Responsabilidad patrimonial por daños causados a la masa activa."
    ),
    "alzamiento_bienes": (
        "Calificación del concurso como culpable agravado. "
        "Responsabilidad penal (art. 257-261 CP) por alzamiento de bienes. "
        "Pérdida de derechos de crédito contra la masa. "
        "Inhabilitación para administrar (hasta 15 años)."
    ),
    "pagos_preferentes": (
        "Calificación del concurso como culpable. "
        "Anulación de pagos impugnables. "
        "Responsabilidad por perjuicio a acreedores. "
        "Inhabilitación temporal."
    ),
}


# ============================
# GENERACIÓN SECCIÓN I: ANTECEDENTES
# ============================

def generar_seccion_antecedentes(
    case_id: str,
    acusaciones: List[AcusacionProbatoria],
    db: Session,
) -> SeccionAntecedentes:
    """
    Genera SECCIÓN I: ANTECEDENTES con hashes SHA256.
    
    Extrae todos los documentos únicos citados en las evidencias
    y genera hashes verificables.
    """
    # Extraer doc_ids únicos
    doc_ids_set: Set[str] = set()
    doc_to_pages: Dict[str, Set[int]] = {}
    
    for acusacion in acusaciones:
        for evidencia in acusacion.evidencia_documental:
            doc_ids_set.add(evidencia.doc_id)
            
            if evidencia.page is not None:
                if evidencia.doc_id not in doc_to_pages:
                    doc_to_pages[evidencia.doc_id] = set()
                doc_to_pages[evidencia.doc_id].add(evidencia.page)
    
    # Recuperar documentos de la DB
    documentos_db = db.query(Document).filter(
        Document.case_id == case_id
    ).all()
    
    # Crear mapa doc_id -> Document
    doc_map = {doc.filename: doc for doc in documentos_db}
    
    # Generar lista de DocumentoAntecedente
    documentos_antecedentes = []
    total_paginas = 0
    
    for doc_id in sorted(doc_ids_set):
        doc_db = doc_map.get(doc_id)
        
        # Generar hash
        if doc_db and doc_db.file_path:
            try:
                with open(doc_db.file_path, 'rb') as f:
                    contenido = f.read()
                    hash_sha256 = generar_hash_documento(contenido)
            except Exception:
                # Fallback: hash del filename si no se puede leer el archivo
                hash_sha256 = generar_hash_documento(doc_id)
        else:
            # Fallback: hash del filename
            hash_sha256 = generar_hash_documento(doc_id)
        
        # Páginas relevantes
        paginas = sorted(list(doc_to_pages.get(doc_id, [])))
        total_paginas += len(paginas) if paginas else 1
        
        # Descripción del documento
        if doc_db:
            descripcion = f"Documento tipo: {doc_db.doc_type or 'sin clasificar'}"
        else:
            descripcion = "Documento citado en evidencias"
        
        doc_antecedente = DocumentoAntecedente(
            doc_id=doc_id,
            nombre_documento=doc_id,  # Usar filename como nombre
            fecha_documento=None,  # TODO: extraer fecha si está en metadata
            hash_sha256=hash_sha256,
            paginas_relevantes=paginas,
            descripcion=descripcion,
        )
        
        documentos_antecedentes.append(doc_antecedente)
    
    # Observaciones preliminares
    if not documentos_antecedentes:
        observaciones = "ADVERTENCIA: No se encontraron documentos en las evidencias."
    elif len(documentos_antecedentes) < 3:
        observaciones = (
            f"Se analizaron {len(documentos_antecedentes)} documento(s). "
            "La base documental puede ser insuficiente para conclusiones definitivas."
        )
    else:
        observaciones = (
            f"Base documental completa: {len(documentos_antecedentes)} documentos analizados. "
            f"Total de páginas con evidencias: {total_paginas}."
        )
    
    return SeccionAntecedentes(
        fecha_generacion=datetime.now(),
        case_id=case_id,
        documentos=documentos_antecedentes,
        total_documentos=len(documentos_antecedentes),
        total_paginas_analizadas=total_paginas,
        observaciones_preliminares=observaciones,
    )


# ============================
# GENERACIÓN SECCIÓN II: HECHOS PROBADOS
# ============================

def generar_seccion_hechos_probados(
    acusaciones: List[AcusacionProbatoria],
) -> SeccionHechosProbados:
    """
    Genera SECCIÓN II: HECHOS PROBADOS numerados con fuentes verificables.
    
    Cada acusación se convierte en un hecho probado enumerado.
    """
    hechos_probados = []
    
    for idx, acusacion in enumerate(acusaciones, start=1):
        # Convertir evidencias a fuentes verificables
        fuentes = []
        for evidencia in acusacion.evidencia_documental:
            ubicacion = f"chars {evidencia.start_char}-{evidencia.end_char}"
            if evidencia.page:
                ubicacion = f"página {evidencia.page}, {ubicacion}"
            
            # Truncar extracto si es muy largo
            extracto = evidencia.extracto_literal
            if len(extracto) > 500:
                extracto = extracto[:497] + "..."
            
            fuente = FuenteVerificable(
                doc_id=evidencia.doc_id,
                chunk_id=evidencia.chunk_id,
                pagina=evidencia.page,
                extracto_literal=extracto,
                ubicacion_exacta=ubicacion,
            )
            fuentes.append(fuente)
        
        # Determinar nivel de certeza basado en confianza
        if acusacion.nivel_confianza >= 0.8:
            nivel_certeza = "PROBADO"
        elif acusacion.nivel_confianza >= 0.6:
            nivel_certeza = "ALTAMENTE_PROBABLE"
        else:
            nivel_certeza = "INDICIARIO"
        
        hecho = HechoProbado(
            numero=idx,
            descripcion_factica=acusacion.descripcion_factica,
            fuentes=fuentes,
            fecha_hecho=None,  # TODO: extraer fecha si está en la descripción
            nivel_certeza=nivel_certeza,
        )
        
        hechos_probados.append(hecho)
    
    # Resumen cronológico (simplificado)
    if len(hechos_probados) == 1:
        resumen = "Se identifica un hecho probado relevante para la calificación concursal."
    else:
        resumen = (
            f"Se identifican {len(hechos_probados)} hechos probados "
            f"que configuran un patrón de conducta relevante para la calificación concursal."
        )
    
    return SeccionHechosProbados(
        hechos=hechos_probados,
        total_hechos=len(hechos_probados),
        resumen_cronologico=resumen,
    )


# ============================
# GENERACIÓN SECCIÓN III: RIESGOS DETECTADOS
# ============================

def generar_seccion_riesgos_detectados(
    acusaciones: List[AcusacionProbatoria],
    hechos_probados: List[HechoProbado],
) -> SeccionRiesgosDetectados:
    """
    Genera SECCIÓN III: RIESGOS DETECTADOS con base legal TRLC.
    
    Cada acusación se convierte en un riesgo con fundamentación legal.
    """
    riesgos = []
    distribucion: Dict[str, int] = {
        "BAJA": 0,
        "MEDIA": 0,
        "ALTA": 0,
        "CRITICA": 0,
    }
    
    for idx, acusacion in enumerate(acusaciones, start=1):
        # Extraer ground del accusation_id (formato: "case_id-ground")
        parts = acusacion.accusation_id.split("-")
        ground = parts[-1] if len(parts) > 1 else "desconocido"
        
        # Título del riesgo
        titulo = GROUND_TO_TITULO.get(ground, f"Riesgo Legal Detectado ({ground})")
        
        # Base legal
        base_legal = BaseLegalTRLC(
            articulo=acusacion.obligacion_legal.articulo,
            texto_articulo=acusacion.obligacion_legal.deber,
            tipo_infraccion="CULPABILIDAD",
        )
        
        # Consecuencias jurídicas
        consecuencias = GROUND_TO_CONSECUENCIAS.get(
            ground,
            "Posible calificación del concurso como culpable con consecuencias legales derivadas."
        )
        
        # Hechos relacionados (mapeo 1:1, el riesgo #N corresponde al hecho #N)
        hechos_relacionados = [idx]
        
        riesgo = RiesgoDetectado(
            numero=idx,
            titulo_riesgo=titulo,
            descripcion_riesgo=(
                f"Se detecta {titulo.lower()} en base a evidencia documental. "
                f"{acusacion.descripcion_factica}"
            ),
            severidad=acusacion.severidad,
            base_legal=base_legal,
            hechos_relacionados=hechos_relacionados,
            consecuencias_juridicas=consecuencias,
            nivel_confianza=acusacion.nivel_confianza,
        )
        
        riesgos.append(riesgo)
        distribucion[acusacion.severidad] += 1
    
    # Calificación concursal sugerida
    if distribucion["CRITICA"] > 0:
        calificacion = "CULPABLE_AGRAVADO"
        fundamento = (
            f"Se detectan {distribucion['CRITICA']} riesgo(s) de severidad CRITICA, "
            "lo que justifica la calificación del concurso como CULPABLE en grado agravado."
        )
    elif distribucion["ALTA"] > 0 or distribucion["MEDIA"] > 0:
        calificacion = "CULPABLE_SIMPLE"
        fundamento = (
            f"Se detectan {distribucion['ALTA']} riesgo(s) de severidad ALTA "
            f"y {distribucion['MEDIA']} de severidad MEDIA, "
            "lo que justifica la calificación del concurso como CULPABLE."
        )
    else:
        calificacion = "FORTUITO"
        fundamento = (
            "Los riesgos detectados son de severidad BAJA. "
            "No se aprecian indicios suficientes para calificación culpable."
        )
    
    return SeccionRiesgosDetectados(
        riesgos=riesgos,
        total_riesgos=len(riesgos),
        distribucion_severidad=distribucion,
        calificacion_concursal_sugerida=calificacion,
        fundamento_calificacion=fundamento,
    )


# ============================
# FUNCIÓN PRINCIPAL
# ============================

def generar_plantilla_formal(
    prosecutor_result: ProsecutorResult,
) -> PlantillaFormalAcusacion:
    """
    Convierte ProsecutorResult a PlantillaFormalAcusacion.
    
    Args:
        prosecutor_result: Resultado del análisis prosecutor
        
    Returns:
        PlantillaFormalAcusacion validada y completa
        
    Raises:
        ValueError: Si el prosecutor_result no tiene acusaciones
        RuntimeError: Si la plantilla generada no cumple validaciones
    """
    # GATE: No se puede generar plantilla sin acusaciones
    if not prosecutor_result.acusaciones:
        raise ValueError(
            "No se puede generar plantilla formal sin acusaciones. "
            f"Solicitud de evidencia: {prosecutor_result.solicitud_evidencia}"
        )
    
    # Obtener sesión de DB
    SessionLocal = get_session_factory()
    db: Session = SessionLocal()
    
    try:
        # SECCIÓN I: ANTECEDENTES
        seccion_antecedentes = generar_seccion_antecedentes(
            case_id=prosecutor_result.case_id,
            acusaciones=prosecutor_result.acusaciones,
            db=db,
        )
        
        # SECCIÓN II: HECHOS PROBADOS
        seccion_hechos = generar_seccion_hechos_probados(
            acusaciones=prosecutor_result.acusaciones,
        )
        
        # SECCIÓN III: RIESGOS DETECTADOS
        seccion_riesgos = generar_seccion_riesgos_detectados(
            acusaciones=prosecutor_result.acusaciones,
            hechos_probados=seccion_hechos.hechos,
        )
        
        # Construir plantilla completa
        plantilla = PlantillaFormalAcusacion(
            seccion_i_antecedentes=seccion_antecedentes,
            seccion_ii_hechos_probados=seccion_hechos,
            seccion_iii_riesgos_detectados=seccion_riesgos,
        )
        
        # VALIDACIÓN FINAL
        es_valida, errores = validar_estructura_obligatoria(plantilla)
        if not es_valida:
            raise RuntimeError(
                f"Plantilla generada no cumple validaciones estructurales: {errores}"
            )
        
        print(f"[CERT] FORMAL_TEMPLATE_GENERATED case_id={prosecutor_result.case_id} "
              f"hechos={len(seccion_hechos.hechos)} "
              f"riesgos={len(seccion_riesgos.riesgos)} "
              f"calificacion={seccion_riesgos.calificacion_concursal_sugerida}")
        
        return plantilla
    
    finally:
        db.close()


def exportar_plantilla_a_texto(plantilla: PlantillaFormalAcusacion) -> str:
    """
    Exporta la plantilla a formato de texto estructurado (para PDF o Word).
    
    Returns:
        Texto formateado con las 3 secciones obligatorias
    """
    lineas = []
    
    # ENCABEZADO
    lineas.append("=" * 80)
    lineas.append("ACUSACIÓN FORMAL - ANÁLISIS CONCURSAL")
    lineas.append("=" * 80)
    lineas.append(f"Generado por: {plantilla.generado_por}")
    lineas.append(f"Versión: {plantilla.version_plantilla}")
    lineas.append(f"Fecha: {plantilla.seccion_i_antecedentes.fecha_generacion.strftime('%Y-%m-%d %H:%M:%S')}")
    lineas.append(f"Caso: {plantilla.seccion_i_antecedentes.case_id}")
    lineas.append("=" * 80)
    lineas.append("")
    
    # SECCIÓN I: ANTECEDENTES
    lineas.append("I. ANTECEDENTES")
    lineas.append("-" * 80)
    lineas.append(f"Total documentos analizados: {plantilla.seccion_i_antecedentes.total_documentos}")
    lineas.append(f"Total páginas analizadas: {plantilla.seccion_i_antecedentes.total_paginas_analizadas}")
    lineas.append("")
    
    if plantilla.seccion_i_antecedentes.observaciones_preliminares:
        lineas.append(f"Observaciones: {plantilla.seccion_i_antecedentes.observaciones_preliminares}")
        lineas.append("")
    
    lineas.append("Documentos:")
    for doc in plantilla.seccion_i_antecedentes.documentos:
        lineas.append(f"\n  {doc.nombre_documento}")
        lineas.append(f"  - ID: {doc.doc_id}")
        lineas.append(f"  - Hash SHA256: {doc.hash_sha256}")
        if doc.paginas_relevantes:
            lineas.append(f"  - Páginas relevantes: {', '.join(map(str, doc.paginas_relevantes))}")
        lineas.append(f"  - Descripción: {doc.descripcion}")
    
    lineas.append("\n")
    
    # SECCIÓN II: HECHOS PROBADOS
    lineas.append("II. HECHOS PROBADOS")
    lineas.append("-" * 80)
    lineas.append(f"Total hechos probados: {plantilla.seccion_ii_hechos_probados.total_hechos}")
    lineas.append("")
    
    if plantilla.seccion_ii_hechos_probados.resumen_cronologico:
        lineas.append(f"{plantilla.seccion_ii_hechos_probados.resumen_cronologico}")
        lineas.append("")
    
    for hecho in plantilla.seccion_ii_hechos_probados.hechos:
        lineas.append(f"\nHECHO #{hecho.numero} [{hecho.nivel_certeza}]")
        lineas.append(f"  {hecho.descripcion_factica}")
        lineas.append(f"\n  Fuentes documentales ({len(hecho.fuentes)}):")
        
        for i, fuente in enumerate(hecho.fuentes, 1):
            lineas.append(f"    [{i}] Documento: {fuente.doc_id}")
            lineas.append(f"        Ubicación: {fuente.ubicacion_exacta}")
            lineas.append(f"        Extracto: \"{fuente.extracto_literal[:200]}...\"")
    
    lineas.append("\n")
    
    # SECCIÓN III: RIESGOS DETECTADOS
    lineas.append("III. RIESGOS DETECTADOS (BASE LEGAL TRLC)")
    lineas.append("-" * 80)
    lineas.append(f"Total riesgos: {plantilla.seccion_iii_riesgos_detectados.total_riesgos}")
    lineas.append(f"Distribución severidad: {plantilla.seccion_iii_riesgos_detectados.distribucion_severidad}")
    lineas.append("")
    lineas.append(f"CALIFICACIÓN SUGERIDA: {plantilla.seccion_iii_riesgos_detectados.calificacion_concursal_sugerida}")
    lineas.append(f"Fundamento: {plantilla.seccion_iii_riesgos_detectados.fundamento_calificacion}")
    lineas.append("")
    
    for riesgo in plantilla.seccion_iii_riesgos_detectados.riesgos:
        lineas.append(f"\nRIESGO #{riesgo.numero} - {riesgo.titulo_riesgo}")
        lineas.append(f"  Severidad: {riesgo.severidad} (Confianza: {riesgo.nivel_confianza:.2f})")
        lineas.append(f"\n  Base Legal:")
        lineas.append(f"    Artículo: {riesgo.base_legal.articulo}")
        lineas.append(f"    Tipo: {riesgo.base_legal.tipo_infraccion}")
        lineas.append(f"    Texto: {riesgo.base_legal.texto_articulo}")
        lineas.append(f"\n  Descripción del Riesgo:")
        lineas.append(f"    {riesgo.descripcion_riesgo}")
        lineas.append(f"\n  Consecuencias Jurídicas:")
        lineas.append(f"    {riesgo.consecuencias_juridicas}")
        lineas.append(f"\n  Hechos Relacionados: {', '.join(f'#{h}' for h in riesgo.hechos_relacionados)}")
    
    lineas.append("\n")
    lineas.append("=" * 80)
    lineas.append(f"CERTIFICACIÓN: {plantilla.certificacion_estructural}")
    lineas.append("=" * 80)
    
    return "\n".join(lineas)


"""
TEST: Plantilla Formal de Acusación Legal

OBJETIVO: Validar que la plantilla formal cumple TODOS los requisitos estructurales.

CASOS DE TEST:
1. Plantilla válida con todas las secciones completas
2. Validación de hashes SHA256 obligatorios
3. Validación de fuentes verificables en hechos probados
4. Validación de base legal TRLC en riesgos
5. Validación de cross-references (hechos ↔ riesgos)
6. Rechazo de plantillas incompletas o mal formadas
"""

import pytest

from app.agents.agent_2_prosecutor.formal_generator import (
    exportar_plantilla_a_texto,
    generar_plantilla_formal,
)
from app.agents.agent_2_prosecutor.formal_template import (
    BaseLegalTRLC,
    DocumentoAntecedente,
    FuenteVerificable,
    HechoProbado,
    PlantillaFormalAcusacion,
    RiesgoDetectado,
    SeccionAntecedentes,
    SeccionHechosProbados,
    SeccionRiesgosDetectados,
    generar_hash_documento,
    validar_estructura_obligatoria,
)
from app.agents.agent_2_prosecutor.schema import (
    AcusacionProbatoria,
    EvidenciaDocumental,
    ObligacionLegal,
    ProsecutorResult,
)

# ============================
# TEST 1: Hash SHA256
# ============================


def test_generar_hash_documento():
    """Validar generación de hash SHA256 determinista."""
    contenido1 = "Este es un documento de prueba"
    contenido2 = "Este es un documento de prueba"
    contenido3 = "Este es otro documento"

    hash1 = generar_hash_documento(contenido1)
    hash2 = generar_hash_documento(contenido2)
    hash3 = generar_hash_documento(contenido3)

    # Mismo contenido → mismo hash
    assert hash1 == hash2

    # Diferente contenido → diferente hash
    assert hash1 != hash3

    # Hash debe ser hexadecimal de 64 caracteres (SHA256)
    assert len(hash1) == 64
    assert all(c in "0123456789abcdef" for c in hash1)


def test_generar_hash_documento_bytes():
    """Validar generación de hash desde bytes."""
    contenido_str = "Documento en string"
    contenido_bytes = b"Documento en string"

    hash_str = generar_hash_documento(contenido_str)
    hash_bytes = generar_hash_documento(contenido_bytes)

    # Mismo contenido en diferentes formatos → mismo hash
    assert hash_str == hash_bytes


# ============================
# TEST 2: Estructura Obligatoria
# ============================


def test_plantilla_valida_cumple_estructura():
    """Validar que una plantilla correcta pasa todas las validaciones."""

    # SECCIÓN I: ANTECEDENTES
    doc1 = DocumentoAntecedente(
        doc_id="balance_2023.pdf",
        nombre_documento="Balance General 2023",
        hash_sha256=generar_hash_documento("contenido del balance"),
        paginas_relevantes=[1, 2, 3],
        descripcion="Balance general del ejercicio 2023",
    )

    seccion_antecedentes = SeccionAntecedentes(
        case_id="CASE_001",
        documentos=[doc1],
        total_documentos=1,
        total_paginas_analizadas=3,
        observaciones_preliminares="Documentación completa",
    )

    # SECCIÓN II: HECHOS PROBADOS
    fuente1 = FuenteVerificable(
        doc_id="balance_2023.pdf",
        chunk_id="chunk_001",
        pagina=1,
        extracto_literal="Patrimonio neto negativo: -150.000 EUR",
        ubicacion_exacta="página 1, chars 100-145",
    )

    hecho1 = HechoProbado(
        numero=1,
        descripcion_factica="El balance general del ejercicio 2023 refleja patrimonio neto negativo.",
        fuentes=[fuente1],
        nivel_certeza="PROBADO",
    )

    seccion_hechos = SeccionHechosProbados(
        hechos=[hecho1],
        total_hechos=1,
    )

    # SECCIÓN III: RIESGOS DETECTADOS
    base_legal1 = BaseLegalTRLC(
        articulo="Art. 5 TRLC",
        texto_articulo="Deber de solicitar concurso dentro de 2 meses",
        tipo_infraccion="CULPABILIDAD",
    )

    riesgo1 = RiesgoDetectado(
        numero=1,
        titulo_riesgo="Retraso en solicitud de concurso",
        descripcion_riesgo="Se detecta patrimonio negativo sin solicitud inmediata de concurso",
        severidad="CRITICA",
        base_legal=base_legal1,
        hechos_relacionados=[1],
        consecuencias_juridicas="Calificación culpable e inhabilitación",
        nivel_confianza=0.85,
    )

    seccion_riesgos = SeccionRiesgosDetectados(
        riesgos=[riesgo1],
        total_riesgos=1,
        distribucion_severidad={"BAJA": 0, "MEDIA": 0, "ALTA": 0, "CRITICA": 1},
        calificacion_concursal_sugerida="CULPABLE_AGRAVADO",
        fundamento_calificacion="Severidad crítica detectada",
    )

    # PLANTILLA COMPLETA
    plantilla = PlantillaFormalAcusacion(
        seccion_i_antecedentes=seccion_antecedentes,
        seccion_ii_hechos_probados=seccion_hechos,
        seccion_iii_riesgos_detectados=seccion_riesgos,
    )

    # VALIDACIÓN
    es_valida, errores = validar_estructura_obligatoria(plantilla)

    assert es_valida is True
    assert len(errores) == 0


def test_plantilla_sin_documentos_falla():
    """Validar rechazo de plantilla sin documentos en SECCIÓN I."""

    seccion_antecedentes = SeccionAntecedentes(
        case_id="CASE_001",
        documentos=[],  # VACÍO → debe fallar
        total_documentos=0,
        total_paginas_analizadas=0,
    )

    fuente1 = FuenteVerificable(
        doc_id="fake.pdf",
        chunk_id="chunk_001",
        extracto_literal="Extracto",
        ubicacion_exacta="chars 0-10",
    )

    hecho1 = HechoProbado(
        numero=1,
        descripcion_factica="Hecho sin documentos",
        fuentes=[fuente1],
        nivel_certeza="PROBADO",
    )

    seccion_hechos = SeccionHechosProbados(
        hechos=[hecho1],
        total_hechos=1,
    )

    base_legal1 = BaseLegalTRLC(
        articulo="Art. 5",
        texto_articulo="Deber legal",
        tipo_infraccion="CULPABILIDAD",
    )

    riesgo1 = RiesgoDetectado(
        numero=1,
        titulo_riesgo="Riesgo",
        descripcion_riesgo="Descripción",
        severidad="ALTA",
        base_legal=base_legal1,
        hechos_relacionados=[1],
        consecuencias_juridicas="Consecuencias",
        nivel_confianza=0.7,
    )

    seccion_riesgos = SeccionRiesgosDetectados(
        riesgos=[riesgo1],
        total_riesgos=1,
        distribucion_severidad={"BAJA": 0, "MEDIA": 0, "ALTA": 1, "CRITICA": 0},
        calificacion_concursal_sugerida="CULPABLE_SIMPLE",
        fundamento_calificacion="Fundamento",
    )

    plantilla = PlantillaFormalAcusacion(
        seccion_i_antecedentes=seccion_antecedentes,
        seccion_ii_hechos_probados=seccion_hechos,
        seccion_iii_riesgos_detectados=seccion_riesgos,
    )

    es_valida, errores = validar_estructura_obligatoria(plantilla)

    assert es_valida is False
    assert any("Falta lista de documentos" in err for err in errores)


def test_plantilla_hecho_sin_fuentes_falla():
    """Validar rechazo de hecho probado sin fuentes verificables."""

    doc1 = DocumentoAntecedente(
        doc_id="doc.pdf",
        nombre_documento="Documento",
        hash_sha256=generar_hash_documento("contenido"),
        descripcion="Descripción",
    )

    seccion_antecedentes = SeccionAntecedentes(
        case_id="CASE_001",
        documentos=[doc1],
        total_documentos=1,
        total_paginas_analizadas=1,
    )

    # Hecho SIN fuentes → debe fallar
    hecho1 = HechoProbado(
        numero=1,
        descripcion_factica="Hecho sin respaldo documental",
        fuentes=[],  # VACÍO → debe fallar
        nivel_certeza="PROBADO",
    )

    seccion_hechos = SeccionHechosProbados(
        hechos=[hecho1],
        total_hechos=1,
    )

    base_legal1 = BaseLegalTRLC(
        articulo="Art. 5",
        texto_articulo="Deber legal",
        tipo_infraccion="CULPABILIDAD",
    )

    riesgo1 = RiesgoDetectado(
        numero=1,
        titulo_riesgo="Riesgo",
        descripcion_riesgo="Descripción",
        severidad="ALTA",
        base_legal=base_legal1,
        hechos_relacionados=[1],
        consecuencias_juridicas="Consecuencias",
        nivel_confianza=0.7,
    )

    seccion_riesgos = SeccionRiesgosDetectados(
        riesgos=[riesgo1],
        total_riesgos=1,
        distribucion_severidad={"BAJA": 0, "MEDIA": 0, "ALTA": 1, "CRITICA": 0},
        calificacion_concursal_sugerida="CULPABLE_SIMPLE",
        fundamento_calificacion="Fundamento",
    )

    plantilla = PlantillaFormalAcusacion(
        seccion_i_antecedentes=seccion_antecedentes,
        seccion_ii_hechos_probados=seccion_hechos,
        seccion_iii_riesgos_detectados=seccion_riesgos,
    )

    es_valida, errores = validar_estructura_obligatoria(plantilla)

    assert es_valida is False
    assert any("sin fuentes verificables" in err for err in errores)


def test_plantilla_riesgo_sin_base_legal_falla():
    """Validar rechazo de riesgo sin base legal TRLC."""

    doc1 = DocumentoAntecedente(
        doc_id="doc.pdf",
        nombre_documento="Documento",
        hash_sha256=generar_hash_documento("contenido"),
        descripcion="Descripción",
    )

    seccion_antecedentes = SeccionAntecedentes(
        case_id="CASE_001",
        documentos=[doc1],
        total_documentos=1,
        total_paginas_analizadas=1,
    )

    fuente1 = FuenteVerificable(
        doc_id="doc.pdf",
        chunk_id="chunk_001",
        extracto_literal="Extracto",
        ubicacion_exacta="chars 0-10",
    )

    hecho1 = HechoProbado(
        numero=1,
        descripcion_factica="Hecho probado",
        fuentes=[fuente1],
        nivel_certeza="PROBADO",
    )

    seccion_hechos = SeccionHechosProbados(
        hechos=[hecho1],
        total_hechos=1,
    )

    # Base legal SIN artículo → debe fallar
    base_legal_invalida = BaseLegalTRLC(
        articulo="",  # VACÍO → debe fallar
        texto_articulo="Sin artículo",
        tipo_infraccion="CULPABILIDAD",
    )

    riesgo1 = RiesgoDetectado(
        numero=1,
        titulo_riesgo="Riesgo sin base legal",
        descripcion_riesgo="Descripción",
        severidad="ALTA",
        base_legal=base_legal_invalida,
        hechos_relacionados=[1],
        consecuencias_juridicas="Consecuencias",
        nivel_confianza=0.7,
    )

    seccion_riesgos = SeccionRiesgosDetectados(
        riesgos=[riesgo1],
        total_riesgos=1,
        distribucion_severidad={"BAJA": 0, "MEDIA": 0, "ALTA": 1, "CRITICA": 0},
        calificacion_concursal_sugerida="CULPABLE_SIMPLE",
        fundamento_calificacion="Fundamento",
    )

    plantilla = PlantillaFormalAcusacion(
        seccion_i_antecedentes=seccion_antecedentes,
        seccion_ii_hechos_probados=seccion_hechos,
        seccion_iii_riesgos_detectados=seccion_riesgos,
    )

    es_valida, errores = validar_estructura_obligatoria(plantilla)

    assert es_valida is False
    assert any("sin base legal TRLC" in err for err in errores)


def test_plantilla_cross_reference_invalida_falla():
    """Validar rechazo de riesgo que referencia hecho inexistente."""

    doc1 = DocumentoAntecedente(
        doc_id="doc.pdf",
        nombre_documento="Documento",
        hash_sha256=generar_hash_documento("contenido"),
        descripcion="Descripción",
    )

    seccion_antecedentes = SeccionAntecedentes(
        case_id="CASE_001",
        documentos=[doc1],
        total_documentos=1,
        total_paginas_analizadas=1,
    )

    fuente1 = FuenteVerificable(
        doc_id="doc.pdf",
        chunk_id="chunk_001",
        extracto_literal="Extracto",
        ubicacion_exacta="chars 0-10",
    )

    hecho1 = HechoProbado(
        numero=1,  # Solo existe hecho #1
        descripcion_factica="Hecho probado",
        fuentes=[fuente1],
        nivel_certeza="PROBADO",
    )

    seccion_hechos = SeccionHechosProbados(
        hechos=[hecho1],
        total_hechos=1,
    )

    base_legal1 = BaseLegalTRLC(
        articulo="Art. 5",
        texto_articulo="Deber legal",
        tipo_infraccion="CULPABILIDAD",
    )

    riesgo1 = RiesgoDetectado(
        numero=1,
        titulo_riesgo="Riesgo",
        descripcion_riesgo="Descripción",
        severidad="ALTA",
        base_legal=base_legal1,
        hechos_relacionados=[999],  # Referencia hecho inexistente #999
        consecuencias_juridicas="Consecuencias",
        nivel_confianza=0.7,
    )

    seccion_riesgos = SeccionRiesgosDetectados(
        riesgos=[riesgo1],
        total_riesgos=1,
        distribucion_severidad={"BAJA": 0, "MEDIA": 0, "ALTA": 1, "CRITICA": 0},
        calificacion_concursal_sugerida="CULPABLE_SIMPLE",
        fundamento_calificacion="Fundamento",
    )

    plantilla = PlantillaFormalAcusacion(
        seccion_i_antecedentes=seccion_antecedentes,
        seccion_ii_hechos_probados=seccion_hechos,
        seccion_iii_riesgos_detectados=seccion_riesgos,
    )

    es_valida, errores = validar_estructura_obligatoria(plantilla)

    assert es_valida is False
    assert any("referencia hecho inexistente" in err for err in errores)


def test_plantilla_narrativa_especulativa_falla():
    """Validar rechazo de hechos con narrativa especulativa."""

    doc1 = DocumentoAntecedente(
        doc_id="doc.pdf",
        nombre_documento="Documento",
        hash_sha256=generar_hash_documento("contenido"),
        descripcion="Descripción",
    )

    seccion_antecedentes = SeccionAntecedentes(
        case_id="CASE_001",
        documentos=[doc1],
        total_documentos=1,
        total_paginas_analizadas=1,
    )

    fuente1 = FuenteVerificable(
        doc_id="doc.pdf",
        chunk_id="chunk_001",
        extracto_literal="Extracto",
        ubicacion_exacta="chars 0-10",
    )

    # Hecho con narrativa especulativa → debe fallar
    hecho1 = HechoProbado(
        numero=1,
        descripcion_factica="Parece que el administrador podría haber actuado negligentemente",  # PROHIBIDO
        fuentes=[fuente1],
        nivel_certeza="PROBADO",
    )

    seccion_hechos = SeccionHechosProbados(
        hechos=[hecho1],
        total_hechos=1,
    )

    base_legal1 = BaseLegalTRLC(
        articulo="Art. 5",
        texto_articulo="Deber legal",
        tipo_infraccion="CULPABILIDAD",
    )

    riesgo1 = RiesgoDetectado(
        numero=1,
        titulo_riesgo="Riesgo",
        descripcion_riesgo="Descripción",
        severidad="ALTA",
        base_legal=base_legal1,
        hechos_relacionados=[1],
        consecuencias_juridicas="Consecuencias",
        nivel_confianza=0.7,
    )

    seccion_riesgos = SeccionRiesgosDetectados(
        riesgos=[riesgo1],
        total_riesgos=1,
        distribucion_severidad={"BAJA": 0, "MEDIA": 0, "ALTA": 1, "CRITICA": 0},
        calificacion_concursal_sugerida="CULPABLE_SIMPLE",
        fundamento_calificacion="Fundamento",
    )

    plantilla = PlantillaFormalAcusacion(
        seccion_i_antecedentes=seccion_antecedentes,
        seccion_ii_hechos_probados=seccion_hechos,
        seccion_iii_riesgos_detectados=seccion_riesgos,
    )

    es_valida, errores = validar_estructura_obligatoria(plantilla)

    assert es_valida is False
    assert any("narrativa especulativa" in err for err in errores)


# ============================
# TEST 3: Generación desde ProsecutorResult
# ============================


def test_generar_plantilla_desde_prosecutor_result(tmp_path, monkeypatch):
    """Validar generación completa de plantilla desde ProsecutorResult."""

    # Mock de DB (evitar dependencias reales)
    class MockDocument:
        filename = "balance.pdf"
        doc_type = "balance"
        file_path = None

    class MockQuery:
        def filter(self, *args, **kwargs):
            return self

        def all(self):
            return [MockDocument()]

    class MockDB:
        def query(self, *args):
            return MockQuery()

        def close(self):
            pass

    def mock_get_session_factory():
        return lambda: MockDB()

    monkeypatch.setattr(
        "app.agents.agent_2_prosecutor.formal_generator.get_session_factory",
        mock_get_session_factory,
    )

    # Crear ProsecutorResult con 1 acusación
    obligacion = ObligacionLegal(
        ley="Ley Concursal",
        articulo="Art. 5 TRLC",
        deber="Solicitar concurso dentro de 2 meses",
    )

    evidencia = EvidenciaDocumental(
        chunk_id="chunk_001",
        doc_id="balance.pdf",
        page=1,
        start_char=100,
        end_char=200,
        extracto_literal="Patrimonio neto negativo: -100.000 EUR",
    )

    acusacion = AcusacionProbatoria(
        accusation_id="CASE_001-retraso_concurso",
        obligacion_legal=obligacion,
        evidencia_documental=[evidencia],
        descripcion_factica="El balance refleja patrimonio negativo desde marzo 2023",
        severidad="CRITICA",
        nivel_confianza=0.85,
        evidencia_faltante=[],
    )

    prosecutor_result = ProsecutorResult(
        case_id="CASE_001",
        acusaciones=[acusacion],
        solicitud_evidencia=None,
        total_acusaciones=1,
    )

    # GENERAR PLANTILLA
    plantilla = generar_plantilla_formal(prosecutor_result)

    # VALIDACIONES
    assert plantilla.seccion_i_antecedentes.case_id == "CASE_001"
    assert len(plantilla.seccion_i_antecedentes.documentos) == 1
    assert plantilla.seccion_i_antecedentes.documentos[0].doc_id == "balance.pdf"

    assert len(plantilla.seccion_ii_hechos_probados.hechos) == 1
    assert plantilla.seccion_ii_hechos_probados.hechos[0].numero == 1
    assert len(plantilla.seccion_ii_hechos_probados.hechos[0].fuentes) == 1

    assert len(plantilla.seccion_iii_riesgos_detectados.riesgos) == 1
    assert (
        plantilla.seccion_iii_riesgos_detectados.riesgos[0].titulo_riesgo
        == "Retraso en la Solicitud de Concurso"
    )
    assert (
        plantilla.seccion_iii_riesgos_detectados.calificacion_concursal_sugerida
        == "CULPABLE_AGRAVADO"
    )

    # Validación estructural
    es_valida, errores = validar_estructura_obligatoria(plantilla)
    assert es_valida is True, f"Errores: {errores}"


def test_generar_plantilla_sin_acusaciones_falla():
    """Validar que NO se puede generar plantilla sin acusaciones."""

    prosecutor_result = ProsecutorResult(
        case_id="CASE_001",
        acusaciones=[],  # VACÍO → debe fallar
        solicitud_evidencia=None,
        total_acusaciones=0,
    )

    with pytest.raises(ValueError, match="sin acusaciones"):
        generar_plantilla_formal(prosecutor_result)


# ============================
# TEST 4: Exportación a Texto
# ============================


def test_exportar_plantilla_a_texto():
    """Validar exportación de plantilla a formato texto estructurado."""

    # Construir plantilla simple
    doc1 = DocumentoAntecedente(
        doc_id="doc.pdf",
        nombre_documento="Documento Test",
        hash_sha256="a" * 64,
        descripcion="Descripción",
    )

    seccion_antecedentes = SeccionAntecedentes(
        case_id="CASE_001",
        documentos=[doc1],
        total_documentos=1,
        total_paginas_analizadas=1,
    )

    fuente1 = FuenteVerificable(
        doc_id="doc.pdf",
        chunk_id="chunk_001",
        extracto_literal="Extracto de prueba",
        ubicacion_exacta="chars 0-20",
    )

    hecho1 = HechoProbado(
        numero=1,
        descripcion_factica="Hecho probado de prueba",
        fuentes=[fuente1],
        nivel_certeza="PROBADO",
    )

    seccion_hechos = SeccionHechosProbados(
        hechos=[hecho1],
        total_hechos=1,
    )

    base_legal1 = BaseLegalTRLC(
        articulo="Art. 5 TRLC",
        texto_articulo="Deber de solicitar concurso",
        tipo_infraccion="CULPABILIDAD",
    )

    riesgo1 = RiesgoDetectado(
        numero=1,
        titulo_riesgo="Riesgo de prueba",
        descripcion_riesgo="Descripción del riesgo",
        severidad="ALTA",
        base_legal=base_legal1,
        hechos_relacionados=[1],
        consecuencias_juridicas="Consecuencias de prueba",
        nivel_confianza=0.8,
    )

    seccion_riesgos = SeccionRiesgosDetectados(
        riesgos=[riesgo1],
        total_riesgos=1,
        distribucion_severidad={"BAJA": 0, "MEDIA": 0, "ALTA": 1, "CRITICA": 0},
        calificacion_concursal_sugerida="CULPABLE_SIMPLE",
        fundamento_calificacion="Fundamento de prueba",
    )

    plantilla = PlantillaFormalAcusacion(
        seccion_i_antecedentes=seccion_antecedentes,
        seccion_ii_hechos_probados=seccion_hechos,
        seccion_iii_riesgos_detectados=seccion_riesgos,
    )

    # EXPORTAR
    texto = exportar_plantilla_a_texto(plantilla)

    # VALIDACIONES
    assert "ACUSACIÓN FORMAL" in texto
    assert "I. ANTECEDENTES" in texto
    assert "II. HECHOS PROBADOS" in texto
    assert "III. RIESGOS DETECTADOS" in texto
    assert "CASE_001" in texto
    assert "Hash SHA256: " + ("a" * 64) in texto
    assert "HECHO #1" in texto
    assert "RIESGO #1" in texto
    assert "CULPABLE_SIMPLE" in texto
    assert "ESTRUCTURA_VALIDADA" in texto


# ============================
# CERT: Invariantes
# ============================


def test_cert_invariante_toda_plantilla_tiene_3_secciones():
    """[CERT] INVARIANTE: Toda plantilla válida DEBE tener las 3 secciones obligatorias."""

    # Construir plantilla mínima válida
    doc1 = DocumentoAntecedente(
        doc_id="doc.pdf",
        nombre_documento="Doc",
        hash_sha256=generar_hash_documento("contenido"),
        descripcion="Desc",
    )

    seccion_antecedentes = SeccionAntecedentes(
        case_id="CASE_001",
        documentos=[doc1],
        total_documentos=1,
        total_paginas_analizadas=1,
    )

    fuente1 = FuenteVerificable(
        doc_id="doc.pdf",
        chunk_id="chunk_001",
        extracto_literal="Extracto",
        ubicacion_exacta="chars 0-10",
    )

    hecho1 = HechoProbado(
        numero=1,
        descripcion_factica="Hecho",
        fuentes=[fuente1],
        nivel_certeza="PROBADO",
    )

    seccion_hechos = SeccionHechosProbados(
        hechos=[hecho1],
        total_hechos=1,
    )

    base_legal1 = BaseLegalTRLC(
        articulo="Art. 5",
        texto_articulo="Deber",
        tipo_infraccion="CULPABILIDAD",
    )

    riesgo1 = RiesgoDetectado(
        numero=1,
        titulo_riesgo="Riesgo",
        descripcion_riesgo="Desc",
        severidad="ALTA",
        base_legal=base_legal1,
        hechos_relacionados=[1],
        consecuencias_juridicas="Cons",
        nivel_confianza=0.7,
    )

    seccion_riesgos = SeccionRiesgosDetectados(
        riesgos=[riesgo1],
        total_riesgos=1,
        distribucion_severidad={"BAJA": 0, "MEDIA": 0, "ALTA": 1, "CRITICA": 0},
        calificacion_concursal_sugerida="CULPABLE_SIMPLE",
        fundamento_calificacion="Fund",
    )

    plantilla = PlantillaFormalAcusacion(
        seccion_i_antecedentes=seccion_antecedentes,
        seccion_ii_hechos_probados=seccion_hechos,
        seccion_iii_riesgos_detectados=seccion_riesgos,
    )

    # INVARIANTE: Toda plantilla válida tiene las 3 secciones
    assert plantilla.seccion_i_antecedentes is not None
    assert plantilla.seccion_ii_hechos_probados is not None
    assert plantilla.seccion_iii_riesgos_detectados is not None

    # INVARIANTE: Validación estructural pasa
    es_valida, errores = validar_estructura_obligatoria(plantilla)
    assert es_valida is True


def test_cert_invariante_todo_hecho_tiene_al_menos_una_fuente():
    """[CERT] INVARIANTE: Todo hecho probado DEBE tener AL MENOS una fuente verificable."""

    fuente1 = FuenteVerificable(
        doc_id="doc.pdf",
        chunk_id="chunk_001",
        extracto_literal="Extracto",
        ubicacion_exacta="chars 0-10",
    )

    hecho = HechoProbado(
        numero=1,
        descripcion_factica="Hecho",
        fuentes=[fuente1],  # Al menos 1
        nivel_certeza="PROBADO",
    )

    # INVARIANTE: min_items=1 en schema
    assert len(hecho.fuentes) >= 1


def test_cert_invariante_todo_riesgo_tiene_base_legal_trlc():
    """[CERT] INVARIANTE: Todo riesgo DEBE tener base legal TRLC obligatoria."""

    base_legal = BaseLegalTRLC(
        articulo="Art. 5 TRLC",
        texto_articulo="Deber legal",
        tipo_infraccion="CULPABILIDAD",
    )

    riesgo = RiesgoDetectado(
        numero=1,
        titulo_riesgo="Riesgo",
        descripcion_riesgo="Desc",
        severidad="ALTA",
        base_legal=base_legal,  # Obligatorio
        hechos_relacionados=[1],
        consecuencias_juridicas="Cons",
        nivel_confianza=0.7,
    )

    # INVARIANTE: base_legal es obligatorio
    assert riesgo.base_legal is not None
    assert riesgo.base_legal.articulo != ""

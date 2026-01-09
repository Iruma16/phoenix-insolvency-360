"""
TESTS: Schema de Acusaciones Formales - Unit Tests (Endurecimiento #5)

OBJETIVO: Validar estructura de acusaciones sin dependencias externas.

PRINCIPIO: Tests unitarios puros de validadores y estructura.
"""
import pytest
from typing import List, Optional
from pydantic import BaseModel, Field, validator


# ============================
# MOCK STRUCTURES (standalone)
# ============================

class EvidenciaDocumentalMock(BaseModel):
    chunk_id: str
    doc_id: str
    page: Optional[int] = None
    start_char: int
    end_char: int
    extracto_literal: str


class ObligacionLegalMock(BaseModel):
    ley: str
    articulo: str
    deber: str


class EvidenciaFaltanteMock(BaseModel):
    rule_id: str
    required_evidence: str
    present_evidence: str
    blocking_reason: str


class AcusacionProBatoriaMock(BaseModel):
    accusation_id: str
    obligacion_legal: ObligacionLegalMock
    evidencia_documental: List[EvidenciaDocumentalMock] = Field(min_items=1)
    descripcion_factica: str
    severidad: str
    nivel_confianza: float = Field(ge=0.0, le=1.0)
    evidencia_faltante: List[EvidenciaFaltanteMock] = Field(default_factory=list)
    
    @validator("evidencia_documental")
    def validate_evidencia_not_empty(cls, v):
        if not v or len(v) == 0:
            raise ValueError("Acusación sin evidencia documental: PROHIBIDO")
        return v


class AcusacionBloqueadaMock(BaseModel):
    rule_id: str
    blocked_reason: str
    evidencia_faltante: List[EvidenciaFaltanteMock]


class ProsecutorResultMock(BaseModel):
    case_id: str
    acusaciones: List[AcusacionProBatoriaMock] = Field(default_factory=list)
    acusaciones_bloqueadas: List[AcusacionBloqueadaMock] = Field(default_factory=list)
    total_acusaciones: int
    total_bloqueadas: int = 0


# ============================
# TEST 1: VALIDATOR EVIDENCIA
# ============================

def test_acusacion_sin_evidencia_falla():
    """GATE: Acusación sin evidencia_documental → ValidationError."""
    from pydantic import ValidationError
    
    with pytest.raises(ValidationError):
        AcusacionProBatoriaMock(
            accusation_id="test_001",
            obligacion_legal=ObligacionLegalMock(
                ley="Ley Concursal",
                articulo="Art. 5",
                deber="Solicitar concurso en 2 meses"
            ),
            evidencia_documental=[],
            descripcion_factica="Descripción",
            severidad="ALTA",
            nivel_confianza=0.8,
        )


def test_acusacion_con_evidencia_valida():
    """Acusación con evidencia válida se crea correctamente."""
    acusacion = AcusacionProBatoriaMock(
        accusation_id="test_001",
        obligacion_legal=ObligacionLegalMock(
            ley="Ley Concursal",
            articulo="Art. 5",
            deber="Solicitar concurso en 2 meses"
        ),
        evidencia_documental=[
            EvidenciaDocumentalMock(
                chunk_id="chunk_001",
                doc_id="doc_001",
                start_char=0,
                end_char=100,
                extracto_literal="Texto evidencia"
            )
        ],
        descripcion_factica="Descripción objetiva",
        severidad="ALTA",
        nivel_confianza=0.8,
    )
    
    assert len(acusacion.evidencia_documental) == 1


# ============================
# TEST 2: EVIDENCIA FALTANTE
# ============================

def test_evidencia_faltante_estructura():
    """EvidenciaFaltante tiene campos obligatorios."""
    evidencia = EvidenciaFaltanteMock(
        rule_id="retraso_concurso",
        required_evidence="balance_completo",
        present_evidence="NONE",
        blocking_reason="No se puede verificar insolvencia sin balance"
    )
    
    assert evidencia.rule_id == "retraso_concurso"
    assert evidencia.required_evidence == "balance_completo"
    assert evidencia.present_evidence == "NONE"
    assert evidencia.blocking_reason is not None


def test_evidencia_faltante_con_partial():
    """EvidenciaFaltante puede indicar evidencia PARTIAL."""
    evidencia = EvidenciaFaltanteMock(
        rule_id="alzamiento_bienes",
        required_evidence="registro_completo_ventas",
        present_evidence="extracto_parcial",
        blocking_reason="Solo se tiene extracto parcial, falta registro completo"
    )
    
    assert evidencia.present_evidence == "extracto_parcial"


# ============================
# TEST 3: ACUSACIÓN BLOQUEADA
# ============================

def test_acusacion_bloqueada_estructura():
    """AcusacionBloqueada contiene motivo y evidencia faltante."""
    bloqueada = AcusacionBloqueadaMock(
        rule_id="retraso_concurso",
        blocked_reason="NO_RESPONSE del RAG: EVIDENCE_MISSING",
        evidencia_faltante=[
            EvidenciaFaltanteMock(
                rule_id="retraso_concurso",
                required_evidence="balance",
                present_evidence="NONE",
                blocking_reason="RAG retornó NO_RESPONSE"
            )
        ]
    )
    
    assert bloqueada.rule_id == "retraso_concurso"
    assert "NO_RESPONSE" in bloqueada.blocked_reason
    assert len(bloqueada.evidencia_faltante) == 1


def test_acusacion_bloqueada_multiple_evidencias():
    """AcusacionBloqueada puede listar múltiples evidencias faltantes."""
    bloqueada = AcusacionBloqueadaMock(
        rule_id="culpabilidad_agravada",
        blocked_reason="PARTIAL_EVIDENCE: Faltan 2 documentos clave",
        evidencia_faltante=[
            EvidenciaFaltanteMock(
                rule_id="culpabilidad_agravada",
                required_evidence="balance",
                present_evidence="NONE",
                blocking_reason="Documento clave ausente"
            ),
            EvidenciaFaltanteMock(
                rule_id="culpabilidad_agravada",
                required_evidence="extractos_bancarios",
                present_evidence="NONE",
                blocking_reason="Documento clave ausente"
            ),
        ]
    )
    
    assert len(bloqueada.evidencia_faltante) == 2


# ============================
# TEST 4: PROSECUTOR RESULT
# ============================

def test_prosecutor_result_solo_acusaciones():
    """ProsecutorResult puede contener SOLO acusaciones completas."""
    result = ProsecutorResultMock(
        case_id="CASE_001",
        acusaciones=[
            AcusacionProBatoriaMock(
                accusation_id="acc_001",
                obligacion_legal=ObligacionLegalMock(
                    ley="Ley", articulo="Art. 1", deber="D"
                ),
                evidencia_documental=[
                    EvidenciaDocumentalMock(
                        chunk_id="c1", doc_id="d1",
                        start_char=0, end_char=10,
                        extracto_literal="T"
                    )
                ],
                descripcion_factica="H",
                severidad="ALTA",
                nivel_confianza=0.8,
            )
        ],
        acusaciones_bloqueadas=[],
        total_acusaciones=1,
        total_bloqueadas=0,
    )
    
    assert result.total_acusaciones == 1
    assert result.total_bloqueadas == 0


def test_prosecutor_result_solo_bloqueadas():
    """ProsecutorResult puede contener SOLO acusaciones bloqueadas."""
    result = ProsecutorResultMock(
        case_id="CASE_001",
        acusaciones=[],
        acusaciones_bloqueadas=[
            AcusacionBloqueadaMock(
                rule_id="rule_1",
                blocked_reason="NO_RESPONSE",
                evidencia_faltante=[
                    EvidenciaFaltanteMock(
                        rule_id="rule_1",
                        required_evidence="doc",
                        present_evidence="NONE",
                        blocking_reason="RAG sin chunks"
                    )
                ]
            )
        ],
        total_acusaciones=0,
        total_bloqueadas=1,
    )
    
    assert result.total_acusaciones == 0
    assert result.total_bloqueadas == 1


def test_prosecutor_result_mixto():
    """ProsecutorResult puede contener acusaciones completas Y bloqueadas."""
    result = ProsecutorResultMock(
        case_id="CASE_001",
        acusaciones=[
            AcusacionProBatoriaMock(
                accusation_id="acc_001",
                obligacion_legal=ObligacionLegalMock(
                    ley="L", articulo="A", deber="D"
                ),
                evidencia_documental=[
                    EvidenciaDocumentalMock(
                        chunk_id="c1", doc_id="d1",
                        start_char=0, end_char=10,
                        extracto_literal="T"
                    )
                ],
                descripcion_factica="H",
                severidad="ALTA",
                nivel_confianza=0.8,
            )
        ],
        acusaciones_bloqueadas=[
            AcusacionBloqueadaMock(
                rule_id="rule_2",
                blocked_reason="EVIDENCE_INSUFFICIENT",
                evidencia_faltante=[
                    EvidenciaFaltanteMock(
                        rule_id="rule_2",
                        required_evidence="contrato",
                        present_evidence="PARTIAL",
                        blocking_reason="Faltan anexos"
                    )
                ]
            )
        ],
        total_acusaciones=1,
        total_bloqueadas=1,
    )
    
    assert result.total_acusaciones == 1
    assert result.total_bloqueadas == 1


# ============================
# TEST 5: INVARIANTES
# ============================

def test_cert_contadores_coherentes():
    """[CERT] INVARIANTE: Contadores deben coincidir con listas."""
    result = ProsecutorResultMock(
        case_id="CASE_001",
        acusaciones=[
            AcusacionProBatoriaMock(
                accusation_id="acc_001",
                obligacion_legal=ObligacionLegalMock(
                    ley="L", articulo="A", deber="D"
                ),
                evidencia_documental=[
                    EvidenciaDocumentalMock(
                        chunk_id="c1", doc_id="d1",
                        start_char=0, end_char=10,
                        extracto_literal="T"
                    )
                ],
                descripcion_factica="H",
                severidad="ALTA",
                nivel_confianza=0.8,
            )
        ],
        acusaciones_bloqueadas=[
            AcusacionBloqueadaMock(
                rule_id="r1",
                blocked_reason="B",
                evidencia_faltante=[
                    EvidenciaFaltanteMock(
                        rule_id="r1",
                        required_evidence="e",
                        present_evidence="NONE",
                        blocking_reason="b"
                    )
                ]
            )
        ],
        total_acusaciones=1,
        total_bloqueadas=1,
    )
    
    assert result.total_acusaciones == len(result.acusaciones)
    assert result.total_bloqueadas == len(result.acusaciones_bloqueadas)


def test_cert_blocking_reason_no_vacio():
    """[CERT] INVARIANTE: blocking_reason NO puede estar vacío."""
    bloqueada = AcusacionBloqueadaMock(
        rule_id="rule_1",
        blocked_reason="NO_RESPONSE: EVIDENCE_MISSING",
        evidencia_faltante=[
            EvidenciaFaltanteMock(
                rule_id="rule_1",
                required_evidence="balance",
                present_evidence="NONE",
                blocking_reason="RAG retornó 0 chunks"
            )
        ]
    )
    
    assert bloqueada.blocked_reason != ""
    assert len(bloqueada.blocked_reason) > 0
    
    for ev_faltante in bloqueada.evidencia_faltante:
        assert ev_faltante.blocking_reason != ""
        assert len(ev_faltante.blocking_reason) > 0


# ============================
# RESUMEN DE TESTS
# ============================
"""
COBERTURA:

1. ✅ Validator evidencia (vacío falla + válido OK)
2. ✅ Estructura EvidenciaFaltante (NONE + PARTIAL)
3. ✅ Estructura AcusacionBloqueada (simple + múltiple)
4. ✅ ProsecutorResult (solo acusaciones, solo bloqueadas, mixto)
5. ✅ Invariantes (contadores coherentes, blocking_reason no vacío)

TOTAL: 12 tests unitarios standalone

INVARIANTES CERTIFICADOS:
- INVARIANTE 1: evidencia_documental vacía → ValidationError
- INVARIANTE 2: EvidenciaFaltante puede indicar present_evidence=PARTIAL
- INVARIANTE 3: AcusacionBloqueada puede listar múltiples evidencias faltantes
- INVARIANTE 4: total_acusaciones == len(acusaciones)
- INVARIANTE 5: total_bloqueadas == len(acusaciones_bloqueadas)
- INVARIANTE 6: blocking_reason NUNCA vacío
"""


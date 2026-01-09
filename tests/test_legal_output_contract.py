"""
TESTS DE CONTRATO DE SALIDA LEGAL (FASE 5 - ENDURECIMIENTO 5).

OBJETIVO:
Validar que toda salida legal cumple el contrato:
- Toda afirmación tiene evidencia
- Toda evidencia tiene location completa
- La salida es serializable y determinista
- NO se permite texto sin respaldo documental

REGLAS DURAS:
1. Finding sin evidencia → excepción
2. Evidencia sin location → excepción
3. Referencia a chunk inexistente → excepción
4. NO se permite salida parcial o degradada
"""
import pytest
from datetime import datetime
from pydantic import ValidationError

from app.models.legal_output import (
    LegalReport,
    LegalFinding,
    DocumentalEvidence,
    EvidenceLocation,
    ExtractionMethod,
    LegalOutputError,
)


class TestEvidenceLocationContract:
    """Tests del contrato de EvidenceLocation."""
    
    def test_valid_location_minimal(self):
        """✅ Location válida con campos obligatorios"""
        location = EvidenceLocation(
            start_char=0,
            end_char=100,
            extraction_method=ExtractionMethod.PDF_TEXT
        )
        
        assert location.start_char == 0
        assert location.end_char == 100
        assert location.extraction_method == ExtractionMethod.PDF_TEXT
    
    def test_location_with_pages(self):
        """✅ Location válida con páginas"""
        location = EvidenceLocation(
            page_start=1,
            page_end=2,
            start_char=0,
            end_char=100,
            extraction_method=ExtractionMethod.PDF_TEXT
        )
        
        assert location.page_start == 1
        assert location.page_end == 2
    
    def test_invalid_char_range_rejected(self):
        """❌ start_char >= end_char → ValidationError"""
        with pytest.raises(ValidationError) as exc_info:
            EvidenceLocation(
                start_char=100,
                end_char=100,  # INVÁLIDO
                extraction_method=ExtractionMethod.PDF_TEXT
            )
        
        assert "end_char" in str(exc_info.value).lower()
    
    def test_invalid_page_range_rejected(self):
        """❌ page_end < page_start → ValidationError"""
        with pytest.raises(ValidationError) as exc_info:
            EvidenceLocation(
                page_start=5,
                page_end=3,  # INVÁLIDO
                start_char=0,
                end_char=100,
                extraction_method=ExtractionMethod.PDF_TEXT
            )
        
        assert "page_end" in str(exc_info.value).lower()
    
    def test_missing_extraction_method_rejected(self):
        """❌ Sin extraction_method → ValidationError"""
        with pytest.raises(ValidationError):
            EvidenceLocation(
                start_char=0,
                end_char=100
                # extraction_method faltante
            )
    
    def test_extra_fields_forbidden(self):
        """❌ Campos extra no permitidos"""
        with pytest.raises(ValidationError):
            EvidenceLocation(
                start_char=0,
                end_char=100,
                extraction_method=ExtractionMethod.PDF_TEXT,
                extra_field="not_allowed"
            )


class TestDocumentalEvidenceContract:
    """Tests del contrato de DocumentalEvidence."""
    
    def test_valid_evidence(self):
        """✅ Evidencia válida con todos los campos obligatorios"""
        location = EvidenceLocation(
            start_char=0,
            end_char=100,
            extraction_method=ExtractionMethod.PDF_TEXT
        )
        
        evidence = DocumentalEvidence(
            chunk_id="chunk_001",
            document_id="doc_001",
            location=location,
            content="Texto literal extraído del documento"
        )
        
        assert evidence.chunk_id == "chunk_001"
        assert evidence.document_id == "doc_001"
        assert evidence.location == location
        assert len(evidence.content) > 0
    
    def test_evidence_without_chunk_id_rejected(self):
        """❌ Evidencia sin chunk_id → ValidationError"""
        location = EvidenceLocation(
            start_char=0,
            end_char=100,
            extraction_method=ExtractionMethod.PDF_TEXT
        )
        
        with pytest.raises(ValidationError):
            DocumentalEvidence(
                # chunk_id faltante
                document_id="doc_001",
                location=location,
                content="texto"
            )
    
    def test_evidence_without_location_rejected(self):
        """❌ Evidencia sin location → ValidationError"""
        with pytest.raises(ValidationError):
            DocumentalEvidence(
                chunk_id="chunk_001",
                document_id="doc_001",
                # location faltante
                content="texto"
            )
    
    def test_evidence_without_content_rejected(self):
        """❌ Evidencia sin content → ValidationError"""
        location = EvidenceLocation(
            start_char=0,
            end_char=100,
            extraction_method=ExtractionMethod.PDF_TEXT
        )
        
        with pytest.raises(ValidationError):
            DocumentalEvidence(
                chunk_id="chunk_001",
                document_id="doc_001",
                location=location,
                # content faltante
            )


class TestLegalFindingContract:
    """Tests del contrato de LegalFinding."""
    
    def test_valid_finding(self):
        """✅ Finding válido con statement y evidencia"""
        location = EvidenceLocation(
            start_char=0,
            end_char=100,
            extraction_method=ExtractionMethod.PDF_TEXT
        )
        
        evidence = DocumentalEvidence(
            chunk_id="chunk_001",
            document_id="doc_001",
            location=location,
            content="Texto del documento"
        )
        
        finding = LegalFinding(
            statement="Afirmación objetiva basada en evidencia documental",
            evidence=[evidence]
        )
        
        assert len(finding.statement) >= 10
        assert len(finding.evidence) == 1
    
    def test_finding_without_evidence_rejected(self):
        """❌ Finding sin evidencia → ValidationError"""
        with pytest.raises(ValidationError) as exc_info:
            LegalFinding(
                statement="Afirmación sin respaldo",
                evidence=[]  # INVÁLIDO: lista vacía
            )
        
        assert "evidence" in str(exc_info.value).lower()
    
    def test_finding_with_short_statement_rejected(self):
        """❌ Finding con statement muy corto → ValidationError"""
        location = EvidenceLocation(
            start_char=0,
            end_char=100,
            extraction_method=ExtractionMethod.PDF_TEXT
        )
        
        evidence = DocumentalEvidence(
            chunk_id="chunk_001",
            document_id="doc_001",
            location=location,
            content="texto"
        )
        
        with pytest.raises(ValidationError):
            LegalFinding(
                statement="Corto",  # INVÁLIDO: < 10 chars
                evidence=[evidence]
            )
    
    def test_finding_with_multiple_evidences(self):
        """✅ Finding con múltiples evidencias"""
        evidences = []
        for i in range(3):
            location = EvidenceLocation(
                start_char=i * 100,
                end_char=(i + 1) * 100,
                extraction_method=ExtractionMethod.PDF_TEXT
            )
            evidence = DocumentalEvidence(
                chunk_id=f"chunk_{i:03d}",
                document_id="doc_001",
                location=location,
                content=f"Texto evidencia {i}"
            )
            evidences.append(evidence)
        
        finding = LegalFinding(
            statement="Afirmación respaldada por múltiples evidencias documentales",
            evidence=evidences
        )
        
        assert len(finding.evidence) == 3


class TestLegalReportContract:
    """Tests del contrato de LegalReport."""
    
    def test_valid_report(self):
        """✅ Reporte válido completo"""
        location = EvidenceLocation(
            start_char=0,
            end_char=100,
            extraction_method=ExtractionMethod.PDF_TEXT
        )
        
        evidence = DocumentalEvidence(
            chunk_id="chunk_001",
            document_id="doc_001",
            location=location,
            content="Texto del documento"
        )
        
        finding = LegalFinding(
            statement="Afirmación objetiva respaldada por evidencia",
            evidence=[evidence]
        )
        
        report = LegalReport(
            case_id="CASE_001",
            issue_analyzed="Análisis de cumplimiento legal de documentación",
            findings=[finding],
            generated_at=datetime.utcnow()
        )
        
        assert report.case_id == "CASE_001"
        assert len(report.findings) == 1
        assert report.schema_version == "1.0.0"
        assert report.source_system == "phoenix_legal"
    
    def test_report_without_findings_rejected(self):
        """❌ Reporte sin findings → ValidationError"""
        with pytest.raises(ValidationError) as exc_info:
            LegalReport(
                case_id="CASE_001",
                issue_analyzed="Análisis sin hallazgos",
                findings=[],  # INVÁLIDO: lista vacía
                generated_at=datetime.utcnow()
            )
        
        assert "findings" in str(exc_info.value).lower()
    
    def test_report_without_case_id_rejected(self):
        """❌ Reporte sin case_id → ValidationError"""
        location = EvidenceLocation(
            start_char=0,
            end_char=100,
            extraction_method=ExtractionMethod.PDF_TEXT
        )
        
        evidence = DocumentalEvidence(
            chunk_id="chunk_001",
            document_id="doc_001",
            location=location,
            content="texto"
        )
        
        finding = LegalFinding(
            statement="Afirmación con evidencia",
            evidence=[evidence]
        )
        
        with pytest.raises(ValidationError):
            LegalReport(
                # case_id faltante
                issue_analyzed="Análisis",
                findings=[finding],
                generated_at=datetime.utcnow()
            )
    
    def test_report_get_all_evidence_ids(self):
        """✅ get_all_evidence_ids retorna todos los chunk_ids"""
        evidences1 = [
            DocumentalEvidence(
                chunk_id="chunk_001",
                document_id="doc_001",
                location=EvidenceLocation(
                    start_char=0,
                    end_char=100,
                    extraction_method=ExtractionMethod.PDF_TEXT
                ),
                content="texto 1"
            ),
            DocumentalEvidence(
                chunk_id="chunk_002",
                document_id="doc_001",
                location=EvidenceLocation(
                    start_char=100,
                    end_char=200,
                    extraction_method=ExtractionMethod.PDF_TEXT
                ),
                content="texto 2"
            )
        ]
        
        evidences2 = [
            DocumentalEvidence(
                chunk_id="chunk_003",
                document_id="doc_002",
                location=EvidenceLocation(
                    start_char=0,
                    end_char=50,
                    extraction_method=ExtractionMethod.PDF_TEXT
                ),
                content="texto 3"
            )
        ]
        
        findings = [
            LegalFinding(
                statement="Hallazgo 1 con múltiples evidencias",
                evidence=evidences1
            ),
            LegalFinding(
                statement="Hallazgo 2 con una evidencia",
                evidence=evidences2
            )
        ]
        
        report = LegalReport(
            case_id="CASE_001",
            issue_analyzed="Análisis completo",
            findings=findings,
            generated_at=datetime.utcnow()
        )
        
        all_ids = report.get_all_evidence_ids()
        assert len(all_ids) == 3
        assert "chunk_001" in all_ids
        assert "chunk_002" in all_ids
        assert "chunk_003" in all_ids
    
    def test_report_get_summary_stats(self):
        """✅ get_summary_stats retorna estadísticas correctas"""
        # Crear reporte con 2 findings, 3 evidencias total
        evidences1 = [
            DocumentalEvidence(
                chunk_id="chunk_001",
                document_id="doc_001",
                location=EvidenceLocation(
                    start_char=0,
                    end_char=100,
                    extraction_method=ExtractionMethod.PDF_TEXT
                ),
                content="texto"
            )
        ]
        
        evidences2 = [
            DocumentalEvidence(
                chunk_id="chunk_002",
                document_id="doc_001",
                location=EvidenceLocation(
                    start_char=100,
                    end_char=200,
                    extraction_method=ExtractionMethod.PDF_TEXT
                ),
                content="texto"
            ),
            DocumentalEvidence(
                chunk_id="chunk_003",
                document_id="doc_002",
                location=EvidenceLocation(
                    start_char=0,
                    end_char=100,
                    extraction_method=ExtractionMethod.PDF_TEXT
                ),
                content="texto"
            )
        ]
        
        findings = [
            LegalFinding(
                statement="Hallazgo 1 con una evidencia",
                evidence=evidences1
            ),
            LegalFinding(
                statement="Hallazgo 2 con dos evidencias",
                evidence=evidences2
            )
        ]
        
        report = LegalReport(
            case_id="CASE_001",
            issue_analyzed="Análisis de documentación legal",
            findings=findings,
            generated_at=datetime.utcnow()
        )
        
        stats = report.get_summary_stats()
        
        assert stats["total_findings"] == 2
        assert stats["total_evidences"] == 3
        assert stats["unique_chunks_used"] == 3
        assert stats["unique_documents_used"] == 2
        assert stats["avg_evidences_per_finding"] == 1.5


class TestSerializability:
    """Tests de serialización y determinismo."""
    
    def test_report_is_serializable(self):
        """✅ Reporte puede ser serializado a JSON"""
        location = EvidenceLocation(
            start_char=0,
            end_char=100,
            extraction_method=ExtractionMethod.PDF_TEXT
        )
        
        evidence = DocumentalEvidence(
            chunk_id="chunk_001",
            document_id="doc_001",
            location=location,
            content="texto"
        )
        
        finding = LegalFinding(
            statement="Afirmación con evidencia",
            evidence=[evidence]
        )
        
        report = LegalReport(
            case_id="CASE_001",
            issue_analyzed="Análisis de cumplimiento",
            findings=[finding],
            generated_at=datetime.utcnow()
        )
        
        # Debe poder serializar a dict
        report_dict = report.dict()
        assert isinstance(report_dict, dict)
        assert report_dict["case_id"] == "CASE_001"
        
        # Debe poder serializar a JSON
        report_json = report.json()
        assert isinstance(report_json, str)
        assert "CASE_001" in report_json
    
    def test_report_schema_is_stable(self):
        """✅ Schema del reporte es estable y versionado"""
        location = EvidenceLocation(
            start_char=0,
            end_char=100,
            extraction_method=ExtractionMethod.PDF_TEXT
        )
        
        evidence = DocumentalEvidence(
            chunk_id="chunk_001",
            document_id="doc_001",
            location=location,
            content="texto"
        )
        
        finding = LegalFinding(
            statement="Afirmación con evidencia",
            evidence=[evidence]
        )
        
        report = LegalReport(
            case_id="CASE_001",
            issue_analyzed="Análisis completo de cumplimiento legal",
            findings=[finding],
            generated_at=datetime.utcnow()
        )
        
        assert report.schema_version == "1.0.0"
        assert report.source_system == "phoenix_legal"


class TestNoAmbiguity:
    """Tests que verifican que no hay ambigüedad jurídica."""
    
    def test_every_statement_has_evidence(self):
        """
        GARANTÍA: Todo statement tiene evidencia asociada.
        NO se permite texto sin respaldo documental.
        """
        # Intentar crear finding sin evidencia debe fallar
        with pytest.raises(ValidationError):
            LegalFinding(
                statement="Afirmación sin respaldo",
                evidence=[]
            )
    
    def test_every_evidence_has_location(self):
        """
        GARANTÍA: Toda evidencia tiene location completa.
        NO se permite evidencia sin ubicación física.
        """
        # Intentar crear evidencia sin location debe fallar
        with pytest.raises(ValidationError):
            DocumentalEvidence(
                chunk_id="chunk_001",
                document_id="doc_001",
                # location faltante
                content="texto"
            )
    
    def test_output_is_verifiable(self):
        """
        GARANTÍA: La salida es verificable físicamente.
        Cada evidencia puede ser localizada en el documento original.
        """
        location = EvidenceLocation(
            page_start=5,
            page_end=5,
            start_char=1234,
            end_char=1567,
            extraction_method=ExtractionMethod.PDF_TEXT
        )
        
        evidence = DocumentalEvidence(
            chunk_id="chunk_test",
            document_id="doc_test",
            location=location,
            content="Texto verificable",
            filename="documento_legal.pdf"
        )
        
        # La evidencia tiene toda la información para localizar el texto:
        # - Archivo: documento_legal.pdf
        # - Página: 5
        # - Caracteres: 1234-1567
        # - Método: pdf_text
        assert evidence.filename == "documento_legal.pdf"
        assert evidence.location.page_start == 5
        assert evidence.location.start_char == 1234
        assert evidence.location.end_char == 1567


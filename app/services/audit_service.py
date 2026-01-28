"""
Servicio de análisis de auditoría.

Este servicio encapsula toda la lógica de negocio relacionada con:
- Ejecución del grafo de auditoría
- Validación de casos
- Generación de análisis
"""
from typing import Any, Optional

from app.core.exceptions import (
    CaseNotFoundException,
    InsufficientEvidenceException,
    LegalAnalysisException,
)
from app.models.case import Case
from app.models.document import Document
from app.services.base import BaseService


class AuditService(BaseService):
    """Servicio de análisis de auditoría."""

    def analyze_case(self, case_id: str, question: Optional[str] = None) -> dict[str, Any]:
        """
        Ejecuta análisis completo del caso.

        Args:
            case_id: ID del caso a analizar
            question: Pregunta específica del usuario (opcional)

        Returns:
            Dict con resultados del análisis

        Raises:
            CaseNotFoundException: Si el caso no existe
            InsufficientEvidenceException: Si falta documentación crítica
            LegalAnalysisException: Si falla el análisis
        """
        self._log_info("Starting case analysis", case_id=case_id, action="audit_start")

        try:
            # 1. Validar que el caso existe
            case = self._get_case_or_raise(case_id)

            # 2. Validar documentación mínima
            self._validate_case_documentation(case)

            # 3. Ejecutar grafo de auditoría
            result = self._run_audit_graph(case_id, question)

            # 4. Post-procesamiento
            enriched_result = self._enrich_result(result, case)

            self._log_info(
                "Case analysis completed",
                case_id=case_id,
                action="audit_complete",
                findings_count=len(enriched_result.get("findings", [])),
            )

            return enriched_result

        except Exception as e:
            phoenix_exc = self._handle_exception(e, "analyze_case", case_id)
            raise phoenix_exc

    def _get_case_or_raise(self, case_id: str) -> Case:
        """
        Obtiene caso o lanza excepción.

        Args:
            case_id: ID del caso

        Returns:
            Case: Objeto del caso

        Raises:
            CaseNotFoundException: Si no existe
        """
        case = self.db.query(Case).filter(Case.case_id == case_id).first()

        if not case:
            raise CaseNotFoundException(case_id=case_id)

        return case

    def _validate_case_documentation(self, case: Case) -> None:
        """
        Valida que el caso tenga documentación mínima.

        Args:
            case: Objeto del caso

        Raises:
            InsufficientEvidenceException: Si falta documentación
        """
        # Contar documentos
        doc_count = self.db.query(Document).filter(Document.case_id == case.case_id).count()

        if doc_count == 0:
            raise InsufficientEvidenceException(
                reason="El caso no tiene documentos cargados", details={"case_id": case.case_id}
            )

        self._log_info(
            "Case documentation validated",
            case_id=case.case_id,
            action="validate_docs",
            document_count=doc_count,
        )

    def _run_audit_graph(self, case_id: str, question: Optional[str] = None) -> dict[str, Any]:
        """
        Ejecuta el grafo de auditoría.

        Args:
            case_id: ID del caso
            question: Pregunta opcional

        Returns:
            Dict con resultados del grafo
        """
        from app.graphs.audit_graph import build_audit_graph

        self._log_info("Executing audit graph", case_id=case_id, action="audit_graph_start")

        try:
            # Construir grafo
            graph = build_audit_graph()

            # Estado inicial
            initial_state = {
                "case_id": case_id,
                "question": question or "Análisis general del caso",
                "documents": [],
                "timeline": [],
                "findings": [],
                "llm_insights": {},
            }

            # Ejecutar grafo
            result = graph.invoke(initial_state)

            return result

        except Exception as e:
            raise LegalAnalysisException(
                message="Error ejecutando grafo de auditoría",
                details={"case_id": case_id},
                original_error=e,
            )

    def _enrich_result(self, result: dict[str, Any], case: Case) -> dict[str, Any]:
        """
        Enriquece resultado con metadata adicional.

        Args:
            result: Resultado del grafo
            case: Objeto del caso

        Returns:
            Dict con resultado enriquecido
        """
        enriched = result.copy()

        # Añadir metadata del caso
        enriched["case_metadata"] = {
            "case_id": case.case_id,
            "company_name": case.company_name,
            "created_at": case.created_at.isoformat() if case.created_at else None,
        }

        # Calcular scores
        enriched["quality_score"] = self._calculate_quality_score(result)

        return enriched

    def _calculate_quality_score(self, result: dict[str, Any]) -> int:
        """
        Calcula score de calidad del análisis.

        Args:
            result: Resultado del análisis

        Returns:
            Score de 0-100
        """
        score = 100

        # Penalizar por falta de documentos
        doc_count = len(result.get("documents", []))
        if doc_count < 3:
            score -= 20

        # Penalizar si no hay timeline
        if not result.get("timeline"):
            score -= 15

        # Penalizar si no hay findings
        findings_count = len(result.get("findings", []))
        if findings_count == 0:
            score -= 30

        return max(0, score)


class CaseService(BaseService):
    """Servicio para gestión de casos."""

    def create_case(self, case_id: str, company_name: str, **kwargs) -> Case:
        """
        Crea un nuevo caso.

        Args:
            case_id: ID único del caso
            company_name: Nombre de la empresa
            **kwargs: Campos adicionales

        Returns:
            Case: Caso creado

        Raises:
            DuplicateCaseException: Si ya existe
        """
        from app.core.exceptions import DuplicateCaseException

        # Verificar si existe
        existing = self.db.query(Case).filter(Case.case_id == case_id).first()

        if existing:
            raise DuplicateCaseException(case_id=case_id)

        # Crear caso
        case = Case(case_id=case_id, company_name=company_name, **kwargs)

        self.db.add(case)
        self.db.commit()
        self.db.refresh(case)

        self._log_info("Case created", case_id=case_id, action="case_create")

        return case

    def get_case(self, case_id: str) -> Case:
        """
        Obtiene un caso por ID.

        Args:
            case_id: ID del caso

        Returns:
            Case: Objeto del caso

        Raises:
            CaseNotFoundException: Si no existe
        """
        case = self.db.query(Case).filter(Case.case_id == case_id).first()

        if not case:
            raise CaseNotFoundException(case_id=case_id)

        return case

    def list_cases(self, limit: int = 100, offset: int = 0):
        """
        Lista todos los casos.

        Args:
            limit: Límite de resultados
            offset: Offset para paginación

        Returns:
            List[Case]: Lista de casos
        """
        return self.db.query(Case).offset(offset).limit(limit).all()

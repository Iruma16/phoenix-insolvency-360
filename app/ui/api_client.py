"""
Cliente API para conectar Streamlit con FastAPI backend.

Este módulo centraliza todas las llamadas HTTP al backend endurecido,
permitiendo que la UI consume los endpoints oficiales (PANTALLAS 0-6).

Incluye:
- Validación Pydantic de respuestas
- Manejo de errores específico por código HTTP
- Timeouts explícitos
"""
from typing import Any, Optional

import requests
from pydantic import ValidationError
from requests.exceptions import ConnectionError, Timeout

# Importar modelos Pydantic del backend para validación
from app.services.financial_analysis import FinancialAnalysisResult

# =========================================================
# EXCEPCIONES PERSONALIZADAS
# =========================================================


class PhoenixLegalAPIError(Exception):
    """Error base para todas las excepciones de la API."""

    pass


class CaseNotFoundError(PhoenixLegalAPIError):
    """Caso no encontrado (404)."""

    pass


class ValidationErrorAPI(PhoenixLegalAPIError):
    """Error de validación de datos (422)."""

    pass


class ParsingError(PhoenixLegalAPIError):
    """Error al procesar/parsear documentos (500)."""

    pass


class ServerError(PhoenixLegalAPIError):
    """Error interno del servidor (500)."""

    pass


class PhoenixLegalClient:
    """Cliente para interactuar con Phoenix Legal API."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        """
        Inicializa el cliente API.

        Args:
            base_url: URL base del servidor FastAPI
        """
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        # NO forzar Content-Type globalmente - requests lo establece automáticamente según el tipo de petición

    # =========================================
    # HEALTH CHECK
    # =========================================

    def health_check(self) -> dict[str, Any]:
        """
        Verifica que el servidor API esté funcionando.

        Returns:
            Estado del servidor
        """
        response = self.session.get(f"{self.base_url}/")
        response.raise_for_status()
        return response.json()

    # =========================================
    # PANTALLA 0: GESTIÓN DE CASOS
    # =========================================

    def create_case(self, name: str, client_ref: Optional[str] = None) -> dict[str, Any]:
        """
        Crea un nuevo caso.

        Args:
            name: Nombre del caso
            client_ref: Referencia del cliente (opcional)

        Returns:
            CaseSummary con case_id generado
        """
        payload = {"name": name}
        if client_ref:
            payload["client_ref"] = client_ref

        response = self.session.post(f"{self.base_url}/api/cases", json=payload)
        response.raise_for_status()
        return response.json()

    def list_cases(self) -> list[dict[str, Any]]:
        """
        Lista todos los casos existentes.

        Returns:
            Lista de CaseSummary
        """
        response = self.session.get(f"{self.base_url}/api/cases")
        response.raise_for_status()
        return response.json()

    def get_case(self, case_id: str) -> dict[str, Any]:
        """
        Obtiene un caso específico.

        Args:
            case_id: ID del caso

        Returns:
            CaseSummary del caso
        """
        response = self.session.get(f"{self.base_url}/api/cases/{case_id}")
        response.raise_for_status()
        return response.json()

    # =========================================
    # PANTALLA 1: DOCUMENTOS
    # =========================================

    def check_duplicates_before_upload(
        self, case_id: str, files: list[tuple]
    ) -> list[dict[str, Any]]:
        """
        Verifica si los archivos son duplicados ANTES de subirlos.

        Args:
            case_id: ID del caso
            files: Lista de tuplas (filename, file_content)

        Returns:
            Lista de diccionarios con información de duplicación:
                - filename: Nombre del archivo
                - is_duplicate: True si es duplicado
                - duplicate_of: Nombre del archivo duplicado
                - should_upload: False si es duplicado
        """

        def get_mime_type(filename: str) -> str:
            """Detecta el tipo MIME según la extensión del archivo."""
            import os

            ext = os.path.splitext(filename)[1].lower()
            mime_types = {
                ".pdf": "application/pdf",
                ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ".xls": "application/vnd.ms-excel",
                ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ".doc": "application/msword",
                ".txt": "text/plain",
                ".csv": "text/csv",
            }
            return mime_types.get(ext, "application/octet-stream")

        files_payload = [
            ("files", (filename, content, get_mime_type(filename))) for filename, content in files
        ]

        response = self.session.post(
            f"{self.base_url}/api/cases/{case_id}/documents/check-duplicates", files=files_payload
        )
        response.raise_for_status()
        return response.json()

    def upload_documents(self, case_id: str, files: list[tuple]) -> list[dict[str, Any]]:
        """
        Sube documentos a un caso.

        Args:
            case_id: ID del caso
            files: Lista de tuplas (filename, file_content)

        Returns:
            Lista de DocumentSummary
        """

        def get_mime_type(filename: str) -> str:
            """Detecta el tipo MIME según la extensión del archivo."""
            import os

            ext = os.path.splitext(filename)[1].lower()
            mime_types = {
                ".pdf": "application/pdf",
                ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ".xls": "application/vnd.ms-excel",
                ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ".doc": "application/msword",
                ".txt": "text/plain",
                ".csv": "text/csv",
            }
            return mime_types.get(ext, "application/octet-stream")

        # DEBUG: Verificar qué estamos recibiendo
        print(f"[DEBUG] upload_documents called with {len(files)} files")
        for i, (fname, content) in enumerate(files):
            print(f"[DEBUG] File {i}: {fname}, size: {len(content)} bytes")

        files_payload = [
            ("files", (filename, content, get_mime_type(filename))) for filename, content in files
        ]

        print(f"[DEBUG] Prepared {len(files_payload)} items for upload")
        print(f"[DEBUG] URL: {self.base_url}/api/cases/{case_id}/documents")

        response = self.session.post(
            f"{self.base_url}/api/cases/{case_id}/documents", files=files_payload
        )

        print(f"[DEBUG] Response status: {response.status_code}")
        print(f"[DEBUG] Response headers: {response.headers}")

        response.raise_for_status()
        return response.json()

    def get_duplicate_pairs(self, case_id: str) -> list[dict[str, Any]]:
        """
        Obtiene lista de pares de documentos duplicados del caso.

        Args:
            case_id: ID del caso

        Returns:
            Lista de DuplicatePairSummary con información de cada par
        """
        response = self.session.get(f"{self.base_url}/api/cases/{case_id}/documents/duplicates")
        response.raise_for_status()
        return response.json()

    def resolve_duplicate_action(
        self,
        case_id: str,
        document_id: str,
        action: str,
        reason: Optional[str] = None,
        decided_by: Optional[str] = None,
        expected_version: int = 0,
    ) -> dict[str, Any]:
        """
        Resuelve acción sobre duplicado CON LOCK OPTIMISTA.

        CRÍTICO: Incluye expected_version para control de concurrencia.

        Args:
            case_id: ID del caso
            document_id: ID del documento
            action: keep_both/mark_duplicate/exclude_from_analysis
            reason: Razón (obligatoria para legal)
            decided_by: Usuario que decide
            expected_version: Versión esperada del par (control concurrencia)

        Returns:
            DocumentSummary actualizado

        Raises:
            409: Si otro usuario modificó el par (versión no coincide)
        """
        payload = {"action": action}
        if reason:
            payload["reason"] = reason
        if decided_by:
            payload["decided_by"] = decided_by

        response = self.session.patch(
            f"{self.base_url}/api/cases/{case_id}/documents/{document_id}/duplicate-action",
            params={"expected_version": expected_version},
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    def simulate_batch_duplicate_action(
        self, case_id: str, action: str, reason: str, pair_ids: list[str], user: str
    ) -> dict[str, Any]:
        """
        SIMULA batch action sin aplicarla (seguro nuclear).

        CRÍTICO: NUNCA aplica cambios, solo retorna impacto.

        Args:
            case_id: ID del caso
            action: Acción a simular
            reason: Razón común
            pair_ids: Lista de pair_ids
            user: Usuario solicitante

        Returns:
            Dict con:
            - total_pairs: int
            - warnings: List[str]
            - decisions_overwritten: int
            - safe_to_proceed: bool
            - impact_summary: str
        """
        response = self.session.post(
            f"{self.base_url}/api/cases/{case_id}/documents/duplicates/simulate-batch",
            json={"action": action, "reason": reason, "pair_ids": pair_ids, "user": user},
        )
        response.raise_for_status()
        return response.json()

    def list_documents(self, case_id: str) -> list[dict[str, Any]]:
        """
        Lista documentos de un caso.

        Args:
            case_id: ID del caso

        Returns:
            Lista de DocumentSummary
        """
        response = self.session.get(f"{self.base_url}/api/cases/{case_id}/documents")
        response.raise_for_status()
        return response.json()

    # =========================================
    # PANTALLA 2: CHUNKS (EXPLORACIÓN)
    # =========================================

    def list_chunks(
        self,
        case_id: str,
        document_id: Optional[str] = None,
        text_contains: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Lista chunks de un caso.

        Args:
            case_id: ID del caso
            document_id: Filtrar por documento (opcional)
            text_contains: Buscar texto literal (opcional)
            limit: Número máximo de resultados

        Returns:
            Lista de ChunkSummary
        """
        params = {"limit": limit}
        if document_id:
            params["document_id"] = document_id
        if text_contains:
            params["text_contains"] = text_contains

        response = self.session.get(f"{self.base_url}/api/cases/{case_id}/chunks", params=params)
        response.raise_for_status()
        return response.json()

    # =========================================
    # PANTALLA 3: ANÁLISIS TÉCNICO / ALERTAS
    # =========================================

    def get_analysis_alerts(self, case_id: str) -> list[dict[str, Any]]:
        """
        Obtiene alertas técnicas de un caso.

        Args:
            case_id: ID del caso

        Returns:
            Lista de AnalysisAlert
        """
        response = self.session.get(f"{self.base_url}/api/cases/{case_id}/analysis/alerts")
        response.raise_for_status()
        return response.json()

    def get_alerts(self, case_id: str) -> list[dict[str, Any]]:
        """
        Alias de compatibilidad para alertas técnicas.

        Históricamente la UI llamó a `get_alerts()`. El nombre oficial es
        `get_analysis_alerts()` y consume el endpoint:
        GET /api/cases/{case_id}/analysis/alerts
        """
        return self.get_analysis_alerts(case_id)

    def get_financial_analysis(self, case_id: str) -> FinancialAnalysisResult:
        """
        Obtiene análisis financiero completo del caso con validación Pydantic.

        Devuelve análisis financiero concursal con:
        - Datos contables estructurados (Balance + PyG)
        - Clasificación de créditos (TRLC)
        - Ratios financieros (semáforo)
        - Detección de insolvencia (multicapa)
        - Timeline de eventos críticos

        Args:
            case_id: ID del caso

        Returns:
            FinancialAnalysisResult validado con Pydantic

        Raises:
            CaseNotFoundError: Si el caso no existe (404)
            ValidationErrorAPI: Si hay error de validación (422)
            ParsingError: Si el backend falló al parsear documentos (500)
            ServerError: Si hay error interno del servidor (500)
            PhoenixLegalAPIError: Para timeout, conexión u otros errores
        """
        try:
            response = self.session.get(
                f"{self.base_url}/api/cases/{case_id}/financial-analysis",
                timeout=30,  # Timeout explícito de 30 segundos
            )

            # Manejo fino de errores HTTP por código
            if response.status_code == 404:
                try:
                    error_detail = response.json().get("detail", f"Caso '{case_id}' no encontrado")
                except:
                    error_detail = f"Caso '{case_id}' no encontrado"
                raise CaseNotFoundError(error_detail)

            elif response.status_code == 422:
                try:
                    error_detail = response.json().get("detail", "Error de validación")
                except:
                    error_detail = "Error de validación"
                raise ValidationErrorAPI(f"Datos inválidos: {error_detail}")

            elif response.status_code == 500:
                try:
                    error_detail = response.json().get("detail", "Error interno del servidor")
                except:
                    # Si la respuesta no es JSON, usar el texto raw
                    error_detail = (
                        response.text[:500] if response.text else "Error interno del servidor"
                    )

                # Distinguir entre error de parsing y error genérico
                if "parse" in str(error_detail).lower() or "extract" in str(error_detail).lower():
                    raise ParsingError(f"Error al procesar documentos: {error_detail}")
                else:
                    raise ServerError(f"Error del servidor: {error_detail}")

            # Si hay otro código de error, usar raise_for_status genérico
            response.raise_for_status()

            # Validar respuesta con Pydantic
            data = response.json()

            try:
                return FinancialAnalysisResult(**data)
            except ValidationError as e:
                # Si el esquema no coincide con lo esperado
                raise PhoenixLegalAPIError(
                    f"Respuesta del servidor no coincide con esquema esperado. "
                    f"El backend devolvió datos con estructura incorrecta: {e}"
                )

        except Timeout:
            raise PhoenixLegalAPIError(
                "Timeout: El análisis financiero está tardando demasiado (>30s). "
                "Esto puede ocurrir con muchos documentos o documentos muy grandes."
            )

        except ConnectionError:
            raise PhoenixLegalAPIError(
                "No se pudo conectar al servidor API. "
                "Verifica que el servidor esté levantado en http://localhost:8000"
            )

    # =========================================
    # PANTALLA 4: INFORME LEGAL
    # =========================================

    def generate_legal_report(self, case_id: str) -> dict[str, Any]:
        """
        Genera informe legal para un caso.

        Args:
            case_id: ID del caso

        Returns:
            LegalReport generado
        """
        response = self.session.post(f"{self.base_url}/api/cases/{case_id}/legal-report")
        response.raise_for_status()
        return response.json()

    # =========================================
    # PANTALLA 5: TRACE Y MANIFEST
    # =========================================

    def get_trace(self, case_id: str) -> dict[str, Any]:
        """
        Obtiene trace de ejecución de un caso.

        Args:
            case_id: ID del caso

        Returns:
            ExecutionTrace
        """
        response = self.session.get(f"{self.base_url}/api/cases/{case_id}/trace")
        response.raise_for_status()
        return response.json()

    def get_manifest(self, case_id: str) -> dict[str, Any]:
        """
        Obtiene manifest certificado de un caso.

        Args:
            case_id: ID del caso

        Returns:
            HardManifest
        """
        response = self.session.get(f"{self.base_url}/api/cases/{case_id}/manifest")
        response.raise_for_status()
        return response.json()

    def certify_execution(self, case_id: str) -> dict[str, Any]:
        """
        Certifica la ejecución de un caso (genera manifest).

        Args:
            case_id: ID del caso

        Returns:
            HardManifest certificado
        """
        response = self.session.post(f"{self.base_url}/api/cases/{case_id}/manifest")
        response.raise_for_status()
        return response.json()

    # =========================================
    # PANTALLA 6: DESCARGA PDF
    # =========================================

    def download_pdf_report(self, case_id: str) -> bytes:
        """
        Descarga informe legal en PDF certificado.

        Args:
            case_id: ID del caso

        Returns:
            Contenido del PDF (bytes)
        """
        response = self.session.get(f"{self.base_url}/api/cases/{case_id}/legal-report/pdf")
        response.raise_for_status()
        return response.content

    # =========================================
    # TIMELINE PAGINADO (ESCALABLE)
    # =========================================

    def get_timeline_paginated(
        self,
        case_id: str,
        page: int = 1,
        page_size: int = 20,
        event_type: Optional[str] = None,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        search: Optional[str] = None,
        sort_by: str = "date",
        sort_order: str = "desc",
        include_stats: bool = False,
    ) -> dict[str, Any]:
        """
        Obtiene timeline paginado con filtros en backend.

        ESCALABLE: Query paginada en BD con índices optimizados.
        Filtros aplicados en SQL, no en memoria.

        Args:
            case_id: ID del caso
            page: Número de página (1-based)
            page_size: Eventos por página (1-100)
            event_type: Filtro opcional por tipo
            category: Filtro opcional por categoría
            severity: Filtro opcional por severidad
            start_date: Filtro fecha inicio (ISO format YYYY-MM-DD)
            end_date: Filtro fecha fin (ISO format YYYY-MM-DD)
            search: Búsqueda en descripción (mín 3 chars)
            sort_by: Campo para ordenar (date/amount/severity)
            sort_order: Orden (asc/desc)
            include_stats: Incluir estadísticas agregadas

        Returns:
            PaginatedTimelineResponse con eventos de la página
        """
        params = {
            "page": page,
            "page_size": page_size,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "include_stats": include_stats,
        }

        # Agregar filtros opcionales solo si están presentes
        if event_type:
            params["event_type"] = event_type
        if category:
            params["category"] = category
        if severity:
            params["severity"] = severity
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if search:
            params["search"] = search

        response = self.session.get(f"{self.base_url}/api/cases/{case_id}/timeline", params=params)
        response.raise_for_status()
        return response.json()

    def get_timeline_types(self, case_id: str) -> list[str]:
        """
        Obtiene lista de tipos de eventos disponibles en el timeline.

        Útil para construir filtros dinámicos en UI.

        Args:
            case_id: ID del caso

        Returns:
            Lista de tipos de eventos únicos
        """
        response = self.session.get(f"{self.base_url}/api/cases/{case_id}/timeline/types")
        response.raise_for_status()
        return response.json()

    def get_timeline_statistics(self, case_id: str) -> dict[str, Any]:
        """
        Obtiene estadísticas agregadas del timeline.

        Sin paginación, devuelve stats globales del timeline completo.

        Args:
            case_id: ID del caso

        Returns:
            Dict con estadísticas (total, por tipo, por severidad, etc.)
        """
        response = self.session.get(f"{self.base_url}/api/cases/{case_id}/timeline/statistics")
        response.raise_for_status()
        return response.json()

    # =========================================
    # UTILIDADES
    # =========================================

"""
Cliente API para conectar Streamlit con FastAPI backend.

Este módulo centraliza todas las llamadas HTTP al backend endurecido,
permitiendo que la UI consume los endpoints oficiales (PANTALLAS 0-6).
"""
import requests
from typing import Optional, List, Dict, Any
from datetime import datetime


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
    
    def health_check(self) -> Dict[str, Any]:
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
    
    def create_case(self, name: str, client_ref: Optional[str] = None) -> Dict[str, Any]:
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
        
        response = self.session.post(
            f"{self.base_url}/api/cases",
            json=payload
        )
        response.raise_for_status()
        return response.json()
    
    def list_cases(self) -> List[Dict[str, Any]]:
        """
        Lista todos los casos existentes.
        
        Returns:
            Lista de CaseSummary
        """
        response = self.session.get(f"{self.base_url}/api/cases")
        response.raise_for_status()
        return response.json()
    
    def get_case(self, case_id: str) -> Dict[str, Any]:
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
    
    def upload_documents(
        self, 
        case_id: str, 
        files: List[tuple]
    ) -> List[Dict[str, Any]]:
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
                '.pdf': 'application/pdf',
                '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                '.xls': 'application/vnd.ms-excel',
                '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                '.doc': 'application/msword',
                '.txt': 'text/plain',
                '.csv': 'text/csv',
            }
            return mime_types.get(ext, 'application/octet-stream')
        
        # DEBUG: Verificar qué estamos recibiendo
        print(f"[DEBUG] upload_documents called with {len(files)} files")
        for i, (fname, content) in enumerate(files):
            print(f"[DEBUG] File {i}: {fname}, size: {len(content)} bytes")
        
        files_payload = [
            ("files", (filename, content, get_mime_type(filename)))
            for filename, content in files
        ]
        
        print(f"[DEBUG] Prepared {len(files_payload)} items for upload")
        print(f"[DEBUG] URL: {self.base_url}/api/cases/{case_id}/documents")
        
        response = self.session.post(
            f"{self.base_url}/api/cases/{case_id}/documents",
            files=files_payload
        )
        
        print(f"[DEBUG] Response status: {response.status_code}")
        print(f"[DEBUG] Response headers: {response.headers}")
        
        response.raise_for_status()
        return response.json()
    
    def list_documents(self, case_id: str) -> List[Dict[str, Any]]:
        """
        Lista documentos de un caso.
        
        Args:
            case_id: ID del caso
            
        Returns:
            Lista de DocumentSummary
        """
        response = self.session.get(
            f"{self.base_url}/api/cases/{case_id}/documents"
        )
        response.raise_for_status()
        return response.json()
    
    def resolve_duplicate_action(
        self, 
        case_id: str, 
        document_id: str, 
        action: str
    ) -> Dict[str, Any]:
        """
        Resuelve la acción a tomar sobre un documento duplicado.
        
        FASE 2A: Permite al abogado decidir qué hacer con duplicados.
        
        Args:
            case_id: ID del caso
            document_id: ID del documento
            action: Acción (keep_both, mark_duplicate, exclude_from_analysis)
            
        Returns:
            DocumentSummary actualizado
        """
        response = self.session.patch(
            f"{self.base_url}/api/cases/{case_id}/documents/{document_id}/duplicate-action",
            params={"action": action}
        )
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
        limit: int = 50
    ) -> List[Dict[str, Any]]:
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
        
        response = self.session.get(
            f"{self.base_url}/api/cases/{case_id}/chunks",
            params=params
        )
        response.raise_for_status()
        return response.json()
    
    # =========================================
    # PANTALLA 3: ANÁLISIS TÉCNICO / ALERTAS
    # =========================================
    
    def get_analysis_alerts(self, case_id: str) -> List[Dict[str, Any]]:
        """
        Obtiene alertas técnicas de un caso.
        
        Args:
            case_id: ID del caso
            
        Returns:
            Lista de AnalysisAlert
        """
        response = self.session.get(
            f"{self.base_url}/api/cases/{case_id}/analysis/alerts"
        )
        response.raise_for_status()
        return response.json()
    
    # =========================================
    # PANTALLA 4: INFORME LEGAL
    # =========================================
    
    def generate_legal_report(self, case_id: str) -> Dict[str, Any]:
        """
        Genera informe legal para un caso.
        
        Args:
            case_id: ID del caso
            
        Returns:
            LegalReport generado
        """
        response = self.session.post(
            f"{self.base_url}/api/cases/{case_id}/legal-report"
        )
        response.raise_for_status()
        return response.json()
    
    # =========================================
    # PANTALLA 5: TRACE Y MANIFEST
    # =========================================
    
    def get_trace(self, case_id: str) -> Dict[str, Any]:
        """
        Obtiene trace de ejecución de un caso.
        
        Args:
            case_id: ID del caso
            
        Returns:
            ExecutionTrace
        """
        response = self.session.get(
            f"{self.base_url}/api/cases/{case_id}/trace"
        )
        response.raise_for_status()
        return response.json()
    
    def get_manifest(self, case_id: str) -> Dict[str, Any]:
        """
        Obtiene manifest certificado de un caso.
        
        Args:
            case_id: ID del caso
            
        Returns:
            HardManifest
        """
        response = self.session.get(
            f"{self.base_url}/api/cases/{case_id}/manifest"
        )
        response.raise_for_status()
        return response.json()
    
    def certify_execution(self, case_id: str) -> Dict[str, Any]:
        """
        Certifica la ejecución de un caso (genera manifest).
        
        Args:
            case_id: ID del caso
            
        Returns:
            HardManifest certificado
        """
        response = self.session.post(
            f"{self.base_url}/api/cases/{case_id}/manifest"
        )
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
        response = self.session.get(
            f"{self.base_url}/api/cases/{case_id}/legal-report/pdf"
        )
        response.raise_for_status()
        return response.content
    
    # =========================================
    # UTILIDADES
    # =========================================
    
    def health_check(self) -> Dict[str, Any]:
        """
        Verifica que el servidor está funcionando.
        
        Returns:
            Info del servicio
        """
        response = self.session.get(f"{self.base_url}/")
        response.raise_for_status()
        return response.json()

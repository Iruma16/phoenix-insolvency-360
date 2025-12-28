"""
API endpoints para gestión de documentos e ingesta.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.folder_ingestion import ingest_folder, ingest_file_from_path
from app.services.document_quality import get_document_quality_summary
from app.models.document import Document


router = APIRouter(prefix="/documents", tags=["Documents"])


# =========================================================
# SCHEMAS
# =========================================================

class FolderIngestionRequest(BaseModel):
    folder_path: str
    case_id: str
    doc_type: Optional[str] = None
    source: Optional[str] = "api_upload"
    recursive: bool = True
    date_start: Optional[datetime] = None
    date_end: Optional[datetime] = None


class FolderIngestionResponse(BaseModel):
    success: bool
    total_files: int
    processed: int
    skipped: int
    errors: int
    warnings_count: int = 0  # ✅ Número de warnings
    warnings: List[str] = []  # ✅ Lista de warnings
    message: str
    document_ids: List[str] = []


class FileIngestionRequest(BaseModel):
    file_path: str
    case_id: str
    doc_type: Optional[str] = None
    source: Optional[str] = "api_upload"
    date_start: Optional[datetime] = None
    date_end: Optional[datetime] = None


class FileIngestionResponse(BaseModel):
    success: bool
    document_id: Optional[str] = None
    message: str


# =========================================================
# ENDPOINTS
# =========================================================

@router.post("/ingest-folder", response_model=FolderIngestionResponse)
def ingest_folder_endpoint(
    request: FolderIngestionRequest,
    db: Session = Depends(get_db),
):
    """
    Ingiere todos los archivos soportados de una carpeta.
    
    Formatos soportados: PDF, TXT, DOCX, CSV, XLS, XLSX
    """
    try:
        folder_path = Path(request.folder_path)
        
        if not folder_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"La carpeta no existe: {request.folder_path}"
            )
        
        if not folder_path.is_dir():
            raise HTTPException(
                status_code=400,
                detail=f"La ruta no es una carpeta: {request.folder_path}"
            )
        
        stats = ingest_folder(
            db=db,
            folder_path=folder_path,
            case_id=request.case_id,
            doc_type=request.doc_type,
            source=request.source,
            recursive=request.recursive,
            date_start=request.date_start,
            date_end=request.date_end,
        )
        
        document_ids = [str(doc.document_id) for doc in stats["documents"]]
        
        return FolderIngestionResponse(
            success=True,
            total_files=stats["total_files"],
            processed=stats["processed"],
            skipped=stats["skipped"],
            errors=stats["errors"],
            warnings_count=len(stats.get("warnings", [])),  # ✅ Contar warnings
            warnings=stats.get("warnings", []),  # ✅ Incluir warnings
            message=f"Procesados {stats['processed']} archivos correctamente",
            document_ids=document_ids,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error procesando carpeta: {str(e)}"
        )


@router.post("/ingest-file", response_model=FileIngestionResponse)
def ingest_file_endpoint(
    request: FileIngestionRequest,
    db: Session = Depends(get_db),
):
    """
    Ingiere un archivo individual.
    
    Formatos soportados: PDF, TXT, DOCX, CSV, XLS, XLSX
    """
    try:
        file_path = Path(request.file_path)
        
        if not file_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"El archivo no existe: {request.file_path}"
            )
        
        if not file_path.is_file():
            raise HTTPException(
                status_code=400,
                detail=f"La ruta no es un archivo: {request.file_path}"
            )
        
        document, warnings = ingest_file_from_path(
            db=db,
            file_path=file_path,
            case_id=request.case_id,
            doc_type=request.doc_type,
            source=request.source,
            date_start=request.date_start,
            date_end=request.date_end,
        )
        
        if document is None:
            # Si hay warnings, incluirlos en el error
            error_detail = "No se pudo procesar el archivo. Verifica el formato y los logs."
            if warnings:
                error_detail += f" Warnings: {'; '.join(warnings)}"
            raise HTTPException(
                status_code=500,
                detail=error_detail
            )
        
        message = f"Archivo procesado correctamente: {document.filename}"
        if warnings:
            message += f" ({len(warnings)} warning(s))"
        
        return FileIngestionResponse(
            success=True,
            document_id=str(document.document_id),
            message=message,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error procesando archivo: {str(e)}"
        )


@router.get("/list/{case_id}")
def list_documents(
    case_id: str,
    db: Session = Depends(get_db),
):
    """
    Lista todos los documentos de un caso.
    """
    documents = (
        db.query(Document)
        .filter(Document.case_id == case_id)
        .all()
    )
    
    return {
        "case_id": case_id,
        "total": len(documents),
        "documents": [
            {
                "document_id": doc.document_id,
                "filename": doc.filename,
                "doc_type": doc.doc_type,
                "file_format": doc.file_format,
                "source": doc.source,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
            }
            for doc in documents
        ]
    }


@router.get("/quality/{case_id}")
def get_case_quality(
    case_id: str,
    db: Session = Depends(get_db),
):
    """
    Obtiene un resumen de calidad documental para un caso.
    
    Incluye:
    - Score de calidad (0-100)
    - Nivel de calidad (excelente, buena, regular, baja, crítica)
    - Estadísticas de documentos, chunks y embeddings
    - Distribución por formato y tipo
    - Issues detectados
    """
    try:
        summary = get_document_quality_summary(db=db, case_id=case_id)
        return summary
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error generando resumen de calidad: {str(e)}"
        )


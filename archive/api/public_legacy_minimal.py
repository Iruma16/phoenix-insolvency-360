"""
API REST pública para Phoenix Legal.

Endpoints mínimos para uso externo del sistema.
"""
import os
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, File, UploadFile, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.variables import DATA
from app.graphs.audit_graph import build_audit_graph


# Inicializar FastAPI
app = FastAPI(
    title="Phoenix Legal API",
    description="API REST para análisis automatizado de casos concursales",
    version="1.0.0"
)

# Construir grafo una vez
graph = build_audit_graph()


# Modelos Pydantic
class CaseCreate(BaseModel):
    """Modelo para creación de caso."""
    case_id: str
    company_name: Optional[str] = "Empresa Desconocida"
    sector: Optional[str] = "Desconocido"
    size: Optional[str] = "PYME"


class AnalysisResponse(BaseModel):
    """Respuesta del análisis."""
    case_id: str
    status: str
    overall_risk: Optional[str] = None
    risks_count: int
    legal_findings_count: int
    pdf_path: Optional[str] = None
    message: str


# Endpoints

@app.get("/")
async def root():
    """Endpoint raíz."""
    return {
        "service": "Phoenix Legal API",
        "version": "1.0.0",
        "status": "operational",
        "endpoints": [
            "POST /cases",
            "POST /cases/{case_id}/documents",
            "POST /cases/{case_id}/analyze",
            "GET /cases/{case_id}/reports/latest"
        ]
    }


@app.post("/cases", status_code=status.HTTP_201_CREATED)
async def create_case(case_data: CaseCreate):
    """
    Crea un nuevo caso en el sistema.
    
    Args:
        case_data: Datos del caso a crear
    
    Returns:
        Confirmación de creación con rutas
    """
    case_id = case_data.case_id
    
    # Validar que el case_id no exista
    case_dir = DATA / "cases" / case_id
    if case_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El caso {case_id} ya existe"
        )
    
    # Crear estructura de directorios
    documents_dir = case_dir / "documents"
    reports_dir = case_dir / "reports"
    
    documents_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    # Crear metadata básica
    metadata = {
        "case_id": case_id,
        "company_name": case_data.company_name,
        "sector": case_data.sector,
        "size": case_data.size,
        "status": "created",
        "documents_count": 0
    }
    
    import json
    metadata_file = case_dir / "metadata.json"
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    return {
        "case_id": case_id,
        "status": "created",
        "paths": {
            "documents": str(documents_dir),
            "reports": str(reports_dir)
        },
        "message": f"Caso {case_id} creado correctamente"
    }


@app.post("/cases/{case_id}/documents")
async def upload_document(case_id: str, file: UploadFile = File(...)):
    """
    Sube un documento al caso especificado.
    
    Args:
        case_id: ID del caso
        file: Archivo a subir (PDF, TXT, etc.)
    
    Returns:
        Confirmación de subida
    """
    # Validar que el caso exista
    case_dir = DATA / "cases" / case_id
    if not case_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"El caso {case_id} no existe. Créalo primero con POST /cases"
        )
    
    # Guardar documento
    documents_dir = case_dir / "documents"
    documents_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = documents_dir / file.filename
    
    # Escribir archivo
    content = await file.read()
    with open(file_path, 'wb') as f:
        f.write(content)
    
    # Actualizar metadata
    metadata_file = case_dir / "metadata.json"
    if metadata_file.exists():
        import json
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)
        
        metadata['documents_count'] = metadata.get('documents_count', 0) + 1
        
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
    
    return {
        "case_id": case_id,
        "filename": file.filename,
        "size": len(content),
        "path": str(file_path),
        "message": f"Documento {file.filename} subido correctamente"
    }


@app.post("/cases/{case_id}/analyze", response_model=AnalysisResponse)
async def analyze_case(case_id: str):
    """
    Ejecuta el análisis completo del caso.
    
    Args:
        case_id: ID del caso a analizar
    
    Returns:
        Resultado del análisis con ruta del PDF
    """
    # Validar que el caso exista
    case_dir = DATA / "cases" / case_id
    if not case_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"El caso {case_id} no existe"
        )
    
    # Validar que haya documentos
    documents_dir = case_dir / "documents"
    documents = list(documents_dir.glob("*.txt")) + list(documents_dir.glob("*.pdf"))
    
    if not documents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El caso {case_id} no tiene documentos. Sube al menos un documento con POST /cases/{case_id}/documents"
        )
    
    try:
        # Construir estado inicial
        from scripts.generate_case_report import load_case_from_filesystem
        
        initial_state = load_case_from_filesystem(case_id)
        
        # Ejecutar grafo
        result = graph.invoke(initial_state)
        
        # Extraer información
        report = result.get('report', {})
        pdf_path = report.get('pdf_path')
        
        return AnalysisResponse(
            case_id=case_id,
            status="completed",
            overall_risk=report.get('overall_risk', 'indeterminate'),
            risks_count=len(result.get('risks', [])),
            legal_findings_count=len(result.get('legal_findings', [])),
            pdf_path=pdf_path,
            message=f"Análisis completado. PDF generado: {pdf_path if pdf_path else 'N/A'}"
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error durante el análisis: {str(e)}"
        )


@app.get("/cases/{case_id}/reports/latest")
async def download_latest_report(case_id: str):
    """
    Descarga el último informe PDF generado para el caso.
    
    Args:
        case_id: ID del caso
    
    Returns:
        Archivo PDF
    """
    # Validar que el caso exista
    case_dir = DATA / "cases" / case_id
    if not case_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"El caso {case_id} no existe"
        )
    
    # Buscar latest.txt
    reports_dir = case_dir / "reports"
    latest_file = reports_dir / "latest.txt"
    
    if not latest_file.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No hay informes generados para el caso {case_id}. Ejecuta POST /cases/{case_id}/analyze primero"
        )
    
    # Leer nombre del último PDF
    with open(latest_file, 'r') as f:
        pdf_filename = f.read().strip()
    
    pdf_path = reports_dir / pdf_filename
    
    if not pdf_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"El PDF {pdf_filename} no se encontró"
        )
    
    # Devolver archivo
    return FileResponse(
        path=str(pdf_path),
        filename=pdf_filename,
        media_type="application/pdf"
    )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "Phoenix Legal API",
        "version": "1.0.0"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


from typing import Optional

from fastapi import Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy.orm import Session

# 👉 IMPORT DEL AGENTE 1 (AUDITOR)
from app.agents.agent_1_auditor.runner import run_auditor

# 👉 IMPORT DEL AGENTE 2 (PROSECUTOR)
from app.agents.agent_2_prosecutor.runner import run_prosecutor_from_auditor

# 👉 IMPORT DEL AGENTE LEGAL
from app.agents.agent_legal.runner import run_legal_agent

# 👉 IMPORT DEL HANDOFF
from app.agents.handoff import HandoffPayload
from app.api.analysis_alerts import router as analysis_alerts_router
from app.api.auth import router as auth_router
from app.api.balance_concursal import router as balance_concursal_router
from app.api.cases import router as cases_router
from app.api.chunks import router as chunks_router
from app.api.documents import router as documents_router
from app.api.economic_report import router as economic_report_router
from app.api.financial_analysis import router as financial_analysis_router
from app.api.legal_report import (
    router as legal_report_router,
)
from app.api.manifest import router as manifest_router
from app.api.pdf_report import router as pdf_report_router
from app.api.reports import router as reports_router
from app.api.situation import router as situation_router
from app.api.submissions import router as submissions_router
from app.api.templates import router as templates_router
from app.api.case_evidence import router as case_evidence_router
from app.api.alerts_voice import router as alerts_voice_router
from app.api.alerts import router_alerts as alerts_router, router_cases as case_alerts_router
from app.api.timeline import router as timeline_router  # ✅ NUEVO: Timeline paginado

# ✅ RE-HABILITADO (imports corregidos)
from app.api.trace import router as trace_router
from app.api.v2_auditor import router as v2_auditor_router
from app.api.v2_prosecutor import router as v2_prosecutor_router
from app.core.database import get_db, get_engine
from app.rag.case_rag.rag import router as rag_router

# =========================================================
# FASTAPI APP (ENTRYPOINT ASGI)
# =========================================================

app = FastAPI(title="Phoenix Insolvency")


# Endpoint raíz
@app.get("/")
def root():
    """Endpoint raíz con información del sistema"""
    return {
        "service": "Phoenix Legal API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "endpoints": {
            "cases": "/api/cases",
            "chunks": "/api/cases/{case_id}/chunks",
            "analysis": "/api/cases/{case_id}/analysis/alerts",
            "legal_report": "/api/cases/{case_id}/legal-report",
            "trace": "/api/cases/{case_id}/trace",
            "manifest": "/api/cases/{case_id}/manifest",
            "pdf_report": "/api/cases/{case_id}/legal-report/pdf",
            "economic_report_pdf": "/api/cases/{case_id}/economic-report/pdf",
            "timeline": "/api/cases/{case_id}/timeline",
        },
    }


@app.get("/health")
def health():
    """Healthcheck simple para Docker/CI."""
    return {"status": "healthy"}


# Routers existentes
app.include_router(rag_router)
app.include_router(documents_router, prefix="/api")  # ✅ FIXED: Añadido prefix
app.include_router(reports_router)
app.include_router(cases_router, prefix="/api")
app.include_router(chunks_router, prefix="/api")
app.include_router(analysis_alerts_router, prefix="/api")
app.include_router(legal_report_router, prefix="/api")  # ✅ RE-HABILITADO
app.include_router(trace_router, prefix="/api")
app.include_router(manifest_router, prefix="/api")
app.include_router(pdf_report_router, prefix="/api")
app.include_router(economic_report_router, prefix="/api")
app.include_router(situation_router, prefix="/api")
app.include_router(submissions_router, prefix="/api")
app.include_router(templates_router, prefix="/api")
app.include_router(case_evidence_router, prefix="/api")
app.include_router(alerts_voice_router, prefix="/api")
app.include_router(case_alerts_router, prefix="/api")
app.include_router(alerts_router, prefix="/api")

# Routers v2
app.include_router(v2_auditor_router)
app.include_router(v2_prosecutor_router)

# FASE 1.3: Balance Concursal
app.include_router(balance_concursal_router, prefix="/api")

# FASE 2B: Análisis Financiero Concursal
app.include_router(financial_analysis_router, prefix="/api")

# Timeline paginado (escalable)
app.include_router(timeline_router, prefix="/api")  # ✅ NUEVO

# Autenticación JWT
app.include_router(auth_router, prefix="/api")


# =========================================================
# MODELOS API – AGENTE AUDITOR
# =========================================================


class AuditorInput(BaseModel):
    case_id: str
    question: str


class LegalAgentInput(BaseModel):
    case_id: str
    question: str
    auditor_summary: Optional[str] = None
    auditor_risks: Optional[list[str]] = None


# =========================================================
# ENDPOINT AGENTE 1 – AUDITOR
# =========================================================


@app.post("/auditor/run")
def run_auditor_agent(
    payload: AuditorInput,
    db: Session = Depends(get_db),
):
    """
    Ejecuta el Agente Auditor con RAG interno.

    El agente usa RAG para recuperar contexto del caso antes de realizar
    el análisis de auditoría.
    """
    result, auditor_fallback = run_auditor(
        case_id=payload.case_id,
        question=payload.question,
        db=db,
    )
    return {
        **result.dict(),
        "auditor_fallback": auditor_fallback,
    }


# =========================================================
# ENDPOINT HANDOFF Y AGENTE 2
# =========================================================


@app.post("/prosecutor/run-from-auditor")
def run_prosecutor_from_auditor_endpoint(payload: HandoffPayload):
    """
    Ejecuta el Agente Prosecutor a partir del resultado del Auditor (handoff).

    Este endpoint recibe el payload del handoff del Auditor (validado con Pydantic)
    y ejecuta el Agente Prosecutor para realizar el análisis fiscal del caso.

    El payload debe incluir:
    - case_id, question, summary, risks, next_actions (obligatorios)
    - auditor_fallback (bool, indica si el Auditor usó fallback)
    """
    # El modelo HandoffPayload ya valida el payload automáticamente
    # Si llega aquí, el payload es válido
    handoff_dict = payload.dict()
    result = run_prosecutor_from_auditor(handoff_dict)
    return result.dict()


# =========================================================
# ENDPOINT AGENTE LEGAL
# =========================================================


@app.post("/legal/analyze")
def run_legal_agent_endpoint(
    payload: LegalAgentInput,
    db: Session = Depends(get_db),
):
    """
    Ejecuta el Agente Legal para analizar riesgos legales específicos.

    El agente analiza el caso desde la perspectiva de un Administrador Concursal
    y Abogado Concursalista, basándose en:
    - Ley Concursal española
    - Jurisprudencia relevante
    - Evidencias del caso

    El agente puede recibir contexto previo del Auditor (opcional).
    """
    result = run_legal_agent(
        case_id=payload.case_id,
        question=payload.question,
        db=db,
        auditor_summary=payload.auditor_summary,
        auditor_risks=payload.auditor_risks,
    )
    return result.dict()


# =========================================================
# MAIN CLÁSICO (solo para tests manuales)
# =========================================================


def main():
    """
    Punto de entrada manual (NO usado por uvicorn).
    Sirve para comprobar que la conexión a base de datos funciona.
    """
    engine = get_engine()
    connection = engine.connect()
    print("✅ Conexión a la base de datos OK")
    connection.close()


if __name__ == "__main__":
    main()

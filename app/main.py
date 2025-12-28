from typing import Optional, List
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_engine, get_db
from app.rag.case_rag.rag import router as rag_router
from app.api.documents import router as documents_router
from app.api.reports import router as reports_router

# 👉 IMPORT DEL AGENTE 1 (AUDITOR)
from app.agents.agent_1_auditor.runner import run_auditor

# 👉 IMPORT DEL AGENTE 2 (PROSECUTOR)
from app.agents.agent_2_prosecutor.runner import run_prosecutor_from_auditor

# 👉 IMPORT DEL AGENTE LEGAL
from app.agents.agent_legal.runner import run_legal_agent

# 👉 IMPORT DEL HANDOFF
from app.agents.handoff import build_agent2_payload, HandoffPayload


# =========================================================
# CARGA DE ENTORNO
# =========================================================

load_dotenv()


# =========================================================
# FASTAPI APP (ENTRYPOINT ASGI)
# =========================================================

app = FastAPI(title="Phoenix Insolvency")

# Routers existentes
app.include_router(rag_router)
app.include_router(documents_router)
app.include_router(reports_router)


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
    auditor_risks: Optional[List[str]] = None


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

"""
Modelo de Auditoría para cumplimiento legal.

Registra TODAS las acciones sensibles en el sistema:
- Acceso a análisis financiero
- Generación de informes
- Modificación de casos
- Consulta de documentos sensibles

Requerido para compliance legal y trazabilidad.
"""
from sqlalchemy import Column, String, DateTime, Text, Integer
from sqlalchemy.sql import func
from app.core.database import Base


class AuditLog(Base):
    """
    Registro de auditoría persistente.
    
    Cada entrada registra:
    - Quién: user_id
    - Qué: action
    - Dónde: case_id (opcional)
    - Cuándo: timestamp
    - Cómo: ip_address, user_agent
    - Detalles: details (JSON)
    """
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String, nullable=False, index=True)
    case_id = Column(String, nullable=True, index=True)
    action = Column(String, nullable=False, index=True)
    details = Column(Text, nullable=True)  # JSON con detalles adicionales
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    
    def __repr__(self):
        return f"<AuditLog {self.id}: {self.user_id} - {self.action} @ {self.timestamp}>"

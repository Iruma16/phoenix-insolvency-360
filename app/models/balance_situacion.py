"""
Modelo SQLAlchemy para Balance de Situación Concursal.

FASE 1.3: Balance de Situación Automático - Persistencia
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Integer, Boolean, JSON, Text, ForeignKey, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class BalanceSituacion(Base):
    """
    Balance de Situación Concursal persistido.
    
    Incluye versionado y trazabilidad legal (P0.5).
    """
    __tablename__ = "balance_situacion"
    
    # PK
    balance_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        comment="UUID del balance"
    )
    
    # FK
    case_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("cases.case_id", name="fk_balance_case_id"),
        nullable=False,
        index=True,
        comment="Caso al que pertenece"
    )
    
    # Metadata
    fecha_analisis: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
        comment="Fecha del análisis"
    )
    
    fecha_cierre: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Fecha de cierre del balance contable"
    )
    
    ejercicio: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
        comment="Ejercicio fiscal (ej: 2024)"
    )
    
    # Versionado (P0.5 - trazabilidad legal)
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Versión del análisis (incremental por caso)"
    )
    
    ruleset_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Versión de reglas TRLC+insolvencia aplicadas"
    )
    
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="True si es la versión activa"
    )
    
    superseded_by: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("balance_situacion.balance_id", name="fk_balance_superseded_by"),
        nullable=True,
        comment="ID del balance que reemplaza a este"
    )
    
    # Balance estructurado (JSON)
    balance_data: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        comment="Balance de situación completo (BalanceSheet)"
    )
    
    pyg_data: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Cuenta de Pérdidas y Ganancias (IncomeStatement)"
    )
    
    # Totales (para queries rápidas)
    total_activo: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Total activo (Decimal como string)"
    )
    
    total_pasivo: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Total pasivo (Decimal como string)"
    )
    
    patrimonio_neto: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Patrimonio neto (Decimal como string)"
    )
    
    # Ratios (JSON)
    ratios: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        comment="Ratios financieros calculados"
    )
    
    # Análisis insolvencia (JSON)
    insolvencia_actual: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Existe insolvencia actual acreditada"
    )
    
    insolvencia_inminente: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Existe insolvencia inminente"
    )
    
    indicadores_insolvencia: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        comment="Análisis completo de insolvencia"
    )
    
    # Dictamen jurídico (JSON)
    dictamen: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        comment="Dictamen jurídico preliminar (LegalOpinion)"
    )
    
    # Confidence
    confidence: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        comment="Confidence granular por tipo de análisis"
    )
    
    # Auditoría
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
        comment="Timestamp de creación"
    )
    
    created_by: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Usuario que creó el análisis"
    )
    
    # Constraints
    __table_args__ = (
        UniqueConstraint(
            'case_id', 'version',
            name='uq_balance_case_version'
        ),
        CheckConstraint(
            'version >= 1',
            name='ck_balance_version_positive'
        ),
    )
    
    # Relationship
    # case = relationship("Case", back_populates="balances")  # TODO: si Case define la relación inversa


class CreditoDB(Base):
    """
    Crédito clasificado según TRLC.
    
    Se vincula a un balance específico.
    """
    __tablename__ = "creditos_concursales"
    
    # PK
    credit_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        comment="UUID del crédito"
    )
    
    # FK
    balance_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("balance_situacion.balance_id", name="fk_credit_balance_id"),
        nullable=False,
        index=True,
        comment="Balance al que pertenece"
    )
    
    # Acreedor
    creditor_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Identificador del acreedor"
    )
    
    creditor_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Nombre del acreedor"
    )
    
    # Importes (como strings para precisión)
    principal_amount: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Importe principal (Decimal como string)"
    )
    
    interest_amount: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="0",
        comment="Importe intereses (Decimal como string)"
    )
    
    total_amount: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Importe total (Decimal como string)"
    )
    
    # Naturaleza jurídica
    nature: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
        comment="Naturaleza jurídica (CreditNature enum)"
    )
    
    # Garantías
    secured: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Tiene garantía"
    )
    
    guarantee_type: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Tipo de garantía (real/personal/ninguna)"
    )
    
    guarantee_value: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Valor de la garantía (Decimal como string)"
    )
    
    # Fechas
    devengo_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Fecha de devengo"
    )
    
    due_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Fecha de vencimiento"
    )
    
    # Origen
    source_document_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        nullable=True,
        comment="ID del documento origen"
    )
    
    source_description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Descripción del origen"
    )
    
    # Clasificación TRLC
    trlc_classification: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
        comment="Clasificación concursal (CreditClassificationTRLC enum)"
    )
    
    classification_reasoning: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Razonamiento jurídico de la clasificación"
    )
    
    excluded_from_categories: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="Categorías de las que fue excluido (auditoría)"
    )
    
    # Metadata
    confidence: Mapped[float] = mapped_column(
        nullable=False,
        default=0.5,
        comment="Confidence de la clasificación"
    )
    
    extraction_method: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="manual",
        comment="Método de extracción"
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
        comment="Timestamp de creación"
    )

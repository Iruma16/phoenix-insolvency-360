"""
Servicio de persistencia para Balance de Situación Concursal.

FASE 1.3: Balance de Situación Automático - Persistencia BD
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.models.balance_concursal_output import BalanceConcursalOutput
from app.models.balance_situacion import BalanceSituacion, CreditoDB


class BalancePersistenceService:
    """Servicio especializado en persistencia de balances concursales."""
    
    @staticmethod
    def persist_balance(
        db: Session,
        output: BalanceConcursalOutput,
        created_by: Optional[str] = None
    ) -> BalanceSituacion:
        """
        Persiste el balance concursal en BD con versionado.
        
        Args:
            db: Sesión de BD
            output: Output completo del análisis
            created_by: Usuario que crea el análisis
            
        Returns:
            BalanceSituacion persistido
        """
        # 1. Obtener versión anterior y calcular nueva versión
        previous_balance = (
            db.query(BalanceSituacion)
            .filter(
                BalanceSituacion.case_id == output.case_id,
                BalanceSituacion.is_active == True
            )
            .first()
        )
        
        new_version = 1
        if previous_balance:
            new_version = previous_balance.version + 1
            # Desactivar versión anterior
            previous_balance.is_active = False
            previous_balance.superseded_by = output.balance_id
        
        # 2. Crear BalanceSituacion (usar mode='json' para serializar Decimals)
        balance_db = BalanceSituacion(
            balance_id=output.balance_id,
            case_id=output.case_id,
            fecha_analisis=output.fecha_analisis,
            version=new_version,
            ruleset_version=output.ruleset_version,
            is_active=True,
            balance_data=output.balance.model_dump(mode='json'),
            pyg_data=output.pyg.model_dump(mode='json') if output.pyg else None,
            total_activo=str(output.balance.total_activo) if output.balance.total_activo else None,
            total_pasivo=str(output.balance.total_pasivo) if output.balance.total_pasivo else None,
            patrimonio_neto=str(output.balance.patrimonio_neto) if output.balance.patrimonio_neto else None,
            ratios={k: v.model_dump(mode='json') for k, v in output.ratios.items()},
            insolvencia_actual=output.analisis_insolvencia["actual"]["existe_insolvencia_actual"],
            insolvencia_inminente=output.analisis_insolvencia["inminente"]["existe_insolvencia_inminente"],
            indicadores_insolvencia=output.analisis_insolvencia,
            dictamen=output.dictamen.model_dump(mode='json'),
            confidence=output.confidence,
            created_by=created_by,
        )
        
        db.add(balance_db)
        db.flush()  # Asegurar que balance_id está disponible
        
        # 3. Crear créditos
        for credit in output.creditos:
            credit_db = CreditoDB(
                credit_id=credit.credit_id,
                balance_id=output.balance_id,
                creditor_id=credit.creditor_id,
                creditor_name=credit.creditor_name,
                principal_amount=str(credit.principal_amount),
                interest_amount=str(credit.interest_amount),
                total_amount=str(credit.total_amount),
                nature=credit.nature.value,
                secured=credit.secured,
                guarantee_type=credit.guarantee_type,
                guarantee_value=str(credit.guarantee_value) if credit.guarantee_value else None,
                devengo_date=credit.devengo_date,
                due_date=credit.due_date,
                source_document_id=credit.source_document_id,
                source_description=credit.source_description,
                trlc_classification=credit.trlc_classification.value,
                classification_reasoning=credit.classification_reasoning,
                excluded_from_categories=credit.excluded_from_categories,
                confidence=credit.confidence,
                extraction_method=credit.extraction_method,
            )
            db.add(credit_db)
        
        db.commit()
        db.refresh(balance_db)
        
        return balance_db
    
    @staticmethod
    def get_active_balance(db: Session, case_id: str) -> Optional[BalanceSituacion]:
        """Obtiene el balance activo de un caso."""
        return (
            db.query(BalanceSituacion)
            .filter(
                BalanceSituacion.case_id == case_id,
                BalanceSituacion.is_active == True
            )
            .first()
        )
    
    @staticmethod
    def get_balance_history(db: Session, case_id: str) -> list[BalanceSituacion]:
        """Obtiene el histórico de balances de un caso."""
        return (
            db.query(BalanceSituacion)
            .filter(BalanceSituacion.case_id == case_id)
            .order_by(BalanceSituacion.version.desc())
            .all()
        )
    
    @staticmethod
    def get_creditos_by_balance(db: Session, balance_id: str) -> list[CreditoDB]:
        """Obtiene los créditos de un balance."""
        return (
            db.query(CreditoDB)
            .filter(CreditoDB.balance_id == balance_id)
            .all()
        )

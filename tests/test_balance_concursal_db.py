"""
Tests de persistencia BD para Balance de Situación Concursal.

FASE 1.3: Balance de Situación Automático - Persistencia
"""
import pytest
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.credit import Credit, CreditNature
from app.models.financial_statement import BalanceSheet
from app.models.balance_situacion import BalanceSituacion, CreditoDB
from app.services.balance_concursal_service import BalanceConcursalService
from app.services.balance_persistence import BalancePersistenceService
from app.core.database import get_engine, Base


@pytest.fixture
def db_session():
    """Crea una sesión de BD temporal para tests."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=engine)
    session = Session()
    
    yield session
    
    session.close()


@pytest.mark.integration
def test_balance_persistence_basic(db_session: Session):
    """Test básico de persistencia de balance."""
    service = BalanceConcursalService()
    persistence = BalancePersistenceService()
    
    balance = BalanceSheet(
        activo_corriente=Decimal("100000"),
        activo_no_corriente=Decimal("50000"),
        total_activo=Decimal("150000"),
        pasivo_corriente=Decimal("60000"),
        pasivo_no_corriente=Decimal("40000"),
        total_pasivo=Decimal("100000"),
        patrimonio_neto=Decimal("50000"),
    )
    
    creditos = [
        Credit(
            credit_id="C1",
            creditor_id="CRED1",
            creditor_name="Banco X",
            principal_amount=Decimal("50000"),
            interest_amount=Decimal("0"),
            total_amount=Decimal("50000"),
            nature=CreditNature.FINANCIERO,
        ),
    ]
    
    # 1. Analizar
    output = service.analyze_balance_concursal(
        case_id="TEST-CASE-DB-001",
        balance=balance,
        creditos=creditos,
    )
    
    # 2. Persistir
    balance_db = persistence.persist_balance(
        db=db_session,
        output=output,
        created_by="test_user"
    )
    
    # 3. Verificar
    assert balance_db.balance_id == output.balance_id
    assert balance_db.case_id == "TEST-CASE-DB-001"
    assert balance_db.version == 1
    assert balance_db.is_active == True
    assert "TRLC" in balance_db.ruleset_version
    
    # 4. Verificar créditos
    creditos_db = persistence.get_creditos_by_balance(db_session, output.balance_id)
    assert len(creditos_db) == 1
    assert creditos_db[0].creditor_name == "Banco X"


@pytest.mark.integration
def test_balance_versioning(db_session: Session):
    """Test de versionado de balances."""
    service = BalanceConcursalService()
    persistence = BalancePersistenceService()
    
    case_id = "TEST-CASE-DB-002"
    
    balance = BalanceSheet(
        activo_corriente=Decimal("100000"),
        activo_no_corriente=Decimal("50000"),
        total_activo=Decimal("150000"),
        pasivo_corriente=Decimal("60000"),
        pasivo_no_corriente=Decimal("40000"),
        total_pasivo=Decimal("100000"),
        patrimonio_neto=Decimal("50000"),
    )
    
    creditos = [
        Credit(
            credit_id="C1",
            creditor_id="CRED1",
            creditor_name="Banco X",
            principal_amount=Decimal("50000"),
            interest_amount=Decimal("0"),
            total_amount=Decimal("50000"),
            nature=CreditNature.FINANCIERO,
        ),
    ]
    
    # 1. Crear primera versión
    output1 = service.analyze_balance_concursal(case_id=case_id, balance=balance, creditos=creditos)
    balance1 = persistence.persist_balance(db=db_session, output=output1, created_by="test")
    
    assert balance1.version == 1
    assert balance1.is_active == True
    
    # 2. Crear segunda versión
    output2 = service.analyze_balance_concursal(case_id=case_id, balance=balance, creditos=creditos)
    balance2 = persistence.persist_balance(db=db_session, output=output2, created_by="test")
    
    assert balance2.version == 2
    assert balance2.is_active == True
    
    # 3. Verificar que v1 fue desactivada
    db_session.refresh(balance1)
    assert balance1.is_active == False
    assert balance1.superseded_by == balance2.balance_id
    
    # 4. Verificar que get_active_balance devuelve v2
    active = persistence.get_active_balance(db_session, case_id)
    assert active.version == 2
    
    # 5. Verificar histórico
    history = persistence.get_balance_history(db_session, case_id)
    assert len(history) == 2
    assert history[0].version == 2  # Más reciente primero
    assert history[1].version == 1

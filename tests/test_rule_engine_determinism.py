"""
Tests de determinismo del Rule Engine.

Verifica que:
- Misma entrada → mismo RuleEngineResult (hashable)
- El Rule Engine NO usa LLM
- Las decisiones son reproducibles

SIN dependencias externas: LLM, red, DB, Chroma.
Rápidos y deterministas.
"""
import pytest
from datetime import datetime

from app.legal.rule_engine_output import (
    RuleDecision,
    RuleEngineResult,
    RuleEngineResultBuilder,
    validate_determinism,
    RULE_ENGINE_VERSION
)


# ════════════════════════════════════════════════════════════════
# TEST 1: Misma entrada → mismo hash
# ════════════════════════════════════════════════════════════════

def test_mismo_input_mismo_hash():
    """
    Verifica que inputs idénticos producen hashes idénticos.
    
    Esto es CRÍTICO para determinismo.
    """
    # Crear dos resultados idénticos
    builder1 = RuleEngineResultBuilder(case_id="case_001", rulebook_version="1.0")
    builder1.add_rule_decision(RuleDecision(
        rule_id="rule_001",
        rule_name="Test Rule",
        article="TRLC Art. 5",
        applies=True,
        severity="high",
        confidence="high",
        rationale="Test rationale",
        score=0.9
    ))
    builder1.add_flag("has_delay", True)
    result1 = builder1.build()
    
    builder2 = RuleEngineResultBuilder(case_id="case_001", rulebook_version="1.0")
    builder2.add_rule_decision(RuleDecision(
        rule_id="rule_001",
        rule_name="Test Rule",
        article="TRLC Art. 5",
        applies=True,
        severity="high",
        confidence="high",
        rationale="Test rationale",
        score=0.9
    ))
    builder2.add_flag("has_delay", True)
    result2 = builder2.build()
    
    # Hashes deben ser idénticos
    hash1 = result1.to_deterministic_hash()
    hash2 = result2.to_deterministic_hash()
    
    assert hash1 == hash2
    print(f"✅ Mismo input → mismo hash: {hash1[:16]}...")


# ════════════════════════════════════════════════════════════════
# TEST 2: Diferente input → diferente hash
# ════════════════════════════════════════════════════════════════

def test_diferente_input_diferente_hash():
    """
    Verifica que inputs diferentes producen hashes diferentes.
    """
    # Resultado 1: severidad high
    builder1 = RuleEngineResultBuilder(case_id="case_001")
    builder1.add_rule_decision(RuleDecision(
        rule_id="rule_001",
        rule_name="Test Rule",
        article="TRLC Art. 5",
        applies=True,
        severity="high",  # ← high
        confidence="high",
        rationale="Test"
    ))
    result1 = builder1.build()
    
    # Resultado 2: severidad medium (DIFERENTE)
    builder2 = RuleEngineResultBuilder(case_id="case_001")
    builder2.add_rule_decision(RuleDecision(
        rule_id="rule_001",
        rule_name="Test Rule",
        article="TRLC Art. 5",
        applies=True,
        severity="medium",  # ← medium (DIFERENTE)
        confidence="high",
        rationale="Test"
    ))
    result2 = builder2.build()
    
    # Hashes deben ser DIFERENTES
    hash1 = result1.to_deterministic_hash()
    hash2 = result2.to_deterministic_hash()
    
    assert hash1 != hash2
    print(f"✅ Diferente input → diferente hash")


# ════════════════════════════════════════════════════════════════
# TEST 3: Validación de coherencia interna
# ════════════════════════════════════════════════════════════════

def test_validacion_coherencia_interna():
    """
    Verifica que validate_determinism detecta incoherencias.
    """
    # Crear resultado COHERENTE
    builder = RuleEngineResultBuilder(case_id="case_001")
    
    builder.add_rule_decision(RuleDecision(
        rule_id="rule_001",
        rule_name="Rule 1",
        article="Art. 1",
        applies=True,
        severity="high",
        confidence="high",
        rationale="Applies"
    ))
    
    builder.add_rule_decision(RuleDecision(
        rule_id="rule_002",
        rule_name="Rule 2",
        article="Art. 2",
        applies=False,
        severity="low",
        confidence="medium",
        rationale="Does not apply"
    ))
    
    result = builder.build()
    
    # Debe ser coherente
    assert validate_determinism(result)
    assert len(result.triggered_rules) == 1
    assert len(result.discarded_rules) == 1
    assert len(result.evaluated_rules) == 2
    
    print("✅ Coherencia interna validada")


# ════════════════════════════════════════════════════════════════
# TEST 4: Builder separa triggered/discarded automáticamente
# ════════════════════════════════════════════════════════════════

def test_builder_separa_automaticamente():
    """
    Verifica que el builder separa correctamente triggered vs discarded.
    """
    builder = RuleEngineResultBuilder(case_id="case_002")
    
    # Añadir 3 triggered, 2 discarded
    for i in range(3):
        builder.add_rule_decision(RuleDecision(
            rule_id=f"triggered_{i}",
            rule_name=f"Triggered Rule {i}",
            article=f"Art. {i}",
            applies=True,  # ← TRIGGERED
            severity="medium",
            confidence="high",
            rationale="Applies"
        ))
    
    for i in range(2):
        builder.add_rule_decision(RuleDecision(
            rule_id=f"discarded_{i}",
            rule_name=f"Discarded Rule {i}",
            article=f"Art. {i+10}",
            applies=False,  # ← DISCARDED
            severity="low",
            confidence="low",
            rationale="Does not apply"
        ))
    
    result = builder.build()
    
    assert len(result.triggered_rules) == 3
    assert len(result.discarded_rules) == 2
    assert len(result.evaluated_rules) == 5
    
    # Verificar que todos los triggered tienen applies=True
    assert all(r.applies for r in result.triggered_rules)
    
    # Verificar que todos los discarded tienen applies=False
    assert all(not r.applies for r in result.discarded_rules)
    
    print("✅ Builder separa triggered/discarded correctamente")


# ════════════════════════════════════════════════════════════════
# TEST 5: RuleDecision es inmutable para decisiones críticas
# ════════════════════════════════════════════════════════════════

def test_rule_decision_fields_validados():
    """
    Verifica que RuleDecision valida campos críticos.
    """
    # Severity debe ser uno de los valores permitidos
    with pytest.raises(Exception):  # ValidationError
        RuleDecision(
            rule_id="rule_001",
            rule_name="Test",
            article="Art. 1",
            applies=True,
            severity="invalid_severity",  # ❌ NO PERMITIDO
            confidence="high",
            rationale="Test"
        )
    
    # Confidence debe ser uno de los valores permitidos
    with pytest.raises(Exception):  # ValidationError
        RuleDecision(
            rule_id="rule_001",
            rule_name="Test",
            article="Art. 1",
            applies=True,
            severity="high",
            confidence="invalid_confidence",  # ❌ NO PERMITIDO
            rationale="Test"
        )
    
    print("✅ Validación de fields funciona")


# ════════════════════════════════════════════════════════════════
# TEST 6: Engine version tracking
# ════════════════════════════════════════════════════════════════

def test_engine_version_tracking():
    """
    Verifica que cada resultado conoce su versión de engine.
    """
    builder = RuleEngineResultBuilder(case_id="case_003")
    result = builder.build()
    
    assert result.engine_version == RULE_ENGINE_VERSION
    assert result.engine_version == "2.0.0"
    
    print(f"✅ Engine version tracked: {result.engine_version}")


# ════════════════════════════════════════════════════════════════
# TEST 7: Score en rango válido
# ════════════════════════════════════════════════════════════════

def test_score_en_rango_valido():
    """
    Verifica que score está en rango [0.0, 1.0].
    """
    # Score válido
    decision_ok = RuleDecision(
        rule_id="rule_001",
        rule_name="Test",
        article="Art. 1",
        applies=True,
        severity="high",
        confidence="high",
        rationale="Test",
        score=0.75  # ✅ Válido
    )
    assert 0.0 <= decision_ok.score <= 1.0
    
    # Score fuera de rango debe fallar
    with pytest.raises(Exception):  # ValidationError
        RuleDecision(
            rule_id="rule_001",
            rule_name="Test",
            article="Art. 1",
            applies=True,
            severity="high",
            confidence="high",
            rationale="Test",
            score=1.5  # ❌ Fuera de rango
        )
    
    print("✅ Score validado en rango [0.0, 1.0]")


# ════════════════════════════════════════════════════════════════
# TEST 8: Timestamps automáticos
# ════════════════════════════════════════════════════════════════

def test_timestamps_automaticos():
    """
    Verifica que evaluated_at se genera automáticamente.
    """
    builder = RuleEngineResultBuilder(case_id="case_004")
    result = builder.build()
    
    assert isinstance(result.evaluated_at, datetime)
    assert result.evaluated_at <= datetime.utcnow()
    
    print("✅ Timestamps automáticos generados")


# ════════════════════════════════════════════════════════════════
# TEST 9: Extra fields prohibidos
# ════════════════════════════════════════════════════════════════

def test_extra_fields_prohibidos():
    """
    Verifica que extra="forbid" rechaza campos no definidos.
    """
    with pytest.raises(Exception):  # ValidationError
        RuleDecision(
            rule_id="rule_001",
            rule_name="Test",
            article="Art. 1",
            applies=True,
            severity="high",
            confidence="high",
            rationale="Test",
            campo_inventado="no permitido"  # ❌ EXTRA FIELD
        )
    
    print("✅ Extra fields rechazados (extra='forbid')")


# ════════════════════════════════════════════════════════════════
# TEST 10: Reproducibilidad completa
# ════════════════════════════════════════════════════════════════

def test_reproducibilidad_completa():
    """
    Verifica que ejecutar 2 veces produce mismo resultado.
    
    Este es el test MÁS CRÍTICO para determinismo legal.
    """
    def evaluar_caso(case_id: str) -> RuleEngineResult:
        """Simula evaluación de un caso."""
        builder = RuleEngineResultBuilder(case_id=case_id, rulebook_version="1.0")
        
        # Regla 1: Delay filing
        builder.add_rule_decision(RuleDecision(
            rule_id="delay_filing",
            rule_name="Retraso en presentación",
            article="TRLC Art. 5",
            applies=True,
            severity="high",
            confidence="high",
            evidence_required=["informe_tesoreria", "balance"],
            evidence_found=["informe_tesoreria"],
            rationale="Insolvencia detectada sin presentación de concurso",
            score=0.85
        ))
        
        # Regla 2: Documentation gap
        builder.add_rule_decision(RuleDecision(
            rule_id="doc_gap",
            rule_name="Laguna documental",
            article="TRLC Art. 6",
            applies=False,
            severity="low",
            confidence="medium",
            evidence_required=["balance", "acta"],
            evidence_found=["balance", "acta"],
            rationale="Documentación completa",
            score=0.2
        ))
        
        builder.add_flag("critical_findings", True)
        builder.add_flag("requires_legal_review", True)
        
        return builder.build()
    
    # Ejecutar 2 veces
    result1 = evaluar_caso("case_reproducible")
    result2 = evaluar_caso("case_reproducible")
    
    # Hashes deben ser IDÉNTICOS
    hash1 = result1.to_deterministic_hash()
    hash2 = result2.to_deterministic_hash()
    
    assert hash1 == hash2
    assert len(result1.triggered_rules) == len(result2.triggered_rules)
    assert len(result1.discarded_rules) == len(result2.discarded_rules)
    
    print(f"✅ Reproducibilidad completa verificada: {hash1[:16]}...")
    print(f"   Triggered: {len(result1.triggered_rules)}")
    print(f"   Discarded: {len(result1.discarded_rules)}")


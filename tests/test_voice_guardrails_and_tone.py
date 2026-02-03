from __future__ import annotations

import re

import pytest

from app.services.assistant_alert_voice import (
    AlertDomain,
    EvidenceRef,
    Relevance,
    VoiceInput,
    find_language_violations,
    generate_voice,
)


@pytest.mark.parametrize(
    "relevance, must_contain_any",
    [
        (Relevance.ALTA, [r"\bojo con\b", r"conviene revisar.*cuidado"]),
        (Relevance.MEDIA, [r"llama la atención", r"conviene mirarlo"]),
        (Relevance.BAJA, [r"detalle a tener en cuenta", r"algo menor"]),
    ],
)
def test_generate_voice_has_required_tone_and_no_robot_terms(relevance, must_contain_any):
    payload = VoiceInput(
        domain=AlertDomain.TGSS,
        findings=["aparece una providencia de apremio con periodos 2024-01 a 2024-03"],
        evidences=[EvidenceRef(filename="tgss.pdf", page_start=1, page_end=1, snippet="...")],
        to_clarify=["Certificado TGSS actualizado", "RNT/RLC de los meses afectados"],
        temporal_window_note=None,
        relevance=relevance,
    )

    out = generate_voice(payload, strict_language=True)

    text = (out.title_human + "\n\n" + out.summary_human + "\n\n" + out.disclaimer_detail).lower()

    # Anti-robot / anti-legal: no violaciones
    assert find_language_violations(text) == []

    # Requeridos por severidad (permitimos que estén en título o cuerpo)
    assert any(re.search(pat, text, flags=re.IGNORECASE) for pat in must_contain_any)

    # Máx 3 párrafos
    paras = [p.strip() for p in out.summary_human.split("\n\n") if p.strip()]
    assert len(paras) <= 3

    # Longitud máxima (ver helper _ensure_max_length)
    assert len(out.summary_human) <= 900


#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validación manual (NO tests) — FASE 3 Voz del asistente.

No levanta UI/API.
Solo imprime ejemplos y hace asserts simples de guardarraíl.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Permitir ejecutar el script desde repo root sin instalar paquete.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.services.assistant_alert_voice import (
    demo_payloads_from_dataset,
    find_language_violations,
    generate_voice,
)


def main() -> None:
    payloads = demo_payloads_from_dataset()
    for p in payloads:
        out = generate_voice(p, strict_language=True)
        text = out.title_human + "\n\n" + out.summary_human
        violations = find_language_violations(text)
        assert not violations, f"Violaciones de lenguaje: {violations}"

        # Reglas formales: <=3 párrafos, incluye cautela y cierre
        paras = [x.strip() for x in out.summary_human.split("\n\n") if x.strip()]
        assert len(paras) <= 3, f"Demasiados párrafos: {len(paras)}"
        assert "no es concluyente" in out.summary_human.lower(), "Falta frase de cautela"
        assert "yo revisaría" in out.summary_human.lower(), "Falta cierre 'yo revisaría'"

        print("=" * 90)
        print(f"[{p.domain.value}] {out.title_human}")
        print()
        print(out.summary_human)
        print()
        print("Checklist:", ", ".join(out.to_clarify[:5]) if out.to_clarify else "—")
        print("Disclaimer:", out.disclaimer_detail)

    print("=" * 90)
    print("✅ Validación manual completada (sin violaciones).")


if __name__ == "__main__":
    main()


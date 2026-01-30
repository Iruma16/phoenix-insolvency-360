"""
FASE 3 (extensión) — Voz del asistente con LLM (híbrido con reglas).

Principio:
- Reglas deterministas construyen el "qué" (findings/evidence/checklist).
- El LLM solo pule el "cómo" (redacción estilo despacho) y devuelve JSON estricto.
- Guardarraíles locales validan vocabulario y estructura. Si falla → fallback determinista.

Importante:
- Todas las llamadas a LLM pasan por `execute_llm()` (regla del repo).
- Para JSON estricto, se desactiva el post-procesado automático del executor (disclaimer/language policy),
  porque podría romper el JSON o introducir vocabulario no deseado.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from typing import Any, Optional

from app.services.assistant_alert_voice import (
    VoiceInput,
    VoiceOutput,
    find_language_violations,
    generate_voice,
)
from app.services.llm_executor import execute_llm


PROMPT_VERSION = "assistant_alert_voice_llm_v1"


def _system_prompt() -> str:
    return (
        "Eres personal de un despacho (administración aplicada) revisando un expediente.\n"
        "No hablas como IA. No emites conclusiones jurídicas. No mencionas “el sistema”.\n"
        "No inventes hechos: usa SOLO los findings y evidencias proporcionados.\n"
        "Prohibido: intención, dolo, fraude cometido, se demuestra, culpable, inocente, delito, crimen, indicio.\n"
        "Evita: “se detecta…”, “el sistema ha identificado…”, “existe indicio de…”.\n"
        "Usa un tono prudente: “no es concluyente, pero…”, “conviene aclarar…”, “por fechas e importes…”.\n"
        "Devuelve SOLO JSON válido con: title_human, summary_human, disclaimer_detail.\n"
        "summary_human: máximo 3 párrafos cortos, incluye 1 frase explícita de cautela "
        "(debe contener literalmente 'no es concluyente') y cierra con 'yo revisaría…'.\n"
        "No incluyas markdown ni code fences."
    )


def _user_prompt(payload: VoiceInput) -> str:
    def _ev(ev) -> dict[str, Any]:
        return {
            "filename": ev.filename,
            "page_start": ev.page_start,
            "page_end": ev.page_end,
            "snippet": (ev.snippet or "")[:500],
        }

    d: dict[str, Any] = {
        "domain": payload.domain.value,
        "relevance": payload.relevance.value if payload.relevance else None,
        "temporal_window_note": payload.temporal_window_note or "",
        "findings": payload.findings or [],
        "evidences": [_ev(e) for e in (payload.evidences or [])],
        "to_clarify": payload.to_clarify or [],
    }

    return (
        "Genera la salida en JSON con exactamente estas claves: "
        "title_human, summary_human, disclaimer_detail.\n\n"
        "Inputs (usar SOLO esto):\n"
        f"{json.dumps(d, ensure_ascii=False, indent=2)}"
    )


def _extract_json(text: str) -> dict[str, Any]:
    """
    Extrae JSON robustamente si el modelo devolvió texto extra.
    """
    if not text:
        raise ValueError("LLM devolvió texto vacío")

    t = text.strip()
    # Quitar posibles fences
    t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*```$", "", t)

    # Si hay texto extra, recortar al primer { ... último }
    if not t.startswith("{"):
        i = t.find("{")
        j = t.rfind("}")
        if i >= 0 and j > i:
            t = t[i : j + 1]

    obj = json.loads(t)
    if not isinstance(obj, dict):
        raise ValueError("JSON devuelto no es un objeto")
    return obj


def _validate_voice_json(obj: dict[str, Any]) -> VoiceOutput:
    missing = [k for k in ("title_human", "summary_human", "disclaimer_detail") if k not in obj]
    if missing:
        raise ValueError(f"JSON sin claves obligatorias: {missing}")

    title = str(obj.get("title_human") or "").strip()
    summary = str(obj.get("summary_human") or "").strip()
    disclaimer = str(obj.get("disclaimer_detail") or "").strip()

    if not title or not summary:
        raise ValueError("title_human y summary_human deben ser no vacíos")

    # Máx 3 párrafos (separados por doble salto)
    paras = [p.strip() for p in summary.split("\n\n") if p.strip()]
    if len(paras) > 3:
        raise ValueError(f"summary_human tiene demasiados párrafos: {len(paras)}")

    s_low = summary.lower()
    if "no es concluyente" not in s_low:
        raise ValueError("summary_human debe incluir literalmente 'no es concluyente'")
    if "yo revisaría" not in s_low:
        raise ValueError("summary_human debe cerrar con 'yo revisaría'")

    # Guardarraíles de lenguaje locales (anti-robot + términos prohibidos)
    violations = find_language_violations(title + "\n\n" + summary + "\n\n" + disclaimer)
    if violations:
        raise ValueError("Violación de guardarraíl: " + "; ".join(violations))

    # Disclaimer: permitir uno corto y consistente
    if not disclaimer:
        disclaimer = (
            "Nota: esto se apoya en hechos objetivos y patrones habituales de revisión de expediente. "
            "La valoración jurídica corresponde al abogado."
        )

    # Checklist se gestiona por reglas fuera del LLM
    return VoiceOutput(
        title_human=title,
        summary_human=summary,
        to_clarify=[],
        disclaimer_detail=disclaimer,
    )


def generate_voice_llm(
    payload: VoiceInput,
    *,
    strict_language: bool = True,
    max_tokens: int = 420,
    retries_on_validation: int = 1,
) -> VoiceOutput:
    """
    Genera voz usando LLM (si está disponible) con fallback determinista.
    """
    # Siempre mantenemos checklist ordenada por reglas deterministas (no delegar en LLM).
    fallback = generate_voice(payload, strict_language=strict_language)

    res = execute_llm(
        task_name="assistant_alert_voice_json",
        prompt_system=_system_prompt(),
        prompt_user=_user_prompt(payload),
        max_tokens=max_tokens,
        # CRÍTICO: no añadir disclaimer/política automática aquí → JSON estricto + prohibición de "indicio(s)"
        postprocess_add_disclaimer=False,
        postprocess_apply_language_policy=False,
    )

    if not res.success or not res.output_text:
        return fallback

    last_err: Optional[Exception] = None
    txt = res.output_text

    for _ in range(max(0, int(retries_on_validation)) + 1):
        try:
            obj = _extract_json(txt)
            out = _validate_voice_json(obj)
            # injertar checklist determinista + disclaimer estándar si falta
            return VoiceOutput(
                title_human=out.title_human,
                summary_human=out.summary_human,
                to_clarify=fallback.to_clarify,
                disclaimer_detail=out.disclaimer_detail or fallback.disclaimer_detail,
            )
        except Exception as e:
            last_err = e
            # Reintento con instrucción extra (sin cambiar hechos).
            # Nota: no hacemos bucle infinito; máximo 1 (configurable).
            fix_prompt = (
                "Tu salida anterior no cumplió los requisitos.\n"
                "Devuelve SOLO JSON válido, sin texto adicional.\n"
                "Asegura: máximo 3 párrafos; incluye 'no es concluyente'; incluye 'yo revisaría'; "
                "no uses palabras prohibidas ni frases robóticas.\n"
            )
            res2 = execute_llm(
                task_name="assistant_alert_voice_json_retry",
                prompt_system=_system_prompt(),
                prompt_user=fix_prompt + "\n\n" + _user_prompt(payload),
                max_tokens=max_tokens,
                postprocess_add_disclaimer=False,
                postprocess_apply_language_policy=False,
            )
            if not res2.success or not res2.output_text:
                break
            txt = res2.output_text

    # Si todo falla, fallback (fail-safe)
    return fallback


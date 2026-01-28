"""
OPERATIONAL PLAYBOOKS - Guías de acción para eventos [CERT]

Define QUÉ HACE NEGOCIO / LEGAL cuando aparece cada evento del sistema.
Lenguaje NO técnico, orientado a acción operativa.

NO contiene lógica de decisión. SOLO mapeo evento → playbook.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Playbook:
    """
    Playbook operativo para un evento del sistema.

    Define en lenguaje negocio:
    - Qué significa el evento
    - Qué debe hacer el responsable
    - Qué NO debe hacer
    """

    evento: str
    significado: str
    accion_recomendada: str
    responsable: str
    prohibido: str
    severidad: str  # INFO, WARNING, ERROR

    def to_dict(self) -> dict:
        """Convierte playbook a diccionario."""
        return {
            "evento": self.evento,
            "significado": self.significado,
            "accion_recomendada": self.accion_recomendada,
            "responsable": self.responsable,
            "prohibido": self.prohibido,
            "severidad": self.severidad,
        }

    def print_playbook(self) -> None:
        """Imprime playbook en formato legible."""
        print(f"\n{'='*80}")
        print(f"EVENTO: {self.evento}")
        print(f"SEVERIDAD: {self.severidad}")
        print(f"{'='*80}")
        print("\n¿QUÉ SIGNIFICA?")
        print(f"  {self.significado}")
        print("\n¿QUÉ HACER?")
        print(f"  {self.accion_recomendada}")
        print("\n¿QUIÉN ACTÚA?")
        print(f"  {self.responsable}")
        print("\n¿QUÉ NO HACER?")
        print(f"  {self.prohibido}")
        print(f"{'='*80}")


# ============================
# PLAYBOOKS RAG
# ============================

PLAYBOOK_RAG_EVIDENCIA_INSUFICIENTE = Playbook(
    evento="RAG: Bloqueo por evidencia insuficiente",
    significado=(
        "El sistema no encontró suficientes documentos relevantes para responder "
        "la pregunta con garantías. Es un bloqueo controlado: el sistema prefiere "
        "NO responder antes que arriesgarse a inventar información."
    ),
    accion_recomendada=(
        "1. Revisar la pregunta formulada (puede ser demasiado específica o ambigua).\n"
        "  2. Verificar qué documentos están cargados en el caso.\n"
        "  3. Si faltan documentos clave, solicitarlos al cliente.\n"
        "  4. Si los documentos existen pero no se recuperan, escalar a tech para revisar embeddings."
    ),
    responsable="Analista legal (primer nivel)",
    prohibido=(
        "NO intentar forzar una respuesta.\n"
        "  NO asumir que el sistema 'no funciona'.\n"
        "  NO completar manualmente sin evidencia documental."
    ),
    severidad="WARNING",
)

PLAYBOOK_RAG_BAJA_CONFIANZA = Playbook(
    evento="RAG: Baja confianza en la respuesta",
    significado=(
        "El sistema recuperó contexto pero considera que la calidad de la información "
        "o la coherencia entre documentos es baja. Puede ser porque:\n"
        "  - Los documentos son ambiguos o contradictorios.\n"
        "  - La pregunta no está bien formulada.\n"
        "  - Hay indicios de que la respuesta podría ser incorrecta."
    ),
    accion_recomendada=(
        "1. Leer el contexto recuperado y verificar manualmente la coherencia.\n"
        "  2. Reformular la pregunta de forma más específica.\n"
        "  3. Si los documentos son de baja calidad, solicitar versiones originales o mejores escaneos.\n"
        "  4. Considerar marcar la respuesta como 'provisional' hasta obtener mejor documentación."
    ),
    responsable="Analista legal + Abogado senior (revisión)",
    prohibido=(
        "NO usar la respuesta como base para conclusiones definitivas.\n"
        "  NO ignorar el warning de baja confianza.\n"
        "  NO asumir que la respuesta es correcta sin validación manual."
    ),
    severidad="WARNING",
)

PLAYBOOK_RAG_RESPUESTA_CON_EVIDENCIA = Playbook(
    evento="RAG: Respuesta con evidencia",
    significado=(
        "El sistema generó una respuesta basada en evidencia documental suficiente "
        "y con nivel de confianza adecuado. Todas las afirmaciones están respaldadas "
        "por citas específicas (documento + página + offsets)."
    ),
    accion_recomendada=(
        "1. Revisar las citas incluidas en la respuesta.\n"
        "  2. Verificar que las citas sean correctas y relevantes.\n"
        "  3. Usar la respuesta como base para el análisis legal.\n"
        "  4. Si hay dudas, consultar directamente los documentos citados (el sistema indica página exacta)."
    ),
    responsable="Analista legal",
    prohibido=(
        "NO asumir que la respuesta es 100% infalible (siempre requiere revisión legal).\n"
        "  NO eliminar las citas al reportar (son la garantía de trazabilidad).\n"
        "  NO modificar la respuesta sin verificar el documento original."
    ),
    severidad="INFO",
)


# ============================
# PLAYBOOKS PROSECUTOR
# ============================

PLAYBOOK_PROSECUTOR_NO_EVIDENCE = Playbook(
    evento="PROSECUTOR: Sin evidencia para acusar",
    significado=(
        "El sistema no encontró documentación alguna que permita evaluar "
        "si hubo incumplimientos legales. No hay base documental para hacer "
        "ninguna afirmación sobre responsabilidades."
    ),
    accion_recomendada=(
        "1. Revisar la lista de 'evidencia_requerida' en la respuesta del sistema.\n"
        "  2. Solicitar al cliente TODOS los documentos listados.\n"
        "  3. NO proceder con el análisis de responsabilidades hasta tener la documentación.\n"
        "  4. Informar al cliente que el análisis requiere documentación mínima obligatoria."
    ),
    responsable="Analista legal",
    prohibido=(
        "NO emitir opiniones sobre posibles incumplimientos sin documentación.\n"
        "  NO asumir ausencia de responsabilidad por falta de evidencia.\n"
        "  NO generar informes parciales."
    ),
    severidad="WARNING",
)

PLAYBOOK_PROSECUTOR_PARTIAL_EVIDENCE = Playbook(
    evento="PROSECUTOR: Evidencia parcial (faltan documentos clave)",
    significado=(
        "El sistema encontró indicios documentados de posibles incumplimientos, "
        "PERO faltan documentos clave para poder formular una acusación completa. "
        "La lista 'evidencia_faltante' indica exactamente qué documentos se requieren."
    ),
    accion_recomendada=(
        "1. Revisar los indicios detectados (pueden ser relevantes).\n"
        "  2. Solicitar ESPECÍFICAMENTE los documentos listados en 'evidencia_faltante'.\n"
        "  3. NO formular acusaciones hasta completar la evidencia.\n"
        "  4. Informar al cliente que se requieren documentos adicionales para concluir."
    ),
    responsable="Analista legal + Abogado senior",
    prohibido=(
        "NO completar la evidencia con inferencias o suposiciones.\n"
        "  NO acusar con evidencia parcial.\n"
        "  NO asumir que 'lo que falta no es relevante'."
    ),
    severidad="WARNING",
)

PLAYBOOK_PROSECUTOR_LOW_CONFIDENCE = Playbook(
    evento="PROSECUTOR: Baja confianza (calidad documental insuficiente)",
    significado=(
        "Existen documentos pero su calidad, coherencia o completitud es insuficiente "
        "para formular acusaciones con garantías. Puede ser por:\n"
        "  - Documentos ilegibles o mal escaneados.\n"
        "  - Documentos contradictorios.\n"
        "  - Información fragmentada o incompleta."
    ),
    accion_recomendada=(
        "1. Solicitar documentos originales o versiones de mejor calidad.\n"
        "  2. Verificar manualmente los documentos aportados.\n"
        "  3. Si persiste baja calidad, informar al cliente que no es posible emitir conclusiones.\n"
        "  4. Escalar a abogado senior si hay contradicciones relevantes."
    ),
    responsable="Analista legal + Abogado senior",
    prohibido=(
        "NO proceder con documentación de baja calidad.\n"
        "  NO forzar acusaciones con evidencia ambigua.\n"
        "  NO asumir hechos no documentados."
    ),
    severidad="WARNING",
)

PLAYBOOK_PROSECUTOR_ACCUSATION_START = Playbook(
    evento="PROSECUTOR: Acusación iniciada (evidencia completa detectada)",
    significado=(
        "El sistema ha detectado un posible incumplimiento legal con evidencia "
        "documental completa, trazable y suficiente. La acusación incluye:\n"
        "  - Obligación legal específica (ley + artículo + deber).\n"
        "  - Evidencia documental con citas exactas (página + offsets).\n"
        "  - Nivel de confianza calculado.\n"
        "  - Severidad estimada."
    ),
    accion_recomendada=(
        "1. REVISAR la acusación generada (el sistema NO reemplaza al abogado).\n"
        "  2. Verificar las evidencias citadas consultando los documentos originales.\n"
        "  3. Validar que la interpretación legal es correcta.\n"
        "  4. Evaluar si la severidad asignada es adecuada.\n"
        "  5. Decidir si procede formular la acusación formalmente.\n"
        "  6. Documentar la decisión final (aceptar, modificar, descartar)."
    ),
    responsable="Abogado senior (revisión obligatoria)",
    prohibido=(
        "NO asumir culpabilidad automática.\n"
        "  NO usar la acusación sin revisión legal.\n"
        "  NO omitir la verificación de evidencias.\n"
        "  NO delegar la decisión final al sistema."
    ),
    severidad="INFO",
)

PLAYBOOK_PROSECUTOR_NARRATIVE_DETECTED = Playbook(
    evento="PROSECUTOR: Narrativa especulativa detectada (ERROR GRAVE)",
    significado=(
        "El sistema intentó generar texto especulativo o conclusiones sin respaldo "
        "documental directo. Esto viola el protocolo probatorio estricto y se considera "
        "un fallo operativo grave."
    ),
    accion_recomendada=(
        "1. DESCARTAR inmediatamente la salida generada.\n"
        "  2. NO usar ninguna parte del output para análisis legal.\n"
        "  3. Escalar a tech lead + legal para investigar causa raíz.\n"
        "  4. Revisar logs completos del caso.\n"
        "  5. Bloquear el caso hasta resolución del incidente."
    ),
    responsable="Tech lead + Director legal",
    prohibido=(
        "NO entregar al cliente.\n"
        "  NO usar como evidencia.\n"
        "  NO continuar con el caso sin investigar.\n"
        "  NO asumir que es un incidente aislado sin análisis."
    ),
    severidad="ERROR",
)


# ============================
# ACCESO A PLAYBOOKS
# ============================

PLAYBOOKS_REGISTRY = {
    # RAG
    "RAG_EVIDENCIA_INSUFICIENTE": PLAYBOOK_RAG_EVIDENCIA_INSUFICIENTE,
    "RAG_BAJA_CONFIANZA": PLAYBOOK_RAG_BAJA_CONFIANZA,
    "RAG_RESPUESTA_CON_EVIDENCIA": PLAYBOOK_RAG_RESPUESTA_CON_EVIDENCIA,
    # PROSECUTOR
    "PROSECUTOR_NO_EVIDENCE": PLAYBOOK_PROSECUTOR_NO_EVIDENCE,
    "PROSECUTOR_PARTIAL_EVIDENCE": PLAYBOOK_PROSECUTOR_PARTIAL_EVIDENCE,
    "PROSECUTOR_LOW_CONFIDENCE": PLAYBOOK_PROSECUTOR_LOW_CONFIDENCE,
    "PROSECUTOR_ACCUSATION_START": PLAYBOOK_PROSECUTOR_ACCUSATION_START,
    "PROSECUTOR_NARRATIVE_DETECTED": PLAYBOOK_PROSECUTOR_NARRATIVE_DETECTED,
}


def get_playbook(event_key: str) -> Optional[Playbook]:
    """
    Obtiene el playbook operativo para un evento.

    Args:
        event_key: Clave del evento (ej: "PROSECUTOR_NO_EVIDENCE")

    Returns:
        Playbook o None si no existe
    """
    return PLAYBOOKS_REGISTRY.get(event_key)


def print_all_playbooks() -> None:
    """Imprime todos los playbooks disponibles."""
    print("\n" + "=" * 80)
    print("PLAYBOOKS OPERACIONALES - PHOENIX")
    print("=" * 80)
    print(f"\nTotal playbooks disponibles: {len(PLAYBOOKS_REGISTRY)}")

    for key, playbook in PLAYBOOKS_REGISTRY.items():
        playbook.print_playbook()


def get_playbooks_by_severity(severity: str) -> list[Playbook]:
    """
    Obtiene playbooks filtrados por severidad.

    Args:
        severity: INFO, WARNING, ERROR

    Returns:
        Lista de playbooks con la severidad indicada
    """
    return [playbook for playbook in PLAYBOOKS_REGISTRY.values() if playbook.severidad == severity]

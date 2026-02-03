"""
Componentes modulares de UI para Phoenix Legal.

Organización por responsabilidad:
- common.py: Helpers compartidos ✅
- evidence.py: Renderizado de evidencias ✅

Para componentes principales (balance, credits, ratios, etc.),
importar directamente desde app.ui.components.

La modularización completa se hará progresivamente en futuras iteraciones.
"""

# Helpers comunes (modulares)
from app.ui.components_modules.common import (
    get_confidence_emoji,
    get_field_value,
)

# Evidencias (modulares)
from app.ui.components_modules.evidence import (
    render_alert_evidence_list,
    render_evidence_expander,
)

__all__ = [
    # Helpers
    "get_field_value",
    "get_confidence_emoji",
    # Evidencias
    "render_evidence_expander",
    "render_alert_evidence_list",
]

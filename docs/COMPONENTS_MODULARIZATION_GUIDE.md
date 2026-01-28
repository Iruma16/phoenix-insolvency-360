# Guía de Modularización de Components

## Estado Actual

**✅ Creados:**
- `app/ui/components_modules/__init__.py` - Exports centralizados
- `app/ui/components_modules/common.py` - Helpers compartidos (testeables)
- `app/ui/components_modules/evidence.py` - Renderizado de evidencias

**❌ Pendientes (extraer de components.py):**
- `balance.py` - render_balance_block()
- `credits.py` - render_credits_block()
- `ratios.py` - render_ratios_block()
- `insolvency.py` - render_insolvency_block()
- `timeline.py` - render_timeline_block() + render_timeline_block_backend()
- `patterns.py` - render_suspicious_patterns()

## Cómo Completar la Modularización

### Paso 1: Extraer cada función a su módulo

Para cada componente, crear archivo nuevo y mover código:

```python
# app/ui/components_modules/balance.py

import streamlit as st
from typing import Dict, Any, Optional

from app.ui.components_modules.common import get_field_value, get_confidence_emoji
from app.ui.components_modules.evidence import render_evidence_expander

def render_balance_block(balance_dict: Optional[Dict[str, Any]], 
                         profit_loss_dict: Optional[Dict[str, Any]]):
    """Renderiza el bloque de datos contables estructurados."""
    # ... copiar código de components.py líneas 254-500
    pass
```

### Paso 2: Actualizar imports en streamlit_mvp.py

```python
# Cambiar de:
from app.ui.components import (
    render_balance_block,
    ...
)

# A:
from app.ui.components_modules import (
    render_balance_block,
    ...
)
```

### Paso 3: Mantener components.py como deprecated

```python
# app/ui/components.py

"""
DEPRECATED: Este archivo será eliminado en v2.0.

Usa app.ui.components_modules en su lugar.
"""

from app.ui.components_modules import *

import warnings
warnings.warn(
    "components.py está deprecated. "
    "Usa app.ui.components_modules",
    DeprecationWarning
)
```

## Beneficios de la Modularización

1. **Testeable**: Cada módulo se puede testear independientemente
2. **Mantenible**: Cambios en balance no afectan timeline
3. **Legible**: Archivos de 100-200 líneas vs 1500+
4. **Escalable**: Fácil agregar nuevos componentes

## Prioridad

**Modularización completa: MEDIA**
- No bloquea funcionalidad
- Bloquea escalabilidad del equipo
- Recomendado antes de v2.0

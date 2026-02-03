"""
Whitelist para Vulture.

Este fichero permite mantener el reporte de "dead code" útil sin bloquear el CI
por falsos positivos típicos (decorators de frameworks, imports dinámicos, etc.).

Regla: solo añadir aquí cuando se haya verificado manualmente que Vulture se equivoca.
"""

# FastAPI/Streamlit suelen referenciar por introspección; mantenemos el whitelist vacío por defecto.

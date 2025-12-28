"""
Cargador de rulebook desde JSON.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from .models import Rulebook

logger = logging.getLogger(__name__)


def load_rulebook(file_path: Path) -> Rulebook:
    """
    Carga un rulebook desde un archivo JSON.

    Args:
        file_path: Ruta al archivo JSON del rulebook

    Returns:
        Rulebook cargado y validado

    Raises:
        FileNotFoundError: Si el archivo no existe
        ValueError: Si el JSON es inválido o no cumple el esquema
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Rulebook no encontrado: {file_path}")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        rulebook = Rulebook(**data)
        logger.info(f"Rulebook cargado: {len(rulebook.rules)} reglas")
        return rulebook
    except json.JSONDecodeError as e:
        raise ValueError(f"Error parseando JSON del rulebook: {e}")
    except Exception as e:
        raise ValueError(f"Error validando rulebook: {e}")


def load_default_rulebook() -> Rulebook:
    """
    Carga el rulebook por defecto del proyecto.

    Returns:
        Rulebook por defecto
    """
    default_path = Path(__file__).parent.parent.parent.parent / "tests" / "reports" / "rulebook_mvp_completo.json"
    return load_rulebook(default_path)


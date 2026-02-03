from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    # app/ui/mvp/debug.py -> repo root = parents[3]
    return Path(__file__).resolve().parents[3]


def log_event(event: dict[str, Any]) -> None:
    """
    Logger JSONL para debug de UI.

    Activación:
      PHOENIX_UI_DEBUG_LOG=1

    Ruta:
      PHOENIX_UI_DEBUG_PATH (default: clients_data/logs/ui_debug.jsonl)
    """
    if (os.getenv("PHOENIX_UI_DEBUG_LOG") or "").strip() != "1":
        return

    rel = os.getenv("PHOENIX_UI_DEBUG_PATH") or "clients_data/logs/ui_debug.jsonl"
    p = (_repo_root() / rel).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def log_tabs_initialized(labels: list[str], binding: dict[str, str], *, location: str) -> None:
    log_event(
        {
            "sessionId": "debug-session",
            "runId": "ui",
            "hypothesisId": "H_TABS_ORDER",
            "location": location,
            "message": "tabs_initialized",
            "data": {"labels": labels, "binding": binding},
            "timestamp": int(time.time() * 1000),
        }
    )

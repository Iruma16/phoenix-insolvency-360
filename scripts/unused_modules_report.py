#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reporte de módulos potencialmente no usados (alcanzabilidad por imports).

Objetivo:
- Dar una lista reproducible de módulos de `app/` que no parecen alcanzables desde
  los entrypoints "oficiales" del repo:
  - API: `app/main.py`
  - UI:  `app/ui/streamlit_mvp.py`
  - Scripts: todo `scripts/*.py`

Limitaciones (importante):
- Es análisis ESTÁTICO: no ve imports dinámicos (`importlib`, strings, plugins).
- FastAPI/Streamlit usan introspección, pero los imports suelen ser explícitos.
- No toma `tests/` como raíz a propósito (queremos "runtime roots").

Uso:
  python scripts/unused_modules_report.py
  python scripts/unused_modules_report.py --json
"""

from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModRef:
    mod: str
    path: Path
    is_package_init: bool


def _find_repo_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / "pyproject.toml").exists() or (p / ".git").exists():
            return p
    return start


def _py_files(root: Path) -> list[Path]:
    return sorted([p for p in root.rglob("*.py") if p.is_file()])


def _module_name_from_path(repo_root: Path, py_path: Path) -> str | None:
    rel = py_path.relative_to(repo_root)
    if rel.parts[0] not in ("app", "scripts"):
        return None

    if rel.parts[0] == "scripts":
        # scripts/foo.py -> scripts.foo
        return "scripts." + rel.with_suffix("").as_posix().replace("/", ".").split(".", 1)[1]

    # app/foo/bar.py -> app.foo.bar
    mod = rel.with_suffix("").as_posix().replace("/", ".")
    if mod.endswith(".__init__"):
        mod = mod[: -len(".__init__")]
    return mod


def _resolve_relative(current_mod: str, level: int, module: str | None) -> str | None:
    """
    Resolve `from ..x import y` relative import to absolute module string.
    current_mod: módulo actual (ej: app.api.documents)
    level: número de puntos (1 => mismo paquete)
    module: parte tras los puntos (puede ser None)
    """
    parts = current_mod.split(".")
    if level <= 0:
        return module
    if len(parts) < level:
        return None
    base = parts[:-level]
    if not base:
        return None
    if module:
        return ".".join(base + module.split("."))
    return ".".join(base)


def _imports_from_ast(tree: ast.AST, current_mod: str, known_modules: set[str]) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                if n.name.startswith(("app.", "scripts.")) or n.name in ("app", "scripts"):
                    out.add(n.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                m = node.module
            else:
                m = _resolve_relative(current_mod, node.level, node.module)
            if not m:
                continue
            if m.startswith(("app.", "scripts.")) or m in ("app", "scripts"):
                out.add(m)
                # Caso común: `from app.services import court_pack_service` donde
                # `app.services.court_pack_service` es un submódulo real.
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    cand = f"{m}.{alias.name}"
                    if cand in known_modules:
                        out.add(cand)
    return out


def build_graph(repo_root: Path) -> tuple[dict[str, ModRef], dict[str, set[str]]]:
    modules: dict[str, ModRef] = {}
    edges: dict[str, set[str]] = {}

    for root_dir in (repo_root / "app", repo_root / "scripts"):
        if not root_dir.exists():
            continue
        for py in _py_files(root_dir):
            mod = _module_name_from_path(repo_root, py)
            if not mod:
                continue
            modules[mod] = ModRef(mod=mod, path=py, is_package_init=(py.name == "__init__.py"))

    for mod, ref in modules.items():
        try:
            src = ref.path.read_text(encoding="utf-8")
        except Exception:
            # best-effort: si hay encoding raro, no bloqueamos el reporte
            continue
        try:
            tree = ast.parse(src, filename=str(ref.path))
        except SyntaxError:
            continue
        edges[mod] = _imports_from_ast(tree, current_mod=mod, known_modules=set(modules.keys()))

    return modules, edges


def reachable(roots: set[str], edges: dict[str, set[str]]) -> set[str]:
    seen: set[str] = set()
    stack = list(roots)
    while stack:
        m = stack.pop()
        if m in seen:
            continue
        seen.add(m)
        for nxt in edges.get(m, set()):
            if nxt not in seen:
                stack.append(nxt)
    return seen


def main() -> None:
    ap = argparse.ArgumentParser(description="Reporte de módulos potencialmente no usados.")
    ap.add_argument("--json", action="store_true", help="Salida en JSON")
    args = ap.parse_args()

    repo_root = _find_repo_root(Path(__file__).resolve())
    modules, edges = build_graph(repo_root)

    roots: set[str] = {
        "app.main",
        "app.ui.streamlit_mvp",
    }
    # todos los scripts como raíces
    for mod in modules:
        if mod.startswith("scripts."):
            roots.add(mod)

    seen = reachable(roots, edges)
    all_mods = set(modules.keys())

    # Filtrar paquetes raíz (app, scripts) y módulos que realmente existen
    unreachable = sorted(
        [m for m in all_mods - seen if m.startswith("app.") and not modules[m].is_package_init]
    )

    payload = {
        "repo_root": str(repo_root),
        "roots": sorted(roots),
        "total_modules": len(all_mods),
        "reachable_modules": len(seen),
        "unreachable_app_modules": len(unreachable),
        "unreachable_app_list": unreachable,
    }

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    print("repo_root:", payload["repo_root"])
    print("roots:", len(payload["roots"]))
    print("total_modules:", payload["total_modules"])
    print("reachable_modules:", payload["reachable_modules"])
    print("unreachable_app_modules:", payload["unreachable_app_modules"])
    print()
    for m in unreachable[:200]:
        print("-", m)
    if len(unreachable) > 200:
        print(f"... ({len(unreachable) - 200} más)")


if __name__ == "__main__":
    main()

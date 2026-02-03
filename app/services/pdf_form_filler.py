from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.generic import BooleanObject, NameObject, TextStringObject

from app.models.court_pack import CourtPackState, DocumentStatus, Issue
from app.services import court_pack_service

TEMPLATE_PDF_PATH = Path(
    "judicial_forms/concurso_voluntario/personas_juridicas/20200521 Procedimientos concursales - Formulario para la solicitud de concurso voluntario pers. jur..pdf"
)
FIELD_MAP_PATH = Path("judicial_forms/concurso_voluntario/personas_juridicas/field_map.json")
OUTPUT_PDF_NAME = "Documento_0_Formulario_Solicitud_Concurso.pdf"
CASE_FIELD_MAP_RAW_NAME = "field_map_raw.json"
CASE_FIELD_MAP_EFFECTIVE_NAME = "field_map_effective.json"
CASE_PROFILE_NAME = "case_profile.json"
CASE_PDF_MAPPING_NAME = "pdf_semantic_mapping.json"


class PdfFillError(RuntimeError):
    pass


def _field_map_has_any_fields(raw: Any) -> bool:
    if not isinstance(raw, dict):
        return False
    sections = raw.get("sections")
    if not isinstance(sections, list):
        return False
    for s in sections:
        if not isinstance(s, dict):
            continue
        fields = s.get("fields")
        if isinstance(fields, list) and len(fields) > 0:
            return True
    return False


def ensure_field_map_populated_from_pdf(
    *,
    case_root: Path,
    template_pdf_path: Path,
    repo_field_map_path: Path,
) -> Path:
    """
    Si el field_map del repo existe pero no tiene campos, genera uno por caso en:
      clients_data/cases/<case_id>/court_pack/inputs/field_map_raw.json

    Extrae nombres reales de campos del PDF (AcroForm o annotations /T) y crea un
    field_map RAW de 1 sección donde:
      field_id == pdf_field == nombre_real_del_campo_pdf

    Devuelve la ruta del field_map efectivo a usar.
    """
    paths = court_pack_service.ensure_court_pack_dirs(case_root)
    out_path = paths["inputs_dir"] / CASE_FIELD_MAP_RAW_NAME

    # 1) Si el field_map del repo ya tiene campos, usarlo (es el mapeo semántico autoritativo)
    try:
        raw_repo = json.loads(repo_field_map_path.read_text(encoding="utf-8") or "{}")
    except Exception:
        raw_repo = {}
    if _field_map_has_any_fields(raw_repo):
        return repo_field_map_path

    # 2) Si ya existe un field_map_raw con campos, úsalo (solo cuando el repo no tiene mapeo válido)
    try:
        if out_path.exists():
            raw_existing = json.loads(out_path.read_text(encoding="utf-8") or "{}")
            if _field_map_has_any_fields(raw_existing):
                return out_path
    except Exception:
        pass

    # 3) Extraer nombres reales de campo del PDF (generar RAW por caso)
    try:
        reader = PdfReader(str(template_pdf_path))
    except Exception:
        # no inventar: deja field_map_raw vacío y usa repo
        out_path.write_text(
            json.dumps({"sections": []}, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return repo_field_map_path

    names: list[str] = []
    name_to_ft: dict[str, str] = {}
    try:
        fields = reader.get_fields() or {}
        if isinstance(fields, dict) and fields:
            names = sorted([str(k) for k in fields.keys()])
    except Exception:
        names = []

    if not names:
        seen: set[str] = set()
        for page in reader.pages:
            annots = page.get("/Annots")
            if not annots:
                continue
            try:
                annots = annots.get_object()
            except Exception:
                pass
            if not isinstance(annots, list):
                continue
            for a in annots:
                try:
                    obj = a.get_object()
                except Exception:
                    continue
                t = obj.get("/T")
                if t:
                    tn = str(t)
                    seen.add(tn)
                    ft = obj.get("/FT")
                    if ft:
                        name_to_ft[tn] = str(ft)
        names = sorted(seen)

    # 4) Si no hay campos, no inventar nada
    if not names:
        out_path.write_text(
            json.dumps({"sections": []}, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return repo_field_map_path

    # 5) Escribir field_map RAW por caso
    field_map = {
        "_meta": {"generated_from_pdf": template_pdf_path.name},
        "sections": [
            {
                "section_id": "RAW",
                "title": "Campos PDF (auto)",
                "fields": [
                    {
                        "field_id": n,
                        "label": n,
                        # best-effort: /Tx text, /Btn button, /Ch choice
                        "type": (
                            "checkbox"
                            if name_to_ft.get(n) == "/Btn"
                            else ("choice" if name_to_ft.get(n) == "/Ch" else "text")
                        ),
                        "pdf_field": n,
                        "default": "",
                    }
                    for n in names
                ],
            }
        ],
    }
    out_path.write_text(json.dumps(field_map, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def load_field_map(field_map_path: Path) -> dict[str, Any]:
    """
    Carga field_map.json y valida estructura mínima (sin inventar campos).
    """
    raw = json.loads(field_map_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("field_map.json must be an object")
    if "sections" not in raw or not isinstance(raw["sections"], list):
        raise ValueError("field_map.json missing 'sections' list")
    return raw


def merge_auto_and_overrides(
    auto_values: dict[str, Any], overrides: dict[str, Any]
) -> dict[str, Any]:
    """
    Merge determinista: overrides pisa auto (solo por clave).
    """
    out = dict(auto_values or {})
    for k, v in (overrides or {}).items():
        # IMPORTANT:
        # Empty overrides ("", whitespace, None) frequently appear from UI drafts / mapping steps.
        # They should NOT erase valid auto values coming from DB snapshots (case_profile.json).
        # If the user needs explicit "clear", we should represent that differently (e.g. null + explicit flag).
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        out[k] = v
    return out


def fill_pdf_acroform(
    template_pdf_path: Path, output_pdf_path: Path, pdf_field_values: dict[str, Any]
) -> None:
    """
    Rellena campos AcroForm por nombre usando pypdf.

    V1 (sin overlay):
    - Si no hay AcroForm o falla el relleno, se escribe el PDF SIN rellenar y se lanza PdfFillError.
    """
    template_bytes = template_pdf_path.read_bytes()
    output_pdf_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        reader = PdfReader(str(template_pdf_path))
    except Exception as e:
        output_pdf_path.write_bytes(template_bytes)
        raise PdfFillError(f"invalid_template_pdf: {e}")

    # pypdf.get_fields() puede fallar en PDFs reales (p.ej. KeyError '/Opt').
    # Si falla o devuelve vacío, hacemos fallback rellenando por annotations (/T).
    try:
        fields = reader.get_fields() or {}
    except Exception:
        fields = {}

    def _scan_annotation_field_names() -> set[str]:
        names: set[str] = set()
        for page in reader.pages:
            annots = page.get("/Annots")
            if not annots:
                continue
            try:
                annots = annots.get_object()
            except Exception:
                pass
            if not isinstance(annots, list):
                continue
            for a in annots:
                try:
                    obj = a.get_object()
                except Exception:
                    continue
                t = obj.get("/T")
                if t:
                    names.add(str(t))
        return names

    annot_names: set[str] = set()
    if not fields:
        annot_names = _scan_annotation_field_names()
        if not annot_names:
            output_pdf_path.write_bytes(template_bytes)
            raise PdfFillError("no_acroform")

    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    # Ensure NeedAppearances so viewers render values
    try:
        root = writer._root_object  # type: ignore[attr-defined]
        acro = root.get("/AcroForm") or reader.trailer["/Root"].get("/AcroForm")
        if acro:
            root.update({NameObject("/AcroForm"): acro})
            root["/AcroForm"].update({NameObject("/NeedAppearances"): BooleanObject(True)})
    except Exception:
        pass

    def _fill_by_annotations() -> None:
        for page in writer.pages:
            annots = page.get("/Annots")
            if not annots:
                continue
            try:
                annots = annots.get_object()
            except Exception:
                pass
            if not isinstance(annots, list):
                continue
            for a in annots:
                try:
                    obj = a.get_object()
                except Exception:
                    continue
                t = obj.get("/T")
                if not t:
                    continue
                name = str(t)
                if name not in pdf_field_values:
                    continue
                v = pdf_field_values.get(name)

                ft = obj.get("/FT")
                if ft == "/Btn":
                    # Checkbox / radio: support bool (checkbox) and string tokens (radio values like "1","2"...)
                    try:
                        ap = obj.get("/AP") or {}
                        try:
                            ap = ap.get_object() if hasattr(ap, "get_object") else ap
                        except Exception:
                            pass
                        if not isinstance(ap, dict):
                            ap = {}

                        n = ap.get("/N") or {}
                        try:
                            n = n.get_object() if hasattr(n, "get_object") else n
                        except Exception:
                            pass
                        if not isinstance(n, dict):
                            n = {}
                        on_name = None
                        if hasattr(n, "keys"):
                            for k in n.keys():
                                ks = str(k)
                                if ks != "/Off":
                                    on_name = k
                                    break
                        # If v is a specific state token (e.g., "1"), try to set that exact state.
                        if isinstance(v, str) and v.strip():
                            token = v.strip()
                            candidates = []
                            if hasattr(n, "keys"):
                                candidates = [str(k) for k in n.keys()]
                            desired = token if token.startswith("/") else f"/{token}"
                            if desired in candidates:
                                desired_name = NameObject(desired)
                                obj.update(
                                    {
                                        NameObject("/AS"): desired_name,
                                        NameObject("/V"): desired_name,
                                    }
                                )
                            elif on_name is not None:
                                obj.update({NameObject("/AS"): on_name, NameObject("/V"): on_name})
                            else:
                                obj.update(
                                    {
                                        NameObject("/AS"): NameObject("/Yes"),
                                        NameObject("/V"): NameObject("/Yes"),
                                    }
                                )
                        else:
                            # default checkbox behavior
                            if bool(v):
                                if on_name is not None:
                                    obj.update(
                                        {NameObject("/AS"): on_name, NameObject("/V"): on_name}
                                    )
                                else:
                                    obj.update(
                                        {
                                            NameObject("/AS"): NameObject("/Yes"),
                                            NameObject("/V"): NameObject("/Yes"),
                                        }
                                    )
                            else:
                                obj.update(
                                    {
                                        NameObject("/AS"): NameObject("/Off"),
                                        NameObject("/V"): NameObject("/Off"),
                                    }
                                )
                    except Exception:
                        pass
                else:
                    # Text/Choice default to string
                    try:
                        obj.update(
                            {NameObject("/V"): TextStringObject("" if v is None else str(v))}
                        )
                    except Exception:
                        pass

    def _scan_button_field_names() -> set[str]:
        """
        Collect /Btn field names. We must avoid passing bools for /Btn into
        update_page_form_field_values because pypdf can write invalid /AS True,
        corrupting the PDF. Buttons are handled via annotation filling.
        """
        names: set[str] = set()
        for page in writer.pages:
            annots = page.get("/Annots")
            if not annots:
                continue
            try:
                annots = annots.get_object()
            except Exception:
                pass
            if not isinstance(annots, list):
                continue
            for a in annots:
                try:
                    obj = a.get_object()
                except Exception:
                    continue
                t = obj.get("/T")
                if not t:
                    continue
                if obj.get("/FT") == "/Btn":
                    names.add(str(t))
        return names

    try:
        btn_names = _scan_button_field_names()
        safe_values = {
            k: v
            for k, v in (pdf_field_values or {}).items()
            if isinstance(k, str) and k and (k not in btn_names)
        }
        for i in range(len(writer.pages)):
            writer.update_page_form_field_values(writer.pages[i], safe_values)
    except Exception:
        # Fallback: fill by annotations (works even if get_fields() is broken)
        try:
            _fill_by_annotations()
        except Exception as e:
            output_pdf_path.write_bytes(template_bytes)
            raise PdfFillError(f"fill_failed: {e}")

    # Always do a best-effort annotation pass (needed for /Btn /AS handling; also harmless for text).
    try:
        _fill_by_annotations()
    except Exception:
        pass

    try:
        with open(output_pdf_path, "wb") as f:
            writer.write(f)
    except Exception as e:
        output_pdf_path.write_bytes(template_bytes)
        raise PdfFillError(f"write_failed: {e}")

    # Validate output looks like a real PDF (avoid leaving corrupt/blank outputs behind).
    # If invalid, fall back to the template and surface a controlled error.
    try:
        out = output_pdf_path.read_bytes()
        # Basic PDF signature and EOF marker check
        if not out.startswith(b"%PDF-"):
            raise PdfFillError("write_invalid_pdf: missing_header")
        tail = out[-2048:] if len(out) >= 2048 else out
        if b"%%EOF" not in tail:
            raise PdfFillError("write_invalid_pdf: missing_eof")
        # Parse check (best-effort; some viewers are stricter than others)
        try:
            rr = PdfReader(str(output_pdf_path))
            # Force-load annotations to catch lazy parse errors introduced by invalid objects
            for p in rr.pages:
                ann = p.get("/Annots")
                if not ann:
                    continue
                try:
                    ann = ann.get_object()
                except Exception:
                    pass
                if isinstance(ann, list):
                    for a in ann[:10]:
                        try:
                            _ = a.get_object().get("/T")
                        except Exception as e:
                            raise PdfFillError(f"write_invalid_pdf: parse_failed: {e}")
        except Exception as e:
            raise PdfFillError(f"write_invalid_pdf: parse_failed: {e}")
    except PdfFillError:
        output_pdf_path.write_bytes(template_bytes)
        raise
    except Exception as e:
        output_pdf_path.write_bytes(template_bytes)
        raise PdfFillError(f"write_invalid_pdf: {e}")


def _load_json_if_exists(p: Path) -> dict[str, Any]:
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8") or "{}")
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def build_auto_values_minimal(case_root: Path, state: CourtPackState) -> dict[str, Any]:
    """
    Fuente: state.debtor_flags + (si existen) inputs JSON en court_pack/inputs/.
    Si un valor no existe: \"\" o \"DESCONOCIDO\" (usamos \"\" por defecto).
    No DB. No lectura de PDFs.
    """
    paths = court_pack_service.ensure_court_pack_dirs(case_root)
    existing_auto = _load_json_if_exists(paths["inputs_formulario_auto"])
    existing_overrides = _load_json_if_exists(paths["inputs_formulario_overrides"])
    existing_final = _load_json_if_exists(paths["inputs_formulario_final"])
    case_profile_path = paths["inputs_dir"] / CASE_PROFILE_NAME
    case_profile: dict[str, Any] = {}
    try:
        if case_profile_path.exists():
            raw = json.loads(case_profile_path.read_text(encoding="utf-8") or "{}")
            if isinstance(raw, dict):
                rf = raw.get("resolved_fields")
                if isinstance(rf, dict):
                    case_profile = rf
    except Exception:
        case_profile = {}

    # Base: debtor_flags (clave literal; no mapeo heurístico)
    auto: dict[str, Any] = {
        "debtor_type": state.debtor_flags.debtor_type,
        "has_workers": state.debtor_flags.has_workers,
        "requires_audit": state.debtor_flags.requires_audit,
        "accounting_obligation": state.debtor_flags.accounting_obligation,
        "has_procurador": state.debtor_flags.has_procurador,
    }

    # Incorporar snapshot DB (case_profile.json) de forma determinista (sin heurística):
    # - Acepta tipos básicos y value_json dicts {"text"/"value"/"number"} -> string/number
    for k, v in (case_profile or {}).items():
        if k in auto:
            continue
        if isinstance(v, dict):
            inner = v.get("value", v.get("text", v.get("number")))
            auto[k] = inner
        else:
            auto[k] = v

    # Incorporar inputs ya existentes (solo para no perder valores previos)
    for src in (existing_auto, existing_overrides, existing_final):
        for k, v in src.items():
            if k not in auto:
                auto[k] = v

    # Completar con field_ids del field_map a vacío si no existen
    if FIELD_MAP_PATH.exists():
        try:
            fm = load_field_map(FIELD_MAP_PATH)
            for sec in fm.get("sections") or []:
                for f in sec.get("fields") or []:
                    fid = f.get("field_id")
                    default = f.get("default", "")
                    if isinstance(fid, str) and fid and fid not in auto:
                        auto[fid] = default if isinstance(default, str) else ""
        except Exception:
            pass

    return auto


def _field_map_to_pdf_values(
    field_map: dict[str, Any], values_by_field_id: dict[str, Any]
) -> dict[str, Any]:
    pdf_values: dict[str, Any] = {}
    for sec in field_map.get("sections") or []:
        for f in sec.get("fields") or []:
            fid = f.get("field_id")
            pdf_field = f.get("pdf_field")
            if isinstance(fid, str) and isinstance(pdf_field, str) and fid and pdf_field:
                if fid not in values_by_field_id:
                    continue
                v = values_by_field_id.get(fid, "")

                # Support for effective mapping fields:
                # - checkbox: expect bool-like
                # - value_map: map semantic value -> radio value token (e.g. "actual" -> "1")
                if isinstance(f, dict) and isinstance(f.get("value_map"), dict):
                    vm = f.get("value_map") or {}
                    key = str(v).strip() if v is not None else ""
                    mapped = vm.get(key)
                    if mapped is not None:
                        pdf_values[pdf_field] = str(mapped)
                    else:
                        pdf_values[pdf_field] = ""
                    continue

                if bool(f.get("checkbox")):
                    if isinstance(v, bool):
                        pdf_values[pdf_field] = v
                    else:
                        vs = str(v).strip().lower()
                        pdf_values[pdf_field] = vs in ("1", "true", "yes", "si", "sí", "on")
                    continue

                pdf_values[pdf_field] = v
    return pdf_values


def _update_doc0_in_state(
    state: CourtPackState,
    *,
    generated_file_path: str,
    inputs_hash: str,
    issues: list[Issue],
) -> CourtPackState:
    docs = []
    for d in state.documents:
        if d.doc_type == "doc0_formulario":
            docs.append(
                d.model_copy(
                    update={
                        "status": DocumentStatus.generated,
                        "generated_file_path": generated_file_path,
                        "last_generated_at": court_pack_service._utc_now_iso(),  # internal helper already in service
                        "inputs_hash": inputs_hash,
                        "issues": issues,
                        "errors_count": sum(1 for x in issues if x.severity == "HIGH"),
                        "warnings_count": sum(1 for x in issues if x.severity in ("MEDIUM", "LOW")),
                    }
                )
            )
        else:
            docs.append(d)
    return state.model_copy(update={"documents": docs})


def generate_document_0(case_root: Path, state: CourtPackState, user_id: str) -> Path:
    """
    Flujo:
      1) ensure dirs
      2) auto = build_auto_values_minimal(...)
      3) guarda inputs/formulario_auto.json
      4) lee inputs/formulario_overrides.json (si no existe, {})
      5) final = merge
      6) guarda inputs/formulario_final.json
      7) usa field_map para traducir field_id -> pdf_field y rellenar
      8) guarda PDF en generated/
      9) actualiza state.documents[doc0] (status=generated, path, hashes)
      10) save_state
    """
    paths = court_pack_service.ensure_court_pack_dirs(case_root)

    if not TEMPLATE_PDF_PATH.exists():
        raise FileNotFoundError(str(TEMPLATE_PDF_PATH))
    if not FIELD_MAP_PATH.exists():
        raise FileNotFoundError(str(FIELD_MAP_PATH))

    auto = build_auto_values_minimal(case_root, state)
    paths["inputs_formulario_auto"].write_text(
        json.dumps(auto, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    overrides = _load_json_if_exists(paths["inputs_formulario_overrides"])
    final = merge_auto_and_overrides(auto, overrides)
    paths["inputs_formulario_final"].write_text(
        json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Ensure we have a RAW field map (names from PDF) available per-case if repo map is empty.
    raw_or_repo_field_map_path = ensure_field_map_populated_from_pdf(
        case_root=case_root,
        template_pdf_path=TEMPLATE_PDF_PATH,
        repo_field_map_path=FIELD_MAP_PATH,
    )
    # Prefer per-case semantic mapping (created from UI) ONLY if it looks compatible with the template PDF.
    # If the "effective" map is empty or points to non-existent pdf_field names, fall back to repo/raw map.
    case_effective = paths["inputs_dir"] / CASE_FIELD_MAP_EFFECTIVE_NAME

    def _scan_pdf_field_names(template_pdf_path: Path) -> set[str]:
        try:
            r = PdfReader(str(template_pdf_path))
        except Exception:
            return set()
        names: set[str] = set()
        # get_fields may be broken; scan annotations /T deterministically
        for page in r.pages:
            annots = page.get("/Annots")
            if not annots:
                continue
            try:
                annots = annots.get_object()
            except Exception:
                pass
            if not isinstance(annots, list):
                continue
            for a in annots:
                try:
                    obj = a.get_object()
                except Exception:
                    continue
                t = obj.get("/T")
                if t:
                    names.add(str(t))
        return names

    chosen_map_path = raw_or_repo_field_map_path
    chosen_reason = "fallback_repo_or_raw"
    if case_effective.exists():
        try:
            eff = load_field_map(case_effective)
            # Gather pdf_field tokens from effective map
            pdf_fields: list[str] = []
            field_ids: list[str] = []
            for sec in eff.get("sections") or []:
                for f in sec.get("fields") or []:
                    pf = (f or {}).get("pdf_field") if isinstance(f, dict) else None
                    if isinstance(pf, str) and pf:
                        pdf_fields.append(pf)
                    fid = (f or {}).get("field_id") if isinstance(f, dict) else None
                    if isinstance(fid, str) and fid:
                        field_ids.append(fid)
            pdf_fields = [x for x in pdf_fields if isinstance(x, str)]
            # Validate coverage against template field names
            pdf_names = _scan_pdf_field_names(TEMPLATE_PDF_PATH)
            hits = sum(1 for pf in pdf_fields if pf in pdf_names)
            coverage = (hits / max(1, len(pdf_fields))) if pdf_fields else 0.0

            # Extra safety: si el effective map no tiene campos de documentación (doc*),
            # no lo usamos para doc0 porque dejaría la sección F sin marcar.
            has_doc_fields = any(fid.startswith("doc") for fid in field_ids)
            if _field_map_has_any_fields(eff) and coverage >= 0.60 and has_doc_fields:
                chosen_map_path = case_effective
                chosen_reason = "effective_ok"
            else:
                chosen_map_path = raw_or_repo_field_map_path
                chosen_reason = (
                    "effective_ignored_low_coverage"
                    if coverage < 0.60
                    else (
                        "effective_ignored_missing_doc_fields"
                        if not has_doc_fields
                        else "effective_ignored_empty"
                    )
                )
        except Exception:
            chosen_map_path = raw_or_repo_field_map_path
            chosen_reason = "effective_ignored_error"

    field_map = load_field_map(chosen_map_path)
    pdf_values = _field_map_to_pdf_values(field_map, final)

    # region agent log (debug-mode)
    try:
        dbg_path = "/Users/irumabragado/Documents/procesos/202512_phoenix-legal/.cursor/debug.log"
        non_empty = 0
        checkbox_true = 0
        for k, v in (pdf_values or {}).items():
            if isinstance(v, bool):
                if v:
                    checkbox_true += 1
                    non_empty += 1
            elif v is None:
                continue
            elif isinstance(v, (int, float)):
                if float(v) != 0:
                    non_empty += 1
            else:
                if str(v).strip():
                    non_empty += 1
        # Count doc* fields in chosen map (helps debug F checkboxes)
        doc_fields = 0
        try:
            for sec in field_map.get("sections") or []:
                for f in sec.get("fields") or []:
                    fid = (f or {}).get("field_id") if isinstance(f, dict) else None
                    if isinstance(fid, str) and fid.startswith("doc"):
                        doc_fields += 1
        except Exception:
            doc_fields = 0

        payload = {
            "sessionId": "debug-session",
            "runId": "post-fix-justificante-v2",
            "hypothesisId": "H_PDFMAP",
            "location": "app/services/pdf_form_filler.py:generate_document_0",
            "message": "map_selection",
            "data": {
                "case_id": str(case_root.name),
                "chosen_map": str(chosen_map_path),
                "reason": chosen_reason,
                "pdf_values_keys": len(list((pdf_values or {}).keys())),
                "pdf_values_non_empty": int(non_empty),
                "checkbox_true": int(checkbox_true),
                "doc_fields_in_map": int(doc_fields),
            },
            "timestamp": int(court_pack_service.time.time() * 1000)
            if hasattr(court_pack_service, "time")
            else None,
        }
        # safer timestamp fallback
        if payload["timestamp"] is None:
            import time as _t

            payload["timestamp"] = int(_t.time() * 1000)
        with open(dbg_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # endregion agent log (debug-mode)

    output_pdf_path = paths["generated_dir"] / OUTPUT_PDF_NAME
    issues: list[Issue] = []
    try:
        fill_pdf_acroform(TEMPLATE_PDF_PATH, output_pdf_path, pdf_values)
    except PdfFillError as e:
        issues.append(
            Issue(
                severity="HIGH",
                code="DOC0_FILL_FAILED",
                message=str(e),
                field_path=None,
                suggestion=None,
            )
        )

    final_hash = court_pack_service.compute_sha256_bytes(
        json.dumps(final, ensure_ascii=False, sort_keys=True).encode("utf-8")
    )
    rel_path = str(output_pdf_path.relative_to(case_root))
    updated_state = _update_doc0_in_state(
        state, generated_file_path=rel_path, inputs_hash=final_hash, issues=issues
    )

    # Save state (auditable via court_pack_service internal audit)
    court_pack_service.save_state(case_root, updated_state)
    return output_pdf_path

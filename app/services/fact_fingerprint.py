import hashlib
import json
import re
from typing import Any, Optional


def _norm_text(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def build_fact_fingerprint(
    *,
    case_id: str,
    fact_type: str,
    date_iso: Optional[str],
    amount_cents: Optional[int],
    counterparty: Optional[str],
    extra: Optional[dict[str, Any]] = None,
) -> str:
    """
    Huella estable del hecho.
    - Si el mismo hecho aparece en email + factura, debe dar el mismo fingerprint.
    """
    payload = {
        "case_id": case_id,
        "fact_type": fact_type.strip().lower(),
        "date": date_iso,
        "amount_cents": amount_cents,
        "counterparty": _norm_text(counterparty),
        "extra": extra or {},
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

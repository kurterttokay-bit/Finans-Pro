import json
import re
from typing import Any, Optional


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _extract_first_json_object(text: str) -> Optional[str]:
    """
    İlk dengeli JSON objesini bulur.
    Regex yerine bracket-counting kullanır.
    """
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(text)):
        ch = text[i]

        if escape:
            escape = False
            continue

        if ch == "\\":
            escape = True
            continue

        if ch == '"':
            in_string = not in_string
            continue

        if not in_string:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]

    return None


def _cleanup_json_string(raw: str) -> str:
    raw = raw.strip()

    # Kod bloğu varsa temizle
    raw = _strip_code_fences(raw)

    # Sondaki gereksiz virgülleri kaldır
    raw = re.sub(r",\s*([}\]])", r"\1", raw)

    # Smart quotes temizliği
    raw = raw.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")

    return raw


def safe_json_loads(text: str) -> Optional[dict[str, Any]]:
    """
    Model çıktısından güvenli şekilde JSON dict çıkarmaya çalışır.
    """
    if not text:
        return None

    text = _strip_code_fences(text)

    # Önce tüm metin JSON mu dene
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # Sonra ilk dengeli objeyi ayıkla
    candidate = _extract_first_json_object(text)
    if not candidate:
        return None

    candidate = _cleanup_json_string(candidate)

    try:
        data = json.loads(candidate)
        if isinstance(data, dict):
            return data
    except Exception:
        return None

    return None

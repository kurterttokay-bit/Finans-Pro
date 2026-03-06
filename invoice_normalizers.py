import re
from datetime import datetime


def normalize_currency(value) -> str:
    if value is None:
        return "TL"

    s = str(value).strip().upper()

    if "USD" in s or "$" in s:
        return "USD"
    if "EUR" in s or "€" in s:
        return "EUR"
    if "TL" in s or "TRY" in s or "₺" in s:
        return "TL"

    return "TL"


def normalize_amount(value) -> float:
    if value is None:
        return 0.0

    s = str(value).strip()

    # Yazı içindeki para karakterlerini temizle
    s = s.replace("TL", "").replace("TRY", "").replace("₺", "")
    s = s.replace("USD", "").replace("EUR", "").replace("$", "").replace("€", "")
    s = s.strip()

    # 1.250,75 -> 1250.75
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")

    # Sadece sayı, eksi, nokta kalsın
    s = re.sub(r"[^0-9.\-]", "", s)

    try:
        return float(s)
    except Exception:
        return 0.0


def normalize_date(value) -> str:
    if not value:
        return datetime.now().strftime("%d.%m.%Y")

    s = str(value).strip()

    for fmt in ("%d.%m.%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%d.%m.%Y")
        except Exception:
            pass

    return datetime.now().strftime("%d.%m.%Y")

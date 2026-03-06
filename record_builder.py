import json
from invoice_normalizers import normalize_amount, normalize_currency, normalize_date

def parse_invoice_from_qr(qr_text: str) -> dict | None:
    if not qr_text:
        return None

    try:
        data = json.loads(qr_text)
    except Exception:
        return None

    kdv_orani = ""
    for key in data.keys():
        if "kdvmatrah(" in key:
            try:
                kdv_orani = key.split("kdvmatrah(")[1].split(")")[0]
            except Exception:
                kdv_orani = ""

    return {
        "firma_adi": "",
        "evrak_tipi": "Fatura",
        "evrak_no": str(data.get("no", "")).strip(),
        "vergi_kimlik_no": str(data.get("avkntckn", "") or data.get("vknckn", "")).strip(),
        "para_birimi": normalize_currency(data.get("parabirimi", "TL")),
        "ara_toplam": normalize_amount(data.get("malhizmettoplam", 0)),
        "kdv_orani": normalize_amount(kdv_orani) if kdv_orani else 0,
        "kdv_tutari": normalize_amount(data.get("hesaplanankdv(20)", 0)),
        "genel_toplam": normalize_amount(data.get("odenecek", data.get("vergidahil", 0))),
        "belge_tarihi": normalize_date(data.get("tarih", "")),
        "aciklama": f"QR senaryo: {data.get('senaryo', '')} / tip: {data.get('tip', '')}",
    }

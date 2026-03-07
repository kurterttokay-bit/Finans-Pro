import re
from io import BytesIO
from datetime import datetime

import pandas as pd
import streamlit as st

# Optional libs
try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None

try:
    from pdf2image import convert_from_bytes
except Exception:
    convert_from_bytes = None

try:
    import pytesseract
except Exception:
    pytesseract = None

try:
    from PIL import Image
except Exception:
    Image = None

st.set_page_config(page_title="Fatura Tara → Excel", page_icon="📄", layout="wide")


def normalize_spaces(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_date(value: str) -> str:
    if not value:
        return ""
    value = value.strip()
    value = value.replace("/", ".").replace("-", ".")
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", value)
    if m:
        return f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
    m = re.search(r"(\d{4})\.(\d{2})\.(\d{2})", value)
    if m:
        return f"{m.group(3)}.{m.group(2)}.{m.group(1)}"
    return value


def normalize_amount(value: str) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().upper()
    s = s.replace("TL", "").replace("TRY", "").replace("₺", "")
    s = s.replace(" ", "")
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(".", "").replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else 0.0


def amount_to_text(v) -> str:
    try:
        num = float(v)
    except Exception:
        return ""
    return f"{num:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


FIELD_LABELS = {
    "invoice_no": [r"Fatura No", r"Belge No", r"Evrak No"],
    "invoice_date": [r"Fatura Tarihi", r"Belge Tarihi", r"Tarih"],
    "order_no": [r"Sipariş No"],
    "order_date": [r"Sipariş Tarihi"],
    "payable_total": [r"Ödenecek Tutar", r"Vergiler Dahil Toplam Tutar", r"Genel Toplam"],
    "subtotal": [r"Mal / Hizmet Toplam Tutarı", r"Mal/Hizmet Toplam Tutarı", r"Ara Toplam"],
    "vat_amount": [r"Hesaplanan KDV", r"KDV Tutarı"],
    "ettn": [r"ETTN"],
}


def find_value_after_label(text: str, labels: list[str], multiline: bool = False) -> str:
    flags = re.IGNORECASE | re.MULTILINE
    for label in labels:
        if multiline:
            pattern = rf"{label}\s*:?\s*(.+)"
        else:
            pattern = rf"{label}\s*:?\s*([^\n]+)"
        m = re.search(pattern, text, flags)
        if m:
            return m.group(1).strip()
    return ""



def extract_pdf_text(file_bytes: bytes) -> str:
    texts = []
    if PdfReader is not None:
        try:
            reader = PdfReader(BytesIO(file_bytes))
            for page in reader.pages:
                texts.append(page.extract_text() or "")
        except Exception:
            pass
    if not "".join(texts).strip() and fitz is not None:
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            for page in doc:
                texts.append(page.get_text("text"))
        except Exception:
            pass
    return normalize_spaces("\n".join(texts))



def ocr_image(pil_image) -> str:
    if pytesseract is None:
        return ""
    return pytesseract.image_to_string(pil_image, lang="eng")



def ocr_pdf(file_bytes: bytes, dpi: int = 300, max_pages: int = 3) -> str:
    if convert_from_bytes is None or pytesseract is None:
        return ""
    texts = []
    try:
        images = convert_from_bytes(file_bytes, dpi=dpi, first_page=1, last_page=max_pages)
        for img in images:
            texts.append(ocr_image(img))
    except Exception:
        return ""
    return normalize_spaces("\n".join(texts))



def read_uploaded_file(uploaded_file, use_ocr: bool) -> tuple[str, str]:
    file_bytes = uploaded_file.getvalue()
    ext = uploaded_file.name.lower().rsplit(".", 1)[-1]
    text = ""
    method = ""

    if ext == "pdf":
        text = extract_pdf_text(file_bytes)
        method = "pdf_text"
        if use_ocr and (not text or len(text) < 80):
            ocr_text = ocr_pdf(file_bytes)
            if len(ocr_text) > len(text):
                text = ocr_text
                method = "ocr_pdf"
    else:
        if Image is None:
            raise RuntimeError("PIL bulunamadı. Görsel işlenemiyor.")
        image = Image.open(BytesIO(file_bytes))
        if use_ocr:
            text = ocr_image(image)
            method = "ocr_image"
    return normalize_spaces(text), method



def parse_seller(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return ""
    stop_words = ("E-FATURA", "E-ARŞİV", "SAYIN", "FATURA NO", "FATURA TARİHİ")
    seller_lines = []
    for ln in lines[:12]:
        up = ln.upper()
        if any(sw in up for sw in stop_words):
            break
        seller_lines.append(ln)
        if len(seller_lines) >= 3:
            break
    return seller_lines[0] if seller_lines else ""



def parse_buyer(text: str) -> str:
    m = re.search(r"SAYIN\s*\n+(.+)", text, re.IGNORECASE)
    if m:
        line = m.group(1).strip()
        line = line.split("\n")[0].strip()
        return line
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if ln.strip().upper() == "SAYIN" and i + 1 < len(lines):
            return lines[i + 1].strip()
    return ""



def parse_product_summary(text: str) -> str:
    start_markers = ["Malzeme /", "Malzeme/Hizmet", "Açıklaması", "Açıklamalar"]
    end_markers = ["Mal / Hizmet Toplam", "Mal/Hizmet Toplam", "Ödenecek Tutar", "Vergiler Dahil Toplam"]
    start_idx = -1
    for marker in start_markers:
        idx = text.find(marker)
        if idx != -1:
            start_idx = idx
            break
    if start_idx == -1:
        return ""
    chunk = text[start_idx:]
    end_idx = len(chunk)
    for marker in end_markers:
        idx = chunk.find(marker)
        if idx != -1:
            end_idx = min(end_idx, idx)
    chunk = chunk[:end_idx]
    lines = [ln.strip() for ln in chunk.splitlines() if ln.strip()]
    noise = {
        "Sıra", "No", "Barkod", "Miktar", "Birim Fiyat", "İskonto", "KDV", "Oranı",
        "Tutarı", "Diğer", "Vergiler", "Malzeme /", "Hizmet Kodu", "Açıklamalar"
    }
    cleaned = []
    for ln in lines:
        if ln in noise:
            continue
        if re.fullmatch(r"[%\d\.,TLAdet]+", ln.replace(" ", "")):
            continue
        cleaned.append(ln)
    joined = " | ".join(cleaned[:4])
    return joined[:250]



def parse_invoice_text(text: str, source_name: str = "") -> dict:
    row = {
        "kaynak_dosya": source_name,
        "fatura_no": find_value_after_label(text, FIELD_LABELS["invoice_no"]),
        "fatura_tarihi": normalize_date(find_value_after_label(text, FIELD_LABELS["invoice_date"])),
        "siparis_no": find_value_after_label(text, FIELD_LABELS["order_no"]),
        "siparis_tarihi": normalize_date(find_value_after_label(text, FIELD_LABELS["order_date"])),
        "ettn": find_value_after_label(text, FIELD_LABELS["ettn"], multiline=True).splitlines()[0].strip() if find_value_after_label(text, FIELD_LABELS["ettn"], multiline=True) else "",
        "satici": parse_seller(text),
        "alici": parse_buyer(text),
        "urun_ozeti": parse_product_summary(text),
        "ara_toplam": 0.0,
        "kdv_tutari": 0.0,
        "odenecek_tutar": 0.0,
        "ham_metin": text,
    }

    subtotal_raw = find_value_after_label(text, FIELD_LABELS["subtotal"])
    vat_raw = find_value_after_label(text, FIELD_LABELS["vat_amount"])
    total_raw = find_value_after_label(text, FIELD_LABELS["payable_total"])

    row["ara_toplam"] = normalize_amount(subtotal_raw)
    row["kdv_tutari"] = normalize_amount(vat_raw)
    row["odenecek_tutar"] = normalize_amount(total_raw)

    if not row["odenecek_tutar"]:
        totals = re.findall(r"(\d{1,3}(?:[\.,]\d{3})*(?:[\.,]\d{2})?)\s*(?:TL|TRY|₺)", text, re.IGNORECASE)
        if totals:
            row["odenecek_tutar"] = normalize_amount(totals[-1])

    if not row["fatura_tarihi"]:
        m = re.search(r"(\d{2}[./-]\d{2}[./-]\d{4})", text)
        if m:
            row["fatura_tarihi"] = normalize_date(m.group(1))

    return row



def to_excel_bytes(df: pd.DataFrame) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Faturalar")
    return output.getvalue()


st.title("📄 Fatura Tara → Excel")
st.caption("Tek işi var: faturayı tara, düz veriyi çıkar, Excel'e at.")

with st.sidebar:
    st.subheader("Ayarlar")
    use_ocr = st.checkbox("OCR kullan", value=True, help="Metin katmanı olmayan PDF'lerde gerekli olabilir.")
    keep_raw_text = st.checkbox("Ham metni Excel'e koy", value=False)

uploaded_files = st.file_uploader(
    "PDF / JPG / PNG faturaları yükle",
    type=["pdf", "jpg", "jpeg", "png"],
    accept_multiple_files=True,
)

if uploaded_files:
    if st.button("Tara ve Excel hazırla", type="primary"):
        rows = []
        previews = []
        progress = st.progress(0)
        status = st.empty()

        for idx, uf in enumerate(uploaded_files, start=1):
            status.info(f"İşleniyor: {uf.name}")
            try:
                text, method = read_uploaded_file(uf, use_ocr=use_ocr)
                row = parse_invoice_text(text, source_name=uf.name)
                row["okuma_yontemi"] = method
                row["tarama_zamani"] = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
                if not keep_raw_text:
                    row.pop("ham_metin", None)
                rows.append(row)
                previews.append({
                    "dosya": uf.name,
                    "yontem": method,
                    "fatura_no": row.get("fatura_no", ""),
                    "fatura_tarihi": row.get("fatura_tarihi", ""),
                    "satici": row.get("satici", ""),
                    "odenecek_tutar": amount_to_text(row.get("odenecek_tutar", 0)),
                })
            except Exception as e:
                rows.append({
                    "kaynak_dosya": uf.name,
                    "fatura_no": "",
                    "fatura_tarihi": "",
                    "satici": "",
                    "alici": "",
                    "urun_ozeti": "",
                    "ara_toplam": 0.0,
                    "kdv_tutari": 0.0,
                    "odenecek_tutar": 0.0,
                    "okuma_yontemi": "hata",
                    "hata": str(e),
                    "tarama_zamani": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
                })
            progress.progress(idx / len(uploaded_files))

        status.success("Tarama tamamlandı")
        df = pd.DataFrame(rows)

        ordered_cols = [
            "kaynak_dosya",
            "fatura_no",
            "fatura_tarihi",
            "siparis_no",
            "siparis_tarihi",
            "ettn",
            "satici",
            "alici",
            "urun_ozeti",
            "ara_toplam",
            "kdv_tutari",
            "odenecek_tutar",
            "okuma_yontemi",
            "tarama_zamani",
        ]
        if keep_raw_text:
            ordered_cols.append("ham_metin")
        remaining = [c for c in df.columns if c not in ordered_cols]
        df = df[[c for c in ordered_cols if c in df.columns] + remaining]

        c1, c2, c3 = st.columns(3)
        c1.metric("Toplam dosya", len(df))
        c2.metric("Fatura no bulunan", int(df["fatura_no"].astype(str).str.len().gt(0).sum()) if "fatura_no" in df.columns else 0)
        c3.metric("Tutar bulunan", int(pd.to_numeric(df.get("odenecek_tutar", 0), errors="coerce").fillna(0).gt(0).sum()))

        st.subheader("Önizleme")
        st.dataframe(pd.DataFrame(previews), use_container_width=True)

        st.subheader("Tam çıktı")
        st.dataframe(df, use_container_width=True)

        excel_bytes = to_excel_bytes(df)
        st.download_button(
            "Excel indir",
            data=excel_bytes,
            file_name=f"fatura_tarama_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
else:
    st.info("Başlamak için bir veya birden fazla fatura yükle.")

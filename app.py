import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import fitz  # PyMuPDF
import numpy as np
import pandas as pd
import pytesseract
import streamlit as st
from PIL import Image
from streamlit_drawable_canvas import st_canvas

TEMPLATE_DIR = Path("templates")
EXPORT_DIR = Path("exports")

FIELD_NAMES = [
    "seller_name",
    "buyer_name",
    "invoice_no",
    "invoice_date",
    "order_no",
    "subtotal",
    "vat_amount",
    "total_amount",
    "payable_amount",
    "notes",
    "item_table",
]

# Tekil alanlar: aynı şablonda birden fazla olmamalı
SINGLETON_FIELDS = {
    "seller_name",
    "buyer_name",
    "invoice_no",
    "invoice_date",
    "order_no",
    "subtotal",
    "vat_amount",
    "total_amount",
    "payable_amount",
    "item_table",
}


# ---------------------- Yardımcı Fonksiyonlar ----------------------
def ensure_dirs() -> None:
    TEMPLATE_DIR.mkdir(exist_ok=True)
    EXPORT_DIR.mkdir(exist_ok=True)


def pdf_first_page_to_image(pdf_bytes: bytes, zoom: float = 2.0) -> Image.Image:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc.load_page(0)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    doc.close()
    return image


def to_normalized_box(rect: Dict, img_w: int, img_h: int) -> Dict:
    x = max(0.0, float(rect.get("left", 0)))
    y = max(0.0, float(rect.get("top", 0)))
    w = max(1.0, float(rect.get("width", 1)))
    h = max(1.0, float(rect.get("height", 1)))
    return {
        "rx": x / img_w,
        "ry": y / img_h,
        "rw": w / img_w,
        "rh": h / img_h,
    }


def denormalize_box(norm_box: Dict, img_w: int, img_h: int) -> Tuple[int, int, int, int]:
    x = int(norm_box["rx"] * img_w)
    y = int(norm_box["ry"] * img_h)
    w = int(norm_box["rw"] * img_w)
    h = int(norm_box["rh"] * img_h)
    x2 = min(img_w, x + w)
    y2 = min(img_h, y + h)
    return max(0, x), max(0, y), max(1, x2), max(1, y2)


def validate_labels(selected_labels: List[str]) -> List[str]:
    errors = []
    counts: Dict[str, int] = {}
    for label in selected_labels:
        counts[label] = counts.get(label, 0) + 1
    for field, count in counts.items():
        if field in SINGLETON_FIELDS and count > 1:
            errors.append(f"'{field}' alanı tekil olmalı. Şablonda {count} kez seçildi.")
    return errors


def save_template(template_name: str, image_size: Tuple[int, int], rectangles: List[Dict], labels: List[str]) -> Path:
    width, height = image_size
    rows = []
    for rect, field in zip(rectangles, labels):
        rows.append({"field": field, **to_normalized_box(rect, width, height)})

    payload = {
        "template_name": template_name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "fields": rows,
    }

    out_path = TEMPLATE_DIR / f"{template_name}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return out_path


def load_template(template_file: str) -> Dict:
    with (TEMPLATE_DIR / template_file).open("r", encoding="utf-8") as f:
        return json.load(f)


def list_templates() -> List[str]:
    return sorted([p.name for p in TEMPLATE_DIR.glob("*.json")])


def clean_text(value: str) -> str:
    return " ".join((value or "").replace("\n", " ").split()).strip()


def ocr_crop(image_np: np.ndarray, box: Tuple[int, int, int, int]) -> str:
    x1, y1, x2, y2 = box
    crop = image_np[y1:y2, x1:x2]
    if crop.size == 0:
        return ""
    try:
        text = pytesseract.image_to_string(crop, config="--psm 6")
    except Exception:
        text = pytesseract.image_to_string(crop)
    return clean_text(text)


def parse_amount(text: str) -> str:
    m = re.search(r"([0-9]{1,3}(?:[\.,][0-9]{3})*(?:[\.,][0-9]{2})|[0-9]+(?:[\.,][0-9]{2})?)", text)
    return m.group(1) if m else clean_text(text)


def extract_totals_from_nearby_text(text: str) -> Dict[str, str]:
    patterns = {
        "subtotal": [r"Ara\s*Toplam\s*[:\-]?\s*([0-9\.,]+)", r"KDV\s*Hariç\s*[:\-]?\s*([0-9\.,]+)"],
        "vat_amount": [r"KDV\s*(?:Tutarı|Toplamı)?\s*[:\-]?\s*([0-9\.,]+)"],
        "total_amount": [r"Genel\s*Toplam\s*[:\-]?\s*([0-9\.,]+)", r"Toplam\s*Tutar\s*[:\-]?\s*([0-9\.,]+)"],
    }
    out = {}
    for field, regs in patterns.items():
        for rgx in regs:
            m = re.search(rgx, text, flags=re.IGNORECASE)
            if m:
                out[field] = parse_amount(m.group(1))
                break
    return out


def empty_result_row() -> Dict[str, str]:
    return {field: "" for field in FIELD_NAMES}


# ---------------------- UI ----------------------
st.set_page_config(page_title="PDF Şablon Öğretme ve Tarama", layout="wide")
ensure_dirs()

st.title("📄 PDF Fatura Şablon Öğretme ve Tarama (MVP)")
st.caption("İlk sürüm: sadece PDF'in ilk sayfası ile kutu çizme, şablon kaydetme ve OCR tarama.")

teach_tab, scan_tab = st.tabs(["1) Şablon Öğret", "2) Şablonla Tara"])

with teach_tab:
    st.subheader("Şablon öğret")
    uploaded = st.file_uploader("PDF yükleyin", type=["pdf"], key="teach_pdf")

    if uploaded is not None:
        try:
            image = pdf_first_page_to_image(uploaded.read(), zoom=2.0)
            image_np = np.array(image)
            h, w = image_np.shape[:2]

            st.info("Mavi yarı saydam kutular çizin. Kutuları köşelerinden büyütüp küçültebilir, taşıyabilirsiniz.")
            canvas_result = st_canvas(
                fill_color="rgba(0, 180, 255, 0.25)",
                stroke_width=2,
                stroke_color="#2dd4ff",
                background_image=image,
                update_streamlit=True,
                height=h,
                width=w,
                drawing_mode="rect",
                key="canvas_teach",
                display_toolbar=True,
            )

            objects = []
            if canvas_result.json_data and canvas_result.json_data.get("objects"):
                objects = [obj for obj in canvas_result.json_data["objects"] if obj.get("type") == "rect"]

            if objects:
                st.markdown("### Kutulara hazır alan etiketi atayın")
                labels: List[str] = []
                for i, _ in enumerate(objects):
                    label = st.selectbox(
                        f"Kutu {i + 1} etiketi",
                        options=FIELD_NAMES,
                        key=f"label_{i}",
                    )
                    labels.append(label)

                errors = validate_labels(labels)
                if errors:
                    for err in errors:
                        st.warning(err)

                col1, col2 = st.columns([2, 1])
                with col1:
                    template_name = st.text_input("Şablon adı", value=f"sablon_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                with col2:

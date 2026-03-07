import hashlib
import json
import re
from datetime import datetime
from io import BytesIO
from pathlib import Path

import cv2
import fitz
import numpy as np
import pandas as pd
import pytesseract
import streamlit as st
from PIL import Image
from streamlit_drawable_canvas import st_canvas


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

AMOUNT_FIELDS = {"subtotal", "vat_amount", "total_amount", "payable_amount"}
TEMPLATE_DIR = Path("templates")
EXPORT_DIR = Path("exports")
MAX_CANVAS_WIDTH = 1100
BOX_FILL = "rgba(0, 170, 255, 0.25)"
BOX_STROKE = "#00d4ff"


def ensure_directories() -> None:
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", name.strip())
    return cleaned.strip("_")


def uploaded_file_id(uploaded_file) -> str:
    return hashlib.md5(uploaded_file.getvalue()).hexdigest()[:12]


def read_pdf_first_page(uploaded_file) -> Image.Image:
    pdf_bytes = uploaded_file.getvalue()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        if doc.page_count == 0:
            raise ValueError("PDF dosyasinda sayfa bulunamadi.")
        page = doc.load_page(0)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        return image
    finally:
        doc.close()


def resize_for_canvas(image: Image.Image, max_width: int = MAX_CANVAS_WIDTH) -> Image.Image:
    if image.width <= max_width:
        return image
    ratio = max_width / float(image.width)
    new_height = max(1, int(image.height * ratio))
    resample = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS
    return image.resize((max_width, new_height), resample)


def extract_rectangles(json_data: dict | None) -> list[dict]:
    if not json_data:
        return []
    rectangles = []
    for obj in json_data.get("objects", []):
        if obj.get("type") != "rect":
            continue
        left = float(obj.get("left", 0))
        top = float(obj.get("top", 0))
        width = float(obj.get("width", 0)) * float(obj.get("scaleX", 1))
        height = float(obj.get("height", 0)) * float(obj.get("scaleY", 1))
        if width <= 1 or height <= 1:
            continue
        rectangles.append({"x": left, "y": top, "w": width, "h": height})
    return rectangles


def find_singleton_conflicts(labels: list[str]) -> list[str]:
    conflicts = []
    for field in SINGLETON_FIELDS:
        count = labels.count(field)
        if count > 1:
            conflicts.append(f"{field} ({count} adet)")
    return sorted(conflicts)


def build_template(
    template_name: str, boxes: list[dict], labels: list[str], canvas_width: int, canvas_height: int
) -> dict:
    fields = []
    for box, label in zip(boxes, labels):
        x = max(0.0, min(1.0, box["x"] / canvas_width))
        y = max(0.0, min(1.0, box["y"] / canvas_height))
        w = max(0.0, min(1.0, box["w"] / canvas_width))
        h = max(0.0, min(1.0, box["h"] / canvas_height))
        fields.append({"field": label, "bbox": {"x": x, "y": y, "w": w, "h": h}})
    return {
        "template_name": template_name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "canvas_size": {"width": canvas_width, "height": canvas_height},
        "fields": fields,
    }


def list_templates() -> list[str]:
    return sorted([p.name for p in TEMPLATE_DIR.glob("*.json")])


def load_template(template_filename: str) -> dict:
    path = TEMPLATE_DIR / template_filename
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def normalized_to_canvas_box(bbox: dict, canvas_width: int, canvas_height: int) -> dict:
    return {
        "x": float(bbox.get("x", 0)) * canvas_width,
        "y": float(bbox.get("y", 0)) * canvas_height,
        "w": float(bbox.get("w", 0)) * canvas_width,
        "h": float(bbox.get("h", 0)) * canvas_height,
    }


def build_initial_drawing(template_fields: list[dict], canvas_width: int, canvas_height: int) -> dict:
    objects = []
    for item in template_fields:
        box = normalized_to_canvas_box(item["bbox"], canvas_width, canvas_height)
        objects.append(
            {
                "type": "rect",
                "left": box["x"],
                "top": box["y"],
                "width": max(1.0, box["w"]),
                "height": max(1.0, box["h"]),
                "fill": BOX_FILL,
                "stroke": BOX_STROKE,
                "strokeWidth": 2,
            }
        )
    return {"version": "4.4.0", "objects": objects}


def clip_box(box: dict, image_width: int, image_height: int) -> tuple[int, int, int, int]:
    x1 = max(0, int(round(box["x"])))
    y1 = max(0, int(round(box["y"])))
    x2 = min(image_width, int(round(box["x"] + box["w"])))
    y2 = min(image_height, int(round(box["y"] + box["h"])))
    return x1, y1, x2, y2


def crop_region(image_np: np.ndarray, box: dict) -> np.ndarray | None:
    h, w = image_np.shape[:2]
    x1, y1, x2, y2 = clip_box(box, w, h)
    if x2 <= x1 or y2 <= y1:
        return None
    return image_np[y1:y2, x1:x2]


def preprocess_for_ocr(crop: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    return cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]


def ocr_image(crop: np.ndarray | None) -> str:
    if crop is None or crop.size == 0:
        return ""
    processed = preprocess_for_ocr(crop)
    text = pytesseract.image_to_string(processed, config="--oem 3 --psm 6")
    return text.strip()


def first_date_in_text(text: str) -> str:
    match = re.search(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b", text)
    return match.group(0) if match else ""


def parse_amount(text: str) -> float | None:
    pattern = r"[-+]?\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{2})|[-+]?\d+(?:[.,]\d{2})"
    candidates = re.findall(pattern, text)
    if not candidates:
        return None

    token = candidates[-1].replace(" ", "")
    if "," in token and "." in token:
        if token.rfind(",") > token.rfind("."):
            token = token.replace(".", "").replace(",", ".")
        else:
            token = token.replace(",", "")
    elif "," in token and "." not in token:
        if len(token.split(",")[-1]) == 2:
            token = token.replace(".", "").replace(",", ".")
        else:
            token = token.replace(",", "")
    elif token.count(".") > 1:
        parts = token.split(".")
        if len(parts[-1]) == 2:
            token = "".join(parts[:-1]) + "." + parts[-1]
        else:
            token = "".join(parts)

    try:
        return float(token)
    except ValueError:
        return None


def keyword_amounts_from_text(text: str) -> dict:
    keyword_map = {
        "subtotal": ["ara toplam", "subtotal", "matrah"],
        "vat_amount": ["kdv", "vat", "tax"],
        "total_amount": ["genel toplam", "toplam", "total"],
    }
    found = {}

    for line in text.splitlines():
        line_l = line.lower()
        amount = parse_amount(line)
        if amount is None:
            continue
        for field, keywords in keyword_map.items():
            if field in found:
                continue
            if any(keyword in line_l for keyword in keywords):
                found[field] = amount

    regex_map = {
        "subtotal": r"(ara\s*toplam|subtotal)[^\d]{0,25}([0-9.,\s]+)",
        "vat_amount": r"(kdv|vat|tax)[^\d]{0,25}([0-9.,\s]+)",
        "total_amount": r"(genel\s*toplam|total|toplam)[^\d]{0,25}([0-9.,\s]+)",
    }
    text_l = text.lower()
    for field, pattern in regex_map.items():
        if field in found:
            continue
        match = re.search(pattern, text_l)
        if not match:
            continue
        amount = parse_amount(match.group(2))
        if amount is not None:
            found[field] = amount
    return found


def payable_context_box(payable_box: dict, image_width: int, image_height: int) -> dict:
    x = max(0.0, payable_box["x"] - payable_box["w"] * 2.2)
    y = max(0.0, payable_box["y"] - payable_box["h"] * 3.5)
    w = min(image_width - x, payable_box["w"] * 5.2)
    h = min(image_height - y, payable_box["h"] * 7.0)
    return {"x": x, "y": y, "w": w, "h": h}


def check_tesseract() -> tuple[bool, str]:
    try:
        _ = pytesseract.get_tesseract_version()
        return True, ""
    except Exception as exc:
        return False, str(exc)


def scan_with_template(image_np: np.ndarray, fields: list[str], boxes: list[dict]) -> dict:
    values = {field: [] for field in FIELD_NAMES}
    first_payable_box = None

    for field, box in zip(fields, boxes):
        text = ocr_image(crop_region(image_np, box))
        if field in AMOUNT_FIELDS:
            amount = parse_amount(text)
            values[field].append(amount if amount is not None else "")
        elif field == "invoice_date":
            detected_date = first_date_in_text(text)
            values[field].append(detected_date if detected_date else text)
        else:
            normalized_text = re.sub(r"[ \t]+", " ", text).strip()
            values[field].append(normalized_text)

        if field == "payable_amount" and first_payable_box is None:
            first_payable_box = box

    row = {field: "" for field in FIELD_NAMES}
    for field in FIELD_NAMES:
        present = [v for v in values[field] if v not in ("", None)]
        if not present:
            continue
        if field in AMOUNT_FIELDS:
            numeric = [v for v in present if isinstance(v, (int, float))]
            row[field] = float(numeric[0]) if numeric else ""
        elif field == "notes":
            row[field] = "\n".join(str(v) for v in present)
        else:
            row[field] = " ".join(str(v) for v in present)

    missing_totals = [f for f in ("subtotal", "vat_amount", "total_amount") if row[f] in ("", None)]
    if row["payable_amount"] not in ("", None) and first_payable_box and missing_totals:
        img_h, img_w = image_np.shape[:2]
        context_box = payable_context_box(first_payable_box, img_w, img_h)
        context_text = ocr_image(crop_region(image_np, context_box))
        guesses = keyword_amounts_from_text(context_text)
        for field in missing_totals:
            if field in guesses:
                row[field] = float(guesses[field])

    return row


def save_excel(df: pd.DataFrame, template_name: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"{safe_filename(template_name)}_{timestamp}.xlsx"
    export_path = EXPORT_DIR / file_name
    df.to_excel(export_path, index=False)
    return export_path


def render_template_training() -> None:
    st.subheader("1) Sablon Ogretme")
    st.write("PDF yukleyin, ilk sayfada kutular cizin ve her kutuya hazir alan etiketi secin.")

    uploaded_pdf = st.file_uploader("Ornek PDF yukle", type=["pdf"], key="train_pdf")
    if not uploaded_pdf:
        st.info("Devam etmek icin bir PDF yukleyin.")
        return

    try:
        page_image = read_pdf_first_page(uploaded_pdf)
    except Exception as exc:
        st.error(f"PDF okunamadi: {exc}")
        return

    canvas_image = resize_for_canvas(page_image)
    canvas_width, canvas_height = canvas_image.size
    file_id = uploaded_file_id(uploaded_pdf)

    draw_mode_label = st.radio(
        "Cizim modu",
        options=["Kutu Ciz", "Kutu Duzenle/Tasi"],
        horizontal=True,
        key=f"draw_mode_{file_id}",
    )
    drawing_mode = "rect" if draw_mode_label == "Kutu Ciz" else "transform"

    st.caption("Kutular yari saydam mavi/holografik gorunur.")
    canvas_result = st_canvas(
        fill_color=BOX_FILL,
        stroke_width=2,
        stroke_color=BOX_STROKE,
        background_image=canvas_image,
        update_streamlit=True,
        height=canvas_height,
        width=canvas_width,
        drawing_mode=drawing_mode,
        display_toolbar=True,
        key=f"teach_canvas_{file_id}",
    )

    rectangles = extract_rectangles(canvas_result.json_data if canvas_result else None)
    if not rectangles:
        st.info("En az bir kutu cizin.")
        return

    st.markdown("### 2) Kutu Etiketlerini Sec")
    labels = []
    for i in range(len(rectangles)):
        labels.append(
            st.selectbox(
                f"Kutu {i + 1} etiketi",
                FIELD_NAMES,
                key=f"train_field_{file_id}_{i}",
            )
        )

    conflicts = find_singleton_conflicts(labels)
    if conflicts:
        st.warning(
            "Tekil alanlar birden fazla secildi. Kaydetmeden once duzeltin: "
            + ", ".join(conflicts)
        )

    template_name = st.text_input("3) Sablon adi", placeholder="ornek_fatura_sablonu")
    if st.button("Sablonu Kaydet", type="primary"):
        if not template_name.strip():
            st.error("Lutfen bir sablon adi girin.")
            return
        if conflicts:
            st.error("Tekil alan tekrarlarini duzeltmeden kayit yapamazsiniz.")
            return
        safe_name = safe_filename(template_name)
        if not safe_name:
            st.error("Sablon adi gecersiz. Harf/rakam kullanin.")
            return

        save_path = TEMPLATE_DIR / f"{safe_name}.json"
        if save_path.exists():
            st.error("Bu isimde bir sablon zaten var. Farkli bir ad deneyin.")
            return

        template_data = build_template(
            template_name=safe_name,
            boxes=rectangles,
            labels=labels,
            canvas_width=canvas_width,
            canvas_height=canvas_height,
        )
        with save_path.open("w", encoding="utf-8") as f:
            json.dump(template_data, f, indent=2, ensure_ascii=False)
        st.success(f"Sablon kaydedildi: {save_path}")


def render_template_scanning() -> None:
    st.subheader("2) Sablonla Tara")
    template_files = list_templates()
    if not template_files:
        st.info("Henuz kayitli sablon yok. Once ustteki adimla bir sablon kaydedin.")
        return

    selected_template = st.selectbox("Sablon sec", template_files)
    try:
        template_data = load_template(selected_template)
    except Exception as exc:
        st.error(f"Sablon okunamadi: {exc}")
        return

    template_fields = template_data.get("fields", [])
    if not template_fields:
        st.error("Secilen sablonda alan bulunamadi.")
        return

    uploaded_pdf = st.file_uploader("Taranacak PDF yukle", type=["pdf"], key="scan_pdf")
    if not uploaded_pdf:
        st.info("Tarama icin bir PDF yukleyin.")
        return

    try:
        page_image = read_pdf_first_page(uploaded_pdf)
    except Exception as exc:
        st.error(f"PDF okunamadi: {exc}")
        return

    canvas_image = resize_for_canvas(page_image)
    canvas_width, canvas_height = canvas_image.size
    file_id = uploaded_file_id(uploaded_pdf)

    st.caption("Kutulari burada manuel tasiyip boyutlandirabilirsiniz.")
    initial_drawing = build_initial_drawing(template_fields, canvas_width, canvas_height)
    canvas_result = st_canvas(
        fill_color=BOX_FILL,
        stroke_width=2,
        stroke_color=BOX_STROKE,
        background_image=canvas_image,
        update_streamlit=True,
        height=canvas_height,
        width=canvas_width,
        drawing_mode="transform",
        display_toolbar=True,
        initial_drawing=initial_drawing,
        key=f"scan_canvas_{selected_template}_{file_id}",
    )

    current_boxes = extract_rectangles(canvas_result.json_data if canvas_result else None)
    expected_fields = [item["field"] for item in template_fields]
    if len(current_boxes) != len(expected_fields):
        st.warning(
            "Kutu sayisi sablonla uyusmuyor. Son kayitli sablon koordinatlariyla devam edilecek."
        )
        current_boxes = [
            normalized_to_canvas_box(item["bbox"], canvas_width, canvas_height) for item in template_fields
        ]

    if st.button("Sablonla Tara ve Excel Olustur", type="primary"):
        ok, message = check_tesseract()
        if not ok:
            st.error(
                "Tesseract bulunamadi. Lutfen Tesseract OCR kurup PATH'e ekleyin. "
                f"Detay: {message}"
            )
            return

        with st.spinner("OCR calisiyor..."):
            image_np = np.array(canvas_image)
            result_row = scan_with_template(image_np, expected_fields, current_boxes)
            result_df = pd.DataFrame([result_row], columns=FIELD_NAMES)
            export_path = save_excel(result_df, Path(selected_template).stem)

            buffer = BytesIO()
            result_df.to_excel(buffer, index=False)
            buffer.seek(0)

        st.success(f"Tarama tamamlandi. Excel kaydedildi: {export_path}")
        st.dataframe(result_df, use_container_width=True)
        st.download_button(
            "Excel indir",
            data=buffer.getvalue(),
            file_name=export_path.name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


def main() -> None:
    st.set_page_config(page_title="PDF Fatura Sablon Araci", layout="wide")
    ensure_directories()

    st.title("PDF Fatura Sablon Ogretme ve Tarama Araci")
    st.caption("MVP: sadece PDF ve ilk sayfa uzerinde kutu tabanli sablon-ogretme ve OCR tarama.")

    render_template_training()
    st.divider()
    render_template_scanning()


if __name__ == "__main__":
    main()

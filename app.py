import io
import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import fitz  # PyMuPDF
import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw

APP_TITLE = "Fatura Öğretme ve Tarama Sistemi — MVP v2"
TEMPLATE_DIR = "templates"
EXPORT_DIR = "exports"

FIELD_LABELS = [
    "seller_name",
    "buyer_name",
    "invoice_no",
    "invoice_date",
    "order_no",
    "item_table",
    "subtotal",
    "vat_amount",
    "total_amount",
    "payable_amount",
    "notes",
]

FIELD_COLORS = {
    "seller_name": (0, 255, 255, 80),
    "buyer_name": (0, 200, 255, 80),
    "invoice_no": (255, 0, 255, 85),
    "invoice_date": (255, 120, 255, 85),
    "order_no": (180, 80, 255, 85),
    "item_table": (255, 180, 0, 70),
    "subtotal": (80, 255, 80, 85),
    "vat_amount": (20, 220, 120, 85),
    "total_amount": (60, 255, 160, 85),
    "payable_amount": (0, 255, 120, 95),
    "notes": (255, 255, 0, 70),
}

TOTAL_LABEL_PATTERNS = {
    "subtotal": [
        r"Mal\s*/?\s*Hizmet\s+Toplam\s+Tutar[ıi]\s*([0-9\.\,]+)",
        r"Ara\s*Toplam\s*([0-9\.\,]+)",
        r"KDV\s+Hari[cç]\s*Toplam\s*([0-9\.\,]+)",
    ],
    "vat_amount": [
        r"Hesaplanan\s+KDV(?:\s*\(%\s*[0-9\.,]+\))?\s*([0-9\.\,]+)",
        r"Toplam\s+KDV\s*([0-9\.\,]+)",
        r"KDV\s+Tutar[ıi]\s*([0-9\.\,]+)",
    ],
    "total_amount": [
        r"Vergiler\s+Dahil\s+Toplam\s+Tutar\s*([0-9\.\,]+)",
        r"Genel\s+Toplam\s*([0-9\.\,]+)",
        r"Toplam\s*Tutar\s*([0-9\.\,]+)",
    ],
    "payable_amount": [
        r"[ÖO]denecek\s+Tutar\s*([0-9\.\,]+)",
        r"Yek[uü]n\s*([0-9\.\,]+)",
    ],
}


def ensure_dirs() -> None:
    os.makedirs(TEMPLATE_DIR, exist_ok=True)
    os.makedirs(EXPORT_DIR, exist_ok=True)


def normalize_text(text: str) -> str:
    return " ".join((text or "").replace("\n", " ").split()).strip()


def clean_amount(value: str) -> str:
    value = normalize_text(value)
    m = re.search(r"([0-9]{1,3}(?:\.[0-9]{3})*(?:,[0-9]{2})|[0-9]+(?:,[0-9]{2})?)", value)
    return m.group(1) if m else value


def open_pdf(file_bytes: bytes) -> fitz.Document:
    return fitz.open(stream=file_bytes, filetype="pdf")


def render_page(doc: fitz.Document, page_num: int = 0, zoom: float = 2.0) -> Image.Image:
    page = doc.load_page(page_num)
    matrix = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix, alpha=False)
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)


def extract_text_blocks(doc: fitz.Document, page_num: int = 0) -> List[Dict[str, Any]]:
    page = doc.load_page(page_num)
    blocks = page.get_text("blocks")
    out = []
    for idx, b in enumerate(blocks):
        x0, y0, x1, y1, text, *_rest = b
        clean = normalize_text(text)
        if not clean:
            continue
        out.append(
            {
                "block_id": idx,
                "x0": float(x0),
                "y0": float(y0),
                "x1": float(x1),
                "y1": float(y1),
                "text": clean,
            }
        )
    return out


def make_rgba(img: Image.Image) -> Image.Image:
    return img.convert("RGBA") if img.mode != "RGBA" else img.copy()


def draw_hologram_preview(
    img: Image.Image,
    blocks: List[Dict[str, Any]],
    overlay_regions: List[Dict[str, Any]],
    zoom: float = 2.0,
) -> Image.Image:
    canvas = make_rgba(img)
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    block_map = {b["block_id"]: b for b in blocks}

    for region in overlay_regions:
        label = region.get("label", "")
        color = FIELD_COLORS.get(label, (255, 140, 0, 75))
        if "block_id" in region and region["block_id"] in block_map:
            b = block_map[region["block_id"]]
            x0, y0, x1, y1 = b["x0"] * zoom, b["y0"] * zoom, b["x1"] * zoom, b["y1"] * zoom
        else:
            x0, y0, x1, y1 = [v * zoom for v in region["bbox"]]

        draw.rounded_rectangle([x0, y0, x1, y1], radius=8, fill=color, outline=(255, 255, 255, 220), width=3)
        caption = f"{label}"
        text_w = max(120, len(caption) * 8)
        cap_y = max(0, y0 - 24)
        draw.rounded_rectangle([x0, cap_y, x0 + text_w, cap_y + 22], radius=8, fill=(10, 10, 20, 210), outline=(255, 255, 255, 180), width=1)
        draw.text((x0 + 8, cap_y + 4), caption, fill=(120, 255, 255, 255))

    out = Image.alpha_composite(canvas, overlay)
    return out.convert("RGB")


def suggest_template_name(blocks: List[Dict[str, Any]]) -> str:
    joined = " ".join([b["text"] for b in blocks[:8]])
    lowered = joined.lower()
    if "amazon" in lowered:
        return "amazon_earsiv_v1"
    if "e-fatura" in lowered or "e-arşiv" in lowered:
        return "earsiv_v1"
    return f"template_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def default_region_from_block(block: Dict[str, Any], page_size: Tuple[int, int], pad_x: float = 0.02, pad_y: float = 0.01) -> Dict[str, float]:
    width, height = page_size
    x0 = max(0.0, block["x0"] / width - pad_x)
    y0 = max(0.0, block["y0"] / height - pad_y)
    x1 = min(1.0, block["x1"] / width + pad_x)
    y1 = min(1.0, block["y1"] / height + pad_y)
    return {"rx0": x0, "ry0": y0, "rx1": x1, "ry1": y1}


def bbox_from_relative(region: Dict[str, float], page_size: Tuple[int, int]) -> Tuple[float, float, float, float]:
    width, height = page_size
    return (
        region["rx0"] * width,
        region["ry0"] * height,
        region["rx1"] * width,
        region["ry1"] * height,
    )


def save_template(
    template_name: str,
    page_size: Tuple[int, int],
    blocks: List[Dict[str, Any]],
    labels: Dict[int, str],
    custom_regions: Dict[str, Dict[str, float]],
) -> str:
    labeled = []
    width, height = page_size
    for block in blocks:
        bid = block["block_id"]
        if bid not in labels:
            continue
        label = labels[bid]
        region = custom_regions.get(label) or default_region_from_block(block, page_size)
        labeled.append(
            {
                "block_id": bid,
                "label": label,
                "text": block["text"],
                "x0": block["x0"],
                "y0": block["y0"],
                "x1": block["x1"],
                "y1": block["y1"],
                "rx0": region["rx0"],
                "ry0": region["ry0"],
                "rx1": region["rx1"],
                "ry1": region["ry1"],
                "anchors": guess_anchors(block["text"], label),
            }
        )

    payload = {
        "template_name": template_name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "page_size": [width, height],
        "fields": labeled,
    }
    path = os.path.join(TEMPLATE_DIR, f"{template_name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def load_templates() -> List[str]:
    ensure_dirs()
    files = [f for f in os.listdir(TEMPLATE_DIR) if f.endswith(".json")]
    return sorted(files)


def load_template(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def guess_anchors(text: str, label: str) -> List[str]:
    anchor_map = {
        "invoice_no": ["Fatura No"],
        "invoice_date": ["Fatura Tarihi"],
        "order_no": ["Sipariş No"],
        "payable_amount": ["Ödenecek Tutar"],
        "vat_amount": ["Hesaplanan KDV", "KDV"],
        "subtotal": ["Mal / Hizmet Toplam", "Ara Toplam"],
        "buyer_name": ["SAYIN"],
    }
    if label in anchor_map:
        return anchor_map[label]
    first = normalize_text(text)[:24]
    return [first] if first else []


def score_block_match(template_field: Dict[str, Any], block: Dict[str, Any], page_size: Tuple[int, int]) -> float:
    width, height = page_size
    target = (
        template_field["rx0"] * width,
        template_field["ry0"] * height,
        template_field["rx1"] * width,
        template_field["ry1"] * height,
    )
    bx = (block["x0"], block["y0"], block["x1"], block["y1"])

    center_dist = abs(((target[0] + target[2]) / 2) - ((bx[0] + bx[2]) / 2)) + abs(((target[1] + target[3]) / 2) - ((bx[1] + bx[3]) / 2))
    area_diff = abs((target[2] - target[0]) * (target[3] - target[1]) - (bx[2] - bx[0]) * (bx[3] - bx[1]))
    text_bonus = 0
    for anchor in template_field.get("anchors", []):
        if anchor and anchor.lower() in block["text"].lower():
            text_bonus -= 250
    sample = normalize_text(template_field.get("text", ""))[:20].lower()
    if sample and sample in block["text"].lower():
        text_bonus -= 100
    return center_dist + (area_diff / 1000.0) + text_bonus


def apply_template(template: Dict[str, Any], blocks: List[Dict[str, Any]], page_size: Tuple[int, int]) -> Tuple[Dict[str, str], Dict[str, int], Dict[str, Dict[str, float]]]:
    result: Dict[str, str] = {}
    matched_ids: Dict[str, int] = {}
    matched_regions: Dict[str, Dict[str, float]] = {}
    used_ids = set()

    for field in template.get("fields", []):
        ranked = sorted(blocks, key=lambda b: score_block_match(field, b, page_size))
        for cand in ranked:
            if cand["block_id"] in used_ids:
                continue
            result[field["label"]] = cand["text"]
            matched_ids[field["label"]] = cand["block_id"]
            matched_regions[field["label"]] = {"rx0": field["rx0"], "ry0": field["ry0"], "rx1": field["rx1"], "ry1": field["ry1"]}
            used_ids.add(cand["block_id"])
            break
    return result, matched_ids, matched_regions


def extract_text_in_region(blocks: List[Dict[str, Any]], bbox: Tuple[float, float, float, float]) -> str:
    x0, y0, x1, y1 = bbox
    parts = []
    for b in blocks:
        cx = (b["x0"] + b["x1"]) / 2
        cy = (b["y0"] + b["y1"]) / 2
        if x0 <= cx <= x1 and y0 <= cy <= y1:
            parts.append(b["text"])
    return "\n".join(parts)


def extract_nearby_totals(
    extracted: Dict[str, str],
    matched_ids: Dict[str, int],
    blocks: List[Dict[str, Any]],
    page_size: Tuple[int, int],
) -> Dict[str, str]:
    payable_id = matched_ids.get("payable_amount")
    if payable_id is None:
        return extracted

    payable_block = next((b for b in blocks if b["block_id"] == payable_id), None)
    if not payable_block:
        return extracted

    width, height = page_size
    x0 = max(0.0, payable_block["x0"] - width * 0.28)
    y0 = max(0.0, payable_block["y0"] - height * 0.18)
    x1 = min(width, payable_block["x1"] + width * 0.05)
    y1 = min(height, payable_block["y1"] + height * 0.10)
    region_text = extract_text_in_region(blocks, (x0, y0, x1, y1))
    merged_text = region_text + "\n" + extracted.get("payable_amount", "")

    for key, patterns in TOTAL_LABEL_PATTERNS.items():
        if extracted.get(key):
            continue
        for pat in patterns:
            m = re.search(pat, merged_text, flags=re.IGNORECASE)
            if m:
                extracted[key] = clean_amount(m.group(1))
                break

    # If payable_amount currently contains the whole nearby text, refine it.
    raw_payable = extracted.get("payable_amount", "")
    if len(raw_payable) > 32 or any(term in raw_payable.lower() for term in ["kdv", "toplam", "ödenecek"]):
        for pat in TOTAL_LABEL_PATTERNS["payable_amount"]:
            m = re.search(pat, merged_text, flags=re.IGNORECASE)
            if m:
                extracted["payable_amount"] = clean_amount(m.group(1))
                break

    return extracted


def fields_to_dataframe(mapping: Dict[str, str]) -> pd.DataFrame:
    rows = [{"field": k, "value": v} for k, v in mapping.items()]
    return pd.DataFrame(rows)


def export_fields_to_excel(mapping: Dict[str, str]) -> bytes:
    ordered = {k: mapping.get(k, "") for k in FIELD_LABELS}
    df = pd.DataFrame([ordered])
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Fatura")
    return buffer.getvalue()


def init_state() -> None:
    defaults = {
        "labels": {},
        "mode": "Öğretme Modu",
        "custom_regions": {},
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def teaching_mode(file_bytes: bytes) -> None:
    doc = open_pdf(file_bytes)
    page = doc.load_page(0)
    page_size = (int(page.rect.width), int(page.rect.height))
    blocks = extract_text_blocks(doc, 0)
    img = render_page(doc, 0, zoom=2.0)

    overlay_regions = []
    for bid, label in st.session_state.labels.items():
        region = st.session_state.custom_regions.get(label)
        if region:
            overlay_regions.append({"label": label, "bbox": bbox_from_relative(region, page_size)})
        else:
            overlay_regions.append({"label": label, "block_id": bid})

    st.subheader("1) Hologramik önizleme")
    preview = draw_hologram_preview(img, blocks, overlay_regions, zoom=2.0)
    st.image(preview, use_container_width=True)

    st.subheader("2) Metin blokları")
    block_options = {f"#{b['block_id']} | {b['text'][:120]}": b["block_id"] for b in blocks}
    selected_label = st.selectbox("Blok seç", list(block_options.keys()))
    selected_id = block_options[selected_label]
    block = next(b for b in blocks if b["block_id"] == selected_id)
    st.text_area("Seçili blok metni", block["text"], height=140)

    c1, c2 = st.columns([2, 1])
    with c1:
        field = st.selectbox("Alan etiketi", FIELD_LABELS)
    with c2:
        if st.button("Etiketi ata"):
            st.session_state.labels[selected_id] = field
            if field not in st.session_state.custom_regions:
                st.session_state.custom_regions[field] = default_region_from_block(block, page_size)
            st.rerun()

    if st.session_state.labels:
        st.subheader("3) Etiketli alanlar")
        labeled_rows = []
        for bid, label in st.session_state.labels.items():
            b = next((x for x in blocks if x["block_id"] == bid), None)
            if b:
                labeled_rows.append({"block_id": bid, "label": label, "text": b["text"]})
        st.dataframe(pd.DataFrame(labeled_rows), use_container_width=True)

        st.subheader("4) Alan penceresini ayarla")
        edit_label = st.selectbox("Düzenlenecek alan", sorted(set(st.session_state.labels.values())))
        region = st.session_state.custom_regions.get(edit_label)
        if not region:
            bid = next((bid for bid, lbl in st.session_state.labels.items() if lbl == edit_label), None)
            if bid is not None:
                region = default_region_from_block(next(b for b in blocks if b["block_id"] == bid), page_size)
                st.session_state.custom_regions[edit_label] = region
        if region:
            col_a, col_b, col_c, col_d = st.columns(4)
            with col_a:
                rx0 = st.slider("Sol", 0.0, 1.0, float(region["rx0"]), 0.005, key=f"rx0_{edit_label}")
            with col_b:
                ry0 = st.slider("Üst", 0.0, 1.0, float(region["ry0"]), 0.005, key=f"ry0_{edit_label}")
            with col_c:
                rx1 = st.slider("Sağ", 0.0, 1.0, float(region["rx1"]), 0.005, key=f"rx1_{edit_label}")
            with col_d:
                ry1 = st.slider("Alt", 0.0, 1.0, float(region["ry1"]), 0.005, key=f"ry1_{edit_label}")

            if rx1 <= rx0:
                rx1 = min(1.0, rx0 + 0.01)
            if ry1 <= ry0:
                ry1 = min(1.0, ry0 + 0.01)
            st.session_state.custom_regions[edit_label] = {"rx0": rx0, "ry0": ry0, "rx1": rx1, "ry1": ry1}

        c3, c4 = st.columns([2, 1])
        with c3:
            template_name = st.text_input("Şablon adı", value=suggest_template_name(blocks))
        with c4:
            if st.button("Şablonu kaydet"):
                path = save_template(template_name, page_size, blocks, st.session_state.labels, st.session_state.custom_regions)
                st.success(f"Şablon kaydedildi: {path}")

    if st.button("Etiketleri sıfırla"):
        st.session_state.labels = {}
        st.session_state.custom_regions = {}
        st.rerun()


def scanning_mode(file_bytes: bytes) -> None:
    templates = load_templates()
    if not templates:
        st.warning("Önce en az bir şablon kaydetmelisin.")
        return

    doc = open_pdf(file_bytes)
    page = doc.load_page(0)
    page_size = (int(page.rect.width), int(page.rect.height))
    blocks = extract_text_blocks(doc, 0)
    img = render_page(doc, 0, zoom=2.0)

    template_file = st.selectbox("Şablon seç", templates)
    template = load_template(os.path.join(TEMPLATE_DIR, template_file))
    extracted, matched_ids, matched_regions = apply_template(template, blocks, page_size)
    extracted = extract_nearby_totals(extracted, matched_ids, blocks, page_size)

    overlay_regions = []
    for label, region in matched_regions.items():
        overlay_regions.append({"label": label, "bbox": bbox_from_relative(region, page_size)})
    st.subheader("Hologramik önizleme")
    preview = draw_hologram_preview(img, blocks, overlay_regions, zoom=2.0)
    st.image(preview, use_container_width=True)

    st.subheader("Çıkarılan alanlar")
    df = fields_to_dataframe(extracted)
    st.dataframe(df, use_container_width=True)

    st.subheader("Yakın toplam mantığı")
    st.caption("Ödenecek Tutar bulunduysa, yakın çevresindeki KDV'siz toplam + KDV + genel toplam da otomatik çekilir.")

    excel_bytes = export_fields_to_excel(extracted)
    st.download_button(
        "Excel indir",
        data=excel_bytes,
        file_name=f"fatura_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    ensure_dirs()
    init_state()
    st.title(APP_TITLE)
    st.caption("Önce öğret, sonra aynı şablonla tara ve Excel'e at.")

    mode = st.radio("Mod", ["Öğretme Modu", "Tarama Modu"], horizontal=True)
    st.session_state.mode = mode

    uploaded = st.file_uploader("PDF yükle", type=["pdf"])
    if not uploaded:
        st.info("Devam etmek için bir PDF yükle.")
        return

    file_bytes = uploaded.read()

    if mode == "Öğretme Modu":
        teaching_mode(file_bytes)
    else:
        scanning_mode(file_bytes)


if __name__ == "__main__":
    main()

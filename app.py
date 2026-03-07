import io
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Tuple

import fitz  # PyMuPDF
import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw

APP_TITLE = "Fatura Öğretme ve Tarama Sistemi — MVP"
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


def ensure_dirs() -> None:
    os.makedirs(TEMPLATE_DIR, exist_ok=True)
    os.makedirs(EXPORT_DIR, exist_ok=True)


def normalize_text(text: str) -> str:
    return " ".join((text or "").replace("\n", " ").split()).strip()


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


def draw_blocks(img: Image.Image, blocks: List[Dict[str, Any]], labels: Dict[int, str], zoom: float = 2.0) -> Image.Image:
    canvas = img.copy()
    draw = ImageDraw.Draw(canvas)
    for block in blocks:
        bid = block["block_id"]
        box = [block["x0"] * zoom, block["y0"] * zoom, block["x1"] * zoom, block["y1"] * zoom]
        label = labels.get(bid, "")
        color = "cyan" if label else "orange"
        draw.rectangle(box, outline=color, width=3)
        if label:
            caption = f"[{label}] #{bid}"
            tx = box[0]
            ty = max(0, box[1] - 18)
            draw.rectangle([tx, ty, tx + max(120, len(caption) * 8), ty + 18], fill="black")
            draw.text((tx + 4, ty + 2), caption, fill="white")
    return canvas


def suggest_template_name(blocks: List[Dict[str, Any]]) -> str:
    joined = " ".join([b["text"] for b in blocks[:8]])
    lowered = joined.lower()
    if "amazon" in lowered:
        return "amazon_earsiv_v1"
    if "e-fatura" in lowered or "e-arşiv" in lowered:
        return "earsiv_v1"
    return f"template_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def save_template(template_name: str, page_size: Tuple[int, int], blocks: List[Dict[str, Any]], labels: Dict[int, str]) -> str:
    labeled = []
    width, height = page_size
    for block in blocks:
        bid = block["block_id"]
        if bid not in labels:
            continue
        labeled.append(
            {
                "block_id": bid,
                "label": labels[bid],
                "text": block["text"],
                "x0": block["x0"],
                "y0": block["y0"],
                "x1": block["x1"],
                "y1": block["y1"],
                "rx0": block["x0"] / width,
                "ry0": block["y0"] / height,
                "rx1": block["x1"] / width,
                "ry1": block["y1"] / height,
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
    sample = normalize_text(template_field.get("text", ""))[:20].lower()
    if sample and sample in block["text"].lower():
        text_bonus = -100
    return center_dist + (area_diff / 1000.0) + text_bonus


def apply_template(template: Dict[str, Any], blocks: List[Dict[str, Any]], page_size: Tuple[int, int]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    used_ids = set()
    for field in template.get("fields", []):
        ranked = sorted(blocks, key=lambda b: score_block_match(field, b, page_size))
        for cand in ranked:
            if cand["block_id"] in used_ids:
                continue
            result[field["label"]] = cand["text"]
            used_ids.add(cand["block_id"])
            break
    return result


def fields_to_dataframe(mapping: Dict[str, str]) -> pd.DataFrame:
    rows = [{"field": k, "value": v} for k, v in mapping.items()]
    return pd.DataFrame(rows)


def export_fields_to_excel(mapping: Dict[str, str]) -> bytes:
    df = pd.DataFrame([mapping])
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Fatura")
    return buffer.getvalue()


def init_state() -> None:
    defaults = {
        "labels": {},
        "selected_block_id": None,
        "mode": "Öğretme Modu",
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

    st.subheader("1) Sayfa önizleme")
    preview = draw_blocks(img, blocks, st.session_state.labels, zoom=2.0)
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
            st.rerun()

    if st.session_state.labels:
        st.subheader("3) Etiketli alanlar")
        labeled_rows = []
        for bid, label in st.session_state.labels.items():
            b = next((x for x in blocks if x["block_id"] == bid), None)
            if b:
                labeled_rows.append({"block_id": bid, "label": label, "text": b["text"]})
        st.dataframe(pd.DataFrame(labeled_rows), use_container_width=True)

        c3, c4 = st.columns([2, 1])
        with c3:
            template_name = st.text_input("Şablon adı", value=suggest_template_name(blocks))
        with c4:
            if st.button("Şablonu kaydet"):
                path = save_template(template_name, page_size, blocks, st.session_state.labels)
                st.success(f"Şablon kaydedildi: {path}")

    if st.button("Etiketleri sıfırla"):
        st.session_state.labels = {}
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
    extracted = apply_template(template, blocks, page_size)

    st.subheader("Önizleme")
    preview_labels = {}
    for field in template.get("fields", []):
        for block in blocks:
            if extracted.get(field["label"]) == block["text"]:
                preview_labels[block["block_id"]] = field["label"]
                break
    preview = draw_blocks(img, blocks, preview_labels, zoom=2.0)
    st.image(preview, use_container_width=True)

    st.subheader("Çıkarılan alanlar")
    df = fields_to_dataframe(extracted)
    st.dataframe(df, use_container_width=True)

    excel_bytes = export_fields_to_excel(extracted)
    st.download_button(
        "Excel indir",
        data=excel_bytes,
        file_name=f"fatura_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def main() -> None:
    ensure_dirs()
    init_state()
    st.set_page_config(page_title=APP_TITLE, layout="wide")
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

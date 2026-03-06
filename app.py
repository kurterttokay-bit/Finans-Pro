from json_utils import safe_json_loads
import streamlit as st
import pandas as pd
import yfinance as yf
import google.generativeai as genai
from datetime import datetime, timedelta
from PIL import Image
import json
import re
import logging
import plotly.express as px
import os
from urllib.parse import urlencode
from io import BytesIO
from invoice_normalizers import normalize_amount, normalize_currency, normalize_date
from sheet_ops import read_sheet, append_row, replace_sheet, SHEET_COLUMNS
# -------------------------
# OPTIONAL LIBS (PDF / OCR)
# -------------------------
PDF_ENABLED = False
OCR_ENABLED = False
try:
    from pdf2image import convert_from_bytes  # requires poppler-utils in Streamlit Cloud
    PDF_ENABLED = True
except Exception:
    PDF_ENABLED = False
try:
    import pytesseract  # requires tesseract-ocr in Streamlit Cloud
    OCR_ENABLED = True
except Exception:
    OCR_ENABLED = False
# -------------------------
# GSHEETS CONNECTION (compat)
# -------------------------
try:
    from streamlit_gsheets import GSheetsConnection
except ImportError:
    try:
        from st_gsheets_connection import GSheetsConnection
    except ImportError:
        GSheetsConnection = None
# -------------------------
# CONFIG
# -------------------------
st.set_page_config(page_title="Finans Enterprise", page_icon="🏦", layout="wide")
logging.basicConfig(level=logging.INFO)
APP_TITLE = "🏦 Finans Enterprise"
WORKSHEET_NAME = "Sayfa1"  # Google Sheets worksheet
def get_sheets_url() -> str:
    """Try to find the Google Sheets URL from secrets in multiple common locations."""
    # 1) Top-level SHEETS_URL
    try:
        v = st.secrets.get("SHEETS_URL", "")
        if v: return str(v)
    except Exception:
        pass
    # 2) connections.gsheets.spreadsheet
    try:
        v = st.secrets.get("connections", {}).get("gsheets", {}).get("spreadsheet", "")
        if v: return str(v)
    except Exception:
        pass
    # 3) connections.gsheets.url (some setups)
    try:
        v = st.secrets.get("connections", {}).get("gsheets", {}).get("url", "")
        if v: return str(v)
    except Exception:
        pass
    return ""
# -------------------------
# THEME (Light/Dark)
# -------------------------
# -------------------------
# THEME (auto from device, user override via sidebar)
# -------------------------
from streamlit import components
def _get_query_params():
    # Streamlit versions differ: try modern st.query_params first
    try:
        return dict(st.query_params)
    except Exception:
        try:
            return st.experimental_get_query_params()
        except Exception:
            return {}
def _set_query_params(**kwargs):
    try:
        st.query_params.update(kwargs)  # modern API
    except Exception:
        st.experimental_set_query_params(**kwargs)
def bootstrap_theme():
    """Initialize theme_mode from URL (?theme=dark|light) or from device preference (prefers-color-scheme).
    - If URL has ?theme=dark|light -> use it.
    - Else: set a safe default (Light) immediately so UI renders,
      then run a one-time JS redirect to append ?theme=... based on device preference.
    """
    qp = _get_query_params()
    # Already initialized this session
    if "theme_mode" in st.session_state:
        return
    qp_theme = None
    if isinstance(qp, dict):
        raw = qp.get("theme")
        if isinstance(raw, list) and raw:
            raw = raw[0]
        if isinstance(raw, str) and raw.strip():
            qp_theme = raw.strip().lower()
    if qp_theme in ("dark", "light"):
        st.session_state.theme_mode = "Dark" if qp_theme == "dark" else "Light"
        st.session_state["_theme_redirected"] = True
        return
    # Render immediately with a safe default (Light)
    st.session_state.theme_mode = "Light"
    # One-time auto-detect + redirect (no st.stop -> prevents 'black screen')
    if not st.session_state.get("_theme_redirected", False):
        st.session_state["_theme_redirected"] = True
        components.v1.html(
            """<script>
            (function() {
              try {
                const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
                const theme = prefersDark ? 'dark' : 'light';
                const url = new URL(window.location.href);
                if (!url.searchParams.get('theme')) {
                  url.searchParams.set('theme', theme);
                  window.location.replace(url.toString());
                }
              } catch (e) {}
            })();
            </script>""",
            height=0,
        )
bootstrap_theme()
def inject_theme_css(theme: str):
    """
    Streamlit built-in theme runtime'da değişmediği için Light/Dark görünümü CSS ile token'lıyoruz.
    Önemli: f-string içinde CSS blok parantezleri {{ }} olmalı.
    """
    is_light = str(theme).lower().startswith("l")
    if is_light:
        bg = "#F6F7FB"
        panel = "#FFFFFF"
        text = "#0F172A"
        muted = "#475569"
        border = "rgba(2, 6, 23, .10)"
        card = "#FFFFFF"
        card2 = "rgba(15, 23, 42, .02)"
        shadow = "0 10px 26px rgba(16,24,40,0.08)"
        input_bg = "#FFFFFF"
    else:
        bg = "#0B1220"
        panel = "rgba(15, 23, 42, .70)"
        text = "#E5E7EB"
        muted = "#9CA3AF"
        border = "rgba(148, 163, 184, .18)"
        card = "rgba(2, 6, 23, .38)"
        card2 = "rgba(255,255,255,.03)"
        shadow = "0 14px 34px rgba(0,0,0,.24)"
        input_bg = "rgba(255,255,255,.04)"
    css = f"""
    <style>
    /* ---- Layout (SaaS-like width + spacing) ---- */
    .block-container {{
        max-width: 1180px;
        padding-top: 1.25rem;
        padding-bottom: 2.5rem;
    }}
    /* ---- Base ---- */
    .stApp {{
        background: {bg};
        color: {text};
    }}
    [data-testid="stMarkdownContainer"] {{
        color: {text};
    }}
    /* Sidebar */
    section[data-testid="stSidebar"] {{
        background: {panel};
        border-right: 1px solid {border};
    }}
    /* Headings */
    h1, h2, h3, h4 {{
        color: {text};
        letter-spacing: -0.02em;
        line-height: 1.15;
    }}
    .muted {{
        color: {muted} !important;
    }}
    /* ---- Cards: use Streamlit native bordered containers ---- */
    div[data-testid="stVerticalBlockBorderWrapper"] {{
        background: {card};
        border: 1px solid {border};
        border-radius: 16px;
        padding: 16px 16px 12px 16px;
        box-shadow: {shadow};
        backdrop-filter: blur(10px);
    }}
    /* ---- Buttons ---- */
    .stDownloadButton button, .stButton button {{
        border-radius: 12px !important;
        border: 1px solid {border} !important;
        background: {card2} !important;
        color: {text} !important;
    }}
    .stDownloadButton button:hover, .stButton button:hover {{
        filter: brightness(1.06);
        transform: translateY(-1px);
    }}
    /* ---- Inputs / Selects: fix "Light mode görünmüyor" ---- */
    .stTextInput input, .stNumberInput input {{
        background: {input_bg} !important;
        color: {text} !important;
        border: 1px solid {border} !important;
        border-radius: 12px !important;
    }}
    .stTextArea textarea {{
        background: {input_bg} !important;
        color: {text} !important;
        border: 1px solid {border} !important;
        border-radius: 12px !important;
    }}
    div[data-baseweb="select"] > div {{
        background: {input_bg} !important;
        border: 1px solid {border} !important;
        border-radius: 12px !important;
        color: {text} !important;
    }}
    div[data-baseweb="select"] span {{
        color: {text} !important;
    }}
    /* File uploader dropzone */
    div[data-testid="stFileUploaderDropzone"] {{
        border-radius: 14px;
        border: 1px dashed {border};
        background: {card2};
        color: {text};
    }}
    /* Dataframe */
    div[data-testid="stDataFrame"] {{
        border-radius: 12px;
        overflow: hidden;
        border: 1px solid {border};
    }}
    /* Badges + accent line */
    .badge {{
        font-size: 12px;
        padding: 4px 10px;
        border-radius: 999px;
        border: 1px solid {border};
        background: {card2};
        color: {muted};
        white-space: nowrap;
    }}
    .accent-line {{
        height: 3px;
        width: 52px;
        border-radius: 999px;
        background: rgba(99, 102, 241, .8);
        margin-top: 10px;
        margin-bottom: 4px;
    }}
    /* Hero */
    .hero {{
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
        gap: 12px;
        margin: 6px 0 18px 0;
    }}
    .hero h1 {{
        font-size: 34px;
        margin: 0;
    }}
    .hero p {{
        margin: 8px 0 0 0;
        color: {muted};
        max-width: 680px;
    }}
    .kpi-row {{
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 12px;
        margin-bottom: 16px;
    }}
    .kpi {{
        background: {card};
        border: 1px solid {border};
        border-radius: 16px;
        padding: 12px 14px;
        box-shadow: {shadow};
    }}
    .kpi .label {{
        color: {muted};
        font-size: 12px;
        margin-bottom: 6px;
    }}
    .kpi .value {{
        font-size: 18px;
        font-weight: 700;
        color: {text};
    }}
    /* Stepper */
    .stepper {{
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 10px;
        margin: 10px 0 18px 0;
    }}
    .step {{
        border: 1px solid {border};
        background: {card2};
        border-radius: 14px;
        padding: 10px 12px;
    }}
    .step .t {{
        font-weight: 700;
        font-size: 13px;
        margin-bottom: 4px;
        color: {text};
    }}
    .step .d {{
        font-size: 12px;
        color: {muted};
        line-height: 1.3;
    }}
    
    /* ---- Flow selector (Islem Merkezi) - scoped to radio key: flow_radio_pick ---- */
    div[data-testid="stRadio"]:has(input[id^="flow_radio_pick"]) > div[role="radiogroup"] {{
        display: flex;
        gap: 14px;
        flex-wrap: wrap;
    }}
    div[data-testid="stRadio"]:has(input[id^="flow_radio_pick"]) label {{
        border: 1px solid {border};
        background: {card};
        border-radius: 18px;
        padding: 18px 18px;
        min-height: 92px;
        align-items: flex-start;
        box-shadow: {shadow};
        flex: 1 1 240px;
        max-width: 420px;
    }}
    div[data-testid="stRadio"]:has(input[id^="flow_radio_pick"]) label p {{
        font-weight: 700;
        font-size: 22px;
        line-height: 1.15;
        margin-top: -2px;
    }}
    div[data-testid="stRadio"]:has(input[id^="flow_radio_pick"]) label:hover {{
        border-color: rgba(59,130,246,.55);
        transform: translateY(-1px);
        transition: transform .12s ease;
    }}
    div[data-testid="stRadio"]:has(input[id^="flow_radio_pick"]) input:checked + div {{
        border-radius: 16px;
        outline: 2px solid rgba(99,102,241,.55);
        outline-offset: 2px;
    }}
    /* ---- Flow cards (Islem Merkezi) ---- */
    .flowcards {{
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 14px;
        margin-top: 8px;
        margin-bottom: 12px;
    }}
    @media (max-width: 1100px) {{
        .flowcards {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    @media (max-width: 600px) {{
        .flowcards {{ grid-template-columns: 1fr; }}
    }}
    a.flowcard {{
        display: block;
        text-decoration: none;
        border-radius: 16px;
        border: 1px solid {border};
        background: {card};
        padding: 16px 16px 14px 16px;
        transition: transform .15s ease, border-color .15s ease, filter .15s ease;
    }}
    a.flowcard:hover {{
        transform: translateY(-1px);
        filter: brightness(1.02);
    }}
    a.flowcard.selected {{
        border-color: rgba(99, 102, 241, .65);
        box-shadow: 0 10px 30px rgba(99, 102, 241, .15);
    }}
    .flow-top {{
        display:flex;
        align-items:center;
        justify-content:space-between;
        gap: 10px;
        margin-bottom: 8px;
    }}
    .flow-ttl {{
        font-weight: 800;
        font-size: 18px;
        letter-spacing: -0.02em;
        color: {text};
        line-height: 1.15;
    }}
    .flow-sub {{
        color: {muted};
        font-size: 14px;
        line-height: 1.35;
    }}
    .flow-pill {{
        font-size: 12px;
        padding: 6px 10px;
        border-radius: 999px;
        border: 1px solid {border};
        color: {muted};
        background: rgba(255,255,255,.04);
        white-space: nowrap;
    }}
    .flow-ico {{
        width: 34px;
        height: 34px;
        border-radius: 12px;
        display:flex;
        align-items:center;
        justify-content:center;
        border: 1px solid {border};
        background: rgba(255,255,255,.04);
        flex: 0 0 auto;
        font-size: 16px;
    }}
    /* Panel entrance animation (only the selected flow panel wrapper) */
    @keyframes fadeUp {{
        from {{ opacity: 0; transform: translateY(8px); }}
        to   {{ opacity: 1; transform: translateY(0px); }}
    }}
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.flow-panel-marker) {{
        animation: fadeUp .22s ease-out;
    }}
</style>
    """
    st.markdown(css, unsafe_allow_html=True)
# -------------------------
# AUTH SYSTEM
# -------------------------
ROLES = {
    "patron125": "PATRON",
    "muhasebe007": "MUHASEBE",
    "kurter": "YONETICI"
}
if "auth" not in st.session_state:
    st.session_state.auth = None
def login():
    inject_theme_css(st.session_state.theme_mode)
    col1, col2, col3 = st.columns([1, 1.3, 1])
    with col2:
        st.markdown(f"<div class='card'>", unsafe_allow_html=True)
        st.title(APP_TITLE)
        st.markdown("<div class='muted'>Güvenli giriş</div>", unsafe_allow_html=True)
        with st.form("login"):
            pwd = st.text_input("Şifre", type="password")
            submit = st.form_submit_button("Giriş")
            if submit:
                if pwd in ROLES:
                    st.session_state.auth = ROLES[pwd]
                    st.rerun()
                else:
                    st.error("Hatalı şifre")
        st.markdown("</div>", unsafe_allow_html=True)
if not st.session_state.auth:
    login()
    st.stop()
ROLE = st.session_state.auth
# -------------------------
# GEMINI CONFIG
# -------------------------
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")
if not GEMINI_API_KEY:
    inject_theme_css(st.session_state.theme_mode)
    st.error("GEMINI_API_KEY bulunamadı. Streamlit Secrets içine ekleyin.")
    st.stop()
genai.configure(api_key=GEMINI_API_KEY)
@st.cache_resource
def get_model_name():
    try:
        available = [m.name for m in genai.list_models() if "generateContent" in getattr(m, "supported_generation_methods", [])]
        for candidate in ["models/gemini-1.5-flash", "gemini-1.5-flash", "models/gemini-pro", "gemini-pro"]:
            if candidate in available:
                return candidate
    except Exception:
        pass
    return "gemini-1.5-flash"
MODEL_NAME = get_model_name()
model = genai.GenerativeModel(MODEL_NAME)
FALLBACK_MODELS = [
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-pro",
]
def _generate_with_fallback(parts):
    
    """Try generate_content with a few model names to survive 404 / unsupported errors."""
    last_err = None
    tried = []
    for name in [MODEL_NAME] + [m for m in FALLBACK_MODELS if m != MODEL_NAME]:
        try:
            tried.append(name)
            m = genai.GenerativeModel(name)
            resp = m.generate_content(parts)
            return resp, name
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"AI çağrısı başarısız. Denenen modeller: {tried}. Son hata: {last_err}")
def extract_response_text(response):
    """
    Gemini yanıtından güvenli şekilde text çıkarmaya çalışır.
    """
    try:
        text = getattr(response, "text", "") or ""
        if text and text.strip():
            return text.strip()
    except Exception:
        pass
    try:
        candidates = getattr(response, "candidates", None)
        if candidates:
            parts = candidates[0].content.parts
            collected = []
            for p in parts:
                t = getattr(p, "text", "")
                if t:
                    collected.append(t)
            joined = "\n".join(collected).strip()
            if joined:
                return joined
    except Exception:
        pass
    return ""
# -------------------------
# GSHEETS CONNECTION
# -------------------------
if GSheetsConnection is None:
    inject_theme_css(st.session_state.theme_mode)
    st.error("GSheetsConnection kütüphanesi bulunamadı. requirements.txt kontrol edin.")
    st.stop()
conn = st.connection("gsheets", type=GSheetsConnection)
# -------------------------
# COLUMN NORMALIZATION (Sayfa1)
# -------------------------
CANON_COLS = [
    "kayit_tarihi", "belge_tarihi", "firma_adi", "evrak_tipi", "evrak_no",
    "vergi_kimlik_no", "para_birimi", "ara_toplam", "kdv_orani", "kdv_tutari",
    "genel_toplam", "kategori", "odeme_durumu", "aciklama", "ham_metin",
    "kaynak_dosya", "created_at", "updated_at"
]
def normalize_sheet(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        out = pd.DataFrame(columns=CANON_COLS)
        out["Belge_Date"] = pd.NaT
        return out
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    for c in CANON_COLS:
        if c not in df.columns:
            df[c] = ""
    df = df[CANON_COLS].copy()
    for col in ["ara_toplam", "kdv_orani", "kdv_tutari", "genel_toplam"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    df["Belge_Date"] = pd.to_datetime(df["belge_tarihi"], dayfirst=True, errors="coerce")
    df["para_birimi"] = df["para_birimi"].astype(str).str.strip().replace({"": "TL"}).fillna("TL")
    df["odeme_durumu"] = df["odeme_durumu"].astype(str).str.strip().replace({"": "Beklemede"}).fillna("Beklemede")
    return df
def build_invoice_record(parsed: dict | None, ocr_text: str = "", source_name: str = "") -> dict:
    parsed = parsed or {}
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    today_str = now.strftime("%d.%m.%Y")
    belge_tarihi = normalize_date(parsed.get("Vade", parsed.get("belge_tarihi", "")))
    genel_toplam = normalize_amount(parsed.get("Tutar", parsed.get("genel_toplam", 0)))
    para_birimi = normalize_currency(parsed.get("Döviz", parsed.get("para_birimi", "TL")))
    return {
        "kayit_tarihi": today_str,
        "belge_tarihi": belge_tarihi,
        "firma_adi": str(parsed.get("Firma Adı", parsed.get("firma_adi", ""))).strip(),
        "evrak_tipi": str(parsed.get("Evrak Tipi", parsed.get("evrak_tipi", "Fatura"))).strip() or "Fatura",
        "evrak_no": str(parsed.get("Evrak No", parsed.get("evrak_no", ""))).strip(),
        "vergi_kimlik_no": str(parsed.get("Vergi Kimlik No", parsed.get("vergi_kimlik_no", ""))).strip(),
        "para_birimi": para_birimi,
        "ara_toplam": normalize_amount(parsed.get("Ara Toplam", parsed.get("ara_toplam", 0))),
        "kdv_orani": normalize_amount(parsed.get("KDV Oranı", parsed.get("kdv_orani", 0))),
        "kdv_tutari": normalize_amount(parsed.get("KDV Tutarı", parsed.get("kdv_tutari", 0))),
        "genel_toplam": genel_toplam,
        "kategori": str(parsed.get("Kategori", parsed.get("kategori", ""))).strip(),
        "odeme_durumu": str(parsed.get("Durum", parsed.get("odeme_durumu", "Beklemede"))).strip() or "Beklemede",
        "aciklama": str(parsed.get("Açıklama", parsed.get("aciklama", ""))).strip(),
        "ham_metin": (ocr_text or str(parsed.get("ham_metin", ""))).strip(),
        "kaynak_dosya": source_name,
        "created_at": now_str,
        "updated_at": now_str,
    }
def render_invoice_review_form(result: dict, key_prefix: str = "rev") -> dict:
    """Render editable invoice form and return normalized dict in legacy field names.
    This keeps build_invoice_record compatible while letting user correct all important fields.
    """
    result = result or {}
    belge_tarihi_default = result.get("Vade", result.get("belge_tarihi", datetime.now().strftime("%d.%m.%Y")))
    firma_default = result.get("Firma Adı", result.get("firma_adi", ""))
    evrak_tipi_default = result.get("Evrak Tipi", result.get("evrak_tipi", "Fatura")) or "Fatura"
    evrak_no_default = result.get("Evrak No", result.get("evrak_no", ""))
    vergi_default = result.get("Vergi Kimlik No", result.get("vergi_kimlik_no", ""))
    para_default = normalize_currency(result.get("Döviz", result.get("para_birimi", "TL")))
    ara_default = normalize_amount(result.get("Ara Toplam", result.get("ara_toplam", 0)))
    kdv_oran_default = normalize_amount(result.get("KDV Oranı", result.get("kdv_orani", 0)))
    kdv_tutar_default = normalize_amount(result.get("KDV Tutarı", result.get("kdv_tutari", 0)))
    genel_default = normalize_amount(result.get("Tutar", result.get("genel_toplam", 0)))
    kategori_default = result.get("Kategori", result.get("kategori", ""))
    durum_default = result.get("Durum", result.get("odeme_durumu", "Beklemede")) or "Beklemede"
    aciklama_default = result.get("Açıklama", result.get("aciklama", ""))
    tip_options = ["Fatura", "e-Fatura", "e-Arşiv", "Gider Pusulası", "Diğer"]
    if evrak_tipi_default not in tip_options:
        tip_options.append(evrak_tipi_default)
    para_options = ["TL", "USD", "EUR"]
    if para_default not in para_options:
        para_options.append(para_default)
    durum_options = ["Beklemede", "Ödendi"]
    if durum_default not in durum_options:
        durum_options.append(durum_default)
    kategori_options = ["", "Ofis Gideri", "Yazılım", "Kargo", "Reklam", "Yemek", "Demirbaş", "Diğer"]
    if kategori_default and kategori_default not in kategori_options:
        kategori_options.append(kategori_default)
    c1, c2, c3 = st.columns(3)
    with c1:
        firma_adi = st.text_input("Firma Adı", value=firma_default, key=f"{key_prefix}_firma")
        evrak_tipi = st.selectbox("Evrak Tipi", tip_options, index=tip_options.index(evrak_tipi_default), key=f"{key_prefix}_tip")
        evrak_no = st.text_input("Evrak No", value=evrak_no_default, key=f"{key_prefix}_no")
    with c2:
        belge_tarihi = st.text_input("Belge Tarihi", value=belge_tarihi_default, key=f"{key_prefix}_tarih")
        para_birimi = st.selectbox("Para Birimi", para_options, index=para_options.index(para_default), key=f"{key_prefix}_para")
        genel_toplam = st.number_input("Genel Toplam", value=float(genel_default), step=100.0, key=f"{key_prefix}_genel")
    with c3:
        vergi_kimlik_no = st.text_input("Vergi Kimlik No", value=vergi_default, key=f"{key_prefix}_vkn")
        kategori = st.selectbox("Kategori", kategori_options, index=kategori_options.index(kategori_default), key=f"{key_prefix}_kategori")
        odeme_durumu = st.selectbox("Ödeme Durumu", durum_options, index=durum_options.index(durum_default), key=f"{key_prefix}_durum")
    d1, d2, d3 = st.columns(3)
    with d1:
        ara_toplam = st.number_input("Ara Toplam", value=float(ara_default), step=100.0, key=f"{key_prefix}_ara")
    with d2:
        kdv_orani = st.number_input("KDV Oranı", value=float(kdv_oran_default), step=1.0, key=f"{key_prefix}_kdv_oran")
    with d3:
        kdv_tutari = st.number_input("KDV Tutarı", value=float(kdv_tutar_default), step=10.0, key=f"{key_prefix}_kdv_tutar")
    aciklama = st.text_area("Açıklama", value=aciklama_default, key=f"{key_prefix}_aciklama")
    return {
        "Firma Adı": firma_adi,
        "Evrak Tipi": evrak_tipi,
        "Evrak No": evrak_no,
        "Vergi Kimlik No": vergi_kimlik_no,
        "Döviz": para_birimi,
        "Ara Toplam": ara_toplam,
        "KDV Oranı": kdv_orani,
        "KDV Tutarı": kdv_tutari,
        "Tutar": genel_toplam,
        "Vade": belge_tarihi,
        "Kategori": kategori,
        "Durum": odeme_durumu,
        "Açıklama": aciklama,
    }
# -------------------------
# DATA LOAD / SAVE
# -------------------------
@st.cache_data(ttl=30)
def load_data():
    try:
        raw = read_sheet(conn, worksheet=WORKSHEET_NAME)
        # Bazı kurulumlarda worksheet adı desteklenmeyebilir veya farklı olabilir.
        if raw is None or raw.empty:
            raw = read_sheet(conn)
        st.session_state["_gsheets_last_error"] = ""
        return normalize_sheet(raw)
    except Exception as e:
        try:
            raw = read_sheet(conn)
            st.session_state["_gsheets_last_error"] = f"Worksheet fallback kullanıldı: {e}"
            return normalize_sheet(raw)
        except Exception as e2:
            st.session_state["_gsheets_last_error"] = f"{e} | fallback: {e2}"
            return normalize_sheet(pd.DataFrame(columns=CANON_COLS))
def save_data(df: pd.DataFrame):
    try:
        cleaned = normalize_sheet(df).drop(columns=["Belge_Date"], errors="ignore")
        replace_sheet(conn, cleaned[CANON_COLS], worksheet=WORKSHEET_NAME)
        st.cache_data.clear()
        return True, ""
    except Exception as e:
        logging.exception(e)
        return False, str(e)
def save_single_record(record: dict):
    """Append one normalized record directly to Google Sheets.
    This avoids stale cached df / full-sheet overwrite issues in AI save flows.
    """
    try:
        clean = {col: record.get(col, "") for col in SHEET_COLUMNS}
        append_row(conn, clean, worksheet=WORKSHEET_NAME)
        st.cache_data.clear()
        return True, ""
    except Exception as e:
        logging.exception(e)
        return False, str(e)

def save_records_batch(records: list[dict]):
    """More stable bulk save: read once, append many rows, write once."""
    try:
        base = load_data().drop(columns=["Belge_Date"], errors="ignore")
        if base is None or base.empty:
            base = pd.DataFrame(columns=CANON_COLS)
        new_df = pd.DataFrame([{col: rec.get(col, "") for col in CANON_COLS} for rec in records])
        combined = pd.concat([base[CANON_COLS], new_df[CANON_COLS]], ignore_index=True)
        return save_data(combined)
    except Exception as e:
        logging.exception(e)
        return False, str(e)
# -------------------------
# FX RATES
# -------------------------
@st.cache_data(ttl=300)
def get_fx():
    def _safe_rate(ticker: str, fallback: float) -> float:
        try:
            fx = yf.download(ticker, period="5d", progress=False, auto_adjust=False)
            if fx is None or fx.empty or "Close" not in fx.columns:
                return fallback
            close = fx["Close"].dropna()
            if close.empty:
                return fallback
            return float(close.iloc[-1])
        except Exception as e:
            logging.error("FX rate fetch failed for %s: %s", ticker, e)
            return fallback
    usd = _safe_rate("USDTRY=X", 34.90)
    eur = _safe_rate("EURTRY=X", 37.80)
    return usd, eur
def compute_tl(df: pd.DataFrame, usd: float, eur: float) -> pd.DataFrame:
    dfx = df.copy()
    kur_map = {
        "USD": usd, "USDT": usd, "DOLAR": usd, "Dolar": usd, "Dolar ": usd,
        "EUR": eur, "EURO": eur, "Euro": eur, "Euro ": eur,
        "TL": 1, "TRY": 1, "₺": 1
    }
    dfx["kur"] = dfx["para_birimi"].map(kur_map).fillna(1)
    dfx["Tutar_TL"] = pd.to_numeric(dfx["genel_toplam"], errors="coerce").fillna(0) * dfx["kur"]
    return dfx
# -------------------------
# OCR / AI INVOICE PARSE
# -------------------------
from PIL import ImageOps, ImageEnhance, ImageFilter
def pdf_first_page_to_image(pdf_bytes: bytes, dpi: int = 350) -> Image.Image:
    pages = convert_from_bytes(pdf_bytes, dpi=dpi, fmt="png")
    return pages[0].convert("RGB")
def enhance_for_reading(img: Image.Image) -> Image.Image:
    g = ImageOps.grayscale(img)
    g = ImageEnhance.Contrast(g).enhance(1.8)
    g = ImageEnhance.Sharpness(g).enhance(2.0)
    g = g.filter(ImageFilter.MedianFilter(size=3))
    return g.convert("RGB")
def decode_qr_opencv(img: Image.Image) -> list[str]:
    try:
        import cv2
        import numpy as np
        arr = np.array(img.convert("RGB"))
        bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        bgr = cv2.resize(bgr, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        detector = cv2.QRCodeDetector()
        data, points, _ = detector.detectAndDecode(bgr)
        if data and data.strip():
            return [data.strip()]
        return []
    except Exception:
        return []
def ocr_read(image: Image.Image) -> str:
    if not OCR_ENABLED:
        return ""
    try:
        return pytesseract.image_to_string(image)
    except Exception:
        return ""
def parse_invoice_from_qr(qr_text: str) -> dict | None:
    if not qr_text:
        return None
    try:
        data = json.loads(qr_text)
    except Exception:
        return None
    kdv_orani = 0.0
    kdv_tutari = 0.0
    for key, value in data.items():
        if isinstance(key, str) and key.startswith("hesaplanankdv("):
            kdv_tutari = normalize_amount(value)
        if isinstance(key, str) and key.startswith("kdvmatrah("):
            try:
                kdv_orani = normalize_amount(key.split("kdvmatrah(")[1].split(")")[0])
            except Exception:
                pass
    return {
        "Firma Adı": "",
        "Evrak Tipi": "Fatura",
        "Tutar": normalize_amount(data.get("odenecek", data.get("vergidahil", 0))),
        "Vade": normalize_date(data.get("tarih", "")),
        "Açıklama": f"QR senaryo: {data.get('senaryo', '')} / tip: {data.get('tip', '')}".strip(" /"),
        "Evrak No": str(data.get("no", "")).strip(),
        "Döviz": normalize_currency(data.get("parabirimi", "TL")),
        "Vergi Kimlik No": str(data.get("avkntckn", "") or data.get("vknckn", "")).strip(),
        "Ara Toplam": normalize_amount(data.get("malhizmettoplam", 0)),
        "KDV Oranı": kdv_orani,
        "KDV Tutarı": kdv_tutari,
    }
def merge_invoice_data(primary: dict | None, secondary: dict | None) -> dict:
    merged = dict(secondary or {})
    for k, v in (primary or {}).items():
        if v not in (None, "", 0, 0.0, []):
            merged[k] = v
    return merged
def process_uploaded_invoice(uploaded_file, do_ocr: bool = False) -> dict:
    raw_image = None
    image = None
    ocr_text = ""
    qr_list = []
    qr_result = None
    source_name = getattr(uploaded_file, "name", "")
    try:
        file_type = getattr(uploaded_file, "type", "") or ""
        if file_type == "application/pdf" or source_name.lower().endswith('.pdf'):
            pdf_bytes = uploaded_file.read()
            if PDF_ENABLED:
                try:
                    raw_image = pdf_first_page_to_image(pdf_bytes, dpi=350)
                except Exception as e:
                    logging.warning("PDF first page image failed for %s: %s", source_name, e)
            if raw_image is None:
                try:
                    import PyPDF2
                    reader = PyPDF2.PdfReader(BytesIO(pdf_bytes))
                    extracted = []
                    for pg in reader.pages[:5]:
                        t = pg.extract_text() or ""
                        if t.strip():
                            extracted.append(t)
                    ocr_text = "\n".join(extracted)[:12000]
                except Exception as e:
                    logging.warning("PDF text extraction failed for %s: %s", source_name, e)
        else:
            uploaded_file.seek(0)
            raw_image = Image.open(uploaded_file).convert("RGB")
        if raw_image is not None:
            image = enhance_for_reading(raw_image)
            qr_list = decode_qr_opencv(raw_image) or decode_qr_opencv(image) or []
            if do_ocr:
                try:
                    ocr_piece = ocr_read(image)
                    if ocr_piece.strip():
                        ocr_text = (ocr_text + "\n" + ocr_piece).strip()
                except Exception as e:
                    logging.warning("OCR failed for %s: %s", source_name, e)
        if qr_list:
            for qr in qr_list:
                qr_result = parse_invoice_from_qr(qr)
                if qr_result:
                    break
        ai_result = None
        if image is not None:
            ai_result = analyze_invoice(image, ocr_text=ocr_text, qr_list=qr_list)
        elif ocr_text.strip():
            ai_result = analyze_invoice_text_only(ocr_text, qr_list=qr_list)
        result = merge_invoice_data(ai_result, qr_result) if (ai_result or qr_result) else None
        return {
            "source_name": source_name,
            "raw_image": raw_image,
            "image": image,
            "ocr_text": ocr_text,
            "qr_list": qr_list,
            "result": result,
            "error": "" if result else "Veri çıkarılamadı",
        }
    except Exception as e:
        logging.exception(e)
        return {
            "source_name": source_name,
            "raw_image": raw_image,
            "image": image,
            "ocr_text": ocr_text,
            "qr_list": qr_list,
            "result": None,
            "error": str(e),
        }
def analyze_invoice(image: Image.Image, ocr_text: str = "", qr_list: list[str] | None = None):
    qr_list = qr_list or []
    prompt = f"""
Sen bir finans muhasebe asistanısın. Bu görsel bir fatura / e-fatura olabilir.
ELİNDE QR/ OCR varsa bunları mutlaka kullan:
QR_VERI: {qr_list}
OCR_METIN: {ocr_text[:4000]}
Sadece geçerli bir JSON nesnesi döndür.
Açıklama, markdown, kod bloğu ekleme.
Şema:
{{
  "firma_adi": "",
  "evrak_tipi": "Fatura",
  "tutar": 0,
  "vade": "DD.MM.YYYY",
  "aciklama": "",
  "evrak_no": "",
  "doviz": "TL"
}}
Notlar:
- vade yoksa fatura tarihini vade olarak yaz.
- tutarı KDV dahil toplam ödenecek tutar olarak yakala.
- dövizi bulamazsan TL yaz.
- evrak_no: fatura no.
- Eğer bir alan bulunamazsa boş string döndür. Tahmin uydurma.
"""
    try:
        response, used_model = _generate_with_fallback([prompt, image])
        text = extract_response_text(response)
        data = safe_json_loads(text)
        if not data and ocr_text:
            logging.warning("Gorsel+prompt parse edilemedi, text-only fallback deneniyor.")
            return analyze_invoice_text_only(ocr_text, qr_list=qr_list)
        if not data:
            logging.warning("Image AI response parse edilemedi: %s", text[:1000])
            return None
        return {
            "Firma Adı": str(data.get("firma_adi", "")).strip(),
            "Evrak Tipi": str(data.get("evrak_tipi", "Fatura")).strip() or "Fatura",
            "Banka": "",
            "Tutar": normalize_amount(data.get("tutar", 0)),
            "Vade": normalize_date(data.get("vade", "")),
            "Açıklama": str(data.get("aciklama", "")).strip(),
            "Çeki veren": "",
            "Cirolu": "",
            "Asıl borçlu": "",
            "Kime verildi": "",
            "Evrak No": str(data.get("evrak_no", "")).strip(),
            "Döviz": normalize_currency(data.get("doviz", "TL")),
            "Durum": "Beklemede"
        }
    except Exception as e:
        logging.exception(e)
        return None
def analyze_invoice_text_only(ocr_text: str, qr_list: list[str] | None = None):
    """Fallback extraction when we can't render a PDF to image."""
    qr_list = qr_list or []
    prompt = f"""
Sen bir finans muhasebe asistanısın. Elinde sadece metin var (PDF içi metin/OCR).
QR_VERI: {qr_list}
OCR_METIN:
{ocr_text[:8000]}
Sadece geçerli bir JSON nesnesi döndür.
Açıklama, markdown, kod bloğu ekleme.
Şema:
{{
  "firma_adi": "",
  "evrak_tipi": "Fatura",
  "tutar": 0,
  "vade": "DD.MM.YYYY",
  "aciklama": "",
  "evrak_no": "",
  "doviz": "TL"
}}
Notlar:
- vade yoksa fatura tarihini vade olarak yaz.
- tutarı KDV dahil toplam ödenecek tutar olarak yakala.
- dövizi bulamazsan TL yaz.
- evrak_no: fatura no.
- Eğer bir alan bulunamazsa boş string döndür. Tahmin uydurma.
"""
    try:
        response, used_model = _generate_with_fallback([prompt])
        text = extract_response_text(response)
        data = safe_json_loads(text)
        if not data:
            logging.warning("Text-only AI response parse edilemedi: %s", text[:1000])
            return None
        return {
            "Firma Adı": str(data.get("firma_adi", "")).strip(),
            "Evrak Tipi": str(data.get("evrak_tipi", "Fatura")).strip() or "Fatura",
            "Banka": "",
            "Tutar": normalize_amount(data.get("tutar", 0)),
            "Vade": normalize_date(data.get("vade", "")),
            "Açıklama": str(data.get("aciklama", "")).strip(),
            "Çeki veren": "",
            "Cirolu": "",
            "Asıl borçlu": "",
            "Kime verildi": "",
            "Evrak No": str(data.get("evrak_no", "")).strip(),
            "Döviz": normalize_currency(data.get("doviz", "TL")),
            "Durum": "Beklemede"
        }
    except Exception as e:
        logging.exception(e)
        return None
def archive_invoice(image: Image.Image) -> str:
    os.makedirs("invoices", exist_ok=True)
    fname = datetime.now().strftime("%Y%m%d_%H%M%S") + ".png"
    path = os.path.join("invoices", fname)
    image.save(path)
    return path
# -------------------------
# TEMPLATE EXCEL (Sayfa1 schema)
# -------------------------
def make_template_xlsx() -> bytes:
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        pd.DataFrame(columns=CANON_COLS).to_excel(writer, index=False, sheet_name=WORKSHEET_NAME)
        # küçük yönlendirme sayfası
        tips = pd.DataFrame({
            "Notlar": [
                "Bu dosyayı indirip doldurun.",
                "Sonra İşlem Merkezi > Excel Upload bölümünden yükleyin.",
                "Belge tarihi formatı: 05.03.2026 (DD.MM.YYYY).",
                "Para birimi: TL / USD / EUR gibi.",
                "Ödeme durumu: Beklemede / Ödendi."
            ]
        })
        tips.to_excel(writer, index=False, sheet_name="README")
    return bio.getvalue()
def read_template_xlsx(uploaded_file) -> pd.DataFrame:
    xls = pd.ExcelFile(uploaded_file)
    sheet = WORKSHEET_NAME if WORKSHEET_NAME in xls.sheet_names else xls.sheet_names[0]
    dfu = pd.read_excel(xls, sheet)
    return normalize_sheet(dfu)
# -------------------------
# UI HELPERS
# -------------------------
def kpi(label, value, delta=None, help_text=None):
    """KPI kutusu: tek markdown ile render (HTML wrapper sorunlarını önler)."""
    caption = label if not help_text else f"{label} · {help_text}"
    delta_html = f"<div class='muted' style='margin-top:6px'>{delta}</div>" if delta is not None else ""
    st.markdown(
        f"""
        <div class="kpi">
          <div class="kpi-cap">{caption}</div>
          <div class="kpi-val">{value}</div>
          {delta_html}
        </div>
        """,
        unsafe_allow_html=True
    )
def card_header(title: str, badge: str | None = None, subtitle: str | None = None):
    """Kart başlığı: tek render (duplicate yok)."""
    badge_html = f"<span class='badge'>{badge}</span>" if badge else ""
    subtitle_html = f"<div class='muted' style='margin-top:6px'>{subtitle}</div>" if subtitle else ""
    line_html = "<div class='accent-line'></div>" if subtitle else ""
    st.markdown(
        f"""
        <div class="card-head">
          <div style="display:flex;align-items:center;justify-content:space-between;gap:10px">
            <h3 style="margin:0;font-size:20px">{title}</h3>
            {badge_html}
          </div>
          {subtitle_html}
          {line_html}
        </div>
        """,
        unsafe_allow_html=True
    )
def _build_href(**updates) -> str:
    """Build a relative href keeping existing query params (theme, etc.)."""
    params = _get_query_params()
    # flatten possible list values (older API)
    flat = {}
    for k, v in params.items():
        if isinstance(v, (list, tuple)):
            flat[k] = v[0] if v else ""
        else:
            flat[k] = v
    flat.update({k: v for k, v in updates.items() if v is not None})
    # drop empties
    flat = {k: str(v) for k, v in flat.items() if v is not None and str(v) != ""}
    qs = urlencode(flat)
    return f"?{qs}" if qs else ""
# -------------------------
# SIDEBAR (menu + settings)
# -------------------------
# -------------------------
with st.sidebar:
    st.markdown("### 🏦 Finans")
    # Theme toggle
    theme_choice = st.radio(
        "",
        ["☀️ Light", "🌙 Dark"],
        horizontal=True,
        label_visibility="collapsed",
        index=0 if st.session_state.theme_mode == "Light" else 1,
        key="theme_choice_radio",
    )
    theme_choice_clean = "Light" if theme_choice.startswith("☀️") else "Dark"
    if theme_choice_clean != st.session_state.theme_mode:
        st.session_state.theme_mode = theme_choice_clean
        _set_query_params(theme="dark" if theme_choice_clean == "Dark" else "light")
        st.rerun()
    inject_theme_css(st.session_state.theme_mode)
    with st.container(border=True):
        st.markdown("<div class='flow-panel-marker'></div>", unsafe_allow_html=True)
        st.markdown(f"**Kullanıcı:** Kurter  \\n**Yetki:** {ROLE}")
    menu = st.radio(
        "",
        ["Dashboard", "İşlem Merkezi", "AI Evrak Analizi", "AI CFO Chat"],
        label_visibility="collapsed",
        key="menu_radio",
    )
    with st.expander("Ayarlar", expanded=False):
        adat_rate = st.number_input("Adat Faizi %", value=39.75) / 100
    st.divider()
    if st.button("🧹 Cache temizle"):
        st.cache_data.clear()
        st.success("Cache temizlendi.")
        st.rerun()
# -------------------------
# LOAD DATA
# -------------------------
df = load_data()
usd, eur = get_fx()
dfx = compute_tl(df, usd, eur)
with st.sidebar:
    with st.expander("🛠️ Google Sheets Debug"):
        st.write("Okunan satır sayısı:", len(df) if df is not None else 0)
        st.write("Kolonlar:", list(df.columns) if df is not None and not df.empty else [])
        st.code(st.session_state.get("_gsheets_last_error", "Yok"))
# -------------------------
# DASHBOARD
# -------------------------
if menu == "Dashboard":
    st.title("📊 Finans Dashboard")
    st.markdown("<div class='muted'>Nakit riskini ve vade dağılımını hızlı gör.</div>", unsafe_allow_html=True)
    st.markdown("<div class='accent-line'></div>", unsafe_allow_html=True)
    if df.empty:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.warning("Google Sheets verisi okunamadı veya boş. Sheet paylaşımı ve secrets formatını kontrol edin.")
        st.markdown("</div>", unsafe_allow_html=True)
        st.stop()
    # ---- Filter Bar
    st.markdown("<div class='card-soft'>", unsafe_allow_html=True)
    f1, f2, f3, f4, f5 = st.columns([1.4, 1, 1, 1, 1])
    with f1:
        search = st.text_input("🔎 Firma ara", placeholder="örn: X FİRMASI")
    with f2:
        only_open = st.selectbox("Durum", ["Hepsi", "Beklemede", "Ödendi", "Takas"], index=0)
    with f3:
        currency_view = st.selectbox("Gösterim", ["TL", "Orijinal"], index=0)
    with f4:
        horizon = st.selectbox("Vade Ufku", ["Hepsi", "Geciken", "0-7", "8-30", "31-90", "90+"], index=0)
    with f5:
        base_cash = st.number_input("Başlangıç Nakit (₺)", value=0.0, step=10000.0)
    st.markdown("</div>", unsafe_allow_html=True)
    data = dfx.copy()
    if search.strip():
        data = data[data["firma_adi"].astype(str).str.contains(search, case=False, na=False)]
    if only_open != "Hepsi":
        data = data[data["odeme_durumu"].astype(str).str.strip().str.lower() == only_open.lower()]
    today = pd.Timestamp(datetime.now().date())
    data["days_to_due"] = (data["Belge_Date"] - today).dt.days
    d = data["days_to_due"].fillna(10**9)
    if horizon == "Geciken":
        data = data[d < 0]
    elif horizon == "0-7":
        data = data[(d >= 0) & (d <= 7)]
    elif horizon == "8-30":
        data = data[(d >= 8) & (d <= 30)]
    elif horizon == "31-90":
        data = data[(d >= 31) & (d <= 90)]
    elif horizon == "90+":
        data = data[d >= 91]
    if currency_view == "TL":
        amt_col = "Tutar_TL"
        suffix = "₺"
    else:
        amt_col = "genel_toplam"
        suffix = ""
    valid = data[data["Belge_Date"].notnull()].copy()
    valid["days_to_due"] = (valid["Belge_Date"] - today).dt.days
    total = float(valid[amt_col].sum()) if not valid.empty else 0.0
    overdue = float(valid.loc[valid["days_to_due"] < 0, amt_col].sum()) if not valid.empty else 0.0
    due7 = float(valid.loc[(valid["days_to_due"] >= 0) & (valid["days_to_due"] <= 7), amt_col].sum()) if not valid.empty else 0.0
    due30 = float(valid.loc[(valid["days_to_due"] > 7) & (valid["days_to_due"] <= 30), amt_col].sum()) if not valid.empty else 0.0
    if not valid.empty and float(valid[amt_col].sum()) > 0:
        weighted = float((valid[amt_col] * valid["days_to_due"]).sum())
        avg_days = weighted / float(valid[amt_col].sum())
        avg_date = today + timedelta(days=int(avg_days))
        adat_cost = (weighted * adat_rate) / 365
    else:
        avg_date = today
        adat_cost = 0.0
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    with k1: kpi("Toplam Borç", f"{total:,.0f} {suffix}", help_text="Vade tarihli kayıtlar")
    with k2: kpi("🔴 Geciken", f"{overdue:,.0f} {suffix}")
    with k3: kpi("🟠 0-7 gün", f"{due7:,.0f} {suffix}")
    with k4: kpi("🟡 8-30 gün", f"{due30:,.0f} {suffix}")
    with k5: kpi("⏳ Ortalama Vade", avg_date.strftime("%d.%m.%Y"))
    with k6: kpi("💸 Adat Yükü", f"{adat_cost:,.0f} ₺", help_text=f"Faiz %{adat_rate*100:.2f}")
    st.markdown("---")
    left, right = st.columns([1.35, 1])
    with left:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        card_header("📅 Ödeme Takvimi", badge="Vade bazlı", subtitle="Yaklaşan ödemeleri tek bakışta gör.")
        if valid.empty:
            st.info("Vade tarihi olan kayıt yok.")
        else:
            pay = valid.groupby("Belge_Date")[amt_col].sum().reset_index()
            fig = px.bar(pay, x="Belge_Date", y=amt_col)
            st.plotly_chart(fig, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
    with right:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        card_header("🧨 Risk Dağılımı", badge="Segment", subtitle="Geciken / yaklaşan / ileri vadeler.")
        if valid.empty:
            st.info("Risk dağılımı için veri yok.")
        else:
            bins = pd.cut(
                valid["days_to_due"],
                bins=[-10**6, -1, 7, 30, 90, 10**6],
                labels=["Geciken", "0-7", "8-30", "31-90", "90+"]
            )
            risk = valid.groupby(bins)[amt_col].sum().reset_index()
            risk.columns = ["Risk", "Tutar"]
            fig2 = px.pie(risk, names="Risk", values="Tutar", hole=0.55)
            st.plotly_chart(fig2, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("---")
    a, b = st.columns([1, 1])
    with a:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        card_header("🏢 İlk 10 Firma", badge="Top", subtitle="Toplam tutara göre sıralı.")
        if valid.empty:
            st.info("Veri yok.")
        else:
            top = valid.groupby("firma_adi")[amt_col].sum().sort_values(ascending=False).head(10).reset_index()
            fig3 = px.bar(top, x="firma_adi", y=amt_col)
            st.plotly_chart(fig3, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
    with b:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        card_header("📉 Nakit Akışı (30/60/90)", badge="Projeksiyon", subtitle="Vade bazlı toplam çıkış ve bakiye.")
        if valid.empty:
            st.info("Projeksiyon için vade tarihi olan kayıt yok.")
        else:
            proj = compute_tl(valid, usd, eur)
            proj = proj[proj["Belge_Date"].notnull()].copy()
            proj = proj.groupby("Belge_Date")["Tutar_TL"].sum().reset_index()
            proj = proj.sort_values("Belge_Date")
            end = today + timedelta(days=90)
            days = pd.date_range(today, end, freq="D")
            timeline = pd.DataFrame({"date": days})
            proj = proj.rename(columns={"Belge_Date": "date", "Tutar_TL": "outflow"})
            timeline = timeline.merge(proj, on="date", how="left").fillna({"outflow": 0.0})
            timeline["balance"] = float(base_cash) - timeline["outflow"].cumsum()
            balance_map = timeline.set_index("date")["balance"].to_dict()
            bal30 = float(balance_map.get(today + timedelta(days=30), timeline["balance"].iloc[-1] if not timeline.empty else float(base_cash)))
            bal60 = float(balance_map.get(today + timedelta(days=60), timeline["balance"].iloc[-1] if not timeline.empty else float(base_cash)))
            bal90 = float(balance_map.get(today + timedelta(days=90), timeline["balance"].iloc[-1] if not timeline.empty else float(base_cash)))
            m1, m2, m3 = st.columns(3)
            m1.metric("30 gün", f"{bal30:,.0f} ₺")
            m2.metric("60 gün", f"{bal60:,.0f} ₺")
            m3.metric("90 gün", f"{bal90:,.0f} ₺")
            fig4 = px.line(timeline, x="date", y="balance")
            st.plotly_chart(fig4, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("---")
    c1, c2 = st.columns([1.25, 1])
    with c1:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        card_header("⚠️ En Riskli Kalemler", badge="Öncelik", subtitle="Gecikene en yakın 15 kayıt.")
        if valid.empty:
            st.info("Riskli kalem yok.")
        else:
            risk_table = valid.sort_values("days_to_due").head(15)
            show_cols = ["firma_adi", "evrak_tipi", "belge_tarihi", "days_to_due", "Tutar_TL", "para_birimi", "odeme_durumu", "evrak_no", "aciklama"]
            st.dataframe(risk_table[show_cols], use_container_width=True, height=420)
        st.markdown("</div>", unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        card_header("🧠 AI CFO", badge="Analiz", subtitle="Filtreleri ayarladıktan sonra çalıştır.")
        if st.button("🧠 AI CFO Analizi Yap", use_container_width=True):
            with st.spinner("AI analiz ediyor..."):
                sample = compute_tl(data, usd, eur).head(80).to_dict()
                prompt = f"""
Sen deneyimli bir CFO'sun.
Aşağıdaki borç tablosunu analiz et ve kısa/öz Türkçe rapor üret:
- Özet risk (geciken, 0-7, 8-30, 31-90, 90+)
- Öncelikli ödeme listesi (ilk 5)
- Nakit yönetimi önerisi
- Faiz/adat etkisi (faiz {adat_rate*100:.2f}%)
VERİ:
{sample}
"""
                try:
                    resp = model.generate_content(prompt)
                    st.markdown(resp.text)
                except Exception as e:
                    st.error(f"AI hata: {e}")
        st.markdown("</div>", unsafe_allow_html=True)
# -------------------------
# İŞLEM MERKEZİ (4 kutu)
# -------------------------
elif menu == "İşlem Merkezi":
    # --- Hero header ---
    st.markdown(
        """
        <div class="hero">
          <div>
            <h1>İşlem Merkezi</h1>
            
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )
    # --- Flow selector (NO navigation; stays in same Streamlit session) ---
    flow_defs = [
        ("template", "📄  Şablon indir", "Şablon", "Excel’i indir, offline doldur."),
        ("upload",    "⬆️  Upload & işle", "Import", "Yükle, önizle, Sheets’e aktar."),
        ("sheets",    "🟩  Sheets’te devam", "Live", "Google Sheets’i aynı sekmede aç."),
        ("scan",      "📷  Tara & ekle", "AI+OCR", "PDF/Foto → alan çıkar → Sheets."),
    ]
    # Map internal flow keys to numbered titles used in the panel header/description
    flow_map = {
        "template": "1) Şablon indir",
        "upload": "2) Upload & işle",
        "sheets": "3) Sheets’te devam",
        "scan": "4) Tara & ekle",
    }
    # Persist selection in session_state (default = upload if user came from elsewhere)
    if "op_flow" not in st.session_state:
        st.session_state.op_flow = "upload"
    # Horizontal radio styled as big cards via CSS (.flow-radio label)
    flow_labels = [d[1] for d in flow_defs]
    flow_keys   = [d[0] for d in flow_defs]
    default_idx = flow_keys.index(st.session_state.op_flow) if st.session_state.op_flow in flow_keys else 0
    picked_label = st.radio(
        "",
        flow_labels,
        index=default_idx,
        horizontal=True,
        label_visibility="collapsed",
        key="flow_radio_pick",
    )
    picked_key = flow_keys[flow_labels.index(picked_label)]
    if picked_key != st.session_state.op_flow:
        st.session_state.op_flow = picked_key
        st.session_state._scroll_flow_panel = True
    step = flow_map.get(st.session_state.op_flow, "2) Upload & işle")
    step_desc = {
        "1) Şablon indir": "Excel şablonunu indir, offline doldur.",
        "2) Upload & işle": "Doldurduğun Excel’i yükle, önizle, Sheets’e aktar.",
        "3) Sheets’te devam": "Google Sheets’i aç, doğrudan orada düzenle.",
        "4) Tara & ekle": "PDF/Foto yükle → alanları çıkar → Sheets’e ekle (olmazsa manuel gir).",
    }
    st.markdown(f"<div class='muted' style='margin-top:0px;margin-bottom:12px'>{step_desc.get(step,'')}</div>", unsafe_allow_html=True)
    # Smooth scroll to panel when a flow is picked (no URL navigation; no new tab; no re-auth)
    if st.session_state.get("_scroll_flow_panel"):
        components.v1.html(
            """<script>
            (function(){
              try{
                const el = document.getElementById('flow-panel');
                if(el){ el.scrollIntoView({behavior:'smooth', block:'start'}); }
              }catch(e){}
            })();
            </script>""",
            height=0,
        )
        st.session_state._scroll_flow_panel = False
    # --- Content area ---
    st.markdown("<div id='flow-panel'></div>", unsafe_allow_html=True)
    with st.container(border=True):
        if step == "1) Şablon indir":
            card_header("Şablon indir", badge="Şablon", subtitle="Excel’i indir, offline doldur, sonra upload et.")
            st.download_button(
                "📥 Taslağı indir (.xlsx)",
                data=make_template_xlsx(),
                file_name="finans_sablon.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
            st.markdown("<div class='muted'>Sheet adı: <b>Sayfa1</b>. Kolonlar otomatik normalize edilir.</div>", unsafe_allow_html=True)
        elif step == "2) Upload & işle":
            card_header("Excel Upload → Google Sheets'e işle", badge="Import", subtitle="Yükle, önizle ve aktar.")
            up = st.file_uploader("Excel yükle (.xlsx)", type=["xlsx"], key="upl_xlsx")
            mode = st.selectbox("Aktarım modu", ["Ekle (append)", "Yerine yaz (overwrite)"], index=0)
            if up:
                try:
                    incoming = read_template_xlsx(up)
                    incoming_view = incoming.drop(columns=["Belge_Date"], errors="ignore")
                    st.markdown("<div class='muted'>Önizleme (ilk 20 satır):</div>", unsafe_allow_html=True)
                    st.dataframe(incoming_view.head(20), use_container_width=True, height=260)
                    nonblank = incoming.copy()
                    mask_blank = (
                        nonblank["firma_adi"].astype(str).str.strip().eq("") &
                        (pd.to_numeric(nonblank["genel_toplam"], errors="coerce").fillna(0) == 0) &
                        nonblank["belge_tarihi"].astype(str).str.strip().eq("")
                    )
                    nonblank = nonblank.loc[~mask_blank].copy()
                    st.markdown(
                        f"<div class='muted'>Yüklü satır: <b>{len(incoming)}</b> · Boş sayılan satır hariç: <b>{len(nonblank)}</b></div>",
                        unsafe_allow_html=True
                    )
                    if st.button("✅ Google Sheets'e aktar", use_container_width=True, key="btn_import"):
                        if mode.startswith("Yerine"):
                            out = normalize_sheet(nonblank.drop(columns=["Belge_Date"], errors="ignore"))
                        else:
                            base = df.copy().drop(columns=["Belge_Date"], errors="ignore")
                            out = pd.concat([base, nonblank.drop(columns=["Belge_Date"], errors="ignore")], ignore_index=True)
                            out = normalize_sheet(out)
                        ok, err = save_data(out)
                        if ok:
                            st.success("Aktarıldı ve kaydedildi.")
                            st.rerun()
                        else:
                            st.error(f"Kaydedilemedi: {err}")
                except Exception as e:
                    st.error(f"Excel okunamadı: {e}")
        elif step == "3) Sheets’te devam":
            card_header("Google Sheets'te devam et", badge="Live", subtitle="Sheet'i aç, doğrudan oradan düzenle.")
            sheets_url = get_sheets_url()
            if sheets_url:
                st.link_button("🔗 Google Sheets'i aç", sheets_url, use_container_width=True)
                st.markdown("<div class='muted'>Sheets'te düzenle — Dashboard otomatik yansır.</div>", unsafe_allow_html=True)
            else:
                st.warning("Sheets linki secrets içinde bulunamadı. `SHEETS_URL` ya da `connections.gsheets.spreadsheet` tanımlı olmalı.")
        else:
            card_header("Tarama → Otomatik Sheets'e ekle", badge="AI + OCR", subtitle="PDF/Foto yükle, AI alanları çıkarıp kaydetsin. Olmazsa manuel gir.")
            types = ["png", "jpg", "jpeg", "pdf"]  # pdf'yi her zaman kabul et
            scan_file = st.file_uploader("Evrak yükle (PDF/Resim)", type=types, key="scan_file")
            do_ocr = st.checkbox("OCR kullan (varsa)", value=False, disabled=not OCR_ENABLED, key="scan_ocr")
            archive = st.checkbox("Görseli arşivle", value=True, key="scan_archive")
            if scan_file and st.button("🧠 Tara & çıkar", use_container_width=True, key="btn_scan"):
                raw_image = None
                ocr_text = ""
                if scan_file.type == "application/pdf":
                    pdf_bytes = scan_file.read()
                    # 1) Eğer pdf2image varsa ilk sayfayı görsele çevir
                    if PDF_ENABLED:
                        try:
                            raw_image = pdf_first_page_to_image(pdf_bytes, dpi=350)
                        except Exception as e:
                            st.error(f"PDF görsele çevrilemedi: {e}")
                    # 2) pdf2image yoksa en azından metin çekmeye çalış (OCR/AI için)
                    if raw_image is None:
                        try:
                            import PyPDF2
                            reader = PyPDF2.PdfReader(BytesIO(pdf_bytes))
                            extracted = []
                            for p in reader.pages[:3]:
                                t = p.extract_text() or ""
                                if t.strip():
                                    extracted.append(t)
                            ocr_text = "\n".join(extracted)[:8000]
                            if not ocr_text.strip():
                                st.warning("PDF metni çıkarılamadı. Poppler (pdf2image) kurulu değilse tarama sınırlı olur.")
                        except Exception:
                            st.warning("PDF metni çıkarılamadı. Daha iyi tarama için poppler-utils (pdf2image) önerilir.")
                else:
                    try:
                        raw_image = Image.open(scan_file).convert("RGB")
                    except Exception as e:
                        st.error(f"Görsel açılamadı: {e}")
                if raw_image is not None:
                    image = enhance_for_reading(raw_image)
                    qr_list = decode_qr_opencv(raw_image) or decode_qr_opencv(image)
                    if do_ocr:
                        with st.spinner("OCR okunuyor..."):
                            ocr_text = (ocr_text + "\n" + ocr_read(image)).strip()
                    with st.spinner("AI alanları çıkarıyor..."):
                        result = analyze_invoice(image, ocr_text=ocr_text, qr_list=qr_list)
                    if result:
                        st.success("✅ Alanlar çıkarıldı. Kaydetmeden önce gözden geçir.")
                        st.session_state["_scan_result"] = result
                        st.session_state["_scan_image"] = image
                        st.session_state["_scan_ocr_text"] = ocr_text
                        st.session_state["_scan_source_name"] = getattr(scan_file, "name", "")
                    else:
                        st.warning("Tarama başarısız / düşük kalite. Aşağıdan manuel giriş yapabilirsin.")
                        st.session_state["_scan_result"] = None
                        st.session_state["_scan_image"] = None
                else:
                    # Görsel yok (PDF->image yok) ama metin varsa, metinle dene
                    if ocr_text.strip():
                        with st.spinner("AI (metin) alanları çıkarıyor..."):
                            result = analyze_invoice_text_only(ocr_text, qr_list=[])
                        if result:
                            st.success("✅ Alanlar çıkarıldı. Kaydetmeden önce gözden geçir.")
                            st.session_state["_scan_result"] = result
                            st.session_state["_scan_image"] = None
                            st.session_state["_scan_ocr_text"] = ocr_text
                            st.session_state["_scan_source_name"] = getattr(scan_file, "name", "")
                        else:
                            st.warning("Metinden alan çıkarılamadı. Manuel girişe geç.")
                    else:
                        st.warning("Tarama için görsel üretilemedi. Manuel girişe geç.")
            # Existing quick edit block stays as-is (below)
            result = st.session_state.get("_scan_result")
            image = st.session_state.get("_scan_image")
            if result:
                st.divider()
                st.markdown("<div class='muted'>Kaydetmeden önce bilgileri kontrol et:</div>", unsafe_allow_html=True)
                edited_result = render_invoice_review_form(result, key_prefix="scan_review")
                if st.button("💾 Sheets'e kaydet", use_container_width=True, key="btn_scan_save"):
                    source_name = st.session_state.get("_scan_source_name", getattr(scan_file, "name", ""))
                    scan_ocr_text = st.session_state.get("_scan_ocr_text", "")
                    new_row = build_invoice_record(edited_result, ocr_text=scan_ocr_text, source_name=source_name)
                    ok, err = save_single_record(new_row)
                    if ok:
                        if archive and image is not None:
                            path = archive_invoice(image)
                            st.info(f"Arşivlendi: {path}")
                        st.success("Kaydedildi.")
                        st.session_state["_scan_result"] = None
                        st.session_state["_scan_image"] = None
                        st.session_state["_scan_ocr_text"] = ""
                        st.session_state["_scan_source_name"] = ""
                        st.rerun()
                    else:
                        st.error(f"Kaydedilemedi: {err}")
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    with st.container(border=True):
        card_header("Manuel giriş (fallback)", badge="Form", subtitle="Tarama olmazsa veya hızlı eklemek istersen.")
        with st.expander("➕ Yeni kayıt ekle", expanded=False):
            c1, c2, c3 = st.columns(3)
            with c1:
                firma = st.text_input("Firma Adı", key="m_firma")
                evrak_tipi = st.selectbox("Evrak Tipi", ["Fatura", "e-Fatura", "e-Arşiv", "Diğer"], index=0, key="m_tip")
                evrak_no = st.text_input("Evrak No", key="m_no")
            with c2:
                belge_tarihi = st.text_input("Belge Tarihi (DD.MM.YYYY)", key="m_belge_tarihi")
                genel_toplam = st.number_input("Genel Toplam", value=0.0, step=100.0, key="m_genel_toplam")
                para_birimi = st.selectbox("Para Birimi", ["TL", "USD", "EUR"], index=0, key="m_para_birimi")
            with c3:
                vergi_kimlik_no = st.text_input("Vergi Kimlik No", key="m_vkn")
                kategori = st.text_input("Kategori", key="m_kategori")
                odeme_durumu = st.selectbox("Ödeme Durumu", ["Beklemede", "Ödendi"], index=0, key="m_odeme")
            aciklama = st.text_input("Açıklama", key="m_ack")
            if st.button("💾 Kaydet", use_container_width=True, key="m_save"):
                new_row = build_invoice_record({
                    "Firma Adı": firma,
                    "Evrak Tipi": evrak_tipi,
                    "Evrak No": evrak_no,
                    "Vade": belge_tarihi,
                    "Tutar": genel_toplam,
                    "Döviz": para_birimi,
                    "Vergi Kimlik No": vergi_kimlik_no,
                    "Kategori": kategori,
                    "Durum": odeme_durumu,
                    "Açıklama": aciklama,
                }, source_name="manuel_giris")
                ok, err = save_single_record(new_row)
                if ok:
                    st.success("Kayıt eklendi.")
                    st.rerun()
                else:
                    st.error(f"Kaydedilemedi: {err}")
        st.divider()
        st.subheader("📌 Mevcut Kayıtlar")
        st.dataframe(df.drop(columns=["Belge_Date"], errors="ignore"), use_container_width=True, height=420)
elif menu == "AI Evrak Analizi":
    st.title("📄 AI Evrak Analizi")
    st.markdown("<div class='muted'>Detaylı önizleme + OCR/QR + manuel düzeltme.</div>", unsafe_allow_html=True)
    st.markdown("<div class='accent-line'></div>", unsafe_allow_html=True)
    types = ["png", "jpg", "jpeg", "pdf"]
    tab_single, tab_bulk = st.tabs(["Tek Evrak", "Toplu Evrak"]) 
    with tab_single:
        uploaded = st.file_uploader("Fatura yükle", type=types, key="ai_single_uploader")
        if not uploaded:
            st.info("Analiz için bir PDF veya görsel yükle.")
        else:
            do_ocr = st.checkbox("OCR kullan (varsa)", value=False, disabled=not OCR_ENABLED, key="detail_ocr")
            archive = st.checkbox("Görseli arşivle", value=True, key="detail_archive")
            if st.button("🧠 AI ile Analiz Et", use_container_width=True, key="btn_detail_ai"):
                with st.spinner("Evrak işleniyor..."):
                    payload = process_uploaded_invoice(uploaded, do_ocr=do_ocr)
                st.session_state["_detail_payload"] = payload
            payload = st.session_state.get("_detail_payload") if st.session_state.get("_detail_payload", {}).get("source_name") == getattr(uploaded, "name", "") else None
            if payload:
                raw_image = payload.get("raw_image")
                image = payload.get("image")
                ocr_text = payload.get("ocr_text", "")
                qr_list = payload.get("qr_list", [])
                result = payload.get("result")
                c1, c2 = st.columns(2)
                with c1:
                    if raw_image is not None:
                        card_header("Orijinal", badge="Preview")
                        st.image(raw_image, use_container_width=True)
                with c2:
                    if image is not None:
                        card_header("İyileştirilmiş", badge="AI/OCR")
                        st.image(image, use_container_width=True)
                if qr_list:
                    st.success("✅ QR bulundu")
                    st.write(qr_list[0])
                if ocr_text.strip():
                    st.text_area("OCR Metni", ocr_text, height=180, key="detail_ocr_view")
                if not result:
                    st.error(payload.get("error", "AI veri çıkaramadı."))
                else:
                    st.success("AI veriyi çıkardı.")
                    st.json(result)
                    st.subheader("✍️ Kaydetmeden önce düzelt")
                    edited_result = render_invoice_review_form(result, key_prefix="detail_review")
                    if st.button("💾 Google Sheets'e Kaydet", use_container_width=True, key="btn_detail_save"):
                        new_row = build_invoice_record(edited_result, ocr_text=ocr_text, source_name=getattr(uploaded, "name", ""))
                        ok, err = save_single_record(new_row)
                        if ok:
                            if archive and image is not None:
                                path = archive_invoice(image)
                                st.info(f"Arşivlendi: {path}")
                            st.success("Kaydedildi.")
                            st.session_state.pop("_detail_payload", None)
                            st.rerun()
                        else:
                            st.error(f"Kaydedilemedi: {err}")
    with tab_bulk:
        st.markdown("<div class='muted'>E-arşiv / e-fatura portalından indirdiğin PDF'leri toplu seçip tek seferde işleyebilirsin.</div>", unsafe_allow_html=True)
        bulk_files = st.file_uploader("Toplu evrak yükle", type=types, accept_multiple_files=True, key="ai_bulk_uploader")
        bulk_ocr = st.checkbox("Toplu işlemde OCR kullan (varsa)", value=False, disabled=not OCR_ENABLED, key="bulk_ocr")
        if bulk_files and st.button("📦 Toplu analiz et ve kaydet", use_container_width=True, key="btn_bulk_save"):
            rows = []
            pending_records = []
            success_count = 0
            fail_count = 0
            progress = st.progress(0)
            for i, uf in enumerate(bulk_files, start=1):
                payload = process_uploaded_invoice(uf, do_ocr=bulk_ocr)
                result = payload.get("result")
                if result:
                    row = build_invoice_record(result, ocr_text=payload.get("ocr_text", ""), source_name=payload.get("source_name", ""))
                    pending_records.append(row)
                    rows.append({
                        "dosya": payload.get("source_name", ""),
                        "durum": "Hazır",
                        "firma": row.get("firma_adi", ""),
                        "tutar": row.get("genel_toplam", 0),
                        "tarih": row.get("belge_tarihi", ""),
                        "mesaj": "",
                    })
                else:
                    fail_count += 1
                    rows.append({
                        "dosya": payload.get("source_name", ""),
                        "durum": "Çözümlenemedi",
                        "firma": "",
                        "tutar": "",
                        "tarih": "",
                        "mesaj": payload.get("error", "Veri çıkarılamadı"),
                    })
                progress.progress(i / max(len(bulk_files), 1))
            if pending_records:
                ok, err = save_records_batch(pending_records)
                if ok:
                    success_count = len(pending_records)
                    for r in rows:
                        if r["durum"] == "Hazır":
                            r["durum"] = "Kaydedildi"
                else:
                    fail_count += len(pending_records)
                    for r in rows:
                        if r["durum"] == "Hazır":
                            r["durum"] = "Kaydedilemedi"
                            r["mesaj"] = err
            st.success(f"Toplu işlem bitti. Başarılı: {success_count} · Hatalı: {fail_count}")
            if rows:
                st.dataframe(pd.DataFrame(rows), use_container_width=True, height=320)
# -------------------------
# AI CFO CHAT
# -------------------------
elif menu == "AI CFO Chat":
    st.title("🧠 AI CFO Chat")
    st.markdown("<div class='muted'>Kısa ve net finans soruları sor. Cevaplar tablondan beslenir.</div>", unsafe_allow_html=True)
    st.markdown("<div class='accent-line'></div>", unsafe_allow_html=True)
    if df.empty:
        st.warning("Önce Google Sheets verisi okunmalı.")
        st.stop()
    st.markdown('<div class="card">', unsafe_allow_html=True)
    q = st.text_area("Soru", placeholder="örn: Önümüzdeki 30 gün nakit riskim nedir? En riskli firmalar hangileri?")
    if st.button("Sor", use_container_width=True) and q.strip():
        with st.spinner("AI düşünüyor..."):
            sample = compute_tl(df, usd, eur).head(120).to_dict()
            prompt = f"""
Sen CFO'sun. Kısa ve net Türkçe cevap ver.
Gerekirse madde madde yaz.
SORU:
{q}
VERİ (ilk 120 kayıt):
{sample}
"""
            try:
                resp = model.generate_content(prompt)
                st.markdown(resp.text)
            except Exception as e:
                st.error(f"AI hata: {e}")
    st.markdown("</div>", unsafe_allow_html=True)

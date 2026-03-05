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
from io import BytesIO

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

# -------------------------
# THEME (Light/Dark)
# -------------------------
if "theme_mode" not in st.session_state:
    st.session_state.theme_mode = "Dark"

def inject_theme_css(theme: str):
    """
    Streamlit'in yerleşik theme ayarları runtime'da değişmediği için,
    modern dashboard hissi veren iki ayrı CSS paletiyle görünümü iyileştiriyoruz.
    """
    if theme == "Light":
        bg = "#F7F7FB"
        card = "#FFFFFF"
        card2 = "#FFFFFF"
        text = "#0B1220"
        muted = "rgba(11,18,32,0.72)"
        border = "rgba(11,18,32,0.10)"
        shadow = "0 10px 30px rgba(16,24,40,0.10)"
        accent = "#2563EB"
        accent2 = "#7C3AED"
        kpi_bg = "linear-gradient(135deg, rgba(37,99,235,0.08), rgba(124,58,237,0.06))"
    else:
        bg = "#0B1020"
        card = "rgba(255,255,255,0.06)"
        card2 = "rgba(255,255,255,0.04)"
        text = "#E8ECF6"
        muted = "rgba(232,236,246,0.72)"
        border = "rgba(255,255,255,0.10)"
        shadow = "0 14px 40px rgba(0,0,0,0.35)"
        accent = "#60A5FA"
        accent2 = "#A78BFA"
        kpi_bg = "linear-gradient(135deg, rgba(96,165,250,0.14), rgba(167,139,250,0.10))"

    st.markdown(
        f"""
        <style>
        /* Page background */
        .stApp {{
            background: {bg};
            color: {text};
        }}

        /* Remove top padding a bit */
        .block-container {{
            padding-top: 1.15rem;
            padding-bottom: 2.2rem;
            max-width: 1350px;
        }}

        /* Sidebar polish */
        section[data-testid="stSidebar"] {{
            background: {card2};
            border-right: 1px solid {border};
        }}

        /* Typography */
        h1, h2, h3, h4, h5, h6, p, div, span, label {{
            color: {text};
        }}
        .muted {{
            color: {muted} !important;
            font-size: 0.92rem;
        }}

        /* Cards */
        .card {{
            background: {card};
            border: 1px solid {border};
            border-radius: 18px;
            padding: 14px 14px 12px 14px;
            box-shadow: {shadow};
        }}
        .card-soft {{
            background: {card2};
            border: 1px solid {border};
            border-radius: 18px;
            padding: 14px;
        }}

        .kpi {{
            background: {kpi_bg};
            border: 1px solid {border};
            border-radius: 18px;
            padding: 14px 14px 10px 14px;
            box-shadow: {shadow};
        }}

        .title-row {{
            display:flex; align-items:center; justify-content:space-between;
            gap: 10px; margin-bottom: 0.25rem;
        }}
        .badge {{
            display:inline-flex; align-items:center; gap: 6px;
            padding: 4px 10px;
            border-radius: 999px;
            border: 1px solid {border};
            background: rgba(255,255,255,0.04);
            color: {muted};
            font-size: 12px;
            white-space: nowrap;
        }}

        /* Buttons */
        .stButton > button {{
            border-radius: 14px !important;
            border: 1px solid {border} !important;
            padding: 0.6rem 0.85rem !important;
        }}
        .stDownloadButton > button {{
            border-radius: 14px !important;
            border: 1px solid {border} !important;
            padding: 0.6rem 0.85rem !important;
        }}

        /* Inputs */
        .stTextInput input, .stNumberInput input, .stDateInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] {{
            border-radius: 14px !important;
        }}

        /* Plotly card feel */
        .stPlotlyChart {{
            background: transparent !important;
        }}

        /* Subtle accent underline for headers */
        .accent-line {{
            height: 3px;
            width: 72px;
            background: linear-gradient(90deg, {accent}, {accent2});
            border-radius: 999px;
            margin-top: 6px;
            margin-bottom: 10px;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )

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
    "Firma Adı", "Evrak Tipi", "Banka", "Tutar", "Vade", "Açıklama", "Çeki veren",
    "Cirolu", "Asıl borçlu", "Kime verildi", "Evrak No", "Döviz", "Durum"
]

def normalize_sheet(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        out = pd.DataFrame(columns=CANON_COLS)
        out["Vade_Date"] = pd.NaT
        return out

    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    for c in CANON_COLS:
        if c not in df.columns:
            df[c] = ""

    df = df[CANON_COLS].copy()

    df["Tutar"] = pd.to_numeric(df["Tutar"], errors="coerce").fillna(0)
    df["Vade_Date"] = pd.to_datetime(df["Vade"], dayfirst=True, errors="coerce")

    df["Döviz"] = df["Döviz"].astype(str).str.strip().replace({"": "TL"}).fillna("TL")
    df["Durum"] = df["Durum"].astype(str).str.strip().replace({"": "Beklemede"}).fillna("Beklemede")
    return df

# -------------------------
# DATA LOAD / SAVE
# -------------------------
@st.cache_data(ttl=120)
def load_data():
    last_err = None

    def try_read(**kwargs):
        nonlocal last_err
        try:
            raw = conn.read(**kwargs)
            return raw, None
        except Exception as e:
            last_err = e
            return None, e

    raw, err = try_read()
    if raw is not None and not raw.empty:
        st.session_state["_gsheets_last_error"] = ""
        return normalize_sheet(raw)

    raw, err = try_read(worksheet=WORKSHEET_NAME)
    if raw is not None and not raw.empty:
        st.session_state["_gsheets_last_error"] = ""
        return normalize_sheet(raw)

    raw, err = try_read(worksheet="Sheet1")
    if raw is not None and not raw.empty:
        st.session_state["_gsheets_last_error"] = ""
        return normalize_sheet(raw)

    st.session_state["_gsheets_last_error"] = str(last_err) if last_err else "Boş veri döndü (Sheet boş olabilir)."
    return normalize_sheet(pd.DataFrame(columns=CANON_COLS))

def save_data(df: pd.DataFrame):
    try:
        conn.update(worksheet=WORKSHEET_NAME, data=df[CANON_COLS])
        st.cache_data.clear()
        return True, ""
    except Exception as e:
        logging.exception(e)
        return False, str(e)

# -------------------------
# FX RATES
# -------------------------
@st.cache_data(ttl=300)
def get_fx():
    try:
        usd = float(yf.download("USDTRY=X", period="1d", progress=False)["Close"].iloc[-1])
        eur = float(yf.download("EURTRY=X", period="1d", progress=False)["Close"].iloc[-1])
        return usd, eur
    except Exception as e:
        logging.error(e)
        return 34.90, 37.80

def compute_tl(df: pd.DataFrame, usd: float, eur: float) -> pd.DataFrame:
    dfx = df.copy()
    kur_map = {
        "USD": usd, "USDT": usd, "DOLAR": usd, "Dolar": usd, "Dolar ": usd,
        "EUR": eur, "EURO": eur, "Euro": eur, "Euro ": eur,
        "TL": 1, "TRY": 1, "₺": 1
    }
    dfx["kur"] = dfx["Döviz"].map(kur_map).fillna(1)
    dfx["Tutar_TL"] = pd.to_numeric(dfx["Tutar"], errors="coerce").fillna(0) * dfx["kur"]
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

def analyze_invoice(image: Image.Image, ocr_text: str = "", qr_list: list[str] | None = None):
    qr_list = qr_list or []
    prompt = f"""
Sen bir finans muhasebe asistanısın. Bu görsel bir fatura / e-fatura olabilir.

ELİNDE QR/ OCR varsa bunları mutlaka kullan:
QR_VERI: {qr_list}
OCR_METIN: {ocr_text[:4000]}

SADECE JSON döndür. Açıklama ekleme.

Şu şemaya uy:
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
"""

    try:
        response = model.generate_content([prompt, image])
        text = getattr(response, "text", "") or ""
        if not text and getattr(response, "candidates", None):
            text = response.candidates[0].content.parts[0].text

        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return None
        data = json.loads(m.group())

        firma = str(data.get("firma_adi", "")).strip()
        evrak_tipi = str(data.get("evrak_tipi", "Fatura")).strip() or "Fatura"
        doviz = str(data.get("doviz", "TL")).strip() or "TL"
        evrak_no = str(data.get("evrak_no", "")).strip()
        aciklama = str(data.get("aciklama", "")).strip()

        tutar = data.get("tutar", 0)
        try:
            tutar = float(str(tutar).replace(".", "").replace(",", "."))
        except Exception:
            tutar = 0.0

        vade = str(data.get("vade", "")).strip()
        if vade and "-" in vade and "." not in vade:
            vade = vade.replace("-", ".")
        if not vade:
            vade = datetime.now().strftime("%d.%m.%Y")

        return {
            "Firma Adı": firma,
            "Evrak Tipi": evrak_tipi,
            "Banka": "",
            "Tutar": tutar,
            "Vade": vade,
            "Açıklama": aciklama,
            "Çeki veren": "",
            "Cirolu": "",
            "Asıl borçlu": "",
            "Kime verildi": "",
            "Evrak No": evrak_no,
            "Döviz": doviz,
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
                "Vade formatı: 05.03.2026 (DD.MM.YYYY).",
                "Döviz: TL / USD / EUR gibi.",
                "Durum: Beklemede / Ödendi / Takas."
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
    st.markdown('<div class="kpi">', unsafe_allow_html=True)
    st.caption(label if not help_text else f"{label} · {help_text}")
    st.subheader(value)
    if delta is not None:
        st.markdown(f"<div class='muted'>{delta}</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

def card_header(title: str, badge: str | None = None, subtitle: str | None = None):
    st.markdown('<div class="title-row">', unsafe_allow_html=True)
    st.markdown(f"<h3 style='margin:0'>{title}</h3>", unsafe_allow_html=True)
    if badge:
        st.markdown(f"<span class='badge'>{badge}</span>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
    if subtitle:
        st.markdown(f"<div class='muted'>{subtitle}</div>", unsafe_allow_html=True)
        st.markdown("<div class='accent-line'></div>", unsafe_allow_html=True)

# -------------------------
# SIDEBAR (menu + settings)
# -------------------------
with st.sidebar:
    st.title("🏦 Finans Panel")

    # Theme toggle
    st.session_state.theme_mode = st.radio("Tema", ["Dark", "Light"], horizontal=True, index=0 if st.session_state.theme_mode == "Dark" else 1)
    inject_theme_css(st.session_state.theme_mode)

    st.markdown("<div class='card-soft'>", unsafe_allow_html=True)
    st.markdown(f"**Kullanıcı:** Kurter  \n**Yetki:** {ROLE}", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    menu = st.radio("Menü", ["Dashboard", "İşlem Merkezi", "AI Evrak Analizi", "AI CFO Chat"])
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
        data = data[data["Firma Adı"].astype(str).str.contains(search, case=False, na=False)]
    if only_open != "Hepsi":
        data = data[data["Durum"].astype(str).str.strip().str.lower() == only_open.lower()]

    today = pd.Timestamp(datetime.now().date())
    data["days_to_due"] = (data["Vade_Date"] - today).dt.days

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
        amt_col = "Tutar"
        suffix = ""

    valid = data[data["Vade_Date"].notnull()].copy()
    valid["days_to_due"] = (valid["Vade_Date"] - today).dt.days

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
            pay = valid.groupby("Vade_Date")[amt_col].sum().reset_index()
            fig = px.bar(pay, x="Vade_Date", y=amt_col)
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
            top = valid.groupby("Firma Adı")[amt_col].sum().sort_values(ascending=False).head(10).reset_index()
            fig3 = px.bar(top, x="Firma Adı", y=amt_col)
            st.plotly_chart(fig3, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with b:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        card_header("📉 Nakit Akışı (30/60/90)", badge="Projeksiyon", subtitle="Vade bazlı toplam çıkış ve bakiye.")
        if valid.empty:
            st.info("Projeksiyon için vade tarihi olan kayıt yok.")
        else:
            proj = compute_tl(valid, usd, eur)
            proj = proj[proj["Vade_Date"].notnull()].copy()
            proj = proj.groupby("Vade_Date")["Tutar_TL"].sum().reset_index()
            proj = proj.sort_values("Vade_Date")

            end = today + timedelta(days=90)
            days = pd.date_range(today, end, freq="D")
            timeline = pd.DataFrame({"date": days})

            proj = proj.rename(columns={"Vade_Date": "date", "Tutar_TL": "outflow"})
            timeline = timeline.merge(proj, on="date", how="left").fillna({"outflow": 0.0})
            timeline["balance"] = float(base_cash) - timeline["outflow"].cumsum()

            bal30 = timeline.loc[timeline["date"] == today + timedelta(days=30), "balance"].iloc[0]
            bal60 = timeline.loc[timeline["date"] == today + timedelta(days=60), "balance"].iloc[0]
            bal90 = timeline.loc[timeline["date"] == today + timedelta(days=90), "balance"].iloc[0]

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
            show_cols = ["Firma Adı", "Evrak Tipi", "Vade", "days_to_due", "Tutar_TL", "Döviz", "Durum", "Evrak No", "Açıklama"]
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
    st.title("🧾 İşlem Merkezi")
    st.markdown("<div class='muted'>4 farklı akış: Excel şablon → Upload → Sheets, doğrudan Sheets, tarama ile otomatik ekleme.</div>", unsafe_allow_html=True)
    st.markdown("<div class='accent-line'></div>", unsafe_allow_html=True)

    # 4 cards layout
    a, b = st.columns(2)
    c, d = st.columns(2)

    # ---- Kutu 1: Template Excel indir
    with a:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        card_header("1) Taslak Excel indir", badge="Şablon", subtitle="İndir, doldur, sonra upload et.")
        st.download_button(
            "📥 Taslağı indir (.xlsx)",
            data=make_template_xlsx(),
            file_name="finans_sablon.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
        st.markdown("<div class='muted'>Sheet adı: <b>Sayfa1</b>. Kolonlar otomatik normalize edilir.</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # ---- Kutu 2: Upload Excel -> Google Sheets
    with b:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        card_header("2) Excel Upload → Google Sheets'e işle", badge="Import", subtitle="Doldurduğun Excel'i yükle, önizle ve aktar.")
        up = st.file_uploader("Excel yükle (.xlsx)", type=["xlsx"], key="upl_xlsx")
        mode = st.selectbox("Aktarım modu", ["Ekle (append)", "Yerine yaz (overwrite)"], index=0)
        if up:
            try:
                incoming = read_template_xlsx(up)
                incoming_view = incoming.drop(columns=["Vade_Date"], errors="ignore")
                st.markdown("<div class='muted'>Önizleme (ilk 20 satır):</div>", unsafe_allow_html=True)
                st.dataframe(incoming_view.head(20), use_container_width=True, height=230)

                # filter blank rows
                nonblank = incoming.copy()
                # consider a row blank if Firma Adı and Tutar and Vade all empty/zero
                mask_blank = (
                    nonblank["Firma Adı"].astype(str).str.strip().eq("") &
                    (pd.to_numeric(nonblank["Tutar"], errors="coerce").fillna(0) == 0) &
                    nonblank["Vade"].astype(str).str.strip().eq("")
                )
                nonblank = nonblank.loc[~mask_blank].copy()

                st.markdown(f"<div class='muted'>Yüklü satır: <b>{len(incoming)}</b> · Boş sayılan satır hariç: <b>{len(nonblank)}</b></div>", unsafe_allow_html=True)

                if st.button("✅ Google Sheets'e aktar", use_container_width=True, key="btn_import"):
                    if mode.startswith("Yerine"):
                        out = nonblank.copy()
                    else:
                        base = df.copy().drop(columns=["Vade_Date"], errors="ignore")
                        out = pd.concat([base, nonblank.drop(columns=["Vade_Date"], errors="ignore")], ignore_index=True)
                        out = normalize_sheet(out)

                    ok, err = save_data(out)
                    if ok:
                        st.success("Aktarıldı ve kaydedildi.")
                        st.rerun()
                    else:
                        st.error(f"Kaydedilemedi: {err}")
            except Exception as e:
                st.error(f"Excel okunamadı: {e}")
        st.markdown("</div>", unsafe_allow_html=True)

    # ---- Kutu 3: Open Google Sheets
    with c:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        card_header("3) Google Sheets'te devam et", badge="Live", subtitle="Sheet'i aç, doğrudan oradan düzenle.")
        sheets_url = st.secrets.get("SHEETS_URL", "")
        if sheets_url:
            st.link_button("🔗 Google Sheets'i aç", sheets_url, use_container_width=True)
            st.markdown("<div class='muted'>İstersen Sheets'te düzenle, Dashboard otomatik yansır.</div>", unsafe_allow_html=True)
        else:
            st.warning("SHEETS_URL secrets içinde yok. Eklemek için: Streamlit → Settings → Secrets → SHEETS_URL")
        st.markdown("</div>", unsafe_allow_html=True)

    # ---- Kutu 4: Scan / auto add; fallback to manual form
    with d:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        card_header("4) Tarama → Otomatik Sheets'e ekle", badge="AI + OCR", subtitle="PDF/Foto yükle, AI alanları çıkarıp kaydetsin. Olmazsa manuel gir.")
        types = ["png", "jpg", "jpeg"]
        if PDF_ENABLED:
            types.append("pdf")
        scan_file = st.file_uploader("Evrak yükle (PDF/Resim)", type=types, key="scan_file")

        do_ocr = st.checkbox("OCR kullan (varsa)", value=False, disabled=not OCR_ENABLED, key="scan_ocr")
        archive = st.checkbox("Görseli arşivle", value=True, key="scan_archive")

        if scan_file and st.button("🧠 Tara & çıkar", use_container_width=True, key="btn_scan"):
            raw_image = None
            if scan_file.type == "application/pdf":
                if not PDF_ENABLED:
                    st.error("PDF desteği kapalı. packages.txt içine poppler-utils ekleyip Reboot edin.")
                else:
                    pdf_bytes = scan_file.read()
                    try:
                        raw_image = pdf_first_page_to_image(pdf_bytes, dpi=350)
                    except Exception as e:
                        st.error(f"PDF görsele çevrilemedi: {e}")
            else:
                try:
                    raw_image = Image.open(scan_file).convert("RGB")
                except Exception as e:
                    st.error(f"Görsel açılamadı: {e}")

            if raw_image is not None:
                image = enhance_for_reading(raw_image)
                qr_list = decode_qr_opencv(raw_image) or decode_qr_opencv(image)
                ocr_text = ""
                if do_ocr:
                    with st.spinner("OCR okunuyor..."):
                        ocr_text = ocr_read(image)

                with st.spinner("AI alanları çıkarıyor..."):
                    result = analyze_invoice(image, ocr_text=ocr_text, qr_list=qr_list)

                if result:
                    st.success("✅ Alanlar çıkarıldı. Kaydetmeden önce gözden geçir.")
                    st.session_state["_scan_result"] = result
                    st.session_state["_scan_image"] = image
                else:
                    st.warning("Tarama başarısız / düşük kalite. Aşağıdan manuel giriş yapabilirsin.")
                    st.session_state["_scan_result"] = None
                    st.session_state["_scan_image"] = None

        # If scan result exists, show quick editor + save
        result = st.session_state.get("_scan_result")
        image = st.session_state.get("_scan_image")
        if result:
            st.markdown("<hr/>", unsafe_allow_html=True)
            st.markdown("<div class='muted'>Hızlı düzeltme:</div>", unsafe_allow_html=True)

            e1, e2 = st.columns(2)
            with e1:
                result["Firma Adı"] = st.text_input("Firma Adı", value=result.get("Firma Adı", ""), key="sr_firma")
                result["Evrak Tipi"] = st.selectbox("Evrak Tipi", ["Fatura", "Çek", "Senet", "Diğer"], index=0, key="sr_tip")
                result["Döviz"] = st.text_input("Döviz", value=result.get("Döviz", "TL"), key="sr_doviz")
                result["Durum"] = st.selectbox("Durum", ["Beklemede", "Ödendi", "Takas"], index=0, key="sr_durum")
            with e2:
                result["Tutar"] = st.number_input("Tutar", value=float(result.get("Tutar", 0.0)), step=100.0, key="sr_tutar")
                result["Vade"] = st.text_input("Vade (DD.MM.YYYY)", value=result.get("Vade", datetime.now().strftime("%d.%m.%Y")), key="sr_vade")
                result["Evrak No"] = st.text_input("Evrak No", value=result.get("Evrak No", ""), key="sr_no")
                result["Açıklama"] = st.text_input("Açıklama", value=result.get("Açıklama", ""), key="sr_ack")

            if st.button("💾 Sheets'e kaydet", use_container_width=True, key="btn_scan_save"):
                df2 = df.copy().drop(columns=["Vade_Date"], errors="ignore")
                df2 = pd.concat([df2, pd.DataFrame([result])], ignore_index=True)
                df2 = normalize_sheet(df2)

                ok, err = save_data(df2)
                if ok:
                    if archive and image is not None:
                        path = archive_invoice(image)
                        st.info(f"Arşivlendi: {path}")
                    st.success("Kaydedildi.")
                    # clear scan state
                    st.session_state["_scan_result"] = None
                    st.session_state["_scan_image"] = None
                    st.rerun()
                else:
                    st.error(f"Kaydedilemedi: {err}")

        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("---")

    # Manual entry always available (fallback)
    st.markdown('<div class="card">', unsafe_allow_html=True)
    card_header("Manuel giriş (fallback)", badge="Form", subtitle="Tarama olmazsa veya hızlı eklemek istersen.")
    with st.expander("➕ Yeni kayıt ekle", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            firma = st.text_input("Firma Adı", key="m_firma")
            evrak_tipi = st.selectbox("Evrak Tipi", ["Çek", "Senet", "Fatura", "Diğer"], index=0, key="m_tip")
            banka = st.text_input("Banka", key="m_banka")
        with c2:
            tutar = st.number_input("Tutar", value=0.0, step=1000.0, key="m_tutar")
            doviz = st.selectbox("Döviz", ["TL", "USD", "EUR", "Dolar", "Euro"], index=0, key="m_doviz")
            vade = st.text_input("Vade (DD.MM.YYYY)", key="m_vade")
        with c3:
            aciklama = st.text_input("Açıklama", key="m_ack")
            evrak_no = st.text_input("Evrak No", key="m_no")
            durum = st.selectbox("Durum", ["Beklemede", "Ödendi", "Takas"], index=0, key="m_durum")
        with c4:
            ceki_veren = st.text_input("Çeki veren", key="m_ceki")
            cirolu = st.text_input("Cirolu", key="m_cirolu")
            asil_borclu = st.text_input("Asıl borçlu", key="m_asil")
            kime_verildi = st.text_input("Kime verildi", key="m_kime")

        if st.button("💾 Kaydet", use_container_width=True, key="m_save"):
            new_row = {
                "Firma Adı": firma,
                "Evrak Tipi": evrak_tipi,
                "Banka": banka,
                "Tutar": float(tutar),
                "Vade": vade,
                "Açıklama": aciklama,
                "Çeki veren": ceki_veren,
                "Cirolu": cirolu,
                "Asıl borçlu": asil_borclu,
                "Kime verildi": kime_verildi,
                "Evrak No": evrak_no,
                "Döviz": doviz,
                "Durum": durum
            }
            df2 = df.copy()
            df2 = pd.concat([df2.drop(columns=["Vade_Date"], errors="ignore"), pd.DataFrame([new_row])], ignore_index=True)
            df2 = normalize_sheet(df2)

            ok, err = save_data(df2)
            if ok:
                st.success("Kayıt eklendi.")
                st.rerun()
            else:
                st.error(f"Kaydedilemedi: {err}")

    st.divider()
    st.subheader("📌 Mevcut Kayıtlar")
    st.dataframe(df.drop(columns=["Vade_Date"], errors="ignore"), use_container_width=True, height=420)
    st.markdown("</div>", unsafe_allow_html=True)

# -------------------------
# AI EVRAK ANALİZİ (ayrı sayfa, detay)
# -------------------------
elif menu == "AI Evrak Analizi":
    st.title("📄 AI Evrak Analizi")
    st.markdown("<div class='muted'>Detaylı önizleme + OCR/QR + manuel düzeltme.</div>", unsafe_allow_html=True)
    st.markdown("<div class='accent-line'></div>", unsafe_allow_html=True)

    types = ["png", "jpg", "jpeg"]
    if PDF_ENABLED:
        types.append("pdf")

    uploaded = st.file_uploader("Fatura yükle", type=types)
    if not uploaded:
        st.info("Bir fatura yükleyin (PDF veya resim).")
        st.stop()

    raw_image = None
    if uploaded.type == "application/pdf":
        if not PDF_ENABLED:
            st.error("PDF desteği kapalı. packages.txt içine poppler-utils ekleyip Reboot edin.")
            st.stop()
        pdf_bytes = uploaded.read()
        try:
            raw_image = pdf_first_page_to_image(pdf_bytes, dpi=350)
        except Exception as e:
            st.error(f"PDF görsele çevrilemedi: {e}")
            st.stop()
    else:
        raw_image = Image.open(uploaded).convert("RGB")

    image = enhance_for_reading(raw_image)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        card_header("Orijinal", badge="Preview")
        st.image(raw_image, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        card_header("İyileştirilmiş", badge="AI/OCR")
        st.image(image, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    colA, colB, colC = st.columns([1, 1, 1])
    with colA:
        do_ocr = st.checkbox("OCR kullan (varsa)", value=False, disabled=not OCR_ENABLED)
    with colB:
        archive = st.checkbox("Görseli arşivle", value=True)
    with colC:
        st.markdown(f"<span class='badge'>Model: {MODEL_NAME}</span>", unsafe_allow_html=True)

    qr_list = decode_qr_opencv(raw_image) or decode_qr_opencv(image)
    if qr_list:
        st.success("✅ QR bulundu")
        st.write(qr_list[0])
    else:
        st.warning("QR bulunamadı (QR çok küçük/flu olabilir. PDF için DPI 350 iyi, gerekirse 400 yaparız).")

    ocr_text = ""
    if do_ocr:
        with st.spinner("OCR okunuyor..."):
            ocr_text = ocr_read(image)
        if ocr_text.strip():
            st.text_area("OCR Metni", ocr_text, height=180)
        else:
            st.info("OCR metni alınamadı (tesseract kurulu değil veya görsel uygun değil).")

    if st.button("🧠 AI ile Analiz Et", use_container_width=True):
        with st.spinner("AI analiz ediyor..."):
            result = analyze_invoice(image, ocr_text=ocr_text, qr_list=qr_list)

        if not result:
            st.error("AI veri çıkaramadı. DPI artırmayı (PDF: 400) veya daha net dosya denemeyi deneyin.")
            st.stop()

        st.success("AI veriyi çıkardı.")
        st.json(result)

        st.subheader("✍️ Kaydetmeden önce düzelt")
        e1, e2, e3, e4 = st.columns(4)
        with e1:
            result["Firma Adı"] = st.text_input("Firma Adı", value=result.get("Firma Adı", ""))
            result["Evrak Tipi"] = st.selectbox("Evrak Tipi", ["Fatura", "Çek", "Senet", "Diğer"], index=0)
            result["Döviz"] = st.text_input("Döviz", value=result.get("Döviz", "TL"))
        with e2:
            result["Tutar"] = st.number_input("Tutar", value=float(result.get("Tutar", 0.0)), step=100.0)
            result["Vade"] = st.text_input("Vade", value=result.get("Vade", datetime.now().strftime("%d.%m.%Y")))
            result["Durum"] = st.selectbox("Durum", ["Beklemede", "Ödendi", "Takas"], index=0)
        with e3:
            result["Evrak No"] = st.text_input("Evrak No", value=result.get("Evrak No", ""))
            result["Banka"] = st.text_input("Banka", value=result.get("Banka", ""))
            result["Açıklama"] = st.text_input("Açıklama", value=result.get("Açıklama", ""))
        with e4:
            result["Çeki veren"] = st.text_input("Çeki veren", value=result.get("Çeki veren", ""))
            result["Cirolu"] = st.text_input("Cirolu", value=result.get("Cirolu", ""))
            result["Asıl borçlu"] = st.text_input("Asıl borçlu", value=result.get("Asıl borçlu", ""))
            result["Kime verildi"] = st.text_input("Kime verildi", value=result.get("Kime verildi", ""))

        if st.button("💾 Google Sheets'e Kaydet", use_container_width=True):
            df2 = df.copy().drop(columns=["Vade_Date"], errors="ignore")
            df2 = pd.concat([df2, pd.DataFrame([result])], ignore_index=True)
            df2 = normalize_sheet(df2)

            ok, err = save_data(df2)
            if ok:
                if archive:
                    path = archive_invoice(image)
                    st.info(f"Arşivlendi: {path}")
                st.success("Kaydedildi.")
                st.rerun()
            else:
                st.error(f"Kaydedilemedi: {err}")
    st.markdown("</div>", unsafe_allow_html=True)

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

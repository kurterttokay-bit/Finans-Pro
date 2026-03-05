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
WORKSHEET_NAME = "Sayfa1"  # ekran görüntünde bu var

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
    col1, col2, col3 = st.columns([1, 1.3, 1])
    with col2:
        st.title(APP_TITLE)
        with st.form("login"):
            pwd = st.text_input("Şifre", type="password")
            submit = st.form_submit_button("Giriş")
            if submit:
                if pwd in ROLES:
                    st.session_state.auth = ROLES[pwd]
                    st.rerun()
                else:
                    st.error("Hatalı şifre")


if not st.session_state.auth:
    login()
    st.stop()

ROLE = st.session_state.auth

# -------------------------
# GEMINI CONFIG
# -------------------------
# secrets.toml: GEMINI_API_KEY = "..."
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")
if not GEMINI_API_KEY:
    st.error("GEMINI_API_KEY bulunamadı. Streamlit Secrets içine ekleyin.")
    st.stop()

genai.configure(api_key=GEMINI_API_KEY)

@st.cache_resource
def get_model_name():
    # kurulu ortamda model isimleri değişebiliyor; güvenli fallback
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
        return pd.DataFrame(columns=CANON_COLS)

    # strip columns
    df.columns = [str(c).strip() for c in df.columns]

    # add missing cols
    for c in CANON_COLS:
        if c not in df.columns:
            df[c] = ""

    # keep only canonical + extras (optional)
    df = df[CANON_COLS].copy()

    # types
    df["Tutar"] = pd.to_numeric(df["Tutar"], errors="coerce").fillna(0)

    # parse vade date helper
    df["Vade_Date"] = pd.to_datetime(df["Vade"], dayfirst=True, errors="coerce")

    # currency normalization
    df["Döviz"] = df["Döviz"].astype(str).str.strip().replace({"": "TL"}).fillna("TL")

    # status
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

    # 1) default (worksheet belirtmeden)
    raw, err = try_read()
    if raw is not None and not raw.empty:
        st.session_state["_gsheets_last_error"] = ""
        return normalize_sheet(raw)

    # 2) Sayfa1 dene
    raw, err = try_read(worksheet="Sayfa1")
    if raw is not None and not raw.empty:
        st.session_state["_gsheets_last_error"] = ""
        return normalize_sheet(raw)

    # 3) Sheet1 dene
    raw, err = try_read(worksheet="Sheet1")
    if raw is not None and not raw.empty:
        st.session_state["_gsheets_last_error"] = ""
        return normalize_sheet(raw)

    # 4) Hepsi başarısız → hata mesajını sakla
    st.session_state["_gsheets_last_error"] = str(last_err) if last_err else "Boş veri döndü (Sheet boş olabilir)."
    return normalize_sheet(pd.DataFrame(columns=CANON_COLS))


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
    # dpi yükselt: 300-400 arası e-fatura için çok fark eder
    pages = convert_from_bytes(pdf_bytes, dpi=dpi, fmt="png")
    return pages[0].convert("RGB")

def enhance_for_reading(img: Image.Image) -> Image.Image:
    # daha net okuma için: grayscale + kontrast + sharp
    g = ImageOps.grayscale(img)
    g = ImageEnhance.Contrast(g).enhance(1.8)
    g = ImageEnhance.Sharpness(g).enhance(2.0)
    # hafif filtre
    g = g.filter(ImageFilter.MedianFilter(size=3))
    return g.convert("RGB")

def decode_qr(img: Image.Image) -> list[str]:
    # QR decode için pyzbar + opencv
    try:
        import cv2
        import numpy as np
        from pyzbar.pyzbar import decode as zdecode

        arr = np.array(img.convert("RGB"))
        bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

        # bazen küçük QR için büyütme işe yarar
        bgr = cv2.resize(bgr, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)

        codes = zdecode(bgr)
        out = []
        for c in codes:
            try:
                out.append(c.data.decode("utf-8", errors="ignore"))
            except Exception:
                pass
        return out
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

        # sanitize
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
        # allow "10-01-2026"
        if vade and "-" in vade and "." not in vade:
            vade = vade.replace("-", ".")
        # fallback: today
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
# PROFESSIONAL DASHBOARD UI HELPERS
# -------------------------
def inject_css():
    st.markdown(
        """
        <style>
        .block-container { padding-top: 1.2rem; padding-bottom: 2rem; }
        .kpi {
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 18px;
            padding: 14px 14px 10px 14px;
        }
        .panel {
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 18px;
            padding: 14px;
        }
        .muted { opacity: .75; font-size: .92rem; }
        .title-row {
            display:flex; align-items:center; justify-content:space-between;
            gap: 8px; margin-bottom: 0.35rem;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

def kpi(label, value, delta=None, help_text=None):
    with st.container():
        st.markdown('<div class="kpi">', unsafe_allow_html=True)
        st.caption(label if not help_text else f"{label} · {help_text}")
        st.subheader(value)
        if delta is not None:
            st.markdown(f"<div class='muted'>{delta}</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)


# -------------------------
# SIDEBAR (menu + adat + cache)
# -------------------------
with st.sidebar:
    st.title("🏦 Finans Panel")
    st.info(f"Kullanıcı: Kurter\nYetki: {ROLE}")

    menu = st.radio("Menü", ["Dashboard", "İşlem Merkezi", "AI Evrak Analizi", "AI CFO Chat"])
    adat_rate = st.number_input("Adat Faizi %", value=39.75) / 100

    st.divider()

    if st.button("🧹 Cache temizle"):
        st.cache_data.clear()
        st.success("Cache temizlendi.")
        st.rerun()

# -------------------------
# LOAD
# -------------------------
df = load_data()
def save_data(df: pd.DataFrame):
    try:
        # yalnız canonical kolonları yaz
        conn.update(worksheet="Sayfa1", data=df[CANON_COLS])
        st.cache_data.clear()
        return True, ""
    except Exception as e:
        logging.exception(e)
        return False, str(e)
usd, eur = get_fx()
dfx = compute_tl(df, usd, eur)
# ---- Debug (df tanımlandıktan sonra)
with st.sidebar:
    with st.expander("🛠️ Google Sheets Debug"):
        st.write("Okunan satır sayısı:", len(df) if df is not None else 0)
        st.write("Kolonlar:", list(df.columns) if df is not None and not df.empty else [])
        st.code(st.session_state.get("_gsheets_last_error", "Yok"))
# -------------------------
# DASHBOARD (PRO)
# -------------------------
if menu == "Dashboard":
    inject_css()
    st.title("📊 Finans Dashboard")

    if df.empty:
        st.warning(
            "Google Sheets verisi okunamadı veya boş. "
            "Sheet paylaşımı ve secrets formatını kontrol edin."
        )
        st.stop()

    # ---- Filter Bar
    with st.container():
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

    data = dfx.copy()

    # search
    if search.strip():
        data = data[data["Firma Adı"].astype(str).str.contains(search, case=False, na=False)]

    # status filter
    if only_open != "Hepsi":
        data = data[data["Durum"].astype(str).str.strip().str.lower() == only_open.lower()]

    # vade helper
    today = pd.Timestamp(datetime.now().date())
    data["days_to_due"] = (data["Vade_Date"] - today).dt.days

    # horizon filter
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

    # amount column for display
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

    # avg vade + adat
    if not valid.empty and float(valid[amt_col].sum()) > 0:
        weighted = float((valid[amt_col] * valid["days_to_due"]).sum())
        avg_days = weighted / float(valid[amt_col].sum())
        avg_date = today + timedelta(days=int(avg_days))
        adat_cost = (weighted * adat_rate) / 365
    else:
        avg_date = today
        adat_cost = 0.0

    # ---- KPI row
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    with k1: kpi("Toplam Borç", f"{total:,.0f} {suffix}", help_text="Vade tarihli kayıtlar")
    with k2: kpi("🔴 Geciken", f"{overdue:,.0f} {suffix}")
    with k3: kpi("🟠 0-7 gün", f"{due7:,.0f} {suffix}")
    with k4: kpi("🟡 8-30 gün", f"{due30:,.0f} {suffix}")
    with k5: kpi("⏳ Ortalama Vade", avg_date.strftime("%d.%m.%Y"))
    with k6: kpi("💸 Adat Yükü", f"{adat_cost:,.0f} ₺", help_text=f"Faiz %{adat_rate*100:.2f}")

    st.markdown("---")

    # ---- Layout
    left, right = st.columns([1.35, 1])

    with left:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown('<div class="title-row"><h3 style="margin:0">📅 Ödeme Takvimi</h3></div>', unsafe_allow_html=True)

        if valid.empty:
            st.info("Vade tarihi olan kayıt yok.")
        else:
            pay = valid.groupby("Vade_Date")[amt_col].sum().reset_index()
            fig = px.bar(pay, x="Vade_Date", y=amt_col)
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown('<div class="title-row"><h3 style="margin:0">🧨 Risk Dağılımı</h3></div>', unsafe_allow_html=True)

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
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown('<div class="title-row"><h3 style="margin:0">🏢 İlk 10 Firma</h3></div>', unsafe_allow_html=True)

        if valid.empty:
            st.info("Veri yok.")
        else:
            top = valid.groupby("Firma Adı")[amt_col].sum().sort_values(ascending=False).head(10).reset_index()
            fig3 = px.bar(top, x="Firma Adı", y=amt_col)
            st.plotly_chart(fig3, use_container_width=True)

        st.markdown("</div>", unsafe_allow_html=True)

    with b:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown('<div class="title-row"><h3 style="margin:0">📉 Nakit Akışı (30/60/90)</h3></div>', unsafe_allow_html=True)
        if valid.empty:
            st.info("Projeksiyon için vade tarihi olan kayıt yok.")
        else:
            # TL bazlı projeksiyon en mantıklısı
            proj = compute_tl(valid, usd, eur)
            proj = proj[proj["Vade_Date"].notnull()].copy()
            proj = proj.groupby("Vade_Date")["Tutar_TL"].sum().reset_index()
            proj = proj.sort_values("Vade_Date")

            # create daily timeline up to 90 days
            end = today + timedelta(days=90)
            days = pd.date_range(today, end, freq="D")
            timeline = pd.DataFrame({"date": days})

            proj = proj.rename(columns={"Vade_Date": "date", "Tutar_TL": "outflow"})
            timeline = timeline.merge(proj, on="date", how="left").fillna({"outflow": 0.0})
            timeline["balance"] = float(base_cash) - timeline["outflow"].cumsum()

            # markers at 30/60/90
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
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown('<div class="title-row"><h3 style="margin:0">⚠️ En Riskli Kalemler</h3></div>', unsafe_allow_html=True)

        if valid.empty:
            st.info("Riskli kalem yok.")
        else:
            risk_table = valid.sort_values("days_to_due").head(15)
            show_cols = ["Firma Adı", "Evrak Tipi", "Vade", "days_to_due", "Tutar_TL", "Döviz", "Durum", "Evrak No", "Açıklama"]
            st.dataframe(risk_table[show_cols], use_container_width=True, height=420)

        st.markdown("</div>", unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown('<div class="title-row"><h3 style="margin:0">🧠 AI CFO</h3></div>', unsafe_allow_html=True)
        st.markdown("<div class='muted'>Filtreleri ayarladıktan sonra analizi çalıştır. Daha isabetli olur.</div>", unsafe_allow_html=True)

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
# İşlem Merkezi (manuel ekleme / düzenleme)
# -------------------------
elif menu == "İşlem Merkezi":
    st.title("🧾 İşlem Merkezi")

    with st.expander("➕ Yeni kayıt ekle", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            firma = st.text_input("Firma Adı")
            evrak_tipi = st.selectbox("Evrak Tipi", ["Çek", "Senet", "Fatura", "Diğer"], index=0)
            banka = st.text_input("Banka")
        with c2:
            tutar = st.number_input("Tutar", value=0.0, step=1000.0)
            doviz = st.selectbox("Döviz", ["TL", "USD", "EUR", "Dolar", "Euro"], index=0)
            vade = st.text_input("Vade (DD.MM.YYYY)")
        with c3:
            aciklama = st.text_input("Açıklama")
            evrak_no = st.text_input("Evrak No")
            durum = st.selectbox("Durum", ["Beklemede", "Ödendi", "Takas"], index=0)
        with c4:
            ceki_veren = st.text_input("Çeki veren")
            cirolu = st.text_input("Cirolu")
            asil_borclu = st.text_input("Asıl borçlu")
            kime_verildi = st.text_input("Kime verildi")

        if st.button("💾 Kaydet", use_container_width=True):
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
    st.dataframe(df.drop(columns=["Vade_Date"], errors="ignore"), use_container_width=True)

# -------------------------
# AI Evrak Analizi (fatura -> sheet)
# -------------------------
elif menu == "AI Evrak Analizi":
    st.title("📄 AI Evrak Analizi")

    types = ["png", "jpg", "jpeg"]
    if PDF_ENABLED:
        types.append("pdf")

    uploaded = st.file_uploader("Fatura yükle", type=types)

    if uploaded:
        # load image
        image = None
        raw_image = None

if uploaded.type == "application/pdf":
    if not PDF_ENABLED:
        st.error("PDF desteği kapalı. packages.txt -> poppler-utils gerekli.")
        st.stop()
    pdf_bytes = uploaded.read()
    raw_image = pdf_first_page_to_image(pdf_bytes, dpi=350)
else:
    raw_image = Image.open(uploaded).convert("RGB")

# iyileştirilmiş versiyon
image = enhance_for_reading(raw_image)

# ekranda ikisini de göster (farkı gör)
c1, c2 = st.columns(2)
with c1:
    st.caption("Orijinal")
    st.image(raw_image, use_container_width=True)
with c2:
    st.caption("İyileştirilmiş (AI/OCR için)")
    st.image(image, use_container_width=True)

# QR oku
qr_list = decode_qr(raw_image) or decode_qr(image)
if qr_list:
    st.success("✅ QR bulundu")
    st.write(qr_list)
else:
    st.warning("QR bulunamadı (zbar/pyzbar kurulu mu, QR çok küçük mü?)")

        st.image(image, width=420)

        colA, colB, colC = st.columns([1, 1, 1])
        with colA:
            do_ocr = st.checkbox("OCR kullan (varsa)", value=False, disabled=not OCR_ENABLED)
        with colB:
            archive = st.checkbox("Görseli arşivle", value=True)
        with colC:
            st.caption(f"Model: {MODEL_NAME}")

        if do_ocr:
            with st.spinner("OCR okunuyor..."):
                txt = ocr_read(image)
                if txt.strip():
                    st.text_area("OCR Metni", txt, height=180)
                else:
                    st.info("OCR metni alınamadı (kurulum yok veya görsel uygun değil).")

        if st.button("🧠 AI ile Analiz Et", use_container_width=True):
            with st.spinner("AI analiz ediyor..."):
                result = analyze_invoice(image)

            if not result:
                st.error("AI veri çıkaramadı. Görseli daha net deneyin.")
            else:
                st.success("AI veriyi çıkardı.")
                st.json(result)

                # allow user edits before save
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

# -------------------------
# AI CFO Chat
# -------------------------
elif menu == "AI CFO Chat":
    st.title("🧠 AI CFO Chat")

    if df.empty:
        st.warning("Önce Google Sheets verisi okunmalı.")
        st.stop()

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

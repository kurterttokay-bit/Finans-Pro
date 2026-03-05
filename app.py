import streamlit as st
import pandas as pd
import yfinance as yf
import google.generativeai as genai
from st_gsheets_connection import GSheetsConnection
from datetime import datetime, timedelta
from PIL import Image
import json
import re
import logging
import plotly.express as px

# -------------------------
# CONFIG
# -------------------------
st.set_page_config(
    page_title="Finans Enterprise Pro",
    page_icon="🏦",
    layout="wide"
)

logging.basicConfig(level=logging.INFO)

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
        st.title("🏦 Finans Sistemi")
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

# -------------------------
# API CONFIG (DINAMIK MODEL KONTROLÜ)
# -------------------------
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
genai.configure(api_key=GEMINI_API_KEY)

# 404 Hatasını önlemek için kullanılabilir modelleri tara
MODEL_NAME = "gemini-1.5-flash" 
try:
    available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    if "models/gemini-1.5-flash" in available_models:
        MODEL_NAME = "models/gemini-1.5-flash"
    elif "gemini-1.5-flash" in available_models:
        MODEL_NAME = "gemini-1.5-flash"
except Exception as e:
    logging.error(f"Model listesi alınamadı: {e}")

model = genai.GenerativeModel(MODEL_NAME)

# -------------------------
# GOOGLE SHEETS
# -------------------------
SHEET_ID = "1gow0J5IA0GaB-BjViSKGbIxoZije0klFGgvDWYHdcNA"
conn = st.connection("gsheets", type=GSheetsConnection)

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
        return 34.80, 37.60 # Güncel varsayılan kurlar

# -------------------------
# DATA LOAD
# -------------------------
@st.cache_data(ttl=120)
def load_data():
    try:
        df = conn.read(spreadsheet=SHEET_ID)
        if df.empty: return df
        df.columns = df.columns.str.strip()
        df["Tutar"] = pd.to_numeric(df["Tutar"], errors="coerce").fillna(0)
        if "Vade" in df.columns:
            df["Vade_Date"] = pd.to_datetime(df["Vade"], dayfirst=True, errors="coerce")
        else:
            df["Vade_Date"] = None
        return df
    except Exception as e:
        logging.error(e)
        return pd.DataFrame()

# -------------------------
# AI ANALYSIS FUNCTIONS
# -------------------------
def analyze_invoice(image):
    prompt = """Extract invoice/check info. Return ONLY JSON: {"firma": "str", "tutar": float, "vade": "DD.MM.YYYY", "banka": "str"}"""
    try:
        response = model.generate_content([prompt, image])
        try:
            text = response.text
        except:
            text = response.candidates[0].content.parts[0].text
        json_match = re.search(r"\{.*\}", text, re.S)
        return json.loads(json_match.group()) if json_match else None
    except Exception as e:
        st.error(f"Evrak Analiz Hatası ({MODEL_NAME}): {e}")
        return None

def ai_cfo_analysis(df):
    if df.empty: return "Analiz edilecek veri yok."
    sample = df.head(50).to_dict()
    prompt = f"Sen bir CFO AI'sısın. Şu borç tablosunu analiz et: {sample}. Nakit akış riskini ve likidite durumunu Türkçe olarak kısa ve öz açıkla."
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"CFO Analiz Hatası ({MODEL_NAME}): {e}"

# -------------------------
# MAIN LOGIC
# -------------------------
df = load_data()
usd, eur = get_fx()

if not df.empty:
    kur_map = {"USD": usd, "EUR": eur}
    df["kur"] = df["Döviz"].map(kur_map).fillna(1)
    df["Tutar_TL"] = df["Tutar"] * df["kur"]

# -------------------------
# SIDEBAR
# -------------------------
with st.sidebar:
    st.title("🏦 Finans Panel")
    st.info(f"Kullanıcı: Kurter\nYetki: {st.session_state.auth}") #
    menu = st.radio("Menü", ["Dashboard", "İşlem Merkezi"])
    adat_rate = st.number_input("Adat Faizi %", value=39.75) / 100
    if st.button("Çıkış"):
        st.session_state.auth = None
        st.rerun()

# -------------------------
# DASHBOARD
# -------------------------
if menu == "Dashboard":
    st.title("📊 Finansal Durum & Analiz")
    if df.empty:
        st.warning("Görüntülenecek veri bulunamadı.")
    else:
        # Metrikler
        total = df["Tutar_TL"].sum()
        today = pd.Timestamp(datetime.now().date())
        valid = df[df["Vade_Date"].notnull()].copy()
        
        if not valid.empty:
            days = (valid["Vade_Date"] - today).dt.days
            weighted = (valid["Tutar_TL"] * days).sum()
            avg_days = weighted / valid["Tutar_TL"].sum() if total > 0 else 0
            avg_date = today + timedelta(days=int(avg_days))
            adat_cost = (weighted * adat_rate) / 365
        else:
            avg_date, adat_cost = today, 0

        c1, c2, c3 = st.columns(3)
        c1.metric("Toplam Borç", f"{total:,.2f} ₺")
        c2.metric("Ortalama Vade", avg_date.strftime("%d.%m.%Y"))
        c3.metric("Adat Yükü", f"{adat_cost:,.2f} ₺")

        # Görselleştirme
        st.subheader("📈 Nakit Akış Zaman Çizelgesi")
        flow = valid.groupby("Vade_Date")["Tutar_TL"].sum().reset_index().sort_values("Vade_Date")
        fig = px.bar(flow, x="Vade_Date", y="Tutar_TL", title="Günlük Ödeme Yükü")
        st.plotly_chart(fig, use_container_width=True)

        # AI Analiz
        st.subheader("🧠 AI CFO Raporu")
        if st.button("Finansal Analiz Oluştur"):
            with st.spinner("AI verileri yorumluyor..."):
                st.markdown(ai_cfo_analysis(df))

        st.dataframe(df.drop(columns=["Vade_Date", "kur", "Tutar_TL"]), use_container_width=True)

# -------------------------
# OPERATION CENTER
# -------------------------
else:
    st.title("📄 AI Evrak Analiz Merkezi")
    img_file = st.file_uploader("Fatura veya Çek Görseli Yükleyin", type=["png", "jpg", "jpeg"])
    
    if img_file and st.button("AI İle Veri Çıkart"):
        with st.spinner("Görsel taranıyor..."):
            image = Image.open(img_file).convert("RGB")
            result = analyze_invoice(image)
            if result:
                st.success("Veriler başarıyla ayrıştırıldı!")
                st.json(result)
                # Buraya Sheets'e kaydetme formu eklenebilir
            else:
                st.error("AI veriyi okuyamadı. Lütfen görselin net olduğundan emin olun.")

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
    page_title="Finans Enterprise",
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
# API CONFIG (DİNAMİK MODEL KONTROLÜ EKLENDİ)
# -------------------------
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
genai.configure(api_key=GEMINI_API_KEY)

# Hangi modelin çalıştığını otomatik bulan güvenli blok
try:
    available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    if "models/gemini-1.5-flash" in available_models:
        MODEL_NAME = "models/gemini-1.5-flash"
    elif "gemini-1.5-flash" in available_models:
        MODEL_NAME = "gemini-1.5-flash"
    else:
        MODEL_NAME = "gemini-pro" 
except Exception as e:
    MODEL_NAME = "gemini-1.5-flash"
    logging.error(f"Model listeleme hatası: {e}")

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
        return 34.0, 37.0

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
# AI ANALYSIS
# -------------------------
def analyze_invoice(image):
    prompt = """Extract invoice information. Return ONLY JSON. {"firma": "", "tutar": number, "vade": "DD.MM.YYYY", "banka": ""}"""
    try:
        response = model.generate_content([prompt, image])
        try:
            text = response.text
        except:
            text = response.candidates[0].content.parts[0].text
        json_match = re.search(r"\{.*\}", text, re.S)
        if json_match:
            return json.loads(json_match.group())
    except Exception as e:
        st.error(f"AI Analiz Hatası ({MODEL_NAME}): {e}")
    return None

def ai_cfo_analysis(df):
    sample = df.head(50).to_dict()
    prompt = f"Sen bir CFO AI'sısın. Şu borç tablosunu analiz et: {sample}. Nakit akışı ve ödeme risklerini kısa ve öz açıkla."
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"CFO Analiz Hatası ({MODEL_NAME}): {e}"

# -------------------------
# SIDEBAR
# -------------------------
with st.sidebar:
    st.title("🏦 Finans Panel")
    st.info(f"Yetki: {st.session_state.auth}")
    menu = st.radio("Menü", ["Dashboard", "İşlem Merkezi"])
    adat_rate = st.number_input("Adat Faizi %", value=39.75) / 100
    if st.button("Çıkış"):
        st.session_state.auth = None
        st.rerun()

# -------------------------
# DATA PREP & DASHBOARD & OPERATION
# -------------------------
df = load_data()
usd, eur = get_fx()

if not df.empty:
    kur_map = {"USD": usd, "EUR": eur}
    df["kur"] = df["Döviz"].map(kur_map).fillna(1)
    df["Tutar_TL"] = df["Tutar"] * df["kur"]

if menu == "Dashboard":
    st.title("📊 Finansal Durum")
    if df.empty:
        st.warning("Veri yok")
    else:
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

        fig = px.bar(valid.groupby("Vade_Date")["Tutar_TL"].sum().reset_index(), x="Vade_Date", y="Tutar_TL", title="Ödeme Takvimi")
        st.plotly_chart(fig, use_container_width=True)

        if st.button("AI Analiz Yap"):
            with st.spinner("AI analiz ediyor..."):
                st.write(ai_cfo_analysis(df))
        
        st.dataframe(df.drop(columns=["Vade_Date", "kur", "Tutar_TL"]), use_container_width=True)

else:
    st.title("📄 AI Evrak Analizi")
    img = st.file_uploader("Fatura / Çek yükle", type=["png", "jpg", "jpeg"])
    if img and st.button("AI Analiz"):
        with st.spinner("AI analiz ediyor..."):
            image = Image.open(img).convert("RGB")
            result = analyze_invoice(image)
            if result:
                st.success(f"AI Veri Çıkardı ({MODEL_NAME})")
                st.json(result)
            else:
                st.error("Veri çıkarılamadı")

import streamlit as st
import pandas as pd
import yfinance as yf
import google.generativeai as genai
from streamlit_gsheets import GSheetsConnection
from datetime import datetime, timedelta
from PIL import Image
import json
import re
import logging

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

    col1, col2, col3 = st.columns([1,1.3,1])

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
# API CONFIG
# -------------------------

GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]

genai.configure(api_key=GEMINI_API_KEY)

MODEL_NAME = "gemini-1.5-flash"

# -------------------------
# GOOGLE SHEETS
# -------------------------

SHEET_URL = "https://docs.google.com/spreadsheets/d/1gow0J5IA0GaB-BjViSKGbIxoZije0klFGgvDWYHdcNA"

conn = st.connection("gsheets", type=GSheetsConnection)

# -------------------------
# FX RATES
# -------------------------

@st.cache_data(ttl=300)
def get_fx():

    try:

        usd = float(
            yf.download(
                "USDTRY=X",
                period="1d",
                progress=False
            )["Close"].iloc[-1]
        )

        eur = float(
            yf.download(
                "EURTRY=X",
                period="1d",
                progress=False
            )["Close"].iloc[-1]
        )

        return usd, eur

    except Exception as e:

        logging.error(e)

        return 35.0, 38.0


# -------------------------
# DATA LOAD
# -------------------------

@st.cache_data(ttl=120)
def load_data():

    try:

        df = conn.read(spreadsheet=SHEET_URL)

        if df.empty:
            return df

        df.columns = df.columns.str.strip()

        df["Tutar"] = pd.to_numeric(df["Tutar"], errors="coerce").fillna(0)

        if "Vade" in df.columns:
            df["Vade_Date"] = pd.to_datetime(
                df["Vade"],
                dayfirst=True,
                errors="coerce"
            )
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

    model = genai.GenerativeModel(MODEL_NAME)

    prompt = """
Extract invoice information.

Return ONLY JSON.

{
"firma": "",
"tutar": number,
"vade": "DD.MM.YYYY",
"banka": ""
}
"""

    response = model.generate_content([prompt, image])

    try:
        text = response.text
    except:
        text = response.candidates[0].content.parts[0].text

    json_match = re.search(r"\{.*\}", text, re.S)

    if json_match:

        return json.loads(json_match.group())

    return None


# -------------------------
# SIDEBAR
# -------------------------

with st.sidebar:

    st.title("🏦 Finans Panel")

    st.info(f"Yetki: {st.session_state.auth}")

    menu = st.radio(
        "Menü",
        ["Dashboard", "İşlem Merkezi"]
    )

    adat_rate = st.number_input(
        "Adat Faizi %",
        value=39.75
    ) / 100

    if st.button("Çıkış"):

        st.session_state.auth = None

        st.rerun()

# -------------------------
# DATA PREP
# -------------------------

df = load_data()

usd, eur = get_fx()

if not df.empty:

    kur_map = {
        "USD": usd,
        "EUR": eur
    }

    df["kur"] = df["Döviz"].map(kur_map).fillna(1)

    df["Tutar_TL"] = df["Tutar"] * df["kur"]

# -------------------------
# DASHBOARD
# -------------------------

if menu == "Dashboard":

    st.title("Finansal Durum")

    if df.empty:

        st.warning("Veri yok")

    else:

        total = df["Tutar_TL"].sum()

        today = pd.Timestamp(datetime.now().date())

        valid = df[df["Vade_Date"].notnull()].copy()

        if not valid.empty:

            days = (valid["Vade_Date"] - today).dt.days

            total_valid = valid["Tutar_TL"].sum()

            weighted = (valid["Tutar_TL"] * days).sum()

            avg_days = weighted / total_valid if total_valid > 0 else 0

            avg_date = today + timedelta(days=int(avg_days))

            adat_cost = (weighted * adat_rate) / 365

        else:

            avg_date = today

            adat_cost = 0

        c1, c2, c3 = st.columns(3)

        c1.metric(
            "Toplam Borç",
            f"{total:,.2f} ₺"
        )

        c2.metric(
            "Ortalama Vade",
            avg_date.strftime("%d.%m.%Y")
        )

        c3.metric(
            "Adat Yükü",
            f"{adat_cost:,.2f} ₺"
        )

        st.dataframe(
            df.drop(columns=["Vade_Date","kur","Tutar_TL"]),
            use_container_width=True
        )

# -------------------------
# OPERATION CENTER
# -------------------------

if menu == "İşlem Merkezi":

    st.title("AI Evrak Analizi")

    img = st.file_uploader(
        "Fatura / Çek yükle",
        type=["png","jpg","jpeg"]
    )

    if img and st.button("AI Analiz"):

        with st.spinner("AI analiz ediyor..."):

            image = Image.open(img).convert("RGB")

            result = analyze_invoice(image)

            if result:

                st.success("AI veri çıkardı")

                st.json(result)

            else:

                st.error("Veri çıkarılamadı")

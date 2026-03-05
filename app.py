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
import pytesseract
import os
from pdf2image import convert_from_bytes

# -------------------------
# STREAMLIT CONFIG
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
# GEMINI AI
# -------------------------

GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
genai.configure(api_key=GEMINI_API_KEY)

model = genai.GenerativeModel("gemini-1.5-flash")

# -------------------------
# GOOGLE SHEETS
# -------------------------

from streamlit_gsheets import GSheetsConnection

SHEET_ID = "1gow0J5IA0GaB-BjViSKGbIxoZije0klFGgvDWYHdcNA"

conn = st.connection("gsheets", type=GSheetsConnection)

# -------------------------
# FX
# -------------------------

@st.cache_data(ttl=300)

def get_fx():

    usd = float(yf.download("USDTRY=X", period="1d")["Close"].iloc[-1])
    eur = float(yf.download("EURTRY=X", period="1d")["Close"].iloc[-1])

    return usd, eur

# -------------------------
# DATA LOAD
# -------------------------

@st.cache_data(ttl=120)

def load_data():

    df = conn.read(spreadsheet=SHEET_ID)

    if df.empty:
        return df

    df["Tutar"] = pd.to_numeric(df["Tutar"], errors="coerce").fillna(0)

    if "Vade" in df.columns:
        df["Vade_Date"] = pd.to_datetime(df["Vade"], dayfirst=True)

    return df

# -------------------------
# OCR
# -------------------------

def ocr_read(image):

    text = pytesseract.image_to_string(image)

    return text

# -------------------------
# AI PARSE
# -------------------------

def analyze_invoice(image):

    prompt = """
Extract invoice data.

Return JSON:

{
"firma":"",
"urun":"",
"tutar":number,
"kdv":number,
"tarih":"DD.MM.YYYY"
}
"""

    response = model.generate_content([prompt,image])

    text = response.text

    json_match = re.search(r"\{.*\}", text, re.S)

    if json_match:

        return json.loads(json_match.group())

    return None

# -------------------------
# SAVE INVOICE
# -------------------------

def save_invoice(image):

    if not os.path.exists("invoices"):
        os.mkdir("invoices")

    path = f"invoices/{datetime.now().timestamp()}.png"

    image.save(path)

    return path

# -------------------------
# GOOGLE SHEETS WRITE
# -------------------------

def add_to_sheet(df, result):

    new = pd.DataFrame([{

        "Firma": result["firma"],
        "Urun": result["urun"],
        "Tutar": result["tutar"],
        "KDV": result["kdv"],
        "Tarih": result["tarih"]

    }])

    df = pd.concat([df,new])

    conn.update(spreadsheet=SHEET_ID,data=df)

# -------------------------
# AI CFO
# -------------------------

def ai_cfo(df):

    sample = df.head(50).to_dict()

    prompt = f"""

Sen deneyimli bir CFO'sun.

Şirketin borç tablosu:

{sample}

Analiz et:

1 riskli ödemeler
2 nakit akışı
3 öneri
"""

    response = model.generate_content(prompt)

    return response.text

# -------------------------
# SIDEBAR
# -------------------------

with st.sidebar:

    st.title("🏦 Finans Panel")

    st.info(f"Kullanıcı: Kurter\nYetki: {st.session_state.auth}")

    menu = st.radio("Menü",

    [
    "Dashboard",
    "AI Evrak Analizi",
    "AI CFO Chat"
    ])

    adat_rate = st.number_input("Adat Faizi %",value=39.75)/100

    if st.button("Çıkış"):
        st.session_state.auth=None
        st.rerun()

# -------------------------
# MAIN DATA
# -------------------------

df = load_data()

usd, eur = get_fx()

if not df.empty:

    kur_map = {

        "USD": usd,
        "EUR": eur

    }

    df["kur"]=df["Döviz"].map(kur_map).fillna(1)

    df["Tutar_TL"]=df["Tutar"]*df["kur"]

# -------------------------
# DASHBOARD
# -------------------------

if menu=="Dashboard":

    st.title("📊 Finans Dashboard")

    if df.empty:

        st.warning("Veri yok")

    else:

        total=df["Tutar_TL"].sum()

        today=pd.Timestamp(datetime.now().date())

        valid=df[df["Vade_Date"].notnull()]

        days=(valid["Vade_Date"]-today).dt.days

        overdue=valid[days<0]["Tutar_TL"].sum()

        due7=valid[(days>=0)&(days<=7)]["Tutar_TL"].sum()

        due30=valid[(days>7)&(days<=30)]["Tutar_TL"].sum()

        c1,c2,c3,c4=st.columns(4)

        c1.metric("Toplam Borç",f"{total:,.2f} ₺")

        c2.metric("Geciken",f"{overdue:,.2f} ₺")

        c3.metric("7 Gün",f"{due7:,.2f} ₺")

        c4.metric("30 Gün",f"{due30:,.2f} ₺")

        fig=px.bar(valid.groupby("Vade_Date")["Tutar_TL"].sum().reset_index(),x="Vade_Date",y="Tutar_TL")

        st.plotly_chart(fig,use_container_width=True)

        if st.button("AI CFO Analizi"):

            st.markdown(ai_cfo(df))

        st.dataframe(df)

# -------------------------
# INVOICE ANALYSIS
# -------------------------

elif menu=="AI Evrak Analizi":

    st.title("📄 Fatura Analizi")

    file=st.file_uploader("Fatura yükle",type=["png","jpg","jpeg","pdf"])

    if file:

        if file.type=="application/pdf":

            pages=convert_from_bytes(file.read())

            image=pages[0]

        else:

            image=Image.open(file)

        st.image(image,width=400)

        if st.button("AI Analiz"):

            with st.spinner("AI analiz ediyor"):

                result=analyze_invoice(image)

                if result:

                    st.json(result)

                    if st.button("Excel'e Kaydet"):

                        add_to_sheet(df,result)

                        save_invoice(image)

                        st.success("Kaydedildi")

                else:

                    st.error("Veri çıkarılamadı")

# -------------------------
# AI CFO CHAT
# -------------------------

elif menu=="AI CFO Chat":

    st.title("🧠 AI CFO")

    question=st.text_input("Soru sor")

    if question:

        prompt=f"""

Bir CFO gibi cevap ver.

Soru:

{question}

Veri:

{df.head(50).to_dict()}

"""

        response=model.generate_content(prompt)

        st.markdown(response.text)

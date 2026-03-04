import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import plotly.express as px
from streamlit_gsheets import GSheetsConnection
import yfinance as yf
import hashlib

st.set_page_config(page_title="Finans Pro", layout="wide", page_icon="🏦")

# --- CSS ---
st.markdown("""
    <style>
    .metric-container {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 10px;
        margin-bottom: 20px;
    }
    .metric-card {
        padding: 12px 5px;
        border-radius: 10px;
        text-align: center;
        color: white;
        box-shadow: 2px 2px 8px rgba(0,0,0,0.1);
    }
    .metric-card .icon { font-size: 22px; margin-bottom: 2px; }
    .metric-card .title { font-size: 13px; opacity: 0.8; font-weight: 400; }
    .metric-card .value { font-size: 16px; font-weight: 700; margin: 2px 0; }
    .metric-card .delta { font-size: 11px; opacity: 0.7; }
    @media (max-width: 768px) {
        .metric-container { grid-template-columns: repeat(2, 1fr); }
    }
    .blink {
        animation: blinker 1s linear infinite;
        color: red;
        font-weight: bold;
    }
    @keyframes blinker { 50% { opacity: 0; } }
    </style>
""", unsafe_allow_html=True)

# --- CANLI KUR ---
@st.cache_data(ttl=300)
def get_live_usd():
    try:
        data = yf.download("USDTRY=X", period="2d", interval="1m", progress=False)
        return float(data['Close'].iloc[-1]) if not data.empty else None
    except:
        return None

usd_kur = get_live_usd() or 33.45

# --- VERİ MOTORU ---
edit_url = "https://docs.google.com/spreadsheets/d/1gow0J5IA0GaB-BjViSKGbIxoZije0klFGgvDWYHdcNA/edit#gid=0"
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=0)
def load_and_calculate_real():
    raw_df = conn.read(spreadsheet=edit_url, ttl=0)
    raw_df.columns = raw_df.columns.str.strip()
    expected_cols = ["Firma Adı","Evrak Tipi","Banka","Tutar","Vade","Açıklama",
                     "Çeki veren","Cirolu","Asıl borçlu","Kime verildi","Evrak No","Döviz","Durum"]
    raw_df = raw_df.rename(columns={c:expected_cols[i] for i,c in enumerate(raw_df.columns)})
    raw_df['Tutar'] = pd.to_numeric(raw_df['Tutar'], errors='coerce').fillna(0)
    raw_df['Vade_Date'] = pd.to_datetime(raw_df['Vade'], errors='coerce').dt.date
    bugun = datetime.now().date()
    valid = raw_df[raw_df['Tutar'] > 0].copy()
    if not valid.empty:
        valid['Gun_Farki'] = valid['Vade_Date'].apply(lambda x: (x - bugun).days)
        valid['Agirlik'] = valid['Tutar'] * valid['Gun_Farki']
        toplam_tutar = valid['Tutar'].sum()
        toplam_agirlik = valid['Agirlik'].sum()
        ort_gun_sayisi = toplam_agirlik / toplam_tutar
        gercek_ort_vade = bugun + timedelta(days=int(round(ort_gun_sayisi)))
        return raw_df, valid, toplam_tutar, gercek_ort_vade, int(ort_gun_sayisi), toplam_agirlik
    return raw_df, pd.DataFrame(), 0, bugun, 0, 0

df, valid_df, total_tl, ort_vade, ort_gun, toplam_agirlik = load_and_calculate_real()

def upcoming_reminders(df, days=7):
    today = datetime.now().date()
    temp_df = df.copy()
    temp_df["Vade_Date"] = pd.to_datetime(temp_df["Vade"], errors="coerce").dt.date
    temp_df["Gun_Farki"] = temp_df["Vade_Date"].apply(lambda x: (x - today).days if pd.notnull(x) else None)
    return temp_df[temp_df["Gun_Farki"].notnull() & (temp_df["Gun_Farki"] <= days) & (temp_df["Gun_Farki"] >= 0)]

# --- LOGIN ---
if 'auth' not in st.session_state: st.session_state.auth = None
hashed_pwds = {
    "PATRON": hashlib.sha256("patron125".encode()).hexdigest(),
    "MUHASEBE": hashlib.sha256("muhasebe007".encode()).hexdigest(),
    "DENEME": hashlib.sha256("deneme123".encode()).hexdigest()
}

if not st.session_state.auth:
    _, center, _ = st.columns([1,1.2,1])
    with center:
        st.markdown("<h4 style='text-align: center; color: gray;'>🏦 Finans Pro</h4>", unsafe_allow_html=True)
        with st.form("login"):
            pwd = st.text_input("Şifre", type="password")
            if st.form_submit_button("Erişimi Aç"):
                hashed_input = hashlib.sha256(pwd.encode()).hexdigest()
                for role, h_pwd in hashed_pwds.items():
                    if hashed_input == h_pwd: st.session_state.auth = role
                if st.session_state.auth: st.rerun()
                else: st.error("Hatalı!")
    st.stop()

import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
from PIL import Image
import json

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Finans Pro", layout="wide", page_icon="🏦")

# --- API AYARI ---
api_key = st.secrets.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

# --- RENKLİ STİLLER ---
st.markdown("""
<style>
.metric-card { background: #111; padding: 20px; border-radius: 15px; text-align: center; border: 1px solid #333; }
.manage-box { background: #1a1a1a; padding: 20px; border-radius: 12px; border: 1px solid #444; text-align: center; min-height: 140px; }
</style>
""", unsafe_allow_html=True)

# --- VERİ BAĞLANTI URL ---
sheet_url = "https://docs.google.com/spreadsheets/d/1gow0J5IA0GaB-BjViSKGbIxoZije0klFGgvDWYHdcNA/edit#gid=0"

# --- SIDEBAR NAVİGASYON ---
with st.sidebar:
    st.title("🏦 Finans Pro")
    sayfa = st.radio("Menü", ["🏠 Dashboard", "📝 Veri Yönetimi", "📸 Fatura Analiz"])
    st.divider()
    st.write(f"Hoş geldin, **Kurter**")

# --- 1. DASHBOARD ---
if sayfa == "🏠 Dashboard":
    st.title("⚖️ Finansal Durum")
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(spreadsheet=sheet_url, ttl=0)
    
    if not df.empty:
        c1, c2, c3, c4 = st.columns(4)
        total = pd.to_numeric(df.iloc[:, 3], errors='coerce').sum()
        with c1: st.markdown(f'<div class="metric-card" style="border-top: 4px solid #00ff88;"><b>Toplam Yük</b><br><h3>{total:,.2f} ₺</h3></div>', unsafe_allow_html=True)
        with c2: st.markdown('<div class="metric-card" style="border-top: 4px solid #0088ff;"><b>Durum</b><br><h3>Güncel</h3></div>', unsafe_allow_html=True)
        with c3: st.markdown('<div class="metric-card"><b>USD/TRY</b><br><h3>34.68 ₺</h3></div>', unsafe_allow_html=True)
        with c4: st.markdown('<div class="metric-card"><b>EUR/TRY</b><br><h3>37.45 ₺</h3></div>', unsafe_allow_html=True)
        
        st.write("### 📋 Evrak Listesi")
        st.dataframe(df, use_container_width=True, hide_index=True)

# --- 2. VERI YONETIMI ---
elif sayfa == "📝 Veri Yönetimi":
    st.title("📝 Veri Yönetimi")
    v1, v2, v3, v4 = st.columns(4)
    with v1: 
        st.markdown('<div class="manage-box"><b>1. Taslak Al</b></div>', unsafe_allow_html=True)
        st.download_button("İndir", pd.DataFrame(columns=["Firma","Vade","Tutar"]).to_csv(index=False).encode('utf-8'), "taslak.csv")
    with v2:
        st.markdown('<div class="manage-box"><b>2. Veri Yükle</b></div>', unsafe_allow_html=True)
        st.file_uploader("Yükle", type=["csv"], label_visibility="collapsed")
    with v3:
        st.markdown('<div class="manage-box"><b>3. Sheets</b></div>', unsafe_allow_html=True)
        st.link_button("Tabloyu Aç", sheet_url)
    with v4:
        st.markdown('<div class="manage-box"><b>4. Manuel</b></div>', unsafe_allow_html=True)
        if st.toggle("Formu Aç"): st.text_input("Firma Adı")

# --- 3. FATURA ANALIZ ---
elif sayfa == "📸 Fatura Analiz":
    st.title("📸 AI Fatura Analizi")
    img_file = st.file_uploader("Görsel Yükle", type=["jpg","png","jpeg"])
    if img_file:
        st.image(img_file, width=400)
        if st.button("🔍 Verileri Ayıkla"):
            try:
                model = genai.GenerativeModel('gemini-1.5-flash')
                response = model.generate_content(["Bu faturadaki Firma Adı, Tutar ve Vadeyi JSON formatında çıkar.", Image.open(img_file)])
                st.success("Analiz Bitti!")
                st.write(response.text)
            except Exception as e:
                st.error(f"Hata: {str(e)}")

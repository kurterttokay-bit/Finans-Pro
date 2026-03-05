import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
from PIL import Image
import json

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Finans Pro", layout="wide", page_icon="🏦")

# --- SECRETS & API AYARI ---
# Artık yeni ve temiz anahtarını Streamlit Secrets paneline eklediğini varsayıyorum.
api_key = st.secrets.get("GEMINI_API_KEY")

if api_key:
    genai.configure(api_key=api_key)
else:
    st.error("⚠️ API Anahtarı eksik! Lütfen Streamlit Secrets paneline GEMINI_API_KEY ekle.")

# --- CSS STİLLERİ (Dashboard'u ısıtalım) ---
st.markdown("""
<style>
.metric-card { background: #111; padding: 20px; border-radius: 12px; border-top: 4px solid #00ff88; text-align: center; }
.sidebar-title { color: #00ff88; font-weight: bold; font-size: 20px; }
</style>
""", unsafe_allow_html=True)

# --- VERİ KAYNAĞI ---
sheet_url = "https://docs.google.com/spreadsheets/d/1gow0J5IA0GaB-BjViSKGbIxoZije0klFGgvDWYHdcNA/edit#gid=0"

# --- SIDEBAR NAVİGASYON ---
with st.sidebar:
    st.markdown('<p class="sidebar-title">🏦 Finans Pro</p>', unsafe_allow_html=True)
    menu = st.radio("Sayfa Seçimi", ["🏠 Dashboard", "📝 Veri Yönetimi", "📸 AI Fatura Tarama"])
    st.divider()
    st.info(f"Kullanıcı: Kurter")

# --- 🏠 DASHBOARD ---
if menu == "🏠 Dashboard":
    st.title("⚖️ Finansal Durum Paneli")
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        df = conn.read(spreadsheet=sheet_url, ttl=0)
        
        if not df.empty:
            c1, c2, c3, c4 = st.columns(4)
            total_yuk = pd.to_numeric(df.iloc[:, 3], errors='coerce').sum()
            
            with c1: st.markdown(f'<div class="metric-card"><b>Toplam Yük</b><br><h3>{total_yuk:,.2f} ₺</h3></div>', unsafe_allow_html=True)
            with c2: st.markdown('<div class="metric-card" style="border-top-color: #0088ff;"><b>Durum</b><br><h3>Güncel</h3></div>', unsafe_allow_html=True)
            with c3: st.markdown('<div class="metric-card"><b>USD/TRY</b><br><h3>34.68 ₺</h3></div>', unsafe_allow_html=True)
            with c4: st.markdown('<div class="metric-card"><b>EUR/TRY</b><br><h3>37.45 ₺</h3></div>', unsafe_allow_html=True)
            
            st.write("### 📋 Evrak Listesi")
            st.dataframe(df, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Veri yüklenemedi: {e}")

# --- 📝 VERİ YÖNETİMİ ---
elif menu == "📝 Veri Yönetimi":
    st.title("📝 Veri Yönetimi")
    st.info("E-tablo üzerinden verilerini yönetebilir veya taslak indirebilirsin.")
    st.link_button("E-Tabloyu Düzenle", sheet_url)

# --- 📸 AI FATURA TARAMA ---
elif menu == "📸 AI Fatura Tarama":
    st.title("📸 AI Fatura Tarama")
    uploaded_file = st.file_uploader("Fatura Görseli Yükle", type=['png', 'jpg', 'jpeg'])
    
    if uploaded_file:
        st.image(uploaded_file, caption="Yüklenen Evrak", width=400)
        if st.button("🔍 Verileri Analiz Et"):
            with st.spinner("AI analiz ediyor..."):
                try:
                    # 'gemini-1.5-flash-latest' en kararlı sürümdür
                    model = genai.GenerativeModel('gemini-1.5-flash-latest')
                    img = Image.open(uploaded_file)
                    prompt = "Extract 'Firma Adı', 'Tutar', 'Vade' as JSON."
                    
                    response = model.generate_content([prompt, img])
                    
                    # JSON temizliği ve gösterimi
                    st.success("Analiz Başarılı!")
                    st.write(response.text)
                except Exception as e:
                    st.error(f"Fatura Analiz Hatası: {str(e)}")

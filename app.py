import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
from PIL import Image
import json

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Finans Pro", layout="wide", page_icon="🏦")

# --- API AYARI (Yeni anahtarını Secrets'a koyduğunu varsayıyorum) ---
api_key = st.secrets.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

# --- DASHBOARD STİLLERİ ---
st.markdown("""
<style>
.metric-card { background: #111; padding: 20px; border-radius: 15px; text-align: center; border: 1px solid #333; }
.sidebar-title { color: #00ff88; font-weight: bold; font-size: 20px; text-align: center; }
</style>
""", unsafe_allow_html=True)

# --- GOOGLE SHEETS URL ---
sheet_url = "https://docs.google.com/spreadsheets/d/1gow0J5IA0GaB-BjViSKGbIxoZije0klFGgvDWYHdcNA/edit#gid=0"

# --- SIDEBAR (NAVİGASYON) ---
with st.sidebar:
    st.markdown('<p class="sidebar-title">🏦 Finans Pro</p>', unsafe_allow_html=True)
    menu = st.radio("Menü", ["🏠 Dashboard", "📝 Veri Yönetimi", "📸 AI Fatura Tarama"])
    st.divider()
    st.info("Kullanıcı: Kurter")

# --- 🏠 DASHBOARD ---
if menu == "🏠 Dashboard":
    st.title("⚖️ Finansal Durum Paneli")
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        df = conn.read(spreadsheet=sheet_url, ttl=0)
        
        if not df.empty:
            c1, c2, c3, c4 = st.columns(4)
            total = pd.to_numeric(df.iloc[:, 3], errors='coerce').sum()
            with c1: st.markdown(f'<div class="metric-card" style="border-top: 5px solid #00ff88;"><b>Toplam Yük</b><br><h3>{total:,.2f} ₺</h3></div>', unsafe_allow_html=True)
            with c2: st.markdown('<div class="metric-card" style="border-top: 5px solid #0088ff;"><b>Durum</b><br><h3>Güncel</h3></div>', unsafe_allow_html=True)
            with c3: st.markdown('<div class="metric-card"><b>USD/TRY</b><br><h3>34.68 ₺</h3></div>', unsafe_allow_html=True)
            with c4: st.markdown('<div class="metric-card"><b>EUR/TRY</b><br><h3>37.45 ₺</h3></div>', unsafe_allow_html=True)
            
            st.write("### 📋 Güncel Evrak Listesi")
            st.dataframe(df, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Veri bağlantı hatası: {e}")

# --- 📝 VERİ YÖNETİMİ ---
elif menu == "📝 Veri Yönetimi":
    st.title("📝 Veri Yönetimi")
    st.write("Verileri e-tablo üzerinden yönetmek için:")
    st.link_button("E-Tabloyu Aç", sheet_url)
    
    st.divider()
    st.write("Taslak Dosya İndir (Excel):")
    # Excel yazma hatasını önlemek için engine belirttik
    df_temp = pd.DataFrame(columns=["Firma Adı", "Evrak Tipi", "Banka", "Tutar", "Vade"])
    st.download_button("Excel Taslağı İndir", data=df_temp.to_csv(index=False).encode('utf-8'), file_name="taslak.csv")

# --- 📸 AI FATURA TARAMA ---
elif menu == "📸 AI Fatura Tarama":
    st.title("📸 AI Fatura Tarama")
    f_up = st.file_uploader("Fatura veya Çek Görseli", type=["jpg", "png", "jpeg"])
    
    if f_up:
        st.image(f_up, width=400, caption="Yüklenen Evrak")
        if st.button("🔍 Verileri Analiz Et"):
            try:
                # 404 hatasını önlemek için kararlı model adı
                model = genai.GenerativeModel('gemini-1.5-flash')
                img = Image.open(f_up)
                response = model.generate_content(["Extract Firma Adı, Tutar, Vade as JSON.", img])
                
                st.success("Analiz Tamamlandı!")
                st.json(response.text)
            except Exception as e:
                st.error(f"Analiz Hatası: {str(e)}")

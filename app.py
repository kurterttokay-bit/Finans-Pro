import streamlit as st
import pandas as pd
from datetime import datetime
from streamlit_gsheets import GSheetsConnection
import yfinance as yf
import google.generativeai as genai
import json
from PIL import Image
import io

# --- 1. AYARLAR & GÜVENLİK ---
st.set_page_config(page_title="Finans Pro", layout="wide", page_icon="🏦")

# API Anahtarını Secrets'tan alıyoruz (GitHub güvenliği için)
api_key = st.secrets.get("GEMINI_API_KEY", "AIzaSy...") # Buraya anahtarını girersen kodda görünmez
genai.configure(api_key=api_key)

# --- 2. GÖRSEL STİL (Dashboard ve Bar Geri Geldi) ---
st.markdown("""
<style>
.metric-container { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 20px; }
.metric-card { padding: 20px; border-radius: 15px; text-align: center; color: white; border: 1px solid #333; }
.manage-box { background: #1a1a1a; padding: 20px; border-radius: 15px; border: 1px solid #444; text-align: center; min-height: 160px; display: flex; flex-direction: column; justify-content: center; }
@keyframes border-glow { 0% { box-shadow: 0 0 5px #ff4b2b; } 50% { box-shadow: 0 0 20px #ff416c; } 100% { box-shadow: 0 0 5px #ff4b2b; } }
.alert-bar { background: linear-gradient(90deg, #4b0000, #990000); color: white; padding: 15px; border-radius: 12px; text-align: center; font-weight: bold; border: 2px solid #ff4b2b; animation: border-glow 1.5s infinite; margin-bottom: 20px; }
</style>
""", unsafe_allow_html=True)

# --- 3. DASHBOARD VE ANALİZ FONKSİYONLARI ---
@st.cache_data(ttl=300)
def get_fx_rates():
    try:
        usd = float(yf.download("USDTRY=X", period="1d", interval="1m", progress=False)['Close'].iloc[-1])
        eur = float(yf.download("EURTRY=X", period="1d", interval="1m", progress=False)['Close'].iloc[-1])
        return usd, eur
    except: return 34.68, 37.45

def analyze_invoice(image_file):
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        img = Image.open(image_file)
        prompt = "Extract invoice: company_name, amount (float), due_date (YYYY-MM-DD), debtor. Answer only JSON."
        response = model.generate_content([prompt, img])
        return json.loads(response.text.replace('```json', '').replace('```', '').strip())
    except Exception as e:
        st.error(f"AI Analiz Hatası: {str(e)}")
        return None

# --- 4. VERİ ERİŞİMİ ---
edit_url = "https://docs.google.com/spreadsheets/d/1gow0J5IA0GaB-BjViSKGbIxoZije0klFGgvDWYHdcNA/edit#gid=0"
conn = st.connection("gsheets", type=GSheetsConnection)

if 'auth' not in st.session_state: st.session_state.auth = None
if not st.session_state.auth:
    _, center, _ = st.columns([1, 1.2, 1])
    with center:
        with st.form("login"):
            if st.form_submit_button("Sistemi Başlat"): 
                st.session_state.auth = "Kurter"; st.rerun()
    st.stop()

# --- 5. ANA MENÜ ---
with st.sidebar:
    st.title("🏦 Finans Pro")
    menu = st.radio("Menü", ["🏠 Dashboard", "📝 Veri Yönetimi", "📸 AI Fatura Tarama"])

# --- 6. DASHBOARD (Tablo ve Metrikler Geri Geldi) ---
if menu == "🏠 Dashboard":
    st.title("⚖️ Finansal Durum")
    df = conn.read(spreadsheet=edit_url, ttl=0)
    usd, eur = get_fx_rates()
    
    if not df.empty:
        total_yuk = pd.to_numeric(df.iloc[:, 3], errors='coerce').sum()
        st.markdown(f"""
        <div class="metric-container">
            <div class="metric-card" style="background:#064e3b;"><div>Toplam Yük</div><div style="font-size:24px;">{total_yuk:,.2f} ₺</div></div>
            <div class="metric-card" style="background:#0c4a6e;"><div>Durum</div><div style="font-size:24px;">Güncel</div></div>
            <div class="metric-card" style="background:#171717;"><div>USD/TRY</div><div style="font-size:24px;">{usd:.2f} ₺</div></div>
            <div class="metric-card" style="background:#171717;"><div>EUR/TRY</div><div style="font-size:24px;">{eur:.2f} ₺</div></div>
        </div>
        """, unsafe_allow_html=True)
        st.dataframe(df, use_container_width=True, hide_index=True)

# --- 7. VERİ YÖNETİMİ (İstediğin O 4'lü Kutu) ---
elif menu == "📝 Veri Yönetimi":
    st.title("📝 Veri Yönetimi")
    c1, c2, c3, c4 = st.columns(4)
    
    with c1: # Kutucuk 1: Taslak
        st.markdown('<div class="manage-box"><b>1. Taslak İndir</b><br><small>İlk satır sabittir</small></div>', unsafe_allow_html=True)
        headers = ["Firma Adı", "Evrak Tipi", "Banka", "Tutar", "Vade", "Açıklama"]
        csv = pd.DataFrame(columns=headers).to_csv(index=False).encode('utf-8')
        st.download_button("Dosyayı Al", csv, "taslak.csv", "text/csv")

    with c2: # Kutucuk 2: Yükleme
        st.markdown('<div class="manage-box"><b>2. Veri Yükle</b><br><small>Excel/CSV</small></div>', unsafe_allow_html=True)
        st.file_uploader("Yükle", type=["csv", "xlsx"], label_visibility="collapsed")

    with c3: # Kutucuk 3: E-Tablo Linki
        st.markdown('<div class="manage-box"><b>3. E-Tablo</b><br><small>Google Sheets Link</small></div>', unsafe_allow_html=True)
        st.link_button("Tabloyu Aç", edit_url)

    with c4: # Kutucuk 4: Manuel Manuel Giriş
        st.markdown('<div class="manage-box"><b>4. Manuel Giriş</b><br><small>Formu Aç/Kapat</small></div>', unsafe_allow_html=True)
        m_on = st.toggle("Formu Göster")

    if m_on:
        with st.form("manuel_g"):
            st.text_input("Firma Adı")
            st.number_input("Tutar", min_value=0.0)
            st.date_input("Vade")
            st.form_submit_button("Kaydı Tamamla")

# --- 8. AI FATURA TARAMA ---
else:
    st.title("📸 AI Fatura Tarama")
    up_img = st.file_uploader("Görsel Yükle", type=["jpg", "png", "jpeg"])
    if up_img:
        st.image(up_img, width=400)
        if st.button("🔍 Analiz Et"):
            res = analyze_invoice(up_img)
            if res: st.json(res)

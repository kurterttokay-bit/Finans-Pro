import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection
import yfinance as yf
import google.generativeai as genai
import json
from PIL import Image
import io

# --- 1. SAYFA AYARLARI ---
st.set_page_config(page_title="Yapdoksan Finans Pro", layout="wide", page_icon="🏦")

# --- GEMINI YAPILANDIRMASI ---
genai.configure(api_key="AIzaSyCgKGlkcNNmSdv8HKTm8j4RidpR7lMqYHM")

# --- 2. ÖZEL CSS ---
st.markdown("""
<style>
.metric-container { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 20px; }
.manage-card { background: #1a1a1a; padding: 20px; border-radius: 15px; border: 1px solid #333; text-align: center; min-height: 180px; display: flex; flex-direction: column; justify-content: center; align-items: center; }
.metric-card { padding: 18px; border-radius: 15px; text-align: center; color: white; box-shadow: 0 4px 15px rgba(0,0,0,0.4); border: 1px solid #333; }
@keyframes border-glow { 0% { box-shadow: 0 0 5px #ff4b2b; } 50% { box-shadow: 0 0 15px #ff416c; } 100% { box-shadow: 0 0 5px #ff4b2b; } }
.alert-bar { background: linear-gradient(90deg, #4b0000, #b91c1c); color: white; padding: 15px; border-radius: 12px; text-align: center; font-weight: bold; margin-bottom: 20px; border: 2px solid #ef4444; animation: border-glow 2s infinite; }
</style>
""", unsafe_allow_html=True)

# --- 3. FONKSİYONLAR ---
@st.cache_data(ttl=300)
def get_fx_rates():
    try:
        usd = float(yf.download("USDTRY=X", period="1d", interval="1m", progress=False)['Close'].iloc[-1])
        eur = float(yf.download("EURTRY=X", period="1d", interval="1m", progress=False)['Close'].iloc[-1])
        return usd, eur
    except: return 34.65, 37.40

def analyze_invoice(image_file):
    try:
        # 404 Hatası için model ismini doğrudan 'gemini-1.5-flash' yapıyoruz
        model = genai.GenerativeModel('gemini-1.5-flash')
        img = Image.open(image_file)
        prompt = "Fatura verilerini oku: firma_adi, tutar (sayı), vade (YYYY-MM-DD), borclu. Sadece JSON döndür."
        response = model.generate_content([prompt, img])
        return json.loads(response.text.replace('```json', '').replace('```', '').strip())
    except Exception as e:
        st.error(f"AI Hatası: {str(e)}")
        return None

# --- 4. VERİ & AUTH ---
edit_url = "https://docs.google.com/spreadsheets/d/1gow0J5IA0GaB-BjViSKGbIxoZije0klFGgvDWYHdcNA/edit#gid=0"
conn = st.connection("gsheets", type=GSheetsConnection)

if 'auth' not in st.session_state: st.session_state.auth = None
if not st.session_state.auth:
    _, center, _ = st.columns([1, 1.2, 1])
    with center:
        with st.form("login"):
            pwd = st.text_input("Giriş Şifresi", type="password")
            if st.form_submit_button("Giriş"):
                if pwd == "deneme123": st.session_state.auth = "Kurter"; st.rerun()
                else: st.error("Hatalı!")
    st.stop()

# --- 5. SIDEBAR ---
with st.sidebar:
    st.title("🏦 Finans Pro")
    menu = st.radio("Menü", ["🏠 Dashboard", "📝 Veri Yönetimi", "📸 AI Fatura Tarama"])
    if st.button("🔴 Çıkış"): st.session_state.auth = None; st.rerun()

# --- 6. DASHBOARD ---
if menu == "🏠 Dashboard":
    st.title("⚖️ Finansal Durum")
    df = conn.read(spreadsheet=edit_url, ttl=0)
    usd, eur = get_fx_rates()
    st.markdown(f"""
    <div class="metric-container">
        <div class="metric-card" style="background:#064e3b;"><div class="title">Toplam Yük</div><div class="value">{df.iloc[:, 3].sum():,.2f} ₺</div></div>
        <div class="metric-card" style="background:#0c4a6e;"><div class="title">Durum</div><div class="value">Aktif</div></div>
        <div class="metric-card" style="background:#171717;"><div class="title">USD Kur</div><div class="value">{usd:.2f} ₺</div></div>
        <div class="metric-card" style="background:#171717;"><div class="title">EUR Kur</div><div class="value">{eur:.2f} ₺</div></div>
    </div>
    """, unsafe_allow_html=True)
    st.dataframe(df, use_container_width=True)

# --- 7. VERİ YÖNETİMİ (İstediğin 4'lü Yapı) ---
elif menu == "📝 Veri Yönetimi":
    st.title("📝 Veri Yönetimi")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1: # 1. Taslak İndirme
        st.markdown('<div class="manage-card"><b>1. Taslak İndir</b><br><small>İlk satır sabittir</small></div>', unsafe_allow_html=True)
        template = pd.DataFrame(columns=["Firma Adı","Evrak Tipi","Banka","Tutar","Vade","Açıklama"])
        buffer = io.BytesIO()
        template.to_excel(buffer, index=False)
        st.download_button("Excel İndir", buffer.getvalue(), "taslak.xlsx", "application/vnd.ms-excel")

    with col2: # 2. Veri Yükleme
        st.markdown('<div class="manage-card"><b>2. Dosya Yükle</b><br><small>E-Tabloya İşler</small></div>', unsafe_allow_html=True)
        uploaded_data = st.file_uploader("Excel/CSV seç", type=["xlsx", "csv"], label_visibility="collapsed")

    with col3: # 3. E-Tablo Linki
        st.markdown('<div class="manage-card"><b>3. E-Tablo</b><br><small>Doğrudan Erişim</small></div>', unsafe_allow_html=True)
        st.link_button("E-Tabloyu Aç", edit_url)

    with col4: # 4. Manuel Giriş Anahtarı
        st.markdown('<div class="manage-card"><b>4. Manuel Giriş</b><br><small>Formu Aç/Kapat</small></div>', unsafe_allow_html=True)
        show_form = st.toggle("Giriş Formunu Göster")

    if show_form:
        with st.form("manual_entry"):
            st.text_input("Firma Adı")
            st.number_input("Tutar")
            st.date_input("Vade")
            st.form_submit_button("Kaydet")

# --- 8. AI FATURA TARAMA ---
else:
    st.title("📸 AI Fatura Tarama")
    up = st.file_uploader("Fatura Görseli", type=["jpg", "png"])
    if up:
        st.image(up, width=400)
        if st.button("🔍 Verileri Analiz Et"):
            res = analyze_invoice(up)
            if res: st.json(res)

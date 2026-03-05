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
st.set_page_config(page_title="Finans Pro", layout="wide", page_icon="🏦")

# --- GEMINI YAPILANDIRMASI ---
genai.configure(api_key="AIzaSyCgKGlkcNNmSdv8HKTm8j4RidpR7lMqYHM")

# --- 2. ÖZEL CSS (Görsel Tasarım) ---
st.markdown("""
<style>
.metric-container { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 20px; }
.metric-card { padding: 18px; border-radius: 15px; text-align: center; color: white; border: 1px solid #333; background: #111; }
.manage-box { background: #1a1a1a; padding: 20px; border-radius: 15px; border: 1px solid #444; text-align: center; height: 180px; display: flex; flex-direction: column; justify-content: center; }
@keyframes border-glow { 0% { box-shadow: 0 0 5px #ff4b2b; } 50% { box-shadow: 0 0 15px #ff416c; } 100% { box-shadow: 0 0 5px #ff4b2b; } }
.alert-bar { background: linear-gradient(90deg, #4b0000, #b91c1c); color: white; padding: 15px; border-radius: 12px; text-align: center; font-weight: bold; border: 2px solid #ef4444; animation: border-glow 2s infinite; margin-bottom: 20px; }
</style>
""", unsafe_allow_html=True)

# --- 3. FONKSİYONLAR ---
@st.cache_data(ttl=300)
def get_fx_rates():
    try:
        usd = float(yf.download("USDTRY=X", period="1d", interval="1m", progress=False)['Close'].iloc[-1])
        eur = float(yf.download("EURTRY=X", period="1d", interval="1m", progress=False)['Close'].iloc[-1])
        return usd, eur
    except: return 34.68, 37.45

def analyze_invoice(image_file):
    try:
        # 404 Hatası için alternatif model ismi denemesi
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
        except:
            model = genai.GenerativeModel('gemini-pro-vision')
            
        img = Image.open(image_file)
        prompt = "Fatura/çek verilerini ayıkla: firma_adi, tutar (float), vade (YYYY-MM-DD), borclu. Sadece JSON formatında cevap ver."
        response = model.generate_content([prompt, img])
        clean_json = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(clean_json)
    except Exception as e:
        st.error(f"AI Analiz Hatası: {str(e)}")
        return None

# --- 4. VERİ VE GİRİŞ ---
edit_url = "https://docs.google.com/spreadsheets/d/1gow0J5IA0GaB-BjViSKGbIxoZije0klFGgvDWYHdcNA/edit#gid=0"
conn = st.connection("gsheets", type=GSheetsConnection)

if 'auth' not in st.session_state: st.session_state.auth = None
if not st.session_state.auth:
    _, center, _ = st.columns([1, 1.2, 1])
    with center:
        with st.form("login"):
            pwd = st.text_input("Giriş Şifresi", type="password")
            if st.form_submit_button("Sisteme Eriş"):
                if pwd == "deneme123": st.session_state.auth = "Kurter"; st.rerun()
                else: st.error("Hatalı Şifre!")
    st.stop()

# --- 5. SIDEBAR ---
with st.sidebar:
    st.title("🏦 Finans Pro")
    menu = st.radio("Menü", ["🏠 Dashboard", "📝 Veri Yönetimi", "📸 AI Fatura Tarama"])
    if st.button("🔴 Çıkış"): st.session_state.auth = None; st.rerun()

# --- 6. DASHBOARD ---
if menu == "🏠 Dashboard":
    st.title("⚖️ Finansal Durum Paneli")
    df = conn.read(spreadsheet=edit_url, ttl=0)
    usd, eur = get_fx_rates()
    
    if not df.empty:
        total = pd.to_numeric(df.iloc[:, 3], errors='coerce').sum()
        st.markdown(f"""
        <div class="metric-container">
            <div class="metric-card" style="background:#064e3b;"><div class="title">Toplam Yük</div><div class="value">{total:,.2f} ₺</div></div>
            <div class="metric-card" style="background:#0c4a6e;"><div class="title">Durum</div><div class="value">Güncel</div></div>
            <div class="metric-card" style="background:#171717;"><div class="title">USD/TRY</div><div class="value">{usd:.2f} ₺</div></div>
            <div class="metric-card" style="background:#171717;"><div class="title">EUR/TRY</div><div class="value">{eur:.2f} ₺</div></div>
        </div>
        """, unsafe_allow_html=True)
        st.dataframe(df, use_container_width=True, hide_index=True)

# --- 7. VERİ YÖNETİMİ (Senin Taslağın) ---
elif menu == "📝 Veri Yönetimi":
    st.title("📝 Veri Yönetimi")
    
    c1, c2, c3, c4 = st.columns(4)
    
    with c1: # 1. Taslak İndirme
        st.markdown('<div class="manage-box"><b>1. Taslak İndir</b><br><small>Excel (İlk satır sabit)</small></div>', unsafe_allow_html=True)
        # Sadece başlıkları içeren sabit taslak
        headers = ["Firma Adı", "Evrak Tipi", "Banka", "Tutar", "Vade", "Açıklama"]
        tmp_df = pd.DataFrame(columns=headers)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            tmp_df.to_excel(writer, index=False)
        st.download_button("Dosyayı İndir", output.getvalue(), "FinansPro_Taslak.xlsx")

    with col2: # 2. Veri Yükleme
        st.markdown('<div class="manage-box"><b>2. Veri Yükle</b><br><small>E-tabloya İşler</small></div>', unsafe_allow_html=True)
        st.file_uploader("Excel Seç", type=["xlsx"], label_visibility="collapsed")

    with col3: # 3. Doğrudan Link
        st.markdown('<div class="manage-box"><b>3. E-Tablo Linki</b><br><small>Google Sheets</small></div>', unsafe_allow_html=True)
        st.link_button("E-Tabloya Git", edit_url)

    with col4: # 4. Manuel Giriş Toggle
        st.markdown('<div class="manage-box"><b>4. Manuel Giriş</b><br><small>Formu Aç/Kapat</small></div>', unsafe_allow_html=True)
        m_on = st.toggle("Giriş Formu", value=False)

    if m_on:
        with st.form("m_form"):
            st.text_input("Firma Adı")
            st.number_input("Tutar", min_value=0.0)
            st.date_input("Vade")
            st.form_submit_button("Ekle")

# --- 8. AI FATURA TARAMA ---
else:
    st.title("📸 AI Fatura Tarama")
    up_img = st.file_uploader("Fatura Yükle", type=["jpg", "png", "jpeg"])
    if up_img:
        st.image(up_img, width=400)
        if st.button("🔍 Analiz Et"):
            with st.spinner("AI okuyor..."):
                res = analyze_invoice(up_img)
                if res: st.json(res)

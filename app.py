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

# --- 2. ÖZEL CSS (Görselliği Koruyoruz) ---
st.markdown("""
<style>
.metric-container { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 20px; }
.metric-card { padding: 20px; border-radius: 15px; text-align: center; color: white; box-shadow: 0 4px 15px rgba(0,0,0,0.3); border: 1px solid #333; }
.manage-box { background: #1a1a1a; padding: 20px; border-radius: 15px; border: 1px solid #444; text-align: center; height: 160px; display: flex; flex-direction: column; justify-content: center; align-items: center; }
@keyframes border-glow { 0% { box-shadow: 0 0 5px #ff4b2b; } 50% { box-shadow: 0 0 20px #ff416c; } 100% { box-shadow: 0 0 5px #ff4b2b; } }
.alert-bar { background: linear-gradient(90deg, #4b0000, #990000); color: white; padding: 15px; border-radius: 12px; text-align: center; font-weight: bold; margin-bottom: 20px; border: 2px solid #ff4b2b; animation: border-glow 1.5s infinite; }
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
        # 404 Hatası Çözümü: v1beta için en kararlı model isimlendirmesi
        model = genai.GenerativeModel('gemini-1.5-flash')
        img = Image.open(image_file)
        prompt = "Extract from invoice: company_name, amount (number), due_date (YYYY-MM-DD), debtor. Answer only JSON."
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
    if st.button("🔴 Güvenli Çıkış"): st.session_state.auth = None; st.rerun()

# --- 6. DASHBOARD ---
if menu == "🏠 Dashboard":
    st.title("⚖️ Finansal Durum Paneli")
    df = conn.read(spreadsheet=edit_url, ttl=0)
    usd, eur = get_fx_rates()
    
    if not df.empty:
        # Metrik Hesaplamaları
        df['Tutar'] = pd.to_numeric(df.iloc[:, 3], errors='coerce').fillna(0)
        df['Vade_D'] = pd.to_datetime(df.iloc[:, 4], errors='coerce', dayfirst=True)
        total_yuk = df['Tutar'].sum()
        
        bugun = pd.Timestamp(datetime.now().date())
        kritik = df[(df['Vade_D'] - bugun).dt.days <= 7] if not df['Vade_D'].isnull().all() else pd.DataFrame()

        # 4'lü Metrik Kartları (Geri Geldi!)
        st.markdown(f"""
        <div class="metric-container">
            <div class="metric-card" style="background:#064e3b;"><div class="title">Toplam Yük</div><div class="value">{total_yuk:,.2f} ₺</div></div>
            <div class="metric-card" style="background:#0c4a6e;"><div class="title">Durum</div><div class="value">Güncel</div></div>
            <div class="metric-card" style="background:#171717;"><div class="title">USD/TRY</div><div class="value">{usd:.2f} ₺</div></div>
            <div class="metric-card" style="background:#171717;"><div class="title">EUR/TRY</div><div class="value">{eur:.2f} ₺</div></div>
        </div>
        """, unsafe_allow_html=True)

        if not kritik.empty:
            st.markdown(f'<div class="alert-bar">⚠ DİKKAT: 7 GÜN İÇİNDE {len(kritik)} ADET ÖDEME VAR!</div>', unsafe_allow_html=True)

        st.subheader("📋 Güncel Evrak Listesi")
        st.dataframe(df, use_container_width=True, hide_index=True)

# --- 7. VERİ YÖNETİMİ (Tam İstediğin Düzen) ---
elif menu == "📝 Veri Yönetimi":
    st.title("📝 Veri Yönetimi")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1: # 1. Taslak
        st.markdown('<div class="manage-box"><b>1. Taslak İndir</b><br><small>İlk satır sabittir</small></div>', unsafe_allow_html=True)
        headers = ["Firma Adı", "Evrak Tipi", "Banka", "Tutar", "Vade", "Açıklama"]
        csv = pd.DataFrame(columns=headers).to_csv(index=False).encode('utf-8')
        st.download_button("Excel/CSV İndir", csv, "FinansPro_Taslak.csv", "text/csv")

    with col2: # 2. Yükleme
        st.markdown('<div class="manage-box"><b>2. Veri Yükle</b><br><small>Dosyayı buraya bırak</small></div>', unsafe_allow_html=True)
        st.file_uploader("Dosya Seç", type=["csv", "xlsx"], label_visibility="collapsed")

    with col3: # 3. Link
        st.markdown('<div class="manage-box"><b>3. E-Tablo</b><br><small>Doğrudan link</small></div>', unsafe_allow_html=True)
        st.link_button("Sheets'i Aç", edit_url)

    with col4: # 4. Manuel Giriş
        st.markdown('<div class="manage-box"><b>4. Manuel Giriş</b><br><small>Formu göster/gizle</small></div>', unsafe_allow_html=True)
        m_check = st.toggle("Giriş Formu")

    if m_check:
        with st.form("manuel_f"):
            st.text_input("Firma Adı")
            st.number_input("Tutar")
            st.date_input("Vade")
            st.form_submit_button("Sisteme İşle")

# --- 8. AI FATURA TARAMA ---
else:
    st.title("📸 AI Fatura Tarama")
    f_up = st.file_uploader("Evrak Görseli Yükle", type=["jpg", "png", "jpeg"])
    if f_up:
        st.image(f_up, width=400)
        if st.button("🔍 Verileri Analiz Et"):
            with st.spinner("AI analiz ediyor..."):
                res = analyze_invoice(f_up)
                if res: st.json(res)

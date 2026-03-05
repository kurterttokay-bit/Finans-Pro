import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection
import yfinance as yf
import google.generativeai as genai
import json
from PIL import Image

# --- 1. SAYFA AYARLARI ---
st.set_page_config(page_title="Finans Pro", layout="wide", page_icon="🏦")

# --- GEMINI YAPILANDIRMASI ---
genai.configure(api_key="AIzaSyCgKGlkcNNmSdv8HKTm8j4RidpR7lMqYHM")

# --- 2. ÖZEL CSS (TASARIM) ---
st.markdown("""
<style>
.metric-container { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 20px; }
.metric-card { padding: 12px 5px; border-radius: 10px; text-align: center; color: white; box-shadow: 2px 2px 8px rgba(0,0,0,0.1); }
.metric-card .icon { font-size: 22px; margin-bottom: 2px; }
.metric-card .title { font-size: 13px; opacity: 0.8; font-weight: 400; }
.metric-card .value { font-size: 16px; font-weight: 700; margin: 2px 0; }
.fx-container { display: flex; flex-direction: column; justify-content: center; height: 100%; }
.fx-row { font-size: 14px; font-weight: 600; display: flex; justify-content: center; gap: 10px; }
@keyframes border-glow {
    0% { box-shadow: 0 0 5px #ff4b2b, 0 0 10px #ff4b2b; }
    50% { box-shadow: 0 0 20px #ff416c, 0 0 30px #ff416c; }
    100% { box-shadow: 0 0 5px #ff4b2b, 0 0 10px #ff4b2b; }
}
.alert-bar {
    background: linear-gradient(90deg, #4b0000, #990000); color: white; padding: 15px; border-radius: 12px;
    text-align: center; font-weight: bold; margin-bottom: 20px; border: 2px solid #ff4b2b; animation: border-glow 1.5s infinite;
}
.manage-card { 
    background: #1E1E1E; border: 1px solid #333; padding: 20px; border-radius: 15px; 
    text-align: center; transition: 0.3s; color: white; height: 160px;
}
.manage-card:hover { border-color: #ff4b2b; transform: translateY(-5px); }
</style>
""", unsafe_allow_html=True)

# --- 3. YARDIMCI FONKSİYONLAR ---
@st.cache_data(ttl=300)
def get_fx_rates():
    try:
        usd = float(yf.download("USDTRY=X", period="1d", interval="1m", progress=False)['Close'].iloc[-1])
        eur = float(yf.download("EURTRY=X", period="1d", interval="1m", progress=False)['Close'].iloc[-1])
        return usd, eur
    except: return 34.25, 37.15

def load_data(url, connection):
    try:
        raw_df = connection.read(spreadsheet=url, ttl=0)
        raw_df.columns = raw_df.columns.str.strip()
        expected_cols = ["Firma Adı","Evrak Tipi","Banka","Tutar","Vade","Açıklama","Çeki veren","Cirolu","Asıl borçlu","Kime verildi","Evrak No","Döviz","Durum"]
        raw_df = raw_df.rename(columns={c:expected_cols[i] for i,c in enumerate(raw_df.columns) if i < len(expected_cols)})
        raw_df['Tutar'] = pd.to_numeric(raw_df['Tutar'], errors='coerce').fillna(0)
        raw_df['Vade_Date'] = pd.to_datetime(raw_df['Vade'], errors='coerce', dayfirst=True)
        return raw_df
    except: return pd.DataFrame()

def analyze_invoice(image_file):
    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = "Bu faturayı oku ve sadece JSON formatında yanıt ver: {'firma_adi': '...', 'tutar': 0.0, 'vade': 'YYYY-MM-DD', 'borclu': '...'}"
    img = Image.open(image_file)
    response = model.generate_content([prompt, img])
    try:
        clean_json = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(clean_json)
    except: return None

# --- 4. VERİ VE BAĞLANTI ---
edit_url = "https://docs.google.com/spreadsheets/d/1gow0J5IA0GaB-BjViSKGbIxoZije0klFGgvDWYHdcNA/edit#gid=0"
conn = st.connection("gsheets", type=GSheetsConnection)
df = load_data(edit_url, conn)
usd_kur, eur_kur = get_fx_rates()

# --- 5. ŞİFRE KONTROLÜ ---
if 'auth' not in st.session_state: st.session_state.auth = None
sifreler = {"patron125": "PATRON", "muhasebe007": "MUHASEBE"}

if not st.session_state.auth:
    _, center, _ = st.columns([1, 1.2, 1])
    with center:
        with st.form("login"):
            pwd = st.text_input("Sistem Şifresi", type="password")
            if st.form_submit_button("Giriş Yap"):
                if pwd in sifreler:
                    st.session_state.auth = sifreler[pwd]
                    st.rerun()
                else: st.error("Hatalı Şifre!")
    st.stop()

# --- 6. NAVİGASYON ---
with st.sidebar:
    st.title("🏦 Finans Pro")
    menu = st.radio("Menü", ["🏠 Dashboard", "📝 Veri Yönetimi"])
    if st.button("🔴 Güvenli Çıkış"):
        st.session_state.auth = None
        st.rerun()

# --- 7. DASHBOARD ---
if menu == "🏠 Dashboard":
    st.title("⚖️ Finansal Durum Paneli")
    bugun = pd.Timestamp(datetime.now().date())
    
    if not df.empty:
        # Hesaplamalar
        total_tl = df['Tutar'].sum()
        valid_df = df[df['Vade_Date'].notnull()].copy()
        
        if not valid_df.empty:
            gun_fark = (valid_df['Vade_Date'] - bugun).dt.days
            ort_gun = int((valid_df['Tutar'] * gun_fark).sum() / total_tl)
            ort_vade = bugun + timedelta(days=ort_gun)
            adat = ((valid_df['Tutar'] * gun_fark).sum() * 0.3975) / 365
        else:
            ort_vade, adat = bugun, 0

        # Metrikler
        st.markdown(f"""
        <div class="metric-container">
            <div class="metric-card" style="background:#2E8B57;"><div class="title">Toplam Yük</div><div class="value">{total_tl:,.2f} ₺</div></div>
            <div class="metric-card" style="background:#0A84FF;"><div class="title">Ort. Vade</div><div class="value">{ort_vade.strftime('%d.%m.%Y')}</div></div>
            <div class="metric-card" style="background:#F77F00;"><div class="title">Adat (Faiz)</div><div class="value">{adat:,.2f} ₺</div></div>
            <div class="metric-card" style="background:#1C1C1E;"><div class="fx-row">USD: {usd_kur:.4f}</div><div class="fx-row">EUR: {eur_kur:.4f}</div></div>
        </div>
        """, unsafe_allow_html=True)

        # Kritik Uyarılar
        kritik = valid_df[(valid_df['Vade_Date'] - bugun).dt.days <= 7]
        if not kritik.empty:
            st.markdown(f'<div class="alert-bar">🔥 DİKKAT: 7 GÜN İÇİNDE {len(kritik)} ÖDEME VAR!</div>', unsafe_allow_html=True)

        st.subheader("📋 Güncel Evrak Listesi")
        st.dataframe(df, use_container_width=True, hide_index=True)

# --- 8. VERİ YÖNETİMİ ---
else:
    st.title("📝 Evrak ve Veri Girişi")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.info("📂 Excel ile toplu yükleme yapabilirsiniz.")
    with c2:
        if st.button("🌐 Google Sheets'i Aç"):
            st.write(f"[Buraya Tıkla]({edit_url})")
    with c3:
        show_form = st.toggle("Manuel Giriş Formunu Aç")

    if show_form:
        with st.form("manual"):
            f1, f2, f3 = st.columns(3)
            with f1: st.text_input("Firma")
            with f2: st.number_input("Tutar", min_value=0.0)
            with f3: st.date_input("Vade")
            if st.form_submit_button("Kaydet"):
                st.success("Sisteme eklendi (Görsel örnektir)")

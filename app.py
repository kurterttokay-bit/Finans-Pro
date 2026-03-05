import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection
import yfinance as yf
import google.generativeai as genai
import json
from PIL import Image

# --- 1. SAYFA AYARLARI ---
st.set_page_config(page_title="Yapdoksan Finans Pro", layout="wide", page_icon="🏦")

# --- GEMINI YAPILANDIRMASI ---
genai.configure(api_key="AIzaSyCgKGlkcNNmSdv8HKTm8j4RidpR7lMqYHM")

# --- 2. ÖZEL CSS (Görselliği Koruyoruz) ---
st.markdown("""
<style>
.metric-container { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 20px; }
.metric-card { padding: 20px; border-radius: 15px; text-align: center; color: white; box-shadow: 0 4px 15px rgba(0,0,0,0.3); border: 1px solid #333; }
.metric-card .title { font-size: 14px; opacity: 0.8; font-weight: 400; }
.metric-card .value { font-size: 22px; font-weight: bold; margin-top: 5px; }
@keyframes border-glow {
    0% { box-shadow: 0 0 5px #ff4b2b; border-color: #ff4b2b; }
    50% { box-shadow: 0 0 20px #ff416c; border-color: #ff416c; }
    100% { box-shadow: 0 0 5px #ff4b2b; border-color: #ff4b2b; }
}
.alert-bar {
    background: linear-gradient(90deg, #4b0000, #990000); color: white; padding: 15px; border-radius: 12px;
    text-align: center; font-weight: bold; margin-bottom: 20px; border: 2px solid #ff4b2b; animation: border-glow 1.5s infinite;
}
</style>
""", unsafe_allow_html=True)

# --- 3. FONKSİYONLAR ---
@st.cache_data(ttl=300)
def get_fx_rates():
    try:
        usd = float(yf.download("USDTRY=X", period="1d", interval="1m", progress=False)['Close'].iloc[-1])
        eur = float(yf.download("EURTRY=X", period="1d", interval="1m", progress=False)['Close'].iloc[-1])
        return usd, eur
    except: return 34.50, 37.25

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
    try:
        # Hata veren yer: Modeli tam sürüm adıyla çağırıyoruz
        model = genai.GenerativeModel('gemini-1.5-flash-latest') 
        img = Image.open(image_file)
        prompt = "Bu bir fatura/çek görselidir. Firma adı, toplam tutar, vade (YYYY-MM-DD) ve borçlu bilgilerini bul. Sadece JSON formatında cevap ver."
        response = model.generate_content([prompt, img])
        clean_json = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(clean_json)
    except Exception as e:
        st.error(f"Fatura Okuma Hatası: {str(e)}")
        return None

# --- 4. DATA & AUTH ---
edit_url = "https://docs.google.com/spreadsheets/d/1gow0J5IA0GaB-BjViSKGbIxoZije0klFGgvDWYHdcNA/edit#gid=0"
conn = st.connection("gsheets", type=GSheetsConnection)
df = load_data(edit_url, conn)
usd_kur, eur_kur = get_fx_rates()

if 'auth' not in st.session_state: st.session_state.auth = None
sifreler = {"deneme123": "DENEME", "patron125": "PATRON", "muhasebe007": "MUHASEBE"}

if not st.session_state.auth:
    _, center, _ = st.columns([1, 1.2, 1])
    with center:
        with st.form("login"):
            pwd = st.text_input("Giriş Şifresi", type="password")
            if st.form_submit_button("Sisteme Giriş"):
                if pwd in sifreler:
                    st.session_state.auth = sifreler[pwd]
                    st.rerun()
                else: st.error("Hatalı Şifre!")
    st.stop()

# --- 5. SIDEBAR ---
with st.sidebar:
    st.title("🏦 Finans Pro")
    st.write(f"Kullanıcı: **{st.session_state.auth}**")
    menu = st.radio("Menü", ["🏠 Dashboard", "📝 Veri Yönetimi", "📸 AI Fatura Tarama"])
    if st.button("🔴 Güvenli Çıkış"):
        st.session_state.auth = None
        st.rerun()

# --- 6. DASHBOARD ---
if menu == "🏠 Dashboard":
    st.title("⚖️ Finansal Durum")
    bugun = pd.Timestamp(datetime.now().date())
    
    if not df.empty:
        total_tl = df['Tutar'].sum()
        valid_v = df[df['Vade_Date'].notnull()].copy()
        if not valid_v.empty:
            gun_fark = (valid_v['Vade_Date'] - bugun).dt.days
            ort_vade = bugun + timedelta(days=int((valid_v['Tutar'] * gun_fark).sum() / total_tl)) if total_tl > 0 else bugun
            adat = ((valid_v['Tutar'] * gun_fark).sum() * 0.3975) / 365
        else: ort_vade, adat = bugun, 0

        st.markdown(f"""
        <div class="metric-container">
            <div class="metric-card" style="background:#004b23;"><div class="title">Toplam Yük</div><div class="value">{total_tl:,.2f} ₺</div></div>
            <div class="metric-card" style="background:#003566;"><div class="title">Ort. Vade</div><div class="value">{ort_vade.strftime('%d.%m.%Y')}</div></div>
            <div class="metric-card" style="background:#9d4c00;"><div class="title">Adat (Faiz)</div><div class="value">{adat:,.2f} ₺</div></div>
            <div class="metric-card" style="background:#1a1a1a;"><div class="title">Döviz Kurları</div><div class="value">$/₺: {usd_kur:.2f} | €/₺: {eur_kur:.2f}</div></div>
        </div>
        """, unsafe_allow_html=True)

        # Yanıp sönen kritik uyarı barı
        kritik = valid_v[(valid_v['Vade_Date'] - bugun).dt.days <= 7]
        if not kritik.empty:
            st.markdown(f'<div class="alert-bar">⚠ DİKKAT: 7 GÜN İÇİNDE {len(kritik)} ADET ÖDEME VAR!</div>', unsafe_allow_html=True)

        st.subheader("📋 Evrak Takip Listesi")
        st.dataframe(df, use_container_width=True, hide_index=True)

# --- 7. VERİ YÖNETİMİ ---
elif menu == "📝 Veri Yönetimi":
    st.title("📝 Veri & Evrak Girişi")
    st.link_button("🌐 Google Sheets Üzerinden Düzenle", edit_url, use_container_width=True)
    
    with st.expander("➕ Manuel Kayıt Formu", expanded=True):
        with st.form("manuel_giris"):
            c1, c2, c3 = st.columns(3)
            with c1: st.text_input("Firma Adı")
            with c2: st.number_input("Tutar", min_value=0.0)
            with c3: st.date_input("Vade Tarihi")
            st.form_submit_button("Sisteme Kaydet")

# --- 8. AI FATURA TARAMA ---
else:
    st.title("📸 AI Fatura Tarama")
    st.info("Faturayı veya çeki yükleyin, verileri Gemini otomatik çıkarsın.")
    up = st.file_uploader("Dosya Seç", type=["jpg", "jpeg", "png"])
    if up:
        st.image(up, width=450, caption="Yüklenen Evrak")
        if st.button("🔍 Verileri Analiz Et"):
            with st.spinner("AI faturayı okuyor..."):
                res = analyze_invoice(up)
                if res:
                    st.success("Analiz tamamlandı!")
                    st.json(res)
                    # Buraya gelen verileri form şeklinde gösterip onay alabilirsin

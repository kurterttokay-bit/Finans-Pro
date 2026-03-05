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

# --- 2. ÖZEL CSS (Tüm Görsellik Burada) ---
st.markdown("""
<style>
.metric-container { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 20px; }
.metric-card { padding: 18px; border-radius: 15px; text-align: center; color: white; box-shadow: 0 4px 15px rgba(0,0,0,0.4); border: 1px solid #333; }
.metric-card .title { font-size: 13px; opacity: 0.8; font-weight: 500; text-transform: uppercase; }
.metric-card .value { font-size: 20px; font-weight: bold; margin-top: 5px; }
@keyframes border-glow {
    0% { box-shadow: 0 0 5px #ff4b2b; border-color: #ff4b2b; }
    50% { box-shadow: 0 0 15px #ff416c; border-color: #ff416c; }
    100% { box-shadow: 0 0 5px #ff4b2b; border-color: #ff4b2b; }
}
.alert-bar {
    background: linear-gradient(90deg, #4b0000, #b91c1c); color: white; padding: 15px; border-radius: 12px;
    text-align: center; font-weight: bold; margin-bottom: 20px; border: 2px solid #ef4444; animation: border-glow 2s infinite;
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
    except: return 34.60, 37.30

def load_data(url, connection):
    try:
        raw_df = connection.read(spreadsheet=url, ttl=0)
        raw_df.columns = raw_df.columns.str.strip()
        expected = ["Firma Adı","Evrak Tipi","Banka","Tutar","Vade","Açıklama","Çeki veren","Cirolu","Asıl borçlu","Kime verildi","Evrak No","Döviz","Durum"]
        raw_df = raw_df.rename(columns={c:expected[i] for i,c in enumerate(raw_df.columns) if i < len(expected)})
        raw_df['Tutar'] = pd.to_numeric(raw_df['Tutar'], errors='coerce').fillna(0)
        raw_df['Vade_Date'] = pd.to_datetime(raw_df['Vade'], errors='coerce', dayfirst=True)
        return raw_df
    except: return pd.DataFrame()

def analyze_invoice(image_file):
    try:
        # 404 Hatası Çözümü: Model ismini doğrudan kütüphane formatında veriyoruz
        model = genai.GenerativeModel('gemini-1.5-flash') 
        img = Image.open(image_file)
        prompt = "Fatura/çek verilerini oku: firma_adi, tutar (sayı), vade (YYYY-MM-DD), borclu. Sadece JSON döndür."
        response = model.generate_content([prompt, img])
        res_text = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(res_text)
    except Exception as e:
        st.error(f"Fatura Okuma Hatası (AI): {str(e)}")
        return None

# --- 4. VERİ & GİRİŞ ---
edit_url = "https://docs.google.com/spreadsheets/d/1gow0J5IA0GaB-BjViSKGbIxoZije0klFGgvDWYHdcNA/edit#gid=0"
conn = st.connection("gsheets", type=GSheetsConnection)
df = load_data(edit_url, conn)
usd_kur, eur_kur = get_fx_rates()

if 'auth' not in st.session_state: st.session_state.auth = None
sifreler = {"deneme123": "DENEME", "patron125": "PATRON"}

if not st.session_state.auth:
    _, center, _ = st.columns([1, 1.2, 1])
    with center:
        with st.form("login"):
            pwd = st.text_input("Sistem Şifresi", type="password")
            if st.form_submit_button("Sisteme Giriş"):
                if pwd in sifreler:
                    st.session_state.auth = sifreler[pwd]; st.rerun()
                else: st.error("Hatalı!")
    st.stop()

# --- 5. SIDEBAR ---
with st.sidebar:
    st.title("🏦 Finans Pro")
    st.write(f"Kullanıcı: **{st.session_state.auth}**")
    menu = st.radio("Menü", ["🏠 Dashboard", "📝 Veri Yönetimi", "📸 AI Fatura Tarama"])
    if st.button("🔴 Güvenli Çıkış"):
        st.session_state.auth = None; st.rerun()

# --- 6. HESAPLAMALAR (ORTAK) ---
bugun = pd.Timestamp(datetime.now().date())
total_tl, ort_vade, adat = 0.0, bugun, 0.0
if not df.empty:
    total_tl = df['Tutar'].sum()
    valid_v = df[df['Vade_Date'].notnull()].copy()
    if not valid_v.empty:
        gun_fark = (valid_v['Vade_Date'] - bugun).dt.days
        ort_vade = bugun + timedelta(days=int((valid_v['Tutar'] * gun_fark).sum() / total_tl)) if total_tl > 0 else bugun
        adat = ((valid_v['Tutar'] * gun_fark).sum() * 0.3975) / 365

# --- 7. DASHBOARD ---
if menu == "🏠 Dashboard":
    st.title("⚖️ Finansal Durum Paneli")
    st.markdown(f"""
    <div class="metric-container">
        <div class="metric-card" style="background:#064e3b;"><div class="title">Toplam Yük</div><div class="value">{total_tl:,.2f} ₺</div></div>
        <div class="metric-card" style="background:#0c4a6e;"><div class="title">Ort. Vade</div><div class="value">{ort_vade.strftime('%d.%m.%Y')}</div></div>
        <div class="metric-card" style="background:#78350f;"><div class="title">Adat (Faiz)</div><div class="value">{adat:,.2f} ₺</div></div>
        <div class="metric-card" style="background:#171717;"><div class="title">Döviz Kuru</div><div class="value">$/₺: {usd_kur:.2f} | €/₺: {eur_kur:.2f}</div></div>
    </div>
    """, unsafe_allow_html=True)
    
    if not df.empty and not valid_v.empty:
        kritik = valid_v[(valid_v['Vade_Date'] - bugun).dt.days <= 7]
        if not kritik.empty:
            st.markdown(f'<div class="alert-bar">⚠ DİKKAT: 7 GÜN İÇİNDE {len(kritik)} ÖDEME VAR!</div>', unsafe_allow_html=True)

    st.subheader("📋 Evrak Listesi")
    st.dataframe(df, use_container_width=True, hide_index=True)

# --- 8. VERİ YÖNETİMİ (Kutular Geri Geldi!) ---
elif menu == "📝 Veri Yönetimi":
    st.title("📝 Veri & Evrak Girişi")
    
    # İsteğin üzerine 4'lü metrik kutularını buraya da çaktım
    st.markdown(f"""
    <div class="metric-container">
        <div class="metric-card" style="background:#1e293b;"><div class="title">Sistemdeki Tutar</div><div class="value">{total_tl:,.2f} ₺</div></div>
        <div class="metric-card" style="background:#1e293b;"><div class="title">Genel Vade</div><div class="value">{ort_vade.strftime('%d.%m.%Y')}</div></div>
        <div class="metric-card" style="background:#1e293b;"><div class="title">Kur (USD)</div><div class="value">{usd_kur:.2f} ₺</div></div>
        <div class="metric-card" style="background:#1e293b;"><div class="title">Kur (EUR)</div><div class="value">{eur_kur:.2f} ₺</div></div>
    </div>
    """, unsafe_allow_html=True)

    st.link_button("🌐 Google Sheets Üzerinden Düzenle", edit_url, use_container_width=True)
    
    with st.expander("➕ Manuel Kayıt Formu", expanded=True):
        with st.form("manuel_form"):
            c1, c2, c3 = st.columns(3)
            with c1: st.text_input("Firma Adı")
            with c2: st.number_input("Tutar", min_value=0.0)
            with c3: st.date_input("Vade")
            st.form_submit_button("Sisteme İşle")

# --- 9. AI FATURA TARAMA ---
else:
    st.title("📸 AI Fatura Tarama")
    st.info("Faturayı yükle, Gemini verileri otomatik ayıklasın.")
    up = st.file_uploader("Dosya Seç", type=["jpg", "jpeg", "png"])
    if up:
        st.image(up, width=400, caption="Yüklenen Evrak")
        if st.button("🔍 Verileri Analiz Et"):
            with st.spinner("AI faturayı okuyor..."):
                res = analyze_invoice(up)
                if res:
                    st.success("Analiz tamamlandı!")
                    st.json(res)

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
# Gemini 1.5 Flash kullanarak faturayı dijital veriye dönüştürüyoruz.
genai.configure(api_key="AIzaSyCgKGlkcNNmSdv8HKTm8j4RidpR7lMqYHM")

# --- 2. ÖZEL CSS (TASARIM) ---
st.markdown("""
<style>
.metric-container { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 20px; }
.metric-card { padding: 12px 5px; border-radius: 10px; text-align: center; color: white; box-shadow: 2px 2px 8px rgba(0,0,0,0.1); }
.metric-card .icon { font-size: 22px; margin-bottom: 2px; }
.metric-card .title { font-size: 13px; opacity: 0.8; font-weight: 400; }
.metric-card .value { font-size: 16px; font-weight: 700; margin: 2px 0; }
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
    text-align: center; color: white; min-height: 140px;
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
    prompt = "Bu faturayı oku ve sadece şu JSON formatında cevap ver: {'firma_adi': '...', 'tutar': 0.0, 'vade': 'YYYY-MM-DD', 'borclu': '...'}"
    img = Image.open(image_file)
    response = model.generate_content([prompt, img])
    try:
        clean_json = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(clean_json)
    except: return None

# --- 4. VERİ BAĞLANTISI ---
edit_url = "https://docs.google.com/spreadsheets/d/1gow0J5IA0GaB-BjViSKGbIxoZije0klFGgvDWYHdcNA/edit#gid=0"
conn = st.connection("gsheets", type=GSheetsConnection)
df = load_data(edit_url, conn)
usd_kur, eur_kur = get_fx_rates()

# --- 5. YETKİ (Şifreler Düzeldi) ---
if 'auth' not in st.session_state: st.session_state.auth = None
sifreler = {"deneme123": "DENEME", "patron125": "PATRON", "muhasebe007": "MUHASEBE"}

if not st.session_state.auth:
    _, center, _ = st.columns([1, 1.2, 1])
    with center:
        with st.form("login"):
            pwd = st.text_input("Giriş Şifresi", type="password")
            if st.form_submit_button("Erişimi Aç"):
                if pwd in sifreler:
                    st.session_state.auth = sifreler[pwd]
                    st.rerun()
                else: st.error("Hatalı Şifre!")
    st.stop()

# --- 6. SIDEBAR ---
with st.sidebar:
    st.title("🏦 Finans Pro")
    menu = st.radio("Navigasyon", ["🏠 Dashboard", "📝 Veri Yönetimi", "📸 AI Fatura Tarama"])
    st.divider()
    if st.button("🔴 Çıkış"):
        st.session_state.auth = None
        st.rerun()

# --- 7. DASHBOARD ---
if menu == "🏠 Dashboard":
    st.title("⚖️ Finans Dashboard")
    bugun = pd.Timestamp(datetime.now().date())
    
    if not df.empty:
        total_tl = df['Tutar'].sum()
        valid_v = df[df['Vade_Date'].notnull()].copy()
        
        if not valid_v.empty:
            gun_fark = (valid_v['Vade_Date'] - bugun).dt.days
            ort_vade = bugun + timedelta(days=int((valid_v['Tutar'] * gun_fark).sum() / total_tl)) if total_tl > 0 else bugun
            adat = ((valid_v['Tutar'] * gun_fark).sum() * 0.3975) / 365
        else:
            ort_vade, adat = bugun, 0

        st.markdown(f"""
        <div class="metric-container">
            <div class="metric-card" style="background:#2E8B57;"><div class="title">Toplam Borç</div><div class="value">{total_tl:,.2f} ₺</div></div>
            <div class="metric-card" style="background:#0A84FF;"><div class="title">Ort. Vade</div><div class="value">{ort_vade.strftime('%d.%m.%Y')}</div></div>
            <div class="metric-card" style="background:#F77F00;"><div class="title">Adat Yükü</div><div class="value">{adat:,.2f} ₺</div></div>
            <div class="metric-card" style="background:#1C1C1E;"><div class="fx-row">USD: {usd_kur:.4f}</div><div class="fx-row">EUR: {eur_kur:.4f}</div></div>
        </div>
        """, unsafe_allow_html=True)

        st.subheader("📋 Takip Listesi")
        st.dataframe(df, use_container_width=True, hide_index=True)

# --- 8. VERİ YÖNETİMİ ---
elif menu == "📝 Veri Yönetimi":
    st.title("📝 Veri Yönetimi")
    c1, c2 = st.columns(2)
    with c1:
        st.link_button("🌐 Google Sheets'i Aç", edit_url, use_container_width=True)
    with c2:
        show_form = st.toggle("Manuel Giriş Formu")

    if show_form:
        with st.form("manuel_entry"):
            f1, f2, f3 = st.columns(3)
            with f1: st.text_input("Firma Adı")
            with f2: st.number_input("Tutar", min_value=0.0)
            with f3: st.date_input("Vade")
            st.form_submit_button("Kaydet")

# --- 9. AI FATURA TARAMA (Buraya eklendi!) ---
else:
    st.title("📸 AI Fatura Tarama")
    st.info("Fatura resmini yükleyin, Gemini verileri otomatik ayrıştırsın.")
    
    uploaded_file = st.file_uploader("Fatura Görseli Seç (JPG, PNG)", type=["jpg", "jpeg", "png"])
    
    if uploaded_file is not None:
        st.image(uploaded_file, caption="Yüklenen Fatura", width=300)
        if st.button("Faturayı Analiz Et"):
            with st.spinner("AI verileri okuyor..."):
                result = analyze_invoice(uploaded_file)
                if result:
                    st.success("Veriler başarıyla çekildi!")
                    st.json(result)
                    # Formu doldurma önerisi
                    with st.expander("Onayla ve Kaydet"):
                        st.text_input("Firma", value=result.get('firma_adi', ''))
                        st.number_input("Tutar", value=float(result.get('tutar', 0.0)))
                        st.text_input("Asıl Borçlu", value=result.get('borclu', ''))
                        st.button("Sheets'e Gönder")
                else:
                    st.error("Fatura okunamadı, lütfen tekrar deneyin.")

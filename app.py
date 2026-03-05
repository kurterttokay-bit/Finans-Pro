import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection
import yfinance as yf
import google.generativeai as genai
from PIL import Image
import json

# --- 1. SAYFA AYARLARI ---
st.set_page_config(page_title="Finans Pro", layout="wide", page_icon="🏦")

# --- 2. ÖZEL CSS ---
st.markdown("""
    <style>
    .metric-container { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 20px; }
    .metric-card { padding: 15px 5px; border-radius: 12px; text-align: center; color: white; box-shadow: 2px 2px 8px rgba(0,0,0,0.3); border: 1px solid #444; }
    .metric-card .icon { font-size: 24px; margin-bottom: 5px; }
    .metric-card .title { font-size: 14px; opacity: 0.8; font-weight: 400; }
    .metric-card .value { font-size: 18px; font-weight: 700; margin: 2px 0; }
    .fx-row { font-size: 14px; font-weight: 600; display: flex; justify-content: center; gap: 10px; }
    @keyframes border-glow {
        0% { box-shadow: 0 0 5px #ff4b2b; }
        50% { box-shadow: 0 0 20px #ff416c; }
        100% { box-shadow: 0 0 5px #ff4b2b; }
    }
    .alert-bar {
        background: linear-gradient(90deg, #4b0000, #990000); color: white; padding: 15px; border-radius: 12px;
        text-align: center; font-weight: bold; margin-bottom: 20px; border: 2px solid #ff4b2b; animation: border-glow 1.5s infinite;
        display: flex; justify-content: space-between; align-items: center;
    }
    .manage-card { background: #1E1E1E; border: 1px solid #333; padding: 20px; border-radius: 15px; text-align: center; color: white; }
    </style>
""", unsafe_allow_html=True)

# --- 3. VERİ VE API FONKSİYONLARI ---
api_key = st.secrets.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

@st.cache_data(ttl=300)
def get_fx_rates():
    try:
        usd = float(yf.download("USDTRY=X", period="1d", interval="1m", progress=False)['Close'].iloc[-1])
        eur = float(yf.download("EURTRY=X", period="1d", interval="1m", progress=False)['Close'].iloc[-1])
        return usd, eur
    except: return 34.68, 37.45

def load_data(url, connection):
    try:
        raw_df = connection.read(spreadsheet=url, ttl=0)
        raw_df.columns = raw_df.columns.str.strip()
        # Veri temizleme
        raw_df['Tutar'] = pd.to_numeric(raw_df['Tutar'], errors='coerce').fillna(0)
        raw_df['Vade_Date'] = pd.to_datetime(raw_df['Vade'], dayfirst=True, errors='coerce')
        if 'Döviz' not in raw_df.columns: raw_df['Döviz'] = 'TL'
        return raw_df
    except: return pd.DataFrame()

# --- 4. BAĞLANTILAR VE VERİ ---
edit_url = "https://docs.google.com/spreadsheets/d/1gow0J5IA0GaB-BjViSKGbIxoZije0klFGgvDWYHdcNA/edit#gid=0"
conn = st.connection("gsheets", type=GSheetsConnection)
df = load_data(edit_url, conn)
usd_kur, eur_kur = get_fx_rates()

# --- 5. YETKİ KONTROLÜ ---
if 'auth' not in st.session_state: st.session_state.auth = None
sifreler = {"deneme123": "DENEME", "patron125": "PATRON", "muhasebe007": "MUHASEBE"}

if not st.session_state.auth:
    _, center, _ = st.columns([1, 1.2, 1])
    with center:
        st.markdown("<h2 style='text-align:center;'>🏦 Finans Pro Giriş</h2>", unsafe_allow_html=True)
        with st.form("login"):
            pwd = st.text_input("Şifre", type="password")
            if st.form_submit_button("Erişimi Aç"):
                if pwd in sifreler:
                    st.session_state.auth = sifreler[pwd]
                    st.rerun()
                else: st.error("Hatalı Şifre!")
    st.stop()

# --- 6. SIDEBAR ---
with st.sidebar:
    st.title(f"🏦 Finans Pro - {st.session_state.auth}")
    menu = st.radio("Navigasyon", ["🏠 Dashboard", "📝 Veri Yönetimi"])
    st.divider()
    if st.button("🔴 Güvenli Çıkış"):
        st.session_state.auth = None
        st.rerun()

# --- 7. DASHBOARD ---
if menu == "🏠 Dashboard":
    st.title("⚖️ Finans Dashboard")
    
    # Hesaplama: Döviz Çevrimi
    def calculate_tl(row):
        if row['Döviz'] == 'USD': return row['Tutar'] * usd_kur
        elif row['Döviz'] == 'EUR': return row['Tutar'] * eur_kur
        return row['Tutar']

    if not df.empty:
        df['Tutar_TL'] = df.apply(calculate_tl, axis=1)
        bugun = pd.Timestamp(datetime.now().date())
        
        # Filtreleme
        f_total_tl = df['Tutar_TL'].sum()
        valid_df = df[df['Vade_Date'].notnull()].copy()
        
        # Ort Vade & Adat
        if not valid_df.empty:
            gun_farklari = (valid_df['Vade_Date'] - bugun).dt.days
            temp_agirlik = (valid_df['Tutar_TL'] * gun_farklari).sum()
            f_ort_gun = int(round(temp_agirlik / f_total_tl)) if f_total_tl > 0 else 0
            f_ort_vade = bugun + timedelta(days=f_ort_gun)
            f_adat = (temp_agirlik * 0.3975) / 365
        else:
            f_ort_vade, f_adat, f_ort_gun = bugun, 0, 0

        # Metrikler
        gun_metni = f"{f_ort_gun} Gün Kaldı" if f_ort_gun >= 0 else f"{abs(f_ort_gun)} Gün Geçti"
        
        st.markdown(f"""
            <div class="metric-container">
                <div class="metric-card" style="background:#1b4332;"><div class="icon">💰</div><div class="title">Toplam (TL Karşılığı)</div><div class="value">{f_total_tl:,.2f} ₺</div></div>
                <div class="metric-card" style="background:#003566;"><div class="icon">⏳</div><div class="title">Ort. Vade</div><div class="value">{f_ort_vade.strftime('%d.%m.%Y')}</div><div style="font-size:11px;">{gun_metni}</div></div>
                <div class="metric-card" style="background:#9d4c00;"><div class="icon">⚠️</div><div class="title">Adat Yükü (Yıllık %39.75)</div><div class="value">{f_adat:,.2f} ₺</div></div>
                <div class="metric-card" style="background:linear-gradient(90deg, #1C1C1E, #3A3A3C);"><div class="fx-row"><span>💵 USD: {usd_kur:.4f}</span></div><div class="fx-row"><span>💶 EUR: {eur_kur:.4f}</span></div></div>
            </div>
        """, unsafe_allow_html=True)

        # Tablo
        st.subheader("📋 Güncel Evrak Listesi")
        st.dataframe(df.drop(columns=['Vade_Date', 'Tutar_TL']), use_container_width=True, hide_index=True)

# --- 8. VERİ YÖNETİMİ ---
else:
    st.title("📝 Veri Yönetimi")
    
    c1, c2, c3, c4 = st.columns(4)
    with c2: # AI Tarama
        uploaded_file = st.file_uploader("Fatura/Çek Yükle", type=["jpg","png","jpeg"])
        if uploaded_file and 'invoice_data' not in st.session_state:
            with st.spinner("AI Analiz Ediyor..."):
                img = Image.open(uploaded_file).convert("RGB")
                model = genai.GenerativeModel('gemini-1.5-flash')
                response = model.generate_content(["Extract: Firma Adı, Tutar (float), Vade (YYYY-MM-DD), Borclu. JSON format.", img])
                try:
                    res_text = response.text.replace('```json', '').replace('```', '').strip()
                    st.session_state.invoice_data = json.loads(res_text)
                    st.rerun()
                except: st.error("AI okuyamadı!")

    st.divider()
    inv = st.session_state.get('invoice_data', {})
    
    with st.form("kayit_formu"):
        st.subheader("Yeni Kayıt Ekle")
        f1, f2, f3 = st.columns(3)
        with f1:
            f_ad = st.text_input("Firma Adı", value=inv.get('firma_adi', ''))
            f_tip = st.selectbox("Tip", ["Çek", "Senet", "Kredi"])
        with f2:
            f_tutar = st.number_input("Tutar", value=float(inv.get('tutar', 0.0)))
            f_vade = st.date_input("Vade", value=datetime.now())
        with f3:
            f_borclu = st.text_input("Asıl Borçlu", value=inv.get('borclu', ''))
            f_doviz = st.selectbox("Döviz", ["TL", "USD", "EUR"])
        
        if st.form_submit_button("✅ Google Sheets'e Kaydet"):
            yeni_satir = pd.DataFrame([{
                "Firma Adı": f_ad,
                "Evrak Tipi": f_tip,
                "Banka": "Belirtilmedi",
                "Tutar": f_tutar,
                "Vade": f_vade.strftime('%d.%m.%Y'),
                "Asıl borçlu": f_borclu,
                "Döviz": f_doviz
            }])
            
            # Veriyi güncelle ve yaz
            updated_df = pd.concat([df, yeni_satir], ignore_index=True)
            try:
                conn.update(spreadsheet=edit_url, data=updated_df)
                st.cache_data.clear() # Listeyi yenilemek için cache temizle
                st.success("Veri başarıyla buluta gönderildi!")
                if 'invoice_data' in st.session_state: del st.session_state.invoice_data
                st.rerun()
            except Exception as e:
                st.error(f"Bağlantı Hatası: {e}")

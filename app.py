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
    @keyframes border-glow { 0% { box-shadow: 0 0 5px #ff4b2b; } 50% { box-shadow: 0 0 20px #ff416c; } 100% { box-shadow: 0 0 5px #ff4b2b; } }
    .alert-bar {
        background: linear-gradient(90deg, #4b0000, #990000); color: white; padding: 15px; border-radius: 12px;
        text-align: center; font-weight: bold; margin-bottom: 20px; border: 2px solid #ff4b2b; animation: border-glow 1.5s infinite;
        display: flex; justify-content: space-between; align-items: center;
    }
    </style>
""", unsafe_allow_html=True)

# --- 3. FONKSİYONLAR ---
api_key = st.secrets.get("GEMINI_API_KEY")
if api_key: genai.configure(api_key=api_key)

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
        raw_df['Tutar'] = pd.to_numeric(raw_df['Tutar'], errors='coerce').fillna(0)
        raw_df['Vade_Date'] = pd.to_datetime(raw_df['Vade'], dayfirst=True, errors='coerce')
        if 'Döviz' not in raw_df.columns: raw_df['Döviz'] = 'TL'
        return raw_df
    except: return pd.DataFrame()

# --- 4. DATA & LOGIN ---
edit_url = "https://docs.google.com/spreadsheets/d/1gow0J5IA0GaB-BjViSKGbIxoZije0klFGgvDWYHdcNA/edit#gid=0"
conn = st.connection("gsheets", type=GSheetsConnection)
df = load_data(edit_url, conn)
usd_kur, eur_kur = get_fx_rates()

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

# --- 5. SIDEBAR ---
with st.sidebar:
    st.title(f"🏦 Finans Pro")
    st.info(f"Kullanıcı: {st.session_state.auth}")
    menu = st.radio("Menü", ["🏠 Dashboard", "📝 Veri Yönetimi"])
    if st.button("🔴 Çıkış"):
        st.session_state.auth = None
        st.rerun()

# --- 6. DASHBOARD SAYFASI ---
if menu == "🏠 Dashboard":
    st.title("⚖️ Finans Dashboard")
    
    def calculate_tl(row):
        if row['Döviz'] == 'USD': return row['Tutar'] * usd_kur
        elif row['Döviz'] == 'EUR': return row['Tutar'] * eur_kur
        return row['Tutar']

    if not df.empty:
        df['Tutar_TL'] = df.apply(calculate_tl, axis=1)
        bugun = pd.Timestamp(datetime.now().date())
        total_tl = df['Tutar_TL'].sum()
        
        valid_v = df[df['Vade_Date'].notnull()].copy()
        if not valid_v.empty:
            gun_farklari = (valid_v['Vade_Date'] - bugun).dt.days
            temp_agirlik = (valid_v['Tutar_TL'] * gun_farklari).sum()
            ort_gun = int(round(temp_agirlik / total_tl)) if total_tl > 0 else 0
            ort_vade = bugun + timedelta(days=ort_gun)
            adat = (temp_agirlik * 0.3975) / 365
        else:
            ort_vade, adat, ort_gun = bugun, 0, 0

        st.markdown(f"""
            <div class="metric-container">
                <div class="metric-card" style="background:#1b4332;"><div class="icon">💰</div><div class="title">Toplam Borç (TL)</div><div class="value">{total_tl:,.2f} ₺</div></div>
                <div class="metric-card" style="background:#003566;"><div class="icon">⏳</div><div class="title">Ort. Vade</div><div class="value">{ort_vade.strftime('%d.%m.%Y')}</div><div style="font-size:11px;">{ort_gun} Gün Kaldı</div></div>
                <div class="metric-card" style="background:#9d4c00;"><div class="icon">⚠️</div><div class="title">Adat Yükü</div><div class="value">{adat:,.2f} ₺</div></div>
                <div class="metric-card" style="background:linear-gradient(90deg, #1C1C1E, #3A3A3C);"><div class="fx-row"><span>💵 $: {usd_kur:.2f}</span></div><div class="fx-row"><span>💶 €: {eur_kur:.2f}</span></div></div>
            </div>
        """, unsafe_allow_html=True)

        # Kritik Uyarı
        valid_v['fark'] = (valid_v['Vade_Date'] - bugun).dt.days
        kritik = valid_v[(valid_v['fark'] <= 7) & (valid_v['fark'] >= 0)]
        if not kritik.empty:
            st.markdown(f'<div class="alert-bar"><span>🔥</span><span>ACİL: 7 Gün İçinde {len(kritik)} Ödeme Var!</span><span>🔥</span></div>', unsafe_allow_html=True)

        st.subheader("📋 Genel Takip Listesi")
        st.dataframe(df.drop(columns=['Vade_Date', 'Tutar_TL']), use_container_width=True, hide_index=True)

# --- 7. VERİ YÖNETİMİ (ONAY MEKANİZMALI) ---
else:
    st.title("📝 Veri Girişi & AI Tarama")
    
    c_fat, c_cek = st.columns(2)
    
    with c_fat:
        st.markdown("### 📄 Fatura İşle")
        up_fat = st.file_uploader("Fatura Yükle", type=["jpg","png","jpeg"], key="u_fat")
        if up_fat and st.button("Faturayı Analiz Et"):
            with st.spinner("Gemini inceliyor..."):
                img = Image.open(up_fat).convert("RGB")
                model = genai.GenerativeModel('gemini-1.5-flash')
                prompt = "Bu bir fatura. Firma adı, Tutar (sayı), Vade (GG.AA.YYYY) bilgilerini JSON olarak ver."
                resp = model.generate_content([prompt, img])
                st.session_state.temp_data = json.loads(resp.text.replace('```json', '').replace('```', '').strip())
                st.session_state.temp_tip = "Fatura"

    with c_cek:
        st.markdown("### 🎫 Çek/Senet İşle")
        up_cek = st.file_uploader("Çek Yükle", type=["jpg","png","jpeg"], key="u_cek")
        if up_cek and st.button("Çeki Analiz Et"):
            with st.spinner("Çek okunuyor..."):
                img = Image.open(up_cek).convert("RGB")
                model = genai.GenerativeModel('gemini-1.5-flash')
                prompt = "Bu bir çek. Keşideci(firma), Tutar(sayı), Vade(GG.AA.YYYY), Banka bilgilerini JSON olarak ver."
                resp = model.generate_content([prompt, img])
                st.session_state.temp_data = json.loads(resp.text.replace('```json', '').replace('```', '').strip())
                st.session_state.temp_tip = "Çek"

    # ARA DURAK: ONAY FORMU
    if 'temp_data' in st.session_state:
        st.divider()
        st.warning(f"🔎 AI'dan Gelen {st.session_state.temp_tip} Verisi: Lütfen Kontrol Edin")
        td = st.session_state.temp_data
        
        with st.form("onay_istasyonu"):
            f1, f2, f3 = st.columns(3)
            with f1:
                final_firma = st.text_input("Firma/Borçlu", value=td.get('firma_adi', td.get('firma', td.get('borclu', ''))))
                final_banka = st.text_input("Banka", value=td.get('banka', ''))
            with f2:
                final_tutar = st.number_input("Tutar", value=float(str(td.get('tutar', 0)).replace('.','').replace(',','.')) if td.get('tutar') else 0.0)
                final_vade = st.text_input("Vade (GG.AA.YYYY)", value=td.get('vade', ''))
            with f3:
                final_tip = st.selectbox("Tür", ["Çek", "Senet", "Fatura"], index=0 if st.session_state.temp_tip=="Çek" else 2)
                final_doviz = st.selectbox("Döviz", ["TL", "USD", "EUR"])
            
            if st.form_submit_button("✅ Tamam Doğru, Taşı"):
                yeni = pd.DataFrame([{
                    "Firma Adı": final_firma,
                    "Evrak Tipi": final_tip,
                    "Banka": final_banka,
                    "Tutar": final_tutar,
                    "Vade": final_vade,
                    "Döviz": final_doviz
                }])
                
                updated_df = pd.concat([df, yeni], ignore_index=True)
                conn.update(spreadsheet=edit_url, data=updated_df)
                st.cache_data.clear()
                del st.session_state.temp_data
                st.success("Veri ana tabloya başarıyla taşındı!")
                st.rerun()

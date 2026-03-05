import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection
import yfinance as yf
import google.generativeai as genai
from PIL import Image
import json
import io

# --- 1. AYARLAR ---
st.set_page_config(page_title="Finans Pro", layout="wide", page_icon="🏦")

# --- 2. CSS (Daha Modern ve Fonksiyonel) ---
st.markdown("""
    <style>
    .metric-container { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 20px; }
    .metric-card { padding: 15px 5px; border-radius: 12px; text-align: center; color: white; border: 1px solid #444; }
    .manage-card { 
        background: #1E1E1E; border: 1px solid #333; padding: 20px; border-radius: 15px; 
        text-align: center; color: white; min-height: 180px; display: flex; flex-direction: column; justify-content: space-between;
    }
    .manage-card:hover { border-color: #00ff88; }
    .alert-bar {
        background: linear-gradient(90deg, #4b0000, #990000); color: white; padding: 15px; border-radius: 12px;
        text-align: center; font-weight: bold; margin-bottom: 20px; border: 2px solid #ff4b2b;
    }
    </style>
""", unsafe_allow_html=True)

# --- 3. VERİ BAĞLANTISI ---
edit_url = "https://docs.google.com/spreadsheets/d/1gow0J5IA0GaB-BjViSKGbIxoZije0klFGgvDWYHdcNA/edit#gid=0"
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=300)
def get_fx_rates():
    try:
        usd = float(yf.download("USDTRY=X", period="1d", interval="1m", progress=False)['Close'].iloc[-1])
        eur = float(yf.download("EURTRY=X", period="1d", interval="1m", progress=False)['Close'].iloc[-1])
        return usd, eur
    except: return 34.68, 37.45

def load_data():
    df = conn.read(spreadsheet=edit_url, ttl=0)
    df.columns = df.columns.str.strip()
    df['Tutar'] = pd.to_numeric(df['Tutar'], errors='coerce').fillna(0)
    df['Vade_Date'] = pd.to_datetime(df['Vade'], dayfirst=True, errors='coerce')
    if 'Döviz' not in df.columns: df['Döviz'] = 'TL'
    return df

df = load_data()
usd_kur, eur_kur = get_fx_rates()

# --- 4. YETKİ KONTROLÜ ---
if 'auth' not in st.session_state: st.session_state.auth = None
sifreler = {"deneme123": "DENEME", "patron125": "PATRON", "muhasebe007": "MUHASEBE"}
if not st.session_state.auth:
    _, center, _ = st.columns([1, 1.2, 1])
    with center:
        st.markdown("<h2 style='text-align:center;'>🏦 Giriş</h2>", unsafe_allow_html=True)
        with st.form("login"):
            pwd = st.text_input("Şifre", type="password")
            if st.form_submit_button("Erişimi Aç"):
                if pwd in sifreler:
                    st.session_state.auth = sifreler[pwd]
                    st.rerun()
                else: st.error("Hatalı!")
    st.stop()

# --- 5. NAVİGASYON ---
menu = st.sidebar.radio("Menü", ["🏠 Dashboard", "📝 Veri Yönetimi"])

# --- 6. DASHBOARD ---
if menu == "🏠 Dashboard":
    st.title("⚖️ Finans Dashboard")
    def calculate_tl(row):
        if row['Döviz'] == 'USD': return row['Tutar'] * usd_kur
        elif row['Döviz'] == 'EUR': return row['Tutar'] * eur_kur
        return row['Tutar']
    
    df['Tutar_TL'] = df.apply(calculate_tl, axis=1)
    total_tl = df['Tutar_TL'].sum()
    bugun = pd.Timestamp(datetime.now().date())
    
    # Metrikler ve Liste (Eski görsellik korunuyor)
    st.markdown(f'<div class="metric-container"><div class="metric-card" style="background:#1b4332;">💰 Toplam: {total_tl:,.2f} ₺</div></div>', unsafe_allow_html=True)
    st.dataframe(df.drop(columns=['Vade_Date', 'Tutar_TL']), use_container_width=True, hide_index=True)

# --- 7. VERİ YÖNETİMİ (4'LÜ KART SİSTEMİ) ---
else:
    st.title("📝 Veri İşlem Merkezi")
    
    c1, c2, c3, c4 = st.columns(4)
    
    with c1: # TASLAK İNDİR
        st.markdown('<div class="manage-card">📥<br><b>Taslak</b><br><small>Excel Şablonu</small></div>', unsafe_allow_html=True)
        taslak_df = pd.DataFrame(columns=["Firma Adı", "Evrak Tipi", "Banka", "Tutar", "Vade", "Asıl borçlu", "Döviz"])
        csv = taslak_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button("Dosyayı İndir", csv, "finans_taslak.csv")

    with c2: # EXCEL YÜKLE
        st.markdown('<div class="manage-card">📤<br><b>Toplu Yükle</b><br><small>Doldurduğun Taslak</small></div>', unsafe_allow_html=True)
        up_excel = st.file_uploader("Dosya Seç", type=["csv", "xlsx"], label_visibility="collapsed")
        if up_excel:
            if st.button("Tabloya İşle"):
                new_data = pd.read_csv(up_excel) if up_excel.name.endswith('csv') else pd.read_excel(up_excel)
                updated_df = pd.concat([df, new_data], ignore_index=True)
                conn.update(spreadsheet=edit_url, data=updated_df)
                st.success("Toplu veri eklendi!")
                st.rerun()

    with c3: # E-TABLO GİT
        st.markdown('<div class="manage-card">🌐<br><b>E-Tablo</b><br><small>Google Sheets</small></div>', unsafe_allow_html=True)
        st.link_button("Tabloyu Aç", edit_url)

    with c4: # MANUEL EKLE
        st.markdown('<div class="manage-card">✍️<br><b>Manuel</b><br><small>Formu Aç</small></div>', unsafe_allow_html=True)
        m_ac = st.toggle("Formu Göster")

    # --- AI VE MANUEL GİRİŞ ALANI ---
    st.divider()
    col_a, col_b = st.columns(2)
    
    with col_a:
        st.subheader("📸 AI Tarama (Fatura/Çek)")
        up_img = st.file_uploader("Görsel Yükle", type=["jpg","png","jpeg"])
        if up_img:
            tip = st.radio("Bu nedir?", ["Fatura", "Çek/Senet"], horizontal=True)
            if st.button("AI Analizi Başlat"):
                try:
                    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    img = Image.open(up_img).convert("RGB")
                    prompt = f"Bu bir {tip}. Firma/Borçlu ismi, Tutar, Vade (GG.AA.YYYY), Banka bilgilerini JSON ver."
                    resp = model.generate_content([prompt, img])
                    st.session_state.temp_data = json.loads(resp.text.replace('```json', '').replace('```', '').strip())
                    st.rerun()
                except Exception as e: st.error(f"AI Hatası: {e}")

    # MANUEL FORM VEYA AI ONAY FORMU
    if m_ac or 'temp_data' in st.session_state:
        td = st.session_state.get('temp_data', {})
        st.info("Aşağıdaki bilgileri kontrol edip onaylayın.")
        with st.form("onay_formu"):
            f1, f2, f3 = st.columns(3)
            with f1:
                v_f = st.text_input("Firma", value=td.get('firma_adi', td.get('borclu', '')))
                v_t = st.selectbox("Tür", ["Çek", "Senet", "Fatura"])
            with f2:
                v_m = st.number_input("Tutar", value=float(td.get('tutar', 0.0)))
                v_v = st.text_input("Vade (GG.AA.YYYY)", value=td.get('vade', ''))
            with f3:
                v_b = st.text_input("Banka", value=td.get('banka', ''))
                v_d = st.selectbox("Döviz", ["TL", "USD", "EUR"])
            
            if st.form_submit_button("✅ Kaydet"):
                yeni = pd.DataFrame([{"Firma Adı": v_f, "Evrak Tipi": v_t, "Banka": v_b, "Tutar": v_m, "Vade": v_v, "Döviz": v_d}])
                conn.update(spreadsheet=edit_url, data=pd.concat([df, yeni], ignore_index=True))
                st.cache_data.clear()
                if 'temp_data' in st.session_state: del st.session_state.temp_data
                st.success("Kaydedildi!")
                st.rerun()

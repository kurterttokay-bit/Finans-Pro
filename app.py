import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection
import yfinance as yf
import google.generativeai as genai
from PIL import Image
import json

# --- 1. AYARLAR VE GÜVENLİK ---
st.set_page_config(page_title="Finans Pro Final", layout="wide", page_icon="🏦")

if 'auth' not in st.session_state: st.session_state.auth = None
sifreler = {"patron125": "PATRON", "muhasebe007": "MUHASEBE", "kurter": "YONETICI"}

if not st.session_state.auth:
    _, center, _ = st.columns([1, 1.2, 1])
    with center:
        st.markdown("<h2 style='text-align:center;'>🏦 Finans Sistemi Giriş</h2>", unsafe_allow_html=True)
        with st.form("login"):
            pwd = st.text_input("Şifre", type="password")
            if st.form_submit_button("Sistemi Aç"):
                if pwd in sifreler:
                    st.session_state.auth = sifreler[pwd]
                    st.rerun()
                else: st.error("Geçersiz Şifre!")
    st.stop()

# --- 2. DİNAMİK MODEL SEÇİMİ (Fallback Geliştirildi) ---
api_key = st.secrets.get("GEMINI_API_KEY")
target_model = "models/gemini-1.5-pro" # En güçlü garanti fallback
if api_key:
    genai.configure(api_key=api_key)
    try:
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        # Öncelik sırası: flash-latest > flash > pro
        if any("1.5-flash-latest" in m for m in models):
            target_model = next(m for m in models if "1.5-flash-latest" in m)
        elif any("1.5-flash" in m for m in models):
            target_model = next(m for m in models if "1.5-flash" in m)
        elif any("1.5-pro" in m for m in models):
            target_model = next(m for m in models if "1.5-pro" in m)
    except: pass

# --- 3. VERİ VE DÖVİZ BAĞLANTISI ---
edit_url = "https://docs.google.com/spreadsheets/d/1gow0J5IA0GaB-BjViSKGbIxoZije0klFGgvDWYHdcNA/edit#gid=0"
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=300)
def get_fx_rates():
    try:
        usd = float(yf.download("USDTRY=X", period="1d", interval="1m", progress=False)['Close'].iloc[-1])
        eur = float(yf.download("EURTRY=X", period="1d", interval="1m", progress=False)['Close'].iloc[-1])
        return usd, eur
    except: return 34.60, 37.40

def load_data():
    try:
        df = conn.read(spreadsheet=edit_url, ttl=0)
        df.columns = df.columns.str.strip()
        df['Tutar'] = pd.to_numeric(df['Tutar'], errors='coerce').fillna(0)
        df['Vade_Date'] = pd.to_datetime(df['Vade'], dayfirst=True, errors='coerce')
        if 'Döviz' not in df.columns: df['Döviz'] = 'TL'
        return df
    except: return pd.DataFrame(columns=["Firma Adı", "Evrak Tipi", "Banka", "Tutar", "Vade", "Döviz"])

df = load_data()
usd_kur, eur_kur = get_fx_rates()

# --- 4. CSS TASARIMI ---
st.markdown("""
    <style>
    .metric-card { padding: 15px; border-radius: 12px; text-align: center; color: white; border: 1px solid #444; }
    .manage-box { background: #1E1E1E; border: 1px solid #333; padding: 20px; border-radius: 15px; text-align: center; color: white; }
    </style>
""", unsafe_allow_html=True)

# ---  navigation ---
menu = st.sidebar.radio("Menü", ["🏠 Dashboard", "📝 Veri Yönetimi"])
if st.sidebar.button("🔴 Güvenli Çıkış"):
    st.session_state.auth = None
    st.rerun()

# --- 5. DASHBOARD (Metrikler Geri Geldi) ---
if menu == "🏠 Dashboard":
    st.title("⚖️ Finansal Durum Paneli")
    
    def to_tl(row):
        if row['Döviz'] == 'USD': return row['Tutar'] * usd_kur
        if row['Döviz'] == 'EUR': return row['Tutar'] * eur_kur
        return row['Tutar']

    df['Tutar_TL'] = df.apply(to_tl, axis=1)
    total_tl = df['Tutar_TL'].sum()
    bugun = pd.Timestamp(datetime.now().date())
    
    # Ortamala Vade ve Adat Hesabı
    valid_v = df[df['Vade_Date'].notnull()].copy()
    if not valid_v.empty:
        gun_farklari = (valid_v['Vade_Date'] - bugun).dt.days
        temp_agirlik = (valid_v['Tutar_TL'] * gun_farklari).sum()
        ort_gun = int(round(temp_agirlik / total_tl)) if total_tl > 0 else 0
        ort_vade = bugun + timedelta(days=ort_gun)
        adat = (temp_agirlik * 0.3975) / 365
    else:
        ort_vade, adat, ort_gun = bugun, 0, 0

    # Üst Metrik Kutuları
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f'<div class="metric-card" style="background:#1b4332;">💰 Toplam Borç<br><b>{total_tl:,.2f} ₺</b></div>', unsafe_allow_html=True)
    c2.markdown(f'<div class="metric-card" style="background:#003566;">⏳ Ort. Vade<br><b>{ort_vade.strftime("%d.%m.%Y")}</b></div>', unsafe_allow_html=True)
    c3.markdown(f'<div class="metric-card" style="background:#9d4c00;">⚠️ Adat Yükü<br><b>{adat:,.2f} ₺</b></div>', unsafe_allow_html=True)
    c4.markdown(f'<div class="metric-card" style="background:#2D2D2D;">💵 Kur: {usd_kur:.2f}<br>💶 Kur: {eur_kur:.2f}</div>', unsafe_allow_html=True)

    st.divider()
    st.subheader("📊 Güncel Evrak Listesi")
    st.dataframe(df.drop(columns=['Vade_Date', 'Tutar_TL']), use_container_width=True, hide_index=True)

# --- 6. VERİ YÖNETİMİ (Walrus Kaldırıldı, Prompt Katılaştırıldı) ---
else:
    st.title("📝 İşlem Merkezi")
    
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown('<div class="manage-box">📥 Taslak</div>', unsafe_allow_html=True)
        taslak = pd.DataFrame(columns=["Firma Adı", "Evrak Tipi", "Banka", "Tutar", "Vade", "Döviz"])
        st.download_button("İndir", taslak.to_csv(index=False).encode('utf-8-sig'), "finans_taslak.csv")
    
    with k2:
        st.markdown('<div class="manage-box">📤 Excel Yükle</div>', unsafe_allow_html=True)
        up_file = st.file_uploader("Seç", type=["csv","xlsx"], label_visibility="collapsed")
        if up_file is not None: # Walrus operator yerine standart kontrol
            if st.button("Tabloya Aktar"):
                new_data = pd.read_csv(up_file) if up_file.name.endswith('csv') else pd.read_excel(up_file)
                conn.update(spreadsheet=edit_url, data=pd.concat([df, new_data], ignore_index=True))
                st.cache_data.clear() # Kesin temizlik
                st.success("Veriler eklendi!")
                st.rerun()

    with k3:
        st.markdown('<div class="manage-box">🌐 E-Tablo</div>', unsafe_allow_html=True)
        st.link_button("Git", edit_url)
    
    with k4:
        st.markdown('<div class="manage-box">✍️ Manuel</div>', unsafe_allow_html=True)
        m_ac = st.toggle("Form", value='temp_data' in st.session_state)

    st.divider()

    # AI VE ONAY MEKANİZMASI
    st.subheader("📸 Belge Analizi")
    up_img = st.file_uploader("Fatura/Çek Görseli", type=["jpg","png","jpeg"])
    
    if up_img and st.button("AI İle Tara"):
        with st.spinner("Belge çözümleniyor..."):
            try:
                model = genai.GenerativeModel(target_model)
                img = Image.open(up_img).convert("RGB")
                # KATI PROMPT
                prompt = "Analyze this document. Respond STRICTLY with valid JSON. Do not include any text, markdown code blocks, or explanations outside the JSON. Format: {'firma': 'str', 'tutar': float, 'vade': 'DD.MM.YYYY', 'banka': 'str'}"
                resp = model.generate_content([prompt, img])
                
                # Güvenli JSON Ayıklama
                clean_json = resp.text.strip().replace('```json', '').replace('```', '')
                try:
                    st.session_state.temp_data = json.loads(clean_json)
                    st.rerun()
                except:
                    st.error("AI veriyi okudu ama formatlayamadı. Lütfen formu doldurun.")
                    st.session_state.temp_data = {} # Fallback: Formu boş aç
            except Exception as e: st.error(f"Hata: {e}")

    if m_ac or 'temp_data' in st.session_state:
        td = st.session_state.get('temp_data', {})
        with st.form("onay_formu"):
            f1, f2, f3 = st.columns(3)
            with f1:
                v_firma = st.text_input("Firma Adı", value=td.get('firma', ''))
                v_tip = st.selectbox("Evrak Tipi", ["Fatura", "Çek", "Senet"])
            with f2:
                v_tutar = st.number_input("Tutar", value=float(td.get('tutar', 0.0)))
                try: dv = datetime.strptime(td.get('vade', ''), '%d.%m.%Y')
                except: dv = datetime.now()
                v_vade = st.date_input("Vade", value=dv) # Tarih inputu güvenliği
            with f3:
                v_banka = st.text_input("Banka", value=td.get('banka', ''))
                v_doviz = st.selectbox("Döviz", ["TL", "USD", "EUR"])
            
            if st.form_submit_button("✅ Onayla ve Gönder"):
                yeni = pd.DataFrame([{
                    "Firma Adı": v_firma, "Evrak Tipi": v_tip, "Banka": v_banka,
                    "Tutar": v_tutar, "Vade": v_vade.strftime('%d.%m.%Y'), "Döviz": v_doviz
                }])
                conn.update(spreadsheet=edit_url, data=pd.concat([df, yeni], ignore_index=True))
                st.cache_data.clear()
                if 'temp_data' in st.session_state: del st.session_state.temp_data
                st.success("Kayıt tamamlandı!")
                st.rerun()

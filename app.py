import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection
import yfinance as yf
import google.generativeai as genai
from PIL import Image
import json

# --- 1. AYARLAR VE GÜVENLİK ---
st.set_page_config(page_title="Finans Pro Enterprise", layout="wide", page_icon="🏦")

if 'auth' not in st.session_state: st.session_state.auth = None
sifreler = {"patron125": "PATRON", "muhasebe007": "MUHASEBE", "kurter": "YONETICI"}

if not st.session_state.auth:
    _, center, _ = st.columns([1, 1.2, 1])
    with center:
        st.markdown("<h2 style='text-align:center;'>🏦 Finans Giriş</h2>", unsafe_allow_html=True)
        with st.form("login"):
            pwd = st.text_input("Şifre", type="password")
            if st.form_submit_button("Sistemi Aç"):
                if pwd in sifreler:
                    st.session_state.auth = sifreler[pwd]
                    st.rerun()
                else: st.error("Hatalı!")
    st.stop()

# --- 2. DİNAMİK AI MODEL SEÇİMİ ---
api_key = st.secrets.get("GEMINI_API_KEY")
target_model = "gemini-1.0-pro"  # garanti fallback

if api_key:
    genai.configure(api_key=api_key)
    try:
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        if any("1.5-flash-latest" in m for m in available_models):
            target_model = [m for m in available_models if "1.5-flash-latest" in m][0]
        elif any("1.5-flash" in m for m in available_models):
            target_model = [m for m in available_models if "1.5-flash" in m][0]
    except Exception as e:
        st.sidebar.warning(f"Model listeleme hatası: {e}")

# --- 3. VERİ BAĞLANTISI ---
edit_url = "https://docs.google.com/spreadsheets/d/1gow0J5IA0GaB-BjViSKGbIxoZije0klFGgvDWYHdcNA/edit#gid=0"
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=60)
def get_fx_rates():
    try:
        usd = float(yf.download("USDTRY=X", period="1d", interval="1m", progress=False)['Close'].iloc[-1])
        eur = float(yf.download("EURTRY=X", period="1d", interval="1m", progress=False)['Close'].iloc[-1])
        return usd, eur
    except: return 34.65, 37.45

def load_data():
    try:
        df = conn.read(spreadsheet=edit_url, ttl=0)
        df.columns = df.columns.str.strip()
        df['Tutar'] = pd.to_numeric(df['Tutar'], errors='coerce').fillna(0)
        df['Vade_Date'] = pd.to_datetime(df['Vade'], dayfirst=True, errors='coerce')
        return df
    except: return pd.DataFrame(columns=["Firma Adı", "Evrak Tipi", "Banka", "Tutar", "Vade", "Döviz"])

df = load_data()
usd_kur, eur_kur = get_fx_rates()

# --- 4. SIDEBAR ---
with st.sidebar:
    st.title("🏦 Finans Pro")
    st.info(f"Yetki: {st.session_state.auth}")
    menu = st.radio("Menü", ["🏠 Dashboard", "📝 Veri Yönetimi"])
    adat_orani = st.number_input("Adat Oranı (%)", value=39.75) / 100
    if st.button("🔴 Çıkış"):
        st.session_state.auth = None
        st.rerun()

# --- 5. DASHBOARD ---
if menu == "🏠 Dashboard":
    st.title("⚖️ Finansal Durum")
    df['Tutar_TL'] = df.apply(lambda r: r['Tutar'] * (usd_kur if r.get('Döviz') == 'USD' else (eur_kur if r.get('Döviz') == 'EUR' else 1)), axis=1)
    total_tl = df['Tutar_TL'].sum()
    bugun = pd.Timestamp(datetime.now().date())
    valid_v = df[df['Vade_Date'].notnull()].copy()
    
    if not valid_v.empty:
        gun_farklari = (valid_v['Vade_Date'] - bugun).dt.days
        temp_agirlik = (valid_v['Tutar_TL'] * gun_farklari).sum()
        ort_vade = bugun + timedelta(days=int(round(temp_agirlik / total_tl))) if total_tl > 0 else bugun
        adat_yuku = (temp_agirlik * adat_orani) / 365
    else: ort_vade, adat_yuku = bugun, 0

    c1, c2, c3 = st.columns(3)
    c1.metric("Toplam Borç", f"{total_tl:,.2f} ₺")
    c2.metric("Ort. Vade", ort_vade.strftime("%d.%m.%Y"))
    c3.metric("Adat Yükü", f"{adat_yuku:,.2f} ₺")
    st.dataframe(df.drop(columns=['Vade_Date', 'Tutar_TL']), use_container_width=True, hide_index=True)
# --- 6. VERİ YÖNETİMİ (Geliştirilmiş) ---
else:
    st.title("📝 İşlem Merkezi")
    
    up_img = st.file_uploader("📸 Fatura/Çek Görseli", type=["jpg","png","jpeg"])
    
    if up_img and st.button("AI İle Analiz Et"):
        # 1.0 Pro görsel desteklemediği için en az 1.5 Flash kullanılmalı
        actual_model = target_model if "1.5" in target_model else "gemini-1.5-flash"
        with st.spinner(f"{actual_model} ile analiz ediliyor..."):
            try:
                model = genai.GenerativeModel(actual_model)
                img = Image.open(up_img).convert("RGB")
                prompt = "Perform OCR. Respond ONLY JSON: {'firma': 'str', 'tutar': float, 'vade': 'DD.MM.YYYY', 'banka': 'str'}"
                resp = model.generate_content([prompt, img])
                
                # Yanıt yakalama (Senin eklediğin güvenli yöntem)
                raw_text = getattr(resp, "text", None)
                if not raw_text and hasattr(resp, "candidates"):
                    raw_text = resp.candidates[0].content.parts[0].text
                
                if raw_text:
                    clean_json = raw_text.strip().replace('```json', '').replace('```', '')
                    st.session_state.temp_data = json.loads(clean_json)
                    st.success("Veriler ayrıştırıldı!")
                    st.rerun()
            except Exception as e:
                st.error(f"AI Analiz Hatası: {e}. Lütfen Gemini 1.5 sürümünü kullandığınızdan emin olun.")

    # Kayıt butonundaki concat işlemini garantiye alalım
    if st.form_submit_button("✅ Google Sheets'e Kaydet"):
        try:
            # Mevcut DF boşsa kolonları manuel oluştur
            yeni_row = pd.DataFrame([{"Firma Adı": v_f, "Evrak Tipi": v_t, "Banka": v_b, "Tutar": v_m, "Vade": v_v.strftime('%d.%m.%Y'), "Döviz": v_d}])
            
            # Eğer Sheets boş gelmişse df'i yeni_row ile başlat
            updated_df = pd.concat([df, yeni_row], ignore_index=True) if not df.empty else yeni_row
            
            conn.update(spreadsheet=edit_url, data=updated_df)
            st.cache_data.clear()
            st.success("Kayıt Başarılı!")
            st.rerun()

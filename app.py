import streamlit as st
import pandas as pd
from datetime import datetime
from streamlit_gsheets import GSheetsConnection
import yfinance as yf
import google.generativeai as genai
from PIL import Image
import json
import io

# --- 1. AYARLAR & GÜVENLİK ---
st.set_page_config(page_title="Finans Pro", layout="wide", page_icon="🏦")

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
                else: st.error("Hatalı Şifre!")
    st.stop()

# --- 2. MODEL ADI VE SÜRÜM UYUMU (Dinamik Seçim) ---
api_key = st.secrets.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)
    try:
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        # Öncelikle flash-latest, yoksa flash, o da yoksa listedeki ilkini seç
        target_model = next((m for m in models if "1.5-flash-latest" in m), 
                           next((m for m in models if "1.5-flash" in m), models[0]))
    except:
        target_model = "models/gemini-1.5-flash" # Fallback

# --- 3. VERİ BAĞLANTISI ---
edit_url = "https://docs.google.com/spreadsheets/d/1gow0J5IA0GaB-BjViSKGbIxoZije0klFGgvDWYHdcNA/edit#gid=0"
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=300)
def load_data():
    df = conn.read(spreadsheet=edit_url, ttl=0)
    df.columns = df.columns.str.strip()
    df['Tutar'] = pd.to_numeric(df['Tutar'], errors='coerce').fillna(0)
    # Vade sütununu datetime yapalım
    df['Vade_Date'] = pd.to_datetime(df['Vade'], dayfirst=True, errors='coerce')
    if 'Döviz' not in df.columns: df['Döviz'] = 'TL'
    return df

df = load_data()

# --- 4. CSS ---
st.markdown("""
    <style>
    .manage-card { 
        background: #1E1E1E; border: 1px solid #333; padding: 20px; border-radius: 15px; 
        text-align: center; color: white; min-height: 140px; display: flex; flex-direction: column; justify-content: center;
    }
    .manage-card:hover { border-color: #00ff88; }
    </style>
""", unsafe_allow_html=True)

# --- 5. NAVİGASYON ---
menu = st.sidebar.radio("Menü", ["🏠 Dashboard", "📝 Veri Yönetimi"])
if st.sidebar.button("🔴 Çıkış"):
    st.session_state.auth = None
    st.rerun()

# --- 6. DASHBOARD ---
if menu == "🏠 Dashboard":
    st.title("⚖️ Finans Dashboard")
    st.dataframe(df.drop(columns=['Vade_Date']), use_container_width=True, hide_index=True)

# --- 7. VERİ YÖNETİMİ ---
else:
    st.title("📝 Veri İşlem Merkezi")
    c1, c2, c3, c4 = st.columns(4)
    
    with c1:
        st.markdown('<div class="manage-card">📥<br><b>Taslak İndir</b></div>', unsafe_allow_html=True)
        taslak = pd.DataFrame(columns=["Firma Adı", "Evrak Tipi", "Banka", "Tutar", "Vade", "Asıl borçlu", "Döviz"])
        st.download_button("CSV İndir", taslak.to_csv(index=False).encode('utf-8-sig'), "taslak.csv")

    with c2:
        st.markdown('<div class="manage-card">📤<br><b>Excel Yükle</b></div>', unsafe_allow_html=True)
        up_file = st.file_uploader("Upload", type=["csv","xlsx"], label_visibility="collapsed")
        if up_excel := up_file:
            if st.button("Tabloya İşle"):
                new_df = pd.read_csv(up_excel) if up_excel.name.endswith('csv') else pd.read_excel(up_excel)
                conn.update(spreadsheet=edit_url, data=pd.concat([df, new_df], ignore_index=True))
                st.cache_data.clear() # VERİ GÜNCELLEME SONRASI CACHE TEMİZLİĞİ
                st.success("Aktarıldı!")
                st.rerun()

    with c3:
        st.markdown('<div class="manage-card">🌐<br><b>E-Tablo</b></div>', unsafe_allow_html=True)
        st.link_button("Sheets'i Aç", edit_url)

    with c4:
        st.markdown('<div class="manage-card">✍️<br><b>Manuel Ekle</b></div>', unsafe_allow_html=True)
        m_ac = st.toggle("Formu Göster", value='temp_data' in st.session_state)

    st.divider()
    
    # --- AI ANALİZ ---
    col_a, col_b = st.columns([1, 2])
    with col_a:
        st.subheader("📸 AI Tarama")
        up_img = st.file_uploader("Fatura/Çek Görseli", type=["jpg","png","jpeg"])
        if up_img and st.button("Analiz Et"):
            try:
                model = genai.GenerativeModel(target_model)
                img = Image.open(up_img).convert("RGB")
                prompt = "Analyze document. Return ONLY JSON: {'firma': 'str', 'tutar': float, 'vade': 'DD.MM.YYYY', 'banka': 'str'}"
                resp = model.generate_content([prompt, img])
                
                # JSON GÜVENLİĞİ & FALLBACK
                clean_text = resp.text.strip().replace('```json', '').replace('```', '')
                try:
                    st.session_state.temp_data = json.loads(clean_text)
                    st.rerun()
                except json.JSONDecodeError:
                    st.error("AI veriyi okudu ama ayrıştıramadı. Formu sizin için açtım, lütfen kontrol ederek doldurun.")
                    st.session_state.temp_data = {} # Formu tetiklemek için boş ata
            except Exception as e:
                st.error(f"Bağlantı Hatası: {e}")

    # --- ONAY & MANUEL FORM (Vade Formatı st.date_input yapıldı) ---
    if m_ac or 'temp_data' in st.session_state:
        td = st.session_state.get('temp_data', {})
        st.info("Bilgileri onaylayın:")
        with st.form("onay_formu"):
            f1, f2, f3 = st.columns(3)
            with f1:
                v_f = st.text_input("Firma/Borçlu", value=td.get('firma', ''))
                v_t = st.selectbox("Tür", ["Çek", "Senet", "Fatura"])
            with f2:
                v_m = st.number_input("Tutar", value=float(td.get('tutar', 0.0)))
                # VADE FORMATI GÜVENLİĞİ
                try: default_date = datetime.strptime(td.get('vade', ''), '%d.%m.%Y')
                except: default_date = datetime.now()
                v_v = st.date_input("Vade Tarihi", value=default_date)
            with f3:
                v_b = st.text_input("Banka", value=td.get('banka', ''))
                v_d = st.selectbox("Döviz", ["TL", "USD", "EUR"])
            
            if st.form_submit_button("✅ Ana Tabloya Kaydet"):
                yeni_row = pd.DataFrame([{
                    "Firma Adı": v_f, "Evrak Tipi": v_t, "Banka": v_b, 
                    "Tutar": v_m, "Vade": v_v.strftime('%d.%m.%Y'), "Döviz": v_d
                }])
                conn.update(spreadsheet=edit_url, data=pd.concat([df, yeni_row], ignore_index=True))
                st.cache_data.clear()
                if 'temp_data' in st.session_state: del st.session_state.temp_data
                st.success("Kayıt Başarılı!")
                st.rerun()

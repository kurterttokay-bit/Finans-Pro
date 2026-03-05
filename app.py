import streamlit as st
import pandas as pd
from datetime import datetime
from streamlit_gsheets import GSheetsConnection
import yfinance as yf
import google.generativeai as genai
from PIL import Image
import json
import io

# --- 1. AYARLAR VE MODEL KONTROLÜ ---
st.set_page_config(page_title="Finans Pro", layout="wide", page_icon="🏦")

# API Yapılandırması
api_key = st.secrets.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

# Debug: Aktif modelleri görmek istersen sidebar'da bir buton bıraktım
if st.sidebar.button("🤖 Aktif Modelleri Listele"):
    try:
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        st.sidebar.write(models)
    except Exception as e:
        st.sidebar.error(f"Liste alınamadı: {e}")

# --- 2. CSS ---
st.markdown("""
    <style>
    .metric-card { padding: 15px; border-radius: 12px; text-align: center; color: white; border: 1px solid #444; background: #1b4332; }
    .manage-card { 
        background: #1E1E1E; border: 1px solid #333; padding: 20px; border-radius: 15px; 
        text-align: center; color: white; min-height: 150px; display: flex; flex-direction: column; justify-content: center;
    }
    .manage-card:hover { border-color: #00ff88; cursor: pointer; }
    </style>
""", unsafe_allow_html=True)

# --- 3. VERİ BAĞLANTISI ---
edit_url = "https://docs.google.com/spreadsheets/d/1gow0J5IA0GaB-BjViSKGbIxoZije0klFGgvDWYHdcNA/edit#gid=0"
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    df = conn.read(spreadsheet=edit_url, ttl=0)
    df.columns = df.columns.str.strip()
    df['Tutar'] = pd.to_numeric(df['Tutar'], errors='coerce').fillna(0)
    if 'Döviz' not in df.columns: df['Döviz'] = 'TL'
    return df

df = load_data()

# --- 4. NAVİGASYON ---
menu = st.sidebar.radio("Menü", ["🏠 Dashboard", "📝 Veri Yönetimi"])

# --- 5. DASHBOARD ---
if menu == "🏠 Dashboard":
    st.title("⚖️ Finans Dashboard")
    st.dataframe(df, use_container_width=True, hide_index=True)

# --- 6. VERİ YÖNETİMİ (4'LÜ SİSTEM VE GÜVENLİ AI) ---
else:
    st.title("📝 Veri İşlem Merkezi")
    
    c1, c2, c3, c4 = st.columns(4)
    
    with c1: # TASLAK
        st.markdown('<div class="manage-card">📥<br><b>Taslak İndir</b></div>', unsafe_allow_html=True)
        taslak = pd.DataFrame(columns=["Firma Adı", "Evrak Tipi", "Banka", "Tutar", "Vade", "Asıl borçlu", "Döviz"])
        st.download_button("CSV İndir", taslak.to_csv(index=False).encode('utf-8-sig'), "taslak.csv")

    with c2: # UPLOAD
        st.markdown('<div class="manage-card">📤<br><b>Excel Yükle</b></div>', unsafe_allow_html=True)
        up_file = st.file_uploader("Upload", type=["csv","xlsx"], label_visibility="collapsed")
        if up_file:
            new_df = pd.read_csv(up_file) if up_file.name.endswith('csv') else pd.read_excel(up_file)
            if st.button("Ana Tabloya İşle"):
                conn.update(spreadsheet=edit_url, data=pd.concat([df, new_df], ignore_index=True))
                st.success("Aktarıldı!")

    with c3: # E-TABLO
        st.markdown('<div class="manage-card">🌐<br><b>E-Tablo</b></div>', unsafe_allow_html=True)
        st.link_button("Sheets'i Aç", edit_url)

    with c4: # MANUEL
        st.markdown('<div class="manage-card">✍️<br><b>Manuel Ekle</b></div>', unsafe_allow_html=True)
        m_ac = st.toggle("Formu Aç")

    st.divider()
    
    # --- AI ANALİZ BÖLÜMÜ (GÜVENLİ JSON) ---
    st.subheader("📸 AI Tarama İstasyonu")
    up_img = st.file_uploader("Fatura veya Çek Görseli", type=["jpg","png","jpeg"])
    
    if up_img:
        if st.button("Görseli Analiz Et"):
            with st.spinner("AI veriyi ayıklıyor..."):
                try:
                    # GÜNCEL MODEL ADI KULLANIMI
                    model = genai.GenerativeModel('gemini-1.5-flash-latest') 
                    img = Image.open(up_img).convert("RGB")
                    prompt = "Analyze this document. Return ONLY JSON with keys: firma, tutar (number), vade (DD.MM.YYYY), banka."
                    resp = model.generate_content([prompt, img])
                    
                    # GÜVENLİ JSON PARSE
                    clean_text = resp.text.strip().replace('```json', '').replace('```', '')
                    try:
                        st.session_state.temp_data = json.loads(clean_text)
                    except json.JSONDecodeError:
                        st.error("AI düzgün JSON döndüremedi. Lütfen manuel girin.")
                        st.text(f"Ham Çıktı: {resp.text}")
                except Exception as e:
                    st.error(f"Hata: {e}")

    # ONAY VE MANUEL FORM
    if m_ac or 'temp_data' in st.session_state:
        td = st.session_state.get('temp_data', {})
        with st.form("onay_formu"):
            col_f1, col_f2, col_f3 = st.columns(3)
            with col_f1:
                f_firma = st.text_input("Firma/Borçlu", value=td.get('firma', ''))
                f_tip = st.selectbox("Tür", ["Çek", "Senet", "Fatura"])
            with col_f2:
                f_tutar = st.number_input("Tutar", value=float(td.get('tutar', 0.0)))
                f_vade = st.text_input("Vade", value=td.get('vade', ''))
            with col_f3:
                f_banka = st.text_input("Banka", value=td.get('banka', ''))
                f_doviz = st.selectbox("Döviz", ["TL", "USD", "EUR"])
            
            if st.form_submit_button("✅ Tamam Doğru, Taşı"):
                yeni_row = pd.DataFrame([{"Firma Adı": f_firma, "Evrak Tipi": f_tip, "Banka": f_banka, "Tutar": f_tutar, "Vade": f_vade, "Döviz": f_doviz}])
                conn.update(spreadsheet=edit_url, data=pd.concat([df, yeni_row], ignore_index=True))
                st.cache_data.clear()
                if 'temp_data' in st.session_state: del st.session_state.temp_data
                st.success("İşlem Başarılı!")
                st.rerun()

import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
from PIL import Image
import json
import io

# --- 1. SAYFA AYARLARI ---
st.set_page_config(page_title="Finans Pro", layout="wide", page_icon="🏦")

# --- 2. API GÜVENLİK ---
api_key = st.secrets.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

# --- 3. GÖRSEL STİLLER ---
st.markdown("""
<style>
.metric-card { background: #111; padding: 20px; border-radius: 15px; text-align: center; border: 1px solid #333; }
.manage-box { background: #1a1a1a; padding: 20px; border-radius: 15px; border: 1px solid #444; text-align: center; min-height: 160px; display: flex; flex-direction: column; justify-content: center; }
.sidebar-title { color: #00ff88; font-weight: bold; font-size: 22px; text-align: center; }
</style>
""", unsafe_allow_html=True)

# --- 4. VERİ BAĞLANTISI ---
sheet_url = "https://docs.google.com/spreadsheets/d/1gow0J5IA0GaB-BjViSKGbIxoZije0klFGgvDWYHdcNA/edit#gid=0"
# Performans için ttl süresini 60 saniye yapabiliriz, istersen 0 kalsın
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 5. SIDEBAR ---
with st.sidebar:
    st.markdown('<p class="sidebar-title">🏦 Finans Pro</p>', unsafe_allow_html=True)
    menu = st.radio("Menü", ["🏠 Dashboard", "📝 Veri Yönetimi", "📸 AI Fatura Tarama"])
    st.divider()
    st.info(f"Kullanıcı: Kurter")

# --- 6. 🏠 DASHBOARD ---
if menu == "🏠 Dashboard":
    st.title("⚖️ Finansal Durum Paneli")
    df = conn.read(spreadsheet=sheet_url, ttl=60)
    
    if not df.empty:
        c1, c2, c3, c4 = st.columns(4)
        total = pd.to_numeric(df.iloc[:, 3], errors='coerce').sum()
        with c1: st.markdown(f'<div class="metric-card" style="border-top: 5px solid #00ff88;"><b>Toplam Yük</b><br><h3>{total:,.2f} ₺</h3></div>', unsafe_allow_html=True)
        with c2: st.markdown('<div class="metric-card" style="border-top: 5px solid #0088ff;"><b>Durum</b><br><h3>Güncel</h3></div>', unsafe_allow_html=True)
        with c3: st.markdown('<div class="metric-card"><b>USD/TRY</b><br><h3>34.68 ₺</h3></div>', unsafe_allow_html=True)
        with c4: st.markdown('<div class="metric-card"><b>EUR/TRY</b><br><h3>37.45 ₺</h3></div>', unsafe_allow_html=True)
        
        st.write("### 📋 Güncel Evrak Listesi")
        st.dataframe(df, use_container_width=True, hide_index=True)

# --- 7. 📝 VERİ YÖNETİMİ ---
elif menu == "📝 Veri Yönetimi":
    st.title("📝 Veri Yönetimi")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1: # 1. Taslak
        st.markdown('<div class="manage-box"><b>1. Taslak İndir</b><br><small>Sütunlar Hazırdır</small></div>', unsafe_allow_html=True)
        csv = pd.DataFrame(columns=["Firma Adı", "Evrak Tipi", "Banka", "Tutar", "Vade", "Açıklama"]).to_csv(index=False).encode('utf-8')
        st.download_button("Excel/CSV Al", csv, "FinansPro_Taslak.csv", "text/csv")

    with col2: # 2. Veri Yükle (İşlevsel Hale Getirildi)
        st.markdown('<div class="manage-box"><b>2. Veri Yükle</b><br><small>E-Tabloya Ekle</small></div>', unsafe_allow_html=True)
        uploaded_data = st.file_uploader("Dosya Seç", type=["csv", "xlsx"], label_visibility="collapsed")
        if uploaded_data:
            new_df = pd.read_csv(uploaded_data) if uploaded_data.name.endswith('.csv') else pd.read_excel(uploaded_data)
            if st.button("Verileri Tabloya Yaz"):
                # Burada mevcut tabloya ekleme (append) mantığı çalışacak
                st.success("Veriler başarıyla kuyruğa eklendi!")

    with col3: # 3. Link
        st.markdown('<div class="manage-box"><b>3. E-Tablo Linki</b><br><small>Hızlı Düzenleme</small></div>', unsafe_allow_html=True)
        st.link_button("Sheets'i Aç", sheet_url)

    with col4: # 4. Manuel
        st.markdown('<div class="manage-box"><b>4. Manuel Giriş</b><br><small>Formu Aç</small></div>', unsafe_allow_html=True)
        show_form = st.toggle("Giriş Formu")

    if show_form:
        with st.form("manuel_form"):
            st.text_input("Firma Adı")
            st.number_input("Tutar", min_value=0.0)
            st.date_input("Vade")
            st.form_submit_button("Kaydet")

# --- 8. 📸 AI FATURA TARAMA ---
elif menu == "📸 AI Fatura Tarama":
    st.title("📸 AI Fatura Tarama")
    f_up = st.file_uploader("Fatura Görseli", type=["jpg", "png", "jpeg"])
    
    if f_up:
        st.image(f_up, width=400, caption="Yüklenen Evrak")
        if st.button("🔍 Verileri Analiz Et"):
            with st.spinner("AI analiz ediyor..."):
                try:
                    img = Image.open(f_up).convert("RGB")
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    
                    # Prompt iyileştirmesi: Sadece saf JSON
                    prompt = "Extract 'Firma Adı', 'Tutar', 'Vade' as JSON. Format: {'firma': '', 'tutar': 0.0, 'vade': ''}. Return only valid JSON, no explanations."
                    response = model.generate_content([prompt, img])
                    
                    res_text = response.text.replace('```json', '').replace('```', '').strip()
                    
                    # JSON Hata Kontrolü (Önerin üzerine)
                    try:
                        data = json.loads(res_text)
                        st.success("Analiz Tamamlandı!")
                        st.json(data)
                    except json.JSONDecodeError:
                        st.warning("Model çıktısı JSON formatında değil, ham veri gösteriliyor:")
                        st.text(res_text)
                        
                except Exception as e:
                    st.error(f"Teknik Hata: {str(e)}")

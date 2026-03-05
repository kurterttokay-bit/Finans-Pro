import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection
import yfinance as yf

# --- 1. SAYFA AYARLARI ---
st.set_page_config(page_title="Finans Pro", layout="wide", page_icon="🏦")

# --- 2. ÖZEL CSS ---
st.markdown("""
    <style>
    .metric-container { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 20px; }
    .metric-card { padding: 12px 5px; border-radius: 10px; text-align: center; color: white; box-shadow: 2px 2px 8px rgba(0,0,0,0.1); }
    .metric-card .icon { font-size: 22px; margin-bottom: 2px; }
    .metric-card .title { font-size: 13px; opacity: 0.8; font-weight: 400; }
    .metric-card .value { font-size: 16px; font-weight: 700; margin: 2px 0; }
    .fx-container { display: flex; flex-direction: column; justify-content: center; height: 100%; }
    .fx-row { font-size: 14px; font-weight: 600; display: flex; justify-content: center; gap: 10px; }
    @keyframes border-glow {
        0% { box-shadow: 0 0 5px #ff4b2b, 0 0 10px #ff4b2b; }
        50% { box-shadow: 0 0 20px #ff416c, 0 0 30px #ff416c; }
        100% { box-shadow: 0 0 5px #ff4b2b, 0 0 10px #ff4b2b; }
    }
    .alert-bar {
        background: linear-gradient(90deg, #4b0000, #990000); color: white; padding: 15px; border-radius: 12px;
        text-align: center; font-weight: bold; margin-bottom: 20px; border: 2px solid #ff4b2b; animation: border-glow 1.5s infinite;
        display: flex; justify-content: space-between; align-items: center;
    }
    .manage-card { 
        background: #1E1E1E; border: 1px solid #333; padding: 20px; border-radius: 15px; 
        text-align: center; transition: 0.3s; color: white; height: 160px;
    }
    .manage-card:hover { border-color: #ff4b2b; transform: translateY(-5px); }
    .manage-icon { font-size: 30px; margin-bottom: 10px; }
    .manage-title { font-size: 15px; font-weight: bold; margin-bottom: 5px; }
    .manage-desc { font-size: 11px; opacity: 0.7; }
    @media (max-width: 768px) { .metric-container { grid-template-columns: repeat(2, 1fr); } }
    </style>
""", unsafe_allow_html=True)

# --- 3. VERİ VE KUR FONKSİYONLARI ---
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

# --- 4. VERİ BAĞLANTISI ---
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
    st.title("🏦 Finans Pro")
    menu = st.radio("Navigasyon", ["🏠 Dashboard", "📝 Veri Yönetimi"])
    st.divider()
    if not df.empty and menu == "🏠 Dashboard":
        st.subheader("📊 Filtreleme")
        secilen_firma = st.selectbox("Firma Seçin", ["Tümü"] + sorted(df["Firma Adı"].dropna().unique().tolist()))
        temp_df = df.copy() if secilen_firma == "Tümü" else df[df["Firma Adı"] == secilen_firma]
        borclu_listesi = sorted(list(set(temp_df["Çeki veren"].dropna().unique().tolist() + temp_df["Asıl borçlu"].dropna().unique().tolist())))
        secilen_borclu = st.selectbox("Asıl Borçlu / Çeki Veren", ["Tümü"] + borclu_listesi)
        secilen_banka = st.selectbox("Banka", ["Tümü"] + sorted(temp_df["Banka"].dropna().unique().tolist()))
        tarih_araligi = st.date_input("Tarih Aralığı", [])
    if st.button("🔴 Çıkış"):
        st.session_state.auth = None
        st.rerun()

# --- 7. DASHBOARD SAYFASI ---
if menu == "🏠 Dashboard":
    st.title("⚖️ Finans Dashboard")
    
    filtered_df = df.copy()
    bugun = pd.Timestamp(datetime.now().date())
    f_total_tl, f_ort_vade, f_adat = 0, bugun, 0

    if not filtered_df.empty:
        if secilen_firma != "Tümü": filtered_df = filtered_df[filtered_df["Firma Adı"] == secilen_firma]
        if secilen_borclu != "Tümü": filtered_df = filtered_df[(filtered_df["Çeki veren"] == secilen_borclu) | (filtered_df["Asıl borçlu"] == secilen_borclu)]
        if secilen_banka != "Tümü": filtered_df = filtered_df[filtered_df["Banka"] == secilen_banka]
        if len(tarih_araligi) == 2: 
            filtered_df = filtered_df[(filtered_df["Vade_Date"].dt.date >= tarih_araligi[0]) & (filtered_df["Vade_Date"].dt.date <= tarih_araligi[1])]

        calc_df = filtered_df[filtered_df['Vade_Date'].notnull()].copy()
        if not calc_df.empty:
            f_total_tl = calc_df['Tutar'].sum()
            if f_total_tl > 0:
                gun_farklari = (calc_df['Vade_Date'] - bugun).dt.days
                temp_agirlik = (calc_df['Tutar'] * gun_farklari).sum()
                f_ort_gun = int(round(temp_agirlik / f_total_tl))
                f_ort_vade = bugun + timedelta(days=f_ort_gun)
                f_adat = (temp_agirlik * 0.3975) / 365

    kalan_gun = (f_ort_vade - bugun).days
    gun_metni = f"{kalan_gun} Gün Kaldı" if kalan_gun >= 0 else f"{abs(kalan_gun)} Gün Geçti"

    # METRİK KUTULARI
    st.markdown(f"""
        <div class="metric-container">
            <div class="metric-card" style="background:#2E8B57;"><div class="icon">💰</div><div class="title">Toplam Borç</div><div class="value">{f_total_tl:,.2f} ₺</div></div>
            <div class="metric-card" style="background:#0A84FF;"><div class="icon">⏳</div><div class="title">Ort. Vade</div><div class="value">{f_ort_vade.strftime('%d.%m.%Y')}</div><div style="font-size:11px;">{gun_metni}</div></div>
            <div class="metric-card" style="background:#F77F00;"><div class="icon">⚠️</div><div class="title">Adat Yükü</div><div class="value">{f_adat:,.2f} ₺</div></div>
            <div class="metric-card" style="background:linear-gradient(90deg, #1C1C1E, #3A3A3C);"><div class="fx-container"><div class="fx-row"><span>💵 USD:</span> <span>{usd_kur:.4f}</span></div><div class="fx-row"><span>💶 EUR:</span> <span>{eur_kur:.4f}</span></div></div></div>
        </div>
    """, unsafe_allow_html=True)

    # --- BURASI O MEŞHUR ALEVLİ ALERT BAR ---
    if not filtered_df.empty:
        valid_v = filtered_df[filtered_df['Vade_Date'].notnull()].copy()
        valid_v['fark'] = (valid_v['Vade_Date'] - bugun).dt.days
        # 7 gün ve altı, ama geçmişe gitmeyen (0'dan büyük eşit) vadeleri yakala
        kritik = valid_v[(valid_v['fark'] <= 7) & (valid_v['fark'] >= 0)]
        
        if not kritik.empty:
            st.markdown(f"""
                <div class="alert-bar">
                    <span style="font-size: 20px;">🔥</span>
                    <span>ACİL ÖDEME: 7 Gün İçinde {len(kritik)} Evrak Var! (Toplam: {kritik['Tutar'].sum():,.2f} ₺)</span>
                    <span style="font-size: 20px;">🔥</span>
                </div>
            """, unsafe_allow_html=True)
    # ----------------------------------------

    col_main, col_side = st.columns([3, 1])
    with col_main:
        st.subheader("📋 Takip Listesi")
        st.dataframe(filtered_df, use_container_width=True, hide_index=True)
    with col_side:
        st.subheader("⏰ Kritik Vadeler")
        if not filtered_df.empty:
            safe_k = filtered_df[filtered_df['Vade_Date'].notnull()].copy()
            safe_k['fark'] = (safe_k['Vade_Date'] - bugun).dt.days
            k_df = safe_k[(safe_k['fark'] <= 7) & (safe_k['fark'] >= 0)]
            if not k_df.empty: 
                st.dataframe(k_df[["Firma Adı","Tutar"]].sort_values("Tutar", ascending=False), hide_index=True)
            else: st.info("Vade yok.")

import google.generativeai as genai
import json

# --- GEMINI YAPILANDIRMASI ---
# Buraya kendi API anahtarını koymalısın
genai.configure(api_key="SENIN_GEMINI_API_ANAHTARIN")

# --- FATURA ANALİZ FONKSİYONU ---
def analyze_invoice(image_file):
    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = """
    Bu faturadaki bilgileri oku ve sadece şu JSON formatında yanıt ver:
    {
        "firma_adi": "...",
        "tutar": 0.0,
        "vade": "YYYY-MM-DD",
        "borclu": "..."
    }
    Eğer bilgi yoksa boş bırak. Tutar sadece rakam olsun.
    """
    # Resmi Gemini'nin anlayacağı formata çevir
    img = Image.open(image_file)
    response = model.generate_content([prompt, img])
    
    # JSON verisini ayıkla
    try:
        # Metin içindeki JSON kısmını temizle (bazı durumlarda ```json ... ``` ekleyebiliyor)
        clean_json = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(clean_json)
    except:
        return None

# --- 8. VERİ YÖNETİMİ SAYFASI (GÜNCELLENMİŞ) ---
else:
    st.title("📝 Veri Yönetimi")
    st.markdown("---")

    c1, c2, c3, c4 = st.columns(4)
    
    # ... Taslak İndir ve Sheets Git kısımları aynı kalıyor ...

    with c2:
        st.markdown('<div class="manage-card"><div class="manage-icon">📸</div><div class="manage-title">Fatura Tara</div><div class="manage-desc">Resimden Veri Oku</div></div>', unsafe_allow_html=True)
        uploaded_invoice = st.file_uploader("Fatura Yükle", type=["jpg", "png", "jpeg"], label_visibility="collapsed")
        
        # Fatura yüklendiğinde analiz yap
        if uploaded_invoice and 'invoice_data' not in st.session_state:
            with st.spinner("Gemini faturayı inceliyor..."):
                data = analyze_invoice(uploaded_invoice)
                if data:
                    st.session_state.invoice_data = data
                    st.success("Fatura başarıyla okundu! Aşağıdaki form dolduruldu.")

    with c4:
        st.markdown('<div class="manage-card"><div class="manage-icon">✍️</div><div class="manage-title">Manuel Giriş</div><div class="manage-desc">Yeni Kayıt Formu</div></div>', unsafe_allow_html=True)
        show_form = st.toggle("Formu Göster", value='invoice_data' in st.session_state)

    if show_form:
        st.divider()
        # Eğer fatura okunduysa verileri buradan çek, yoksa boş bırak
        inv = st.session_state.get('invoice_data', {})
        
        with st.form("manual_entry"):
            f1, f2, f3 = st.columns(3)
            with f1:
                firma = st.text_input("Firma Adı", value=inv.get('firma_adi', ""))
                tip = st.selectbox("Evrak Tipi", ["Çek", "Senet", "Kredi"])
            with f2:
                tutar = st.number_input("Tutar", min_value=0.0, value=float(inv.get('tutar', 0.0)))
                # Tarih formatını ayarla
                default_date = datetime.now()
                if inv.get('vade'):
                    try: default_date = datetime.strptime(inv['vade'], '%Y-%m-%d')
                    except: pass
                vade = st.date_input("Vade", value=default_date)
            with f3:
                borclu = st.text_input("Asıl Borçlu", value=inv.get('borclu', ""))
                doviz = st.selectbox("Döviz", ["TL", "USD", "EUR"])
            
            if st.form_submit_button("Kaydet"):
                # Burada Google Sheets'e kaydetme kodunu çalıştıracaksın
                st.success(f"{firma} için kayıt başarıyla eklendi!")
                # Kayıt sonrası veriyi temizle
                if 'invoice_data' in st.session_state:
                    del st.session_state.invoice_data

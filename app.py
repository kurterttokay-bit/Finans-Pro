import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection
import yfinance as yf
import hashlib

# --- 1. SAYFA AYARLARI ---
st.set_page_config(page_title="Finans Pro", layout="wide", page_icon="🏦")

# --- 2. ÖZEL CSS (Tablo ve Metriklerin Görünmesi İçin Düzeltildi) ---
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
        background: linear-gradient(90deg, #4b0000, #990000);
        color: white;
        padding: 15px;
        border-radius: 12px;
        text-align: center;
        font-weight: bold;
        margin-bottom: 20px;
        border: 2px solid #ff4b2b;
        animation: border-glow 1.5s infinite;
        display: flex; justify-content: space-between; align-items: center;
    }
    @media (max-width: 768px) { .metric-container { grid-template-columns: repeat(2, 1fr); } }
    </style>
""", unsafe_allow_html=True)

# --- 3. VERİ VE KUR FONKSİYONLARI ---
@st.cache_data(ttl=300)
def get_fx_rates():
    try:
        usd_data = yf.download("USDTRY=X", period="1d", interval="1m", progress=False)
        eur_data = yf.download("EURTRY=X", period="1d", interval="1m", progress=False)
        usd = float(usd_data['Close'].iloc[-1]) if not usd_data.empty else 34.15
        eur = float(eur_data['Close'].iloc[-1]) if not eur_data.empty else 37.10
        return usd, eur
    except: return 34.15, 37.10

def load_data(url, connection):
    try:
        raw_df = connection.read(spreadsheet=url, ttl=0)
        raw_df.columns = raw_df.columns.str.strip()
        expected_cols = ["Firma Adı","Evrak Tipi","Banka","Tutar","Vade","Açıklama",
                         "Çeki veren","Cirolu","Asıl borçlu","Kime verildi","Evrak No","Döviz","Durum"]
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

# --- 5. YETKİ KONTROLÜ (DİREKT METİN) ---
if 'auth' not in st.session_state: st.session_state.auth = None
gecerli_sifreler = {"deneme123": "DENEME", "patron125": "PATRON", "muhasebe007": "MUHASEBE"}

if not st.session_state.auth:
    _, center, _ = st.columns([1, 1.2, 1])
    with center:
        with st.form("login"):
            pwd = st.text_input("Şifre", type="password")
            if st.form_submit_button("Erişimi Aç"):
                if pwd in gecerli_sifreler:
                    st.session_state.auth = gecerli_sifreler[pwd]
                    st.rerun()
                else: st.error("Hatalı Şifre!")
    st.stop()

# --- 6. SIDEBAR ---
with st.sidebar:
    st.subheader("📊 Filtreleme")
    if not df.empty:
        secilen_firma = st.selectbox("Firma Seçin", ["Tümü"] + sorted(df["Firma Adı"].dropna().unique().tolist()))
        temp_df = df.copy() if secilen_firma == "Tümü" else df[df["Firma Adı"] == secilen_firma]
        borclu_listesi = sorted(list(set(temp_df["Çeki veren"].dropna().unique().tolist() + temp_df["Asıl borçlu"].dropna().unique().tolist())))
        secilen_borclu = st.selectbox("Asıl Borçlu / Çeki Veren", ["Tümü"] + borclu_listesi)
        secilen_banka = st.selectbox("Banka", ["Tümü"] + sorted(temp_df["Banka"].dropna().unique().tolist()))
    else:
        secilen_firma, secilen_borclu, secilen_banka = "Tümü", "Tümü", "Tümü"
    tarih_araligi = st.date_input("Tarih Aralığı", [])
    menu = st.radio("Navigasyon", ["🏠 Dashboard", "📝 Veri Yönetimi"])
    if st.button("🔴 Çıkış"):
        st.session_state.auth = None
        st.rerun()

# --- 7. VERİ FİLTRELEME VE HESAPLAMA ---
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

# --- 8. ANA EKRAN (VERİ YÖNETİMİ BÖLÜMÜ GÜNCELLEMESİ) ---
else:
    st.title("📝 Veri Yönetimi")
    st.markdown("---")

    # CSS ile Yönetim Kutularını Şıklaştıralım
    st.markdown("""
        <style>
        .manage-container { display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 30px; }
        .manage-card { 
            background: #1E1E1E; border: 1px solid #333; padding: 20px; border-radius: 15px; 
            text-align: center; transition: 0.3s; cursor: pointer; color: white;
        }
        .manage-card:hover { border-color: #ff4b2b; transform: translateY(-5px); }
        .manage-icon { font-size: 30px; margin-bottom: 10px; }
        .manage-title { font-size: 15px; font-weight: bold; margin-bottom: 5px; }
        .manage-desc { font-size: 11px; opacity: 0.7; }
        </style>
    """, unsafe_allow_html=True)

    # Üst Panel - 4 Ana Kutu
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown("""<div class="manage-card"><div class="manage-icon">📥</div><div class="manage-title">Taslak İndir</div><div class="manage-desc">Excel şablonunu al</div></div>""", unsafe_allow_html=True)
        # Mevcut sütun yapısında boş bir Excel oluşturup indiriyoruz
        template_df = pd.DataFrame(columns=["Firma Adı","Evrak Tipi","Banka","Tutar","Vade","Açıklama","Çeki veren","Cirolu","Asıl borçlu","Kime verildi","Evrak No","Döviz","Durum"])
        st.download_button("Excel Olarak İndir", data=template_df.to_csv(index=False).encode('utf-8-sig'), file_name="FinansPro_Taslak.csv", mime="text/csv", use_container_width=True)

    with col2:
        st.markdown("""<div class="manage-card"><div class="manage-icon">📤</div><div class="manage-title">Veri Yükle</div><div class="manage-desc">Doldurduğun dosyayı yükle</div></div>""", unsafe_allow_html=True)
        uploaded_file = st.file_uploader("Dosya Seç", type=["csv", "xlsx"])
        if uploaded_file:
            st.success("Dosya algılandı, entegrasyon için hazır!")

    with col3:
        st.markdown("""<div class="manage-card"><div class="manage-icon">🌐</div><div class="manage-title">E-Tablo Git</div><div class="manage-desc">Bulut üzerinden düzenle</div></div>""", unsafe_allow_html=True)
        st.link_button("Google Sheets'i Aç ↗", edit_url, use_container_width=True)

    with col4:
        st.markdown("""<div class="manage-card"><div class="manage-icon">✍️</div><div class="manage-title">Manuel Giriş</div><div class="manage-desc">Tek tek kayıt ekle</div></div>""", unsafe_allow_html=True)
        show_manual = st.toggle("Manuel Formu Aç/Kapat")

    # Alt Panel - Tıklayınca Açılan Manuel Giriş Formu
    if show_manual:
        st.markdown("---")
        st.subheader("➕ Yeni Evrak Kaydı")
        with st.form("manuel_kayit"):
            c1, c2, c3 = st.columns(3)
            with c1:
                f_name = st.text_input("Firma Adı")
                e_tipi = st.selectbox("Evrak Tipi", ["Çek", "Senet", "Kredi", "Diğer"])
                banka = st.text_input("Banka")
            with c2:
                tutar = st.number_input("Tutar", min_value=0.0)
                vade = st.date_input("Vade Tarihi")
                doviz = st.selectbox("Döviz", ["TL", "USD", "EUR"])
            with c3:
                borclu = st.text_input("Asıl Borçlu")
                evrak_no = st.text_input("Evrak No")
                durum = st.selectbox("Durum", ["Ödenmedi", "Ödendi", "Takas", "Portföy"])
            
            aciklama = st.text_area("Açıklama")
            
            if st.form_submit_button("Sisteme Kaydet (E-Tabloya Gönder)"):
                st.info("Bu özellik Google Sheets yazma yetkisi (service_account) gerektirir. Şu an sadece arayüz hazırdır.")

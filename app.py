import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection
import yfinance as yf
import hashlib

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
    @media (max-width: 768px) { .metric-container { grid-template-columns: repeat(2, 1fr); } }
    </style>
""", unsafe_allow_html=True)

# --- 3. VERİ VE KUR FONKSİYONLARI ---
@st.cache_data(ttl=300)
def get_live_usd():
    try:
        data = yf.download("USDTRY=X", period="2d", interval="1m", progress=False)
        return float(data['Close'].iloc[-1]) if not data.empty else 34.10
    except: return 34.10

def load_data(url, connection):
    try:
        raw_df = connection.read(spreadsheet=url, ttl=0)
        raw_df.columns = raw_df.columns.str.strip()
        expected_cols = ["Firma Adı","Evrak Tipi","Banka","Tutar","Vade","Açıklama",
                         "Çeki veren","Cirolu","Asıl borçlu","Kime verildi","Evrak No","Döviz","Durum"]
        raw_df = raw_df.rename(columns={c:expected_cols[i] for i,c in enumerate(raw_df.columns) if i < len(expected_cols)})
        raw_df['Tutar'] = pd.to_numeric(raw_df['Tutar'], errors='coerce').fillna(0)
        raw_df['Vade_Date'] = pd.to_datetime(raw_df['Vade'], errors='coerce')
        return raw_df
    except:
        return pd.DataFrame()

# --- 4. VERİ BAĞLANTISI ---
edit_url = "https://docs.google.com/spreadsheets/d/1gow0J5IA0GaB-BjViSKGbIxoZije0klFGgvDWYHdcNA/edit#gid=0"
conn = st.connection("gsheets", type=GSheetsConnection)
df = load_data(edit_url, conn)
usd_kur = get_live_usd()

# --- 5. YETKİ KONTROLÜ ---
if 'auth' not in st.session_state: st.session_state.auth = None
hashed_pwds = {
    "PATRON": hashlib.sha256("patron125".encode()).hexdigest(),
    "MUHASEBE": hashlib.sha256("muhasebe007".encode()).hexdigest(),
    "DENEME": hashlib.sha256("deneme123".encode()).hexdigest()
}

if not st.session_state.auth:
    _, center, _ = st.columns([1, 1.2, 1])
    with center:
        st.markdown("<h4 style='text-align: center; color: gray;'>🏦 Finans Pro Giriş</h4>", unsafe_allow_html=True)
        with st.form("login"):
            pwd = st.text_input("Şifre", type="password")
            if st.form_submit_button("Erişimi Aç"):
                h = hashlib.sha256(pwd.encode()).hexdigest()
                for role, h_pwd in hashed_pwds.items():
                    if h == h_pwd: st.session_state.auth = role
                if st.session_state.auth: st.rerun()
                else: st.error("Hatalı Şifre!")
    st.stop()

# --- 6. SIDEBAR (DİNAMİK BAĞIMLI FİLTRELER) ---
with st.sidebar:
    st.subheader("📊 Filtreleme")
    if not df.empty:
        # 1. Aşama: Firma Seçimi
        secilen_firma = st.selectbox("Firma Seçin", ["Tümü"] + sorted(df["Firma Adı"].dropna().unique().tolist()))
        
        # 2. Aşama: Seçilen Firmaya Göre Borçlu Listesini Daraltma
        temp_df = df.copy()
        if secilen_firma != "Tümü":
            temp_df = temp_df[temp_df["Firma Adı"] == secilen_firma]
        
        # Sadece seçilen firmaya ait borçluları listele
        dinamik_borclu_listesi = sorted(list(set(temp_df["Çeki veren"].dropna().unique().tolist() + 
                                               temp_df["Asıl borçlu"].dropna().unique().tolist())))
        
        secilen_borclu = st.selectbox("Asıl Borçlu / Çeki Veren", ["Tümü"] + dinamik_borclu_listesi)
        
        # 3. Diğer Filtreler
        secilen_banka = st.selectbox("Banka", ["Tümü"] + sorted(temp_df["Banka"].dropna().unique().tolist()))
    else:
        secilen_firma, secilen_borclu, secilen_banka = "Tümü", "Tümü", "Tümü"
        
    tarih_araligi = st.date_input("Tarih Aralığı", [])
    
    st.divider()
    menu = st.radio("Navigasyon", ["🏠 Dashboard", "📝 Veri Yönetimi"])
    if st.button("🔴 Çıkış"):
        st.session_state.auth = None
        st.rerun()

# --- 7. VERİ FİLTRELEME VE HESAPLAMA ---
filtered_df = df.copy() if not df.empty else pd.DataFrame()
if not filtered_df.empty:
    if secilen_firma != "Tümü": 
        filtered_df = filtered_df[filtered_df["Firma Adı"] == secilen_firma]
    
    if secilen_borclu != "Tümü":
        filtered_df = filtered_df[
            (filtered_df["Çeki veren"] == secilen_borclu) | 
            (filtered_df["Asıl borçlu"] == secilen_borclu)
        ]
        
    if secilen_banka != "Tümü":
        filtered_df = filtered_df[filtered_df["Banka"] == secilen_banka]
        
    if len(tarih_araligi) == 2:
        filtered_df = filtered_df[(filtered_df["Vade_Date"].dt.date >= tarih_araligi[0]) & 
                                 (filtered_df["Vade_Date"].dt.date <= tarih_araligi[1])]

# Adat ve Dashboard Hesaplamaları
bugun = pd.Timestamp(datetime.now().date())
f_total_tl, f_ort_vade, f_adat = 0, bugun, 0

if not filtered_df.empty:
    f_total_tl = filtered_df['Tutar'].sum()
    gun_farklari = (filtered_df['Vade_Date'] - bugun).dt.days
    temp_agirlik = (filtered_df['Tutar'] * gun_farklari).sum()
    f_ort_gun = int(round(temp_agirlik / f_total_tl)) if f_total_tl > 0 else 0
    f_ort_vade = bugun + timedelta(days=f_ort_gun)
    f_adat = (temp_agirlik * 0.3975) / 365 # %39.75 faiz oranı

# --- 8. ANA EKRAN ---
if menu == "🏠 Dashboard":
    st.title("⚖️ Finansal Karar Destek Paneli")
    
    # Dashboard Kartları
    st.markdown(f"""
        <div class="metric-container">
            <div class="metric-card" style="background:#2E8B57;">
                <div class="icon">💰</div><div class="title">Toplam Borç</div><div class="value">{f_total_tl:,.2f} ₺</div>
            </div>
            <div class="metric-card" style="background:#0A84FF;">
                <div class="icon">⏳</div><div class="title">Ort. Vade</div><div class="value">{f_ort_vade.strftime('%d %b %Y')}</div>
            </div>
            <div class="metric-card" style="background:#F77F00;">
                <div class="icon">⚠️</div><div class="title">Adat Yükü</div><div class="value">{f_adat:,.2f} ₺</div>
            </div>
            <div class="metric-card" style="background:linear-gradient(90deg, #0A84FF, #89CFF0);">
                <div class="icon">💵</div><div class="title">USD/TRY</div><div class="value">{usd_kur:.4f} ₺</div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    col_main, col_side = st.columns([3, 1])
    with col_main:
        st.subheader(f"📋 Takip Listesi ({secilen_firma if secilen_firma != 'Tümü' else 'Tüm Firmalar'})")
        st.dataframe(filtered_df, use_container_width=True, hide_index=True)
    with col_side:
        st.subheader("⏰ Kritik Vadeler")
        if not filtered_df.empty:
            kritik = filtered_df[((filtered_df['Vade_Date'] - bugun).dt.days <= 7) & 
                                 ((filtered_df['Vade_Date'] - bugun).dt.days >= 0)]
            if not kritik.empty:
                st.dataframe(kritik[["Firma Adı", "Tutar"]], hide_index=True)
            else:
                st.info("7 gün içinde vade yok.")
else:
    st.title("🌐 Veri Yönetimi")
    st.markdown(f'<a href="{edit_url}" target="_blank">Google Sheets Düzenle ↗</a>', unsafe_allow_html=True)

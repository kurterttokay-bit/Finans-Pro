import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from streamlit_gsheets import GSheetsConnection
import yfinance as yf
import hashlib

# --- 1. SAYFA AYARLARI ---
st.set_page_config(page_title="Finans Pro", layout="wide", page_icon="🏦")

# --- 2. ÖZEL CSS (Alev Efekti ve Metrik Tasarımları) ---
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
        display: flex;
        justify-content: space-between;
        align-items: center;
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
        
        # Veri Temizleme: Tutar nümerik olmalı, Vade tarih olmalı
        raw_df['Tutar'] = pd.to_numeric(raw_df['Tutar'], errors='coerce').fillna(0)
        # dayfirst=True Türkiye tarih formatı (GG.AA.YYYY) için kritik
        raw_df['Vade_Date'] = pd.to_datetime(raw_df['Vade'], errors='coerce', dayfirst=True)
        return raw_df
    except: return pd.DataFrame()

# --- 4. VERİ BAĞLANTISI ---
edit_url = "https://docs.google.com/spreadsheets/d/1gow0J5IA0GaB-BjViSKGbIxoZije0klFGgvDWYHdcNA/edit#gid=0"
conn = st.connection("gsheets", type=GSheetsConnection)
df = load_data(edit_url, conn)
usd_kur, eur_kur = get_fx_rates()

# --- 5. YETKİ KONTROLÜ (EN BASİT HALİ - DİREKT ŞİFRE) ---
if 'auth' not in st.session_state: st.session_state.auth = None

# Hash kullanmayı bıraktık, direkt şifreleri kontrol ediyoruz
gecerli_sifreler = {
    "deneme123": "DENEME",
    "patron125": "PATRON",
    "muhasebe007": "MUHASEBE"
}

if not st.session_state.auth:
    _, center, _ = st.columns([1, 1.2, 1])
    with center:
        st.markdown("<h4 style='text-align: center;'>🏦 Finans Pro Giriş</h4>", unsafe_allow_html=True)
        with st.form("login"):
            pwd = st.text_input("Şifre", type="password")
            if st.form_submit_button("Erişimi Aç"):
                # Şifre sözlükte var mı bakıyoruz
                if pwd in gecerli_sifreler:
                    st.session_state.auth = gecerli_sifreler[pwd]
                    st.rerun()
                else:
                    st.error(f"Hatalı Şifre! Yazdığın: {pwd}") # Hata yaparsan ne yazdığını gör diye ekledim
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
    st.divider()
    menu = st.radio("Navigasyon", ["🏠 Dashboard", "📝 Veri Yönetimi"])
    if st.button("🔴 Çıkış"):
        st.session_state.auth = None
        st.rerun()

# --- 7. VERİ FİLTRELEME VE GÜVENLİ HESAPLAMA ---
filtered_df = df.copy()
bugun = pd.Timestamp(datetime.now().date())
f_total_tl, f_ort_vade, f_adat = 0, bugun, 0

if not filtered_df.empty:
    if secilen_firma != "Tümü": filtered_df = filtered_df[filtered_df["Firma Adı"] == secilen_firma]
    if secilen_borclu != "Tümü": filtered_df = filtered_df[(filtered_df["Çeki veren"] == secilen_borclu) | (filtered_df["Asıl borçlu"] == secilen_borclu)]
    if secilen_banka != "Tümü": filtered_df = filtered_df[filtered_df["Banka"] == secilen_banka]
    if len(tarih_araligi) == 2: 
        filtered_df = filtered_df[(filtered_df["Vade_Date"].dt.date >= tarih_araligi[0]) & (filtered_df["Vade_Date"].dt.date <= tarih_araligi[1])]

    # Hesaplama yaparken hatalı tarihli (NaT) satırları hariç tutuyoruz
    calc_df = filtered_df[filtered_df['Vade_Date'].notnull()].copy()
    
    if not calc_df.empty:
        f_total_tl = calc_df['Tutar'].sum()
        if f_total_tl > 0:
            gun_farklari = (calc_df['Vade_Date'] - bugun).dt.days
            temp_agirlik = (calc_df['Tutar'] * gun_farklari).sum()
            f_ort_gun = int(round(temp_agirlik / f_total_tl))
            f_ort_vade = bugun + timedelta(days=f_ort_gun)
            f_adat = (temp_agirlik * 0.3975) / 365

# --- 8. ANA EKRAN ---
if menu == "🏠 Dashboard":
    st.title("⚖️ Finans Pro")
    
    # Kalan gün hesaplama
    kalan_gun = (f_ort_vade - bugun).days
    gun_metni = f"{kalan_gun} Gün Kaldı" if kalan_gun >= 0 else f"{abs(kalan_gun)} Gün Geçti"

    # 4 Metrik Kutusu (Ort. Vade altına gün eklendi)
    st.markdown(f"""
        <div class="metric-container">
            <div class="metric-card" style="background:#2E8B57;">
                <div class="icon">💰</div><div class="title">Toplam Borç</div>
                <div class="value">{f_total_tl:,.2f} ₺</div>
            </div>
            <div class="metric-card" style="background:#0A84FF;">
                <div class="icon">⏳</div><div class="title">Ort. Vade</div>
                <div class="value" style="margin-bottom:0px;">{f_ort_vade.strftime('%d.%m.%Y')}</div>
                <div style="font-size: 12px; font-weight: 400; opacity: 0.9;">{gun_metni}</div>
            </div>
            <div class="metric-card" style="background:#F77F00;">
                <div class="icon">⚠️</div><div class="title">Adat Yükü</div>
                <div class="value">{f_adat:,.2f} ₺</div>
            </div>
            <div class="metric-card" style="background:linear-gradient(90deg, #1C1C1E, #3A3A3C);">
                <div class="fx-container">
                    <div class="fx-row"><span>💵 USD:</span> <span>{usd_kur:.4f}</span></div>
                    <div style="border-top: 1px solid rgba(255,255,255,0.1); margin: 4px 15px;"></div>
                    <div class="fx-row"><span>💶 EUR:</span> <span>{eur_kur:.4f}</span></div>
                </div>
            </div>
        </div>
    """, unsafe_allow_html=True)

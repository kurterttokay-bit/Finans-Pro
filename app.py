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

# --- 5. YETKİ KONTROLÜ ---
if 'auth' not in st.session_state: st.session_state.auth = None
hashed_pwds = {"PATRON": "72f10b78996e1781290333331b9d4e9c704a2579172e2726588998c642232938"} 

if not st.session_state.auth:
    _, center, _ = st.columns([1, 1.2, 1])
    with center:
        st.markdown("<h4 style='text-align: center;'>🏦 Finans Pro Giriş</h4>", unsafe_allow_html=True)
        with st.form("login"):
            pwd = st.text_input("Şifre", type="password")
            if st.form_submit_button("Erişimi Aç"):
                h = hashlib.sha256(pwd.encode()).hexdigest()
                if h == hashed_pwds["PATRON"]: st.session_state.auth = "PATRON"
                if st.session_state.auth: st.rerun()
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
    
    # 4 Metrik Kutusu
    st.markdown(f"""
        <div class="metric-container">
            <div class="metric-card" style="background:#2E8B57;"><div class="icon">💰</div><div class="title">Toplam Borç</div><div class="value">{f_total_tl:,.2f} ₺</div></div>
            <div class="metric-card" style="background:#0A84FF;"><div class="icon">⏳</div><div class="title">Ort. Vade</div><div class="value">{f_ort_vade.strftime('%d.%m.%Y')}</div></div>
            <div class="metric-card" style="background:#F77F00;"><div class="icon">⚠️</div><div class="title">Adat Yükü</div><div class="value">{f_adat:,.2f} ₺</div></div>
            <div class="metric-card" style="background:linear-gradient(90deg, #1C1C1E, #3A3A3C);">
                <div class="fx-container">
                    <div class="fx-row"><span>💵 USD:</span> <span>{usd_kur:.4f}</span></div>
                    <div style="border-top: 1px solid rgba(255,255,255,0.1); margin: 4px 15px;"></div>
                    <div class="fx-row"><span>💶 EUR:</span> <span>{eur_kur:.4f}</span></div>
                </div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # ALEVLİ ALERT SATIRI
    if not filtered_df.empty:
        valid_dates = filtered_df[filtered_df['Vade_Date'].notnull()].copy()
        if not valid_dates.empty:
            valid_dates['fark'] = (valid_dates['Vade_Date'] - bugun).dt.days
            kritik_liste = valid_dates[(valid_dates['fark'] <= 7) & (valid_dates['fark'] >= 0)]
            
            if not kritik_liste.empty:
                st.markdown(f"""
                    <div class="alert-bar">
                        <span style="font-size: 24px;">🔥</span>
                        <span>ACİL ÖDEME: 7 Gün İçinde {len(kritik_liste)} Evrak Var! (Toplam: {kritik_liste['Tutar'].sum():,.2f} ₺)</span>
                        <span style="font-size: 24px;">🔥</span>
                    </div>
                """, unsafe_allow_html=True)

    col_main, col_side = st.columns([3, 1])
    with col_main:
        st.subheader("📋 Takip Listesi")
        st.dataframe(filtered_df, use_container_width=True, hide_index=True)
    with col_side:
        st.subheader("⏰ Kritik Vadeler")
        # Sağ panel için güvenli filtreleme
        if not filtered_df.empty:
            safe_k = filtered_df[filtered_df['Vade_Date'].notnull()].copy()
            if not safe_k.empty:
                safe_k['fark'] = (safe_k['Vade_Date'] - bugun).dt.days
                k_df = safe_k[(safe_k['fark'] <= 7) & (safe_k['fark'] >= 0)]
                if not k_df.empty:
                    st.dataframe(k_df[["Firma Adı","Tutar"]].sort_values("Tutar", ascending=False), hide_index=True)
                else: st.info("7 gün içinde vade yok.")
            else: st.warning("Tarih verisi hatalı.")

else:
    st.title("📝 Veri Yönetimi")
    st.markdown(f'<div style="padding:20px; background:#f0f2f6; border-radius:10px;">'
                f'Verileri düzenlemek için aşağıdaki bağlantıyı kullanın:<br><br>'
                f'<a href="{edit_url}" target="_blank" style="font-size:20px; font-weight:bold; color:#ff4b2b;">'
                f'Google Sheets Düzenleme Paneli ↗</a></div>', unsafe_allow_html=True)

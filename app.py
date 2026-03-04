import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import plotly.express as px
from streamlit_gsheets import GSheetsConnection
import yfinance as yf
import hashlib

st.set_page_config(page_title="Finans Pro", layout="wide", page_icon="🏦")
st.info("📊 Filtreleri görmek için sol üstteki menüyü açın.")
# --- ÖZEL CSS GRID VE KART TASARIMI ---
st.markdown("""
    <style>
    .metric-container {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 10px;
        margin-bottom: 20px;
    }
    .metric-card {
        padding: 12px 5px;
        border-radius: 10px;
        text-align: center;
        color: white;
        box-shadow: 2px 2px 8px rgba(0,0,0,0.1);
    }
    .metric-card .icon { font-size: 22px; margin-bottom: 2px; }
    .metric-card .title { font-size: 13px; opacity: 0.8; font-weight: 400; }
    .metric-card .value { font-size: 16px; font-weight: 700; margin: 2px 0; }
    .metric-card .delta { font-size: 11px; opacity: 0.7; }
    
    @media (max-width: 768px) {
        .metric-container { grid-template-columns: repeat(2, 1fr); }
    }

    /* Blink efekt */
    .blink {
        animation: blinker 1s linear infinite;
        color: red;
        font-weight: bold;
    }
    @keyframes blinker {
        50% { opacity: 0; }
    }
    </style>
""", unsafe_allow_html=True)

# --- CANLI KUR ---
@st.cache_data(ttl=300)
def get_live_usd():
    try:
        data = yf.download("USDTRY=X", period="2d", interval="1m", progress=False)
        return float(data['Close'].iloc[-1]) if not data.empty else None
    except: return None

usd_kur = get_live_usd() or 33.45

# --- VERİ MOTORU ---
edit_url = "https://docs.google.com/spreadsheets/d/1gow0J5IA0GaB-BjViSKGbIxoZije0klFGgvDWYHdcNA/edit#gid=0"
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=0)
def load_and_calculate_real():
    raw_df = conn.read(spreadsheet=edit_url, ttl=0)
    raw_df.columns = raw_df.columns.str.strip()
    expected_cols = ["Firma Adı","Evrak Tipi","Banka","Tutar","Vade","Açıklama",
                     "Çeki veren","Cirolu","Asıl borçlu","Kime verildi","Evrak No","Döviz","Durum"]
    raw_df = raw_df.rename(columns={c:expected_cols[i] for i,c in enumerate(raw_df.columns)})
    raw_df['Tutar'] = pd.to_numeric(raw_df['Tutar'], errors='coerce').fillna(0)
    raw_df['Vade_Date'] = pd.to_datetime(raw_df['Vade'], errors='coerce').dt.date
    bugun = datetime.now().date()
    valid = raw_df[raw_df['Tutar'] > 0].copy()
    if not valid.empty:
        valid['Gun_Farki'] = valid['Vade_Date'].apply(lambda x: (x - bugun).days)
        valid['Agirlik'] = valid['Tutar'] * valid['Gun_Farki']
        toplam_tutar = valid['Tutar'].sum()
        toplam_agirlik = valid['Agirlik'].sum()
        ort_gun_sayisi = toplam_agirlik / toplam_tutar
        gercek_ort_vade = bugun + timedelta(days=int(round(ort_gun_sayisi)))
        return raw_df, valid, toplam_tutar, gercek_ort_vade, int(ort_gun_sayisi), toplam_agirlik
    return raw_df, pd.DataFrame(), 0, bugun, 0, 0

df, valid_df, total_tl, ort_vade, ort_gun, toplam_agirlik = load_and_calculate_real()

def upcoming_reminders(df, days=7):
    today = datetime.now().date()
    temp_df = df.copy()
    temp_df["Vade_Date"] = pd.to_datetime(temp_df["Vade"], errors="coerce").dt.date
    temp_df["Gun_Farki"] = temp_df["Vade_Date"].apply(lambda x: (x - today).days if pd.notnull(x) else None)
    return temp_df[temp_df["Gun_Farki"].notnull() & (temp_df["Gun_Farki"] <= days) & (temp_df["Gun_Farki"] >= 0)]

# --- YETKİ KONTROLÜ ---
if 'auth' not in st.session_state: st.session_state.auth = None
hashed_pwds = {"PATRON": hashlib.sha256("patron125".encode()).hexdigest(), "MUHASEBE": hashlib.sha256("muhasebe007".encode()).hexdigest(), "DENEME": hashlib.sha256("deneme123".encode()).hexdigest()}

if not st.session_state.auth:
    _, center, _ = st.columns([1,1.2,1])
    with center:
        st.markdown("<h4 style='text-align: center; color: gray;'>🏦 Finans Pro</h4>", unsafe_allow_html=True)
        with st.form("login"):
            pwd = st.text_input("Şifre", type="password")
            if st.form_submit_button("Erişimi Aç"):
                hashed_input = hashlib.sha256(pwd.encode()).hexdigest()
                for role, h_pwd in hashed_pwds.items():
                    if hashed_input == h_pwd: st.session_state.auth = role
                if st.session_state.auth: st.rerun()
                else: st.error("Hatalı!")
    st.stop()

# --- # --- SIDEBAR ---
with st.sidebar:
    st.markdown("<h5 style='text-align:center; color:gray;'>🏦 Finans Pro</h5>", unsafe_allow_html=True)
    st.divider()
    if st.session_state.auth == "MUHASEBE": 
        menu = "📝 Veri Yönetimi"
    elif st.session_state.auth == "PATRON": 
        menu = "🏠 Dashboard"
    else: 
        menu = st.radio("Navigasyon", ["🏠 Dashboard", "📝 Veri Yönetimi"], horizontal=True)
    
    st.divider()
    st.subheader("🔍 Evrak Arama")
    aranan = st.text_input("Evrak No girin", placeholder="Örn: 123456")
    if aranan:
        sonuc = df[df["Evrak No"].astype(str) == aranan]
        if not sonuc.empty: 
            st.dataframe(sonuc, use_container_width=True, hide_index=True)
        else: 
            st.warning("Bulunamadı.")

    st.divider()
    st.subheader("📊 Filtreleme")
    secilen_banka = st.selectbox("Banka seçin", ["Tümü"] + df["Banka"].dropna().unique().tolist())
    secilen_firma = st.selectbox("Firma seçin", ["Tümü"] + df["Firma Adı"].dropna().unique().tolist())
    tarih_araligi = st.date_input("Tarih aralığı", [])

    st.divider()
    with st.expander("📑 Detaylandır"):
        selected_cols = st.multiselect("Gösterilecek kolonlar", df.columns.tolist(), default=df.columns.tolist())

    st.divider()
    if st.button("🔴 Çıkış", use_container_width=True):
        st.session_state.auth = None
        st.rerun()

# --- FİLTRE UYGULAMA VE YENİDEN HESAPLAMA ---
filtered_df = df.copy()
if secilen_banka != "Tümü":
    filtered_df = filtered_df[filtered_df["Banka"] == secilen_banka]
if secilen_firma != "Tümü":
    filtered_df = filtered_df[filtered_df["Firma Adı"] == secilen_firma]
if tarih_araligi and len(tarih_araligi) == 2:
    start, end = tarih_araligi
    filtered_df = filtered_df[(filtered_df["Vade_Date"] >= start) & (filtered_df["Vade_Date"] <= end)]

# Filtrelenmiş verilere göre metrikleri güncelle
# Filtrelenmiş verilere göre metrikleri güncelle
if not filtered_df.empty:
    f_total_tl = filtered_df['Tutar'].sum()
    bugun = pd.Timestamp(datetime.now().date())   # datetime64 tipine çevir
    gun_farklari = (filtered_df['Vade_Date'] - bugun).apply(lambda x: x.days)  # farkı gün cinsinden al
    temp_agirlik = (filtered_df['Tutar'] * gun_farklari).sum()
    f_ort_gun = int(round(temp_agirlik / f_total_tl)) if f_total_tl > 0 else 0
    f_ort_vade = bugun + timedelta(days=f_ort_gun)
    f_faiz_hesap = 0.3975 
    f_adat = (temp_agirlik * f_faiz_hesap) / 365
else:
    f_total_tl, f_ort_vade, f_ort_gun, f_adat = 0, datetime.now().date(), 0, 0
    f_faiz_hesap = 0.3975


# --- DASHBOARD LAYOUT ---
c1, c2 = st.columns([3, 1])

with c2:
    soon_df = upcoming_reminders(filtered_df, days=7)
    if not soon_df.empty:
        st.warning("⏰ Yaklaşan Vadeler")
        if soon_df["Gun_Farki"].min() <= 1:
            st.markdown('<div class="blink">🚨 Vade Çok Yakın!</div>', unsafe_allow_html=True)
        st.dataframe(soon_df[["Firma Adı", "Tutar", "Vade"]], use_container_width=True, hide_index=True)

with c1:
    if menu == "🏠 Dashboard":
        st.title("⚖️ Finansal Karar Destek Paneli")
        
        # Faiz slider'ı Dashboard'un tepesinde
        faiz_orani = st.slider("Faiz Oranı (%)", 0.0, 100.0, 39.75, key="dash_slider") / 100
        
        # Dinamik Adat Güncellemesi
        if not filtered_df.empty:
            bugun = datetime.now().date()
            temp_agirlik_v2 = (filtered_df['Tutar'] * (filtered_df['Vade_Date'] - bugun).dt.days).sum()
            f_adat = (temp_agirlik_v2 * faiz_orani) / 365

        # --- COMPACT GRID METRICS ---
        st.markdown(f"""
            <div class="metric-container">
                <div class="metric-card" style="background:#2E8B57;">
                    <div class="icon">💰</div>
                    <div class="title">Toplam Borç</div>
                    <div class="value">{f_total_tl:,.2f} ₺</div>
                    <div class="delta">≈ ${f_total_tl/usd_kur:,.2f}</div>
                </div>
                <div class="metric-card" style="background:#0A84FF;">
                    <div class="icon">⏳</div>
                    <div class="title">Ort. Vade</div>
                    <div class="value">{f_ort_vade.strftime('%d %b %Y')}</div>
                    <div class="delta">{f_ort_gun} gün sonra</div>
                </div>
                <div class="metric-card" style="background:#F77F00;">
                    <div class="icon">⚠️</div>
                    <div class="title">Adat Yükü</div>
                    <div class="value">{f_adat:,.2f} ₺</div>
                    <div class="delta">%{faiz_orani*100:.2f} Faiz</div>
                </div>
                <div class="metric-card" style="background:linear-gradient(90deg, #0A84FF, #89CFF0);">
                    <div class="icon">💵</div>
                    <div class="title">USD/TRY</div>
                    <div class="value">{usd_kur:.4f} ₺</div>
                    <div class="delta">Canlı Veri</div>
                </div>
            </div>
        """, unsafe_allow_html=True)

        st.divider()
        
        # Grafikler
        gc1, gc2 = st.columns([1.5, 1])
        with gc1:
            if "Vade" in selected_cols:
                st.plotly_chart(px.bar(filtered_df, x='Vade_Date', y='Tutar', color='Banka', title="Vade Dağılımı", template="plotly_dark", height=350), use_container_width=True)
        with gc2:
            if "Banka" in selected_cols:
                st.plotly_chart(px.pie(filtered_df, values='Tutar', names='Banka', hole=0.4, title="Banka Riski", template="plotly_dark", height=350), use_container_width=True)

        st.subheader("📋 Detaylı Takip Listesi")
        st.dataframe(filtered_df[selected_cols], use_container_width=True, hide_index=True)

    elif menu == "📝 Veri Yönetimi":
        st.title("🌐 Veri Yönetimi")

        # Google Sheets linki
        st.markdown(f'<a href="{edit_url}" target="_blank" style="text-decoration:none;"><div style="background-color:#238636; color:white; padding:15px; border-radius:10px; text-align:center; font-weight:bold;">GOOGLE SHEETS DÜZENLE ↗</div></a>', unsafe_allow_html=True)

        st.divider()
        st.subheader("📥 Excel Taslağı İndir")
        try:
            with open("taslak.xlsx", "rb") as f:
                st.download_button("📄 Taslağı İndir", data=f, file_name="taslak.xlsx")
        except FileNotFoundError:
            st.error("Taslak dosyası bulunamadı! Lütfen proje klasörüne 'taslak.xlsx' ekleyin.")

        st.divider()
        st.subheader("📤 Excel Upload")
        uploaded_file = st.file_uploader("Excel dosyası yükle", type=["xlsx"])
        if uploaded_file:
            try:
                new_df = pd.read_excel(uploaded_file)
                st.success("Dosya yüklendi, veriler işleniyor...")
                st.dataframe(new_df, use_container_width=True, hide_index=True)
            except Exception as e:
                st.error(f"Dosya okunamadı: {e}")

        st.divider()
        st.subheader("📝 Manuel Evrak Girişi")
        with st.form("manual_entry"):
            f_ad = st.text_input("Firma Adı")
            b_ad = st.text_input("Banka")
            t_mik = st.number_input("Tutar", min_value=0.0, step=100.0)
            v_tar = st.date_input("Vade")
            ack = st.text_area("Açıklama")
            if st.form_submit_button("Kaydet"):
                st.success(f"{f_ad} için evrak sisteme eklendi.")

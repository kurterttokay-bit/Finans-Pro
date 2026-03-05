if menu == "Dashboard":
    st.markdown("""
    <style>
      .block-container { padding-top: 1.2rem; padding-bottom: 2rem; }
      div[data-testid="stMetric"] {
        background: rgba(255,255,255,0.05);
        border: 1px solid rgba(255,255,255,0.08);
        padding: 14px 14px 10px 14px;
        border-radius: 16px;
      }
      .card {
        background: rgba(255,255,255,0.05);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 16px;
        padding: 14px;
      }
      .muted { opacity: .75; font-size: .92rem; }
    </style>
    """, unsafe_allow_html=True)

    st.title("📊 Finans Dashboard")

    if df.empty:
        st.warning("Veri yok / Google Sheets okunamadı. Sheet erişimini kontrol edin.")
        st.stop()

    # -------------------------
    # Filtre Bar
    # -------------------------
    with st.container():
        c1, c2, c3, c4 = st.columns([1.2, 1, 1, 1])
        with c1:
            q = st.text_input("🔎 Firma ara", placeholder="örn: SS GLOBAL")
        with c2:
            only_overdue = st.toggle("Sadece gecikenler", value=False)
        with c3:
            currency = st.selectbox("Para birimi", ["TL", "Orijinal"], index=0)
        with c4:
            horizon = st.selectbox("Vade ufku", ["Hepsi", "0-7 gün", "8-30 gün", "31-90 gün", "90+ gün"], index=0)

    dfx = df.copy()

    # arama
    if q.strip():
        col_candidates = [c for c in ["Firma", "firma", "Unvan", "Cari"] if c in dfx.columns]
        if col_candidates:
            col = col_candidates[0]
            dfx = dfx[dfx[col].astype(str).str.contains(q, case=False, na=False)]

    # vade filtre
    today = pd.Timestamp(datetime.now().date())
    if "Vade_Date" in dfx.columns:
        dfx["days_to_due"] = (dfx["Vade_Date"] - today).dt.days
    else:
        dfx["days_to_due"] = None

    if only_overdue:
        dfx = dfx[dfx["days_to_due"].fillna(10**9) < 0]

    if horizon != "Hepsi":
        d = dfx["days_to_due"].fillna(10**9)
        if horizon == "0-7 gün":
            dfx = dfx[(d >= 0) & (d <= 7)]
        elif horizon == "8-30 gün":
            dfx = dfx[(d >= 8) & (d <= 30)]
        elif horizon == "31-90 gün":
            dfx = dfx[(d >= 31) & (d <= 90)]
        else:
            dfx = dfx[d >= 91]

    # tutar kolon seçimi
    if currency == "TL" and "Tutar_TL" in dfx.columns:
        amt_col = "Tutar_TL"
        amt_suffix = "₺"
    else:
        amt_col = "Tutar"
        amt_suffix = ""

    # -------------------------
    # KPI Kartları
    # -------------------------
    valid = dfx[dfx["Vade_Date"].notnull()].copy()
    valid["days_to_due"] = (valid["Vade_Date"] - today).dt.days

    total = float(valid[amt_col].sum()) if not valid.empty else 0.0
    overdue = float(valid.loc[valid["days_to_due"] < 0, amt_col].sum()) if not valid.empty else 0.0
    due7 = float(valid.loc[(valid["days_to_due"] >= 0) & (valid["days_to_due"] <= 7), amt_col].sum()) if not valid.empty else 0.0
    due30 = float(valid.loc[(valid["days_to_due"] > 7) & (valid["days_to_due"] <= 30), amt_col].sum()) if not valid.empty else 0.0

    # Ortalama vade
    if not valid.empty and total > 0:
        weighted = float((valid[amt_col] * valid["days_to_due"]).sum())
        avg_days = weighted / total
        avg_date = (today + timedelta(days=int(avg_days))).strftime("%d.%m.%Y")
    else:
        avg_date = today.strftime("%d.%m.%Y")

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Toplam Borç", f"{total:,.2f} {amt_suffix}")
    k2.metric("🔴 Geciken", f"{overdue:,.2f} {amt_suffix}")
    k3.metric("🟠 0-7 gün", f"{due7:,.2f} {amt_suffix}")
    k4.metric("🟡 8-30 gün", f"{due30:,.2f} {amt_suffix}")
    k5.metric("⏳ Ortalama Vade", avg_date)

    st.markdown("---")

    # -------------------------
    # Grafik Alanı
    # -------------------------
    left, right = st.columns([1.25, 1])

    with left:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("📅 Ödeme Takvimi")
        if not valid.empty:
            pay = valid.groupby("Vade_Date")[amt_col].sum().reset_index()
            fig = px.bar(pay, x="Vade_Date", y=amt_col)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Grafik için vade tarihi olan kayıt yok.")
        st.markdown('</div>', unsafe_allow_html=True)

    with right:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("🧨 Risk Dağılımı")

        if not valid.empty:
            bins = pd.cut(
                valid["days_to_due"],
                bins=[-10**6, -1, 7, 30, 90, 10**6],
                labels=["Geciken", "0-7", "8-30", "31-90", "90+"]
            )
            risk = valid.groupby(bins)[amt_col].sum().reset_index()
            risk.columns = ["Risk", "Tutar"]
            fig2 = px.pie(risk, names="Risk", values="Tutar", hole=0.55)
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Risk analizi için veri yok.")
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("---")

    # -------------------------
    # Firma / Ürün dağılımı + Riskli kalemler
    # -------------------------
    a, b = st.columns([1, 1])

    with a:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("🏢 İlk 10 Firma")
        # Firma kolonu senin sheet’e göre değişebilir:
        firma_col = next((c for c in ["Firma", "firma", "Unvan", "Cari"] if c in valid.columns), None)
        if firma_col:
            top = valid.groupby(firma_col)[amt_col].sum().sort_values(ascending=False).head(10).reset_index()
            fig3 = px.bar(top, x=firma_col, y=amt_col)
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.info("Firma kolonu bulunamadı (Sheet kolon adını kontrol edin).")
        st.markdown('</div>', unsafe_allow_html=True)

    with b:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("⚠️ En Riskli Kalemler (Geciken / Yakın Vade)")
        if not valid.empty:
            risk_table = valid.sort_values("days_to_due").head(12)
            cols = [c for c in [firma_col, "Vade_Date", "days_to_due", amt_col, "Döviz"] if c and c in risk_table.columns]
            st.dataframe(risk_table[cols], use_container_width=True, height=360)
        else:
            st.info("Gösterilecek riskli kalem yok.")
        st.markdown('</div>', unsafe_allow_html=True)

    # -------------------------
    # AI CFO (buton) - mevcut fonksiyonun aynen kalsın
    # -------------------------
    st.markdown("---")
    cta1, cta2 = st.columns([1, 2])
    with cta1:
        if st.button("🧠 AI CFO Analizi Yap", use_container_width=True):
            with st.spinner("AI analiz ediyor..."):
                st.markdown(ai_cfo_analysis(df))
    with cta2:
        st.markdown('<div class="muted">İpucu: Filtreleyip sonra AI CFO çalıştırırsan analiz çok daha isabetli olur.</div>', unsafe_allow_html=True)

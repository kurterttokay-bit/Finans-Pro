import streamlit as st
import google.generativeai as genai
from PIL import Image
import json

# API anahtarını güvenli şekilde çekiyoruz
api_key = st.secrets.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)
else:
    st.error("API Anahtarı bulunamadı! Lütfen Streamlit Secrets ayarlarını yap.")

def analyze_invoice(image_file):
    try:
        # En kararlı model ismini kullanıyoruz
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        img = Image.open(image_file)
        
        prompt = """
        Bu faturayı/çeki analiz et ve bilgileri şu JSON formatında döndür:
        {
          "firma_adi": "...",
          "tutar": 0.0,
          "vade": "YYYY-MM-DD",
          "borclu": "..."
        }
        Sadece JSON döndür, başka açıklama yapma.
        """
        
        response = model.generate_content([prompt, img])
        
        # Markdown temizliği
        clean_res = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(clean_res)
    except Exception as e:
        # Hatayı detaylı görmek için
        st.error(f"AI Teknik Hatası: {str(e)}")
        return None

# --- UI KISMI ---
st.title("📸 AI Fatura Tarama")
uploaded_file = st.file_uploader("Fatura Görseli", type=['png', 'jpg', 'jpeg'])

if uploaded_file:
    st.image(uploaded_file, caption="Yüklenen Evrak", width=400)
    if st.button("🔍 Verileri Analiz Et"):
        with st.spinner("AI inceliyor, lütfen bekleyin..."):
            sonuc = analyze_invoice(uploaded_file)
            if sonuc:
                st.success("Veriler başarıyla ayrıştırıldı!")
                st.json(sonuc)


import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="Envío Masivo WhatsApp", layout="centered")

st.title("📤 Envío Masivo de WhatsApp con Excel")

api_key = st.text_input("🔐 Ingresa tu API Key de 360dialog", type="password")
endpoint = "https://waba-v2.360dialog.io/messages"

uploaded_file = st.file_uploader("📎 Sube tu archivo Excel con los contactos", type=["xlsx"])

if uploaded_file and api_key:
    df = pd.read_excel(uploaded_file)

    st.success(f"Archivo cargado con {len(df)} filas.")
    plantilla_col = st.selectbox("🧩 Columna que contiene el nombre de la plantilla:", df.columns)
    telefono_col = st.selectbox("📱 Columna de teléfono:", df.columns)
    pais_col = st.selectbox("🌎 Columna del código de país:", df.columns)

    param_cols = [col for col in df.columns if col.startswith("{{")]

    if st.button("🚀 Enviar mensajes"):
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        for i, row in df.iterrows():
            numero = f"{row[pais_col]}{row[telefono_col]}"
            plantilla = row[plantilla_col]
            componentes = []
            if param_cols:
                componentes.append({
                    "type": "body",
                    "parameters": [{"type": "text", "text": str(row[param])} for param in param_cols]
                })
            payload = {
                "messaging_product": "whatsapp",
                "to": numero,
                "type": "template",
                "template": {
                    "name": plantilla,
                    "language": {"code": "es_MX"},
                    "components": componentes
                }
            }
            response = requests.post(endpoint, headers=headers, json=payload)
            if response.status_code == 200:
                st.write(f"✅ Enviado a {numero}")
            else:
                st.write(f"❌ Error con {numero}: {response.text}")

import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="Envío Masivo de WhatsApp", layout="centered")

st.title("📨 Envío Masivo de WhatsApp con Excel")

# Ingresar API Key
api_key = st.text_input("🔐 Ingresa tu API Key de 360dialog", type="password")

# Cargar archivo Excel
st.subheader("📁 Sube tu archivo Excel con los contactos")
file = st.file_uploader("Drag and drop o haz clic para subir (.xlsx)", type=["xlsx"])

if file:
    df = pd.read_excel(file)
    st.success(f"Archivo cargado con {len(df)} filas.")

    # Mostrar columnas disponibles
    columns = df.columns.tolist()
    plantilla = st.selectbox("🧩 Columna con el nombre de la plantilla:", columns)
    telefono_col = st.selectbox("📱 Columna del teléfono:", columns)
    pais_col = st.selectbox("🌎 Columna del código de país:", columns)

    # Parámetros opcionales
    param1 = st.selectbox("🔢 Parámetro {{1}}:", ["(ninguno)"] + columns)
    param2 = st.selectbox("🔢 Parámetro {{2}} (opcional):", ["(ninguno)"] + columns)

    if st.button("🚀 Enviar mensajes"):
        if not api_key:
            st.error("⚠️ Debes ingresar una API Key.")
            st.stop()

        for idx, row in df.iterrows():
            to_number = f"{row[pais_col]}{row[telefono_col]}"
            template_name = row[plantilla]
            language = "es_MX"

            components = [{
                "type": "body",
                "parameters": []
            }]

            if param1 != "(ninguno)":
                components[0]["parameters"].append({
                    "type": "text",
                    "text": str(row[param1])
                })

            if param2 != "(ninguno)":
                components[0]["parameters"].append({
                    "type": "text",
                    "text": str(row[param2])
                })

            payload = {
                "messaging_product": "whatsapp",
                "to": to_number,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {
                        "code": language
                    },
                    "components": components
                }
            }

            headers = {
                "Content-Type": "application/json",
                "D360-API-KEY": api_key
            }

            response = requests.post("https://waba-v2.360dialog.io/messages", headers=headers, json=payload)

            if response.status_code == 200:
                st.success(f"✅ Mensaje enviado a {to_number}")
            else:
                st.error(f"❌ Error con {to_number}: {response.text}")

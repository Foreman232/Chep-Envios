import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="Envío Masivo de WhatsApp", layout="centered")
st.title("📨 Envío Masivo de WhatsApp con Excel")

api_key = st.text_input("🔐 Ingresa tu API Key de 360dialog", type="password")
file = st.file_uploader("📁 Sube tu archivo Excel con los contactos", type=["xlsx"])

if file:
    df = pd.read_excel(file)
    st.success(f"Archivo cargado con {len(df)} filas.")
    df.columns = df.columns.str.strip()
    columns = df.columns.tolist()

    plantilla = st.selectbox("🧩 Columna de la plantilla:", columns)
    telefono_col = st.selectbox("📱 Columna del teléfono:", columns)
    pais_col = st.selectbox("🌎 Columna del código de país:", columns)
    param1 = st.selectbox("🔢 Parámetro {{1}}:", columns)
    param2 = st.selectbox("🔢 Parámetro {{2}} (opcional):", ["(ninguno)"] + columns)

    if st.button("🚀 Enviar mensajes"):
        if not api_key:
            st.error("⚠️ Debes ingresar una API Key.")
            st.stop()

        for idx, row in df.iterrows():
            phone = f"{str(row[pais_col]).strip()}{str(row[telefono_col]).strip().replace(' ', '').replace('-', '')}"
            template_name = row[plantilla]
            name = str(row[param1])
            language = "es_MX"

            parameters = [{"type": "text", "text": name}]
            if param2 != "(ninguno)":
                parameters.append({"type": "text", "text": str(row[param2])})

            payload = {
                "messaging_product": "whatsapp",
                "to": phone,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": language},
                    "components": [{
                        "type": "body",
                        "parameters": parameters
                    }]
                }
            }

            headers = {
                "Content-Type": "application/json",
                "D360-API-KEY": api_key
            }

            r = requests.post("https://waba-v2.360dialog.io/messages", headers=headers, json=payload)

            if r.status_code == 200:
                st.success(f"✅ WhatsApp: {phone}")

                # Enviar a Chatwoot
                chatwoot_payload = {
                    "phone": phone,
                    "name": name,
                    "content": name  # Puedes cambiar esto si quieres otro mensaje
                }

                try:
                    cw = requests.post("https://srv870442.hstgr.cloud/send-chatwoot-message", json=chatwoot_payload)
                    if cw.status_code == 200:
                        st.info(f"📥 Chatwoot OK: {phone}")
                    else:
                        st.warning(f"⚠️ Chatwoot error: {cw.text}")
                except Exception as e:
                    st.error(f"❌ Fallo al reflejar en Chatwoot: {e}")

            else:
                st.error(f"❌ WhatsApp error {phone}: {r.text}")

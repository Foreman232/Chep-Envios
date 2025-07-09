import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="Envío Masivo de WhatsApp", layout="centered")
st.title("📨 Envío Masivo de WhatsApp con Excel")

api_key = st.text_input("🔐 Ingresa tu API Key de 360dialog", type="password")
file = st.file_uploader("📁 Sube tu archivo Excel", type=["xlsx"])

if file:
    df = pd.read_excel(file)
    st.success(f"Archivo cargado con {len(df)} filas.")
    df.columns = df.columns.str.strip()
    columns = df.columns.tolist()

    plantilla = st.selectbox("🧩 Columna plantilla:", columns)
    telefono_col = st.selectbox("📱 Teléfono:", columns)
    pais_col = st.selectbox("🌎 Código país:", columns)
    param1 = st.selectbox("🔢 Parámetro {{1}}:", columns)
    param2 = st.selectbox("🔢 Parámetro {{2}} (opcional):", ["(ninguno)"] + columns)

    if st.button("🚀 Enviar mensajes"):
        if not api_key:
            st.error("⚠️ Falta API Key.")
            st.stop()

        for idx, row in df.iterrows():
            raw_number = f"{str(row[pais_col])}{str(row[telefono_col])}".replace(' ', '').replace('-', '')
            name = str(row[param1])
            parameters = [{"type": "text", "text": name}]

            if param2 != "(ninguno)":
                parameters.append({"type": "text", "text": str(row[param2])})

            payload = {
                "messaging_product": "whatsapp",
                "to": raw_number,
                "type": "template",
                "template": {
                    "name": row[plantilla],
                    "language": {"code": "es_MX"},
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
                st.success(f"✅ WhatsApp OK: {raw_number}")

                chatwoot_payload = {
                    "phone": raw_number,
                    "name": name,
                    "content": f"Mensaje enviado: {name}"
                }

                try:
                    cw = requests.post("https://srv870442.hstgr.cloud/send-chatwoot-message", json=chatwoot_payload)
                    if cw.status_code == 200:
                        st.info(f"📥 Reflejado en Chatwoot: {raw_number}")
                    else:
                        st.warning(f"⚠️ Chatwoot error: {cw.text}")
                except Exception as e:
                    st.error(f"❌ Error al reflejar en Chatwoot: {e}")

            else:
                st.error(f"❌ WhatsApp error: {r.text}")

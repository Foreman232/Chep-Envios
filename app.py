import streamlit as st
import pandas as pd
import requests

# Configuración inicial de la app
st.set_page_config(page_title="Envío Masivo de WhatsApp", layout="centered")
st.title("📨 Envío Masivo de WhatsApp con Excel")

# Entrada de la API Key
api_key = st.text_input("🔐 Ingresa tu API Key de 360dialog", type="password")

# Subida de archivo Excel
file = st.file_uploader("📁 Sube tu archivo Excel", type=["xlsx"])

if file:
    # Lectura del archivo y validación
    df = pd.read_excel(file)
    st.success(f"Archivo cargado con {len(df)} filas.")
    df.columns = df.columns.str.strip()
    columns = df.columns.tolist()

    # Selección de columnas
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
            try:
                # Limpieza del número de teléfono
                raw_number = f"{str(row[pais_col])}{str(row[telefono_col])}"
                raw_number = raw_number.replace(' ', '').replace('-', '').replace('+', '')

                name = str(row[param1])
                parameters = [{"type": "text", "text": name}]

                content_text = f"Plantilla: {row[plantilla]} - Param1: {name}"

                if param2 != "(ninguno)":
                    second_param = str(row[param2])
                    parameters.append({"type": "text", "text": second_param})
                    content_text += f" - Param2: {second_param}"

                # Payload para WhatsApp
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

                    # Reflejo en Chatwoot
                    chatwoot_payload = {
                        "phone": raw_number,
                        "name": name,
                        "content": content_text
                    }

                    try:
                        cw = requests.post("https://srv870442.hstgr.cloud/send-chatwoot-message", json=chatwoot_payload, timeout=5)
                        if cw.status_code == 200:
                            st.info(f"📥 Reflejado en Chatwoot: {raw_number}")
                        else:
                            st.warning(f"⚠️ Chatwoot error ({cw.status_code}): {cw.text}")
                    except Exception as e:
                        st.error(f"❌ Error conectando con Chatwoot: {e}")
                else:
                    st.error(f"❌ Error WhatsApp {raw_number}: {r.status_code} - {r.text}")

            except Exception as e:
                st.error(f"❌ Error en fila {idx + 1}: {e}")

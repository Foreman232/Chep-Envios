import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="Envío Masivo de WhatsApp", layout="centered")
st.title("📨 Envío Masivo de WhatsApp con Excel")

api_key = st.text_input("🔐 Ingresa tu API Key de 360dialog", type="password")

st.subheader("📁 Sube tu archivo Excel con los contactos")
file = st.file_uploader("Arrastra o haz clic para subir (.xlsx)", type=["xlsx"])

if file:
    df = pd.read_excel(file)
    st.success(f"Archivo cargado con {len(df)} filas.")
    df.columns = df.columns.str.strip()

    columns = df.columns.tolist()
    plantilla_col = st.selectbox("🧩 Columna con el nombre de la plantilla:", columns)
    telefono_col = st.selectbox("📱 Columna del teléfono:", columns)
    pais_col = st.selectbox("🌎 Columna del código de país:", columns)

    param1 = st.selectbox("🔢 Parámetro {{1}} (Nombre del cliente):", columns)
    param2 = st.selectbox("🔢 Parámetro {{2}} (opcional):", ["(ninguno)"] + columns)

    if st.button("🚀 Enviar mensajes"):
        if not api_key:
            st.error("⚠️ Debes ingresar una API Key.")
            st.stop()

        for idx, row in df.iterrows():
            try:
                to_number = f"{row[pais_col]}{row[telefono_col]}"
                template_name = row[plantilla_col]
                language = "es_MX"

                parameters = [{
                    "type": "text",
                    "text": str(row[param1]) if not pd.isna(row[param1]) else ""
                }]
                if param2 != "(ninguno)" and not pd.isna(row[param2]):
                    parameters.append({
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

                response = requests.post("https://waba-v2.360dialog.io/messages", headers=headers, json=payload)

                if response.status_code == 200:
                    st.success(f"✅ Mensaje enviado a {to_number}")

                    # Reflejar mensaje en Chatwoot
                    msg_text = " ".join([p["text"] for p in parameters])
                    cw_payload = {
                        "phone": to_number,
                        "name": str(row[param1]) if not pd.isna(row[param1]) else "Cliente WhatsApp",
                        "message": msg_text
                    }
                    try:
                        cw_response = requests.post("https://srv870442.hstgr.cloud/send-chatwoot-message", json=cw_payload)
                        if cw_response.status_code == 200:
                            st.info("💬 Reflejado en Chatwoot")
                        else:
                            st.warning(f"⚠️ Enviado a WhatsApp, pero Chatwoot falló ({cw_response.status_code})")
                    except Exception as e:
                        st.warning(f"⚠️ WhatsApp enviado, pero Chatwoot falló: {e}")
                else:
                    st.error(f"❌ Error con {to_number}: {response.text}")

            except Exception as general_err:
                st.error(f"❌ Error procesando fila {idx + 1}: {general_err}")

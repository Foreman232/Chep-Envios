import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="Envío Masivo de WhatsApp", layout="centered")
st.title("📨 Envío Masivo de WhatsApp con Excel")

api_key = "icCVWtPvpn2Eb9c2C5wjfA4NAK"
chatwoot_token = "vP4SkyT1VZZVNsYTE6U6xjxP"
base_url = "https://srv870442.hstgr.cloud/api/v1/accounts/1"
inbox_id = 1

file = st.file_uploader("📁 Sube tu archivo Excel con los contactos (.xlsx)", type=["xlsx"])

if file:
    df = pd.read_excel(file)
    st.success(f"✅ Archivo cargado con {len(df)} filas.")
    df.columns = df.columns.str.strip()
    columns = df.columns.tolist()

    plantilla = st.selectbox("🧩 Columna con el nombre de la plantilla:", columns)
    telefono_col = st.selectbox("📱 Columna del teléfono:", columns)
    pais_col = st.selectbox("🌎 Columna del código de país:", columns)
    param1 = st.selectbox("🔢 Parámetro {{1}} (nombre cliente):", columns)
    param2 = st.selectbox("🔢 Parámetro {{2}} (opcional):", ["(ninguno)"] + columns)

    if st.button("🚀 Enviar mensajes"):
        for idx, row in df.iterrows():
            to_number = f"{row[pais_col]}{row[telefono_col]}"
            to_number_plus = f"+{to_number}"
            template_name = row["nombre_plantilla"]
            language = "es_MX"

            parameters = [{"type": "text", "text": str(row[param1])}]
            if param2 != "(ninguno)":
                parameters.append({"type": "text", "text": str(row[param2])})

            payload = {
                "messaging_product": "whatsapp",
                "to": to_number,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": language},
                    "components": [{"type": "body", "parameters": parameters}]
                }
            }

            headers = {
                "Content-Type": "application/json",
                "D360-API-KEY": api_key
            }

            response = requests.post("https://waba-v2.360dialog.io/messages", headers=headers, json=payload)

            if response.status_code == 200:
                st.success(f"✅ WhatsApp enviado a {to_number}")

                try:
                    headers_cw = {"api_access_token": chatwoot_token}

                    # Crear contacto o buscar
                    contact_payload = {
                        "identifier": to_number_plus,
                        "name": str(row[param1]),
                        "phone_number": to_number_plus,
                        "inbox_id": inbox_id
                    }
                    r = requests.post(f"{base_url}/contacts", json=contact_payload, headers=headers_cw)
                    if "has already been taken" in r.text or r.status_code == 422:
                        r = requests.get(f"{base_url}/contacts/search?q={to_number_plus}", headers=headers_cw)
                        contact_id = r.json()["payload"][0]["id"]
                    else:
                        contact_id = r.json()["payload"]["id"]

                    # Enlazar contacto al inbox
                    try:
                        requests.post(f"{base_url}/contacts/{contact_id}/contact_inboxes", json={
                            "inbox_id": inbox_id,
                            "source_id": to_number_plus
                        }, headers=headers_cw)
                    except:
                        pass

                    # Buscar o crear conversación
                    r_conv = requests.get(f"{base_url}/contacts/{contact_id}/conversations", headers=headers_cw)
                    if r_conv.json()["payload"]:
                        conversation_id = r_conv.json()["payload"][0]["id"]
                    else:
                        r_conv = requests.post(f"{base_url}/conversations", json={
                            "source_id": to_number_plus,
                            "inbox_id": inbox_id
                        }, headers=headers_cw)
                        conversation_id = r_conv.json()["id"]

                    # Enviar mensaje como saliente
                    msg_text = parameters[0]["text"]
                    msg_payload = {
                        "content": msg_text,
                        "message_type": "outgoing",
                        "private": False
                    }
                    requests.post(f"{base_url}/conversations/{conversation_id}/messages", json=msg_payload, headers=headers_cw)

                except Exception as e:
                    st.warning(f"⚠️ WhatsApp enviado, pero falló en Chatwoot: {e}")

            else:
                st.error(f"❌ Error con {to_number}: {response.text}")

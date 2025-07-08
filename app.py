import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="Envío Masivo de WhatsApp", layout="centered")

st.title("📨 Envío Masivo de WhatsApp con Excel")

api_key = "icCVWtPvpn2Eb9c2C5wjfA4NAK"  # ✅ 360dialog API Key fija

st.subheader("📁 Sube tu archivo Excel con los contactos")
file = st.file_uploader("Sube un archivo (.xlsx)", type=["xlsx"])

if file:
    df = pd.read_excel(file)
    df.columns = df.columns.str.strip()
    st.success(f"Archivo cargado con {len(df)} registros")

    columns = df.columns.tolist()
    plantilla_col = st.selectbox("🧩 Columna del nombre de la plantilla", columns)
    telefono_col = st.selectbox("📱 Columna del teléfono", columns)
    pais_col = st.selectbox("🌎 Columna del código de país", columns)
    param1 = st.selectbox("🔢 Parámetro {{1}} (Nombre)", columns)
    param2 = st.selectbox("🔢 Parámetro {{2}} (opcional)", ["(ninguno)"] + columns)

    if st.button("🚀 Enviar mensajes"):
        for _, row in df.iterrows():
            to_number = f"{row[pais_col]}{row[telefono_col]}"
            plantilla = row[plantilla_col]
            name_param1 = str(row[param1])
            name_param2 = str(row[param2]) if param2 != "(ninguno)" else None

            # Payload para 360dialog
            components = [{
                "type": "body",
                "parameters": [{"type": "text", "text": name_param1}]
            }]
            if name_param2:
                components[0]["parameters"].append({"type": "text", "text": name_param2})

            payload = {
                "messaging_product": "whatsapp",
                "to": to_number,
                "type": "template",
                "template": {
                    "name": plantilla,
                    "language": {"code": "es_MX"},
                    "components": components
                }
            }

            headers = {
                "Content-Type": "application/json",
                "D360-API-KEY": api_key
            }

            r = requests.post("https://waba-v2.360dialog.io/messages", headers=headers, json=payload)

            if r.status_code == 200:
                st.success(f"✅ WhatsApp enviado a {to_number}")

                # Reflejar mensaje saliente en Chatwoot
                try:
                    chatwoot_token = "vP4SkyT1VZZVNsYTE6U6xjxP"
                    base_url = "https://srv870442.hstgr.cloud/api/v1/accounts/1"
                    headers_cw = {"api_access_token": chatwoot_token}
                    to_plus = f"+{to_number}"

                    # Crear o buscar contacto
                    contact_payload = {
                        "identifier": to_plus,
                        "name": name_param1,
                        "phone_number": to_plus,
                        "inbox_id": 1
                    }
                    r = requests.post(f"{base_url}/contacts", json=contact_payload, headers=headers_cw)

                    if r.status_code == 422 or "has already been taken" in r.text:
                        r = requests.get(f"{base_url}/contacts/search?q={to_plus}", headers=headers_cw)
                        contact_id = r.json()["payload"][0]["id"]
                    else:
                        contact_id = r.json()["payload"]["id"]

                    # Crear o buscar conversación
                    r = requests.get(f"{base_url}/contacts/{contact_id}/conversations", headers=headers_cw)
                    if r.json()["payload"]:
                        conversation_id = r.json()["payload"][0]["id"]
                    else:
                        r = requests.post(f"{base_url}/conversations", json={
                            "source_id": to_plus,
                            "inbox_id": 1
                        }, headers=headers_cw)
                        conversation_id = r.json()["id"]

                    # Enviar mensaje a Chatwoot
                    text_out = components[0]["parameters"][0]["text"]
                    msg_payload = {
                        "content": text_out,
                        "message_type": "outgoing",
                        "private": False
                    }
                    requests.post(f"{base_url}/conversations/{conversation_id}/messages", json=msg_payload, headers=headers_cw)

                except Exception as e:
                    st.warning(f"⚠️ WhatsApp enviado, pero error en Chatwoot: {e}")
            else:
                st.error(f"❌ Error con {to_number}: {r.text}")

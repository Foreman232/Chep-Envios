import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="Envío Masivo de WhatsApp", layout="centered")
st.title("📨 Envío Masivo de WhatsApp con Excel")

# Ingresar API Key
api_key = st.text_input("🔐 Ingresa tu API Key de 360dialog", type="password", value="icCVWtPvpn2Eb9c2C5wjfA4NAK")

# Cargar archivo Excel
st.subheader("📁 Sube tu archivo Excel con los contactos")
file = st.file_uploader("Drag and drop o haz clic para subir (.xlsx)", type=["xlsx"])

if file:
    df = pd.read_excel(file)
    df.columns = df.columns.str.strip()  # Limpiar espacios
    st.success(f"✅ Archivo cargado con {len(df)} registros.")

    # Verificar columnas disponibles
    columnas = df.columns.tolist()
    st.write("Columnas detectadas:", columnas)

    col_telefono = st.selectbox("📱 Columna del teléfono:", columnas)
    col_pais = st.selectbox("🌎 Columna del código de país:", columnas)
    col_plantilla = st.selectbox("🧩 Columna con el NOMBRE REAL de la plantilla:", columnas)
    col_param1 = st.selectbox("🔢 Parámetro {{1}}:", columnas)
    col_param2 = st.selectbox("🔢 Parámetro {{2}} (opcional):", ["(ninguno)"] + columnas)

    if st.button("🚀 Enviar mensajes"):
        for idx, row in df.iterrows():
            try:
                to_number = f"{row[col_pais]}{row[col_telefono]}"
                plantilla_name = row[col_plantilla]
                param1 = str(row[col_param1])
                param2 = str(row[col_param2]) if col_param2 != "(ninguno)" else None

                components = [{
                    "type": "body",
                    "parameters": [{"type": "text", "text": param1}]
                }]
                if param2:
                    components[0]["parameters"].append({"type": "text", "text": param2})

                payload = {
                    "messaging_product": "whatsapp",
                    "to": to_number,
                    "type": "template",
                    "template": {
                        "name": plantilla_name,
                        "language": {"code": "es_MX"},
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

                    # Reflejar como saliente en Chatwoot
                    try:
                        to_number_plus = f"+{to_number}"
                        chatwoot_token = "vP4SkyT1VZZVNsYTE6U6xjxP"
                        base_url = "https://srv870442.hstgr.cloud/api/v1/accounts/1"
                        headers_cw = {"api_access_token": chatwoot_token}

                        contact_payload = {
                            "identifier": to_number_plus,
                            "name": param1,
                            "phone_number": to_number_plus,
                            "inbox_id": 1
                        }
                        r = requests.post(f"{base_url}/contacts", json=contact_payload, headers=headers_cw)

                        if "has already been taken" in r.text or r.status_code == 422:
                            r = requests.get(f"{base_url}/contacts/search?q={to_number_plus}", headers=headers_cw)
                            contact_id = r.json()["payload"][0]["id"]
                        else:
                            contact_id = r.json()["payload"]["id"]

                        r_conv = requests.get(f"{base_url}/contacts/{contact_id}/conversations", headers=headers_cw)
                        if r_conv.json()["payload"]:
                            conversation_id = r_conv.json()["payload"][0]["id"]
                        else:
                            r_conv = requests.post(f"{base_url}/conversations", json={
                                "source_id": to_number_plus,
                                "inbox_id": 1
                            }, headers=headers_cw)
                            conversation_id = r_conv.json()["id"]

                        msg_text = payload["template"]["components"][0]["parameters"][0]["text"]
                        msg_payload = {
                            "content": msg_text,
                            "message_type": "outgoing",
                            "private": False
                        }
                        requests.post(f"{base_url}/conversations/{conversation_id}/messages", json=msg_payload, headers=headers_cw)

                    except Exception as e:
                        st.warning(f"⚠️ Enviado a WhatsApp, pero falló en Chatwoot (saliente): {e}")

                else:
                    st.error(f"❌ Error con {to_number}: {response.text}")

            except Exception as e:
                st.error(f"❌ Fallo en la fila {idx+1}: {e}")

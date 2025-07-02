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

    # Verificar las columnas
    st.write(df.columns)  # Esto imprimirá los nombres de todas las columnas

    # Limpiar espacios de las columnas (si existen)
    df.columns = df.columns.str.strip()

    # Mostrar columnas disponibles
    columns = df.columns.tolist()
    plantilla = st.selectbox("🧩 Columna con el nombre de la plantilla:", columns)
    telefono_col = st.selectbox("📱 Columna del teléfono:", columns)
    pais_col = st.selectbox("🌎 Columna del código de país:", columns)

    # Parámetros opcionales
    param1 = st.selectbox("🔢 Parámetro {{1}} (Nombre del cliente):", columns)
    param2 = st.selectbox("🔢 Parámetro {{2}} (opcional):", ["(ninguno)"] + columns)

    if st.button("🚀 Enviar mensajes"):
        if not api_key:
            st.error("⚠️ Debes ingresar una API Key.")
            st.stop()

        for idx, row in df.iterrows():
            to_number = f"{row[pais_col]}{row[telefono_col]}"
            template_name = row["nombre_plantilla"]
            language = "es_MX"

            components = [{
                "type": "body",
                "parameters": []
            }]

            # Reemplazar {{1}} con el nombre del cliente
            components[0]["parameters"].append({
                "type": "text",
                "text": str(row[plantilla])
            })

            # Agregar segundo parámetro si aplica
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

                # ✅ Reflejar mensaje también en Chatwoot como entrante
                try:
                    to_number_plus = f"+{to_number}"
                    chatwoot_token = "vP4SkyT1VZZVNsYTE6U6xjxP"
                    base_url = "https://srv870442.hstgr.cloud/api/v1/accounts/1"
                    headers_cw = {"api_access_token": chatwoot_token}

                    # 1. Buscar o crear contacto
                    contact_payload = {
                        "identifier": to_number_plus,
                        "name": str(row[param1]),
                        "phone_number": to_number_plus,
                        "inbox_id": 1
                    }
                    r = requests.post(f"{base_url}/contacts", json=contact_payload, headers=headers_cw)

                    if "has already been taken" in r.text or r.status_code == 422:
                        r = requests.get(f"{base_url}/contacts/search?q={to_number_plus}", headers=headers_cw)
                        contact_id = r.json()["payload"][0]["id"]
                    else:
                        contact_id = r.json()["payload"]["id"]

                    # 2. Obtener o crear conversación
                    r_conv = requests.get(f"{base_url}/contacts/{contact_id}/conversations", headers=headers_cw)
                    if r_conv.json()["payload"]:
                        conversation_id = r_conv.json()["payload"][0]["id"]
                    else:
                        r_conv = requests.post(f"{base_url}/conversations", json={
                            "source_id": to_number_plus,
                            "inbox_id": 1
                        }, headers=headers_cw)
                        conversation_id = r_conv.json()["id"]

                    # 3. Enviar mensaje a Chatwoot como "incoming"
                    msg_text = payload["template"]["components"][0]["parameters"][0]["text"]
                    msg_payload = {
                        "content": msg_text,
                        "message_type": "incoming",
                        "private": False
                    }
                    requests.post(f"{base_url}/conversations/{conversation_id}/messages", json=msg_payload, headers=headers_cw)

                except Exception as e:
                    st.warning(f"⚠️ El mensaje se envió a WhatsApp, pero falló en Chatwoot: {e}")

            else:
                st.error(f"❌ Error con {to_number}: {response.text}")

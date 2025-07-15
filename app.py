import streamlit as st
import pandas as pd
import requests
import time

st.set_page_config(page_title="Envío Masivo de WhatsApp", layout="centered")
st.title("📨 Envío Masivo de WhatsApp con Excel")

if "ya_ejecuto" not in st.session_state:
    st.session_state["ya_ejecuto"] = False

api_key = st.text_input("🔐 Ingresa tu API Key de 360dialog", type="password")
file = st.file_uploader("📁 Sube tu archivo Excel", type=["xlsx"])

plantillas = {
    "mensaje_entre_semana_24_hrs": lambda localidad: f"""Buen día, te saludamos de CHEP (Tarimas azules), es un gusto en saludarte.

Te escribo para confirmar que el día de mañana tenemos programada la recolección de tarimas en tu localidad: {localidad}.

¿Me podrías indicar cuántas tarimas tienes para entregar? Así podremos coordinar la unidad.""",

    "recordatorio_24_hrs": lambda: "Buen día, estamos siguiendo tu solicitud, ¿Me ayudarías a confirmar si puedo validar la cantidad de tarimas que serán entregadas?"
}

def normalizar_numero(phone):
    if phone.startswith("+521"):
        return "+52" + phone[4:]
    return phone

def crear_contacto_en_chatwoot(phone, name):
    unified_phone = phone.replace("+52", "+521")
    url = "https://srv904439.hstgr.cloud/api/v1/accounts/1/contacts"
    headers = {
        "Content-Type": "application/json",
        "api_access_token": "orUPYDWoDBkCShVrTSRUZsRx"
    }
    payload = {
        "inbox_id": 1,
        "name": name,
        "identifier": unified_phone,
        "phone_number": unified_phone
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code in [200, 201]:
        return True
    elif "has already been taken" in response.text:
        return True
    else:
        print("❌ Error creando contacto:", response.text)
        return False

if file:
    df = pd.read_excel(file)
    df.columns = df.columns.str.strip()
    st.success(f"Archivo cargado con {len(df)} filas.")
    columns = df.columns.tolist()

    plantilla = st.selectbox("🧩 Columna plantilla:", columns)
    telefono_col = st.selectbox("📱 Teléfono:", columns)
    pais_col = st.selectbox("🌎 Código país:", columns)
    param1 = st.selectbox("🔢 Parámetro {{1}}:", ["(ninguno)"] + columns)
    param2 = st.selectbox("🔢 Parámetro {{2}} (opcional):", ["(ninguno)"] + columns)

    if st.button("🚀 Enviar mensajes") and not st.session_state["ya_ejecuto"]:
        if not api_key:
            st.error("⚠️ Falta API Key.")
            st.stop()

        st.session_state["ya_ejecuto"] = True

        for idx, row in df.iterrows():
            raw_number = f"{str(row[pais_col])}{str(row[telefono_col])}".replace(' ', '').replace('-', '')
            chatwoot_number = f"+{raw_number}"
            whatsapp_number = normalizar_numero(chatwoot_number)

            if "enviado" in df.columns and row.get("enviado") == True:
                continue

            plantilla_nombre = str(row[plantilla]).strip()
            parameters = []
            param_text_1 = ""
            param_text_2 = ""

            if plantilla_nombre == "recordatorio_24_hrs":
                mensaje_real = plantillas["recordatorio_24_hrs"]()
                param_text_1 = "Cliente WhatsApp"
            else:
                if param1 != "(ninguno)":
                    param_text_1 = str(row[param1])
                    parameters.append({"type": "text", "text": param_text_1})
                if param2 != "(ninguno)":
                    param_text_2 = str(row[param2])
                    parameters.append({"type": "text", "text": param_text_2})
                mensaje_real = plantillas.get(plantilla_nombre, lambda x: f"Mensaje enviado con parámetro: {x}")(param_text_1)

            # 1. Crear contacto en Chatwoot
            if not crear_contacto_en_chatwoot(chatwoot_number, param_text_1 or "Cliente WhatsApp"):
                st.warning(f"⚠️ No se pudo crear contacto para {chatwoot_number}")
                continue

            # 2. Reflejar en Chatwoot antes de enviar a WhatsApp
            chatwoot_payload = {
                "phone": chatwoot_number,
                "name": param_text_1 or "Cliente WhatsApp",
                "content": mensaje_real
            }

            try:
                cw = requests.post("https://srv904439.hstgr.cloud/send-chatwoot-message", json=chatwoot_payload)
                if cw.status_code == 200:
                    st.info(f"📥 Reflejado en Chatwoot: {chatwoot_number}")
                else:
                    st.warning(f"⚠️ Error Chatwoot ({chatwoot_number}): {cw.text}")
            except Exception as e:
                st.error(f"❌ Error Chatwoot: {e}")

            # 3. Esperar un poco para asegurar conversación
            time.sleep(2)

            # 4. Enviar mensaje real por WhatsApp (360dialog)
            payload = {
                "messaging_product": "whatsapp",
                "to": whatsapp_number.replace("+", ""),
                "type": "template",
                "template": {
                    "name": plantilla_nombre,
                    "language": {"code": "es_MX"},
                    "components": []
                }
            }

            if parameters:
                payload["template"]["components"].append({
                    "type": "body",
                    "parameters": parameters
                })

            headers = {
                "Content-Type": "application/json",
                "D360-API-KEY": api_key
            }

            r = requests.post("https://waba-v2.360dialog.io/messages", headers=headers, json=payload)
            df.at[idx, "enviado"] = r.status_code == 200

            if r.status_code == 200:
                st.success(f"✅ WhatsApp enviado: {whatsapp_number}")
            else:
                st.error(f"❌ Error WhatsApp ({whatsapp_number}): {r.text}")

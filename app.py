import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="Envío Masivo de WhatsApp", layout="centered")
st.title("📨 Envío Masivo de WhatsApp con Excel")

api_key = st.text_input("🔐 Ingresa tu API Key de 360dialog", type="password")
file = st.file_uploader("📁 Sube tu archivo Excel", type=["xlsx"])

# Plantillas reales con sus textos renderizados (para reflejar en Chatwoot si hay parámetros)
plantillas = {
    "mensaje_entre_semana_24_hrs": lambda localidad: f"""Buen día, te saludamos de CHEP (Tarimas azules), es un gusto en saludarte.

Te escribo para confirmar que el día de mañana tenemos programada la recolección de tarimas en tu localidad: {localidad}.

¿Me podrías indicar cuántas tarimas tienes para entregar? Así podremos coordinar la unidad.""",
    
    "recordatorio_24_hrs": lambda: "Buen día, estamos siguiendo tu solicitud, ¿Me ayudarías a confirmar si puedo validar la cantidad de tarimas que serán entregadas?"
}

if file:
    df = pd.read_excel(file)
    st.success(f"Archivo cargado con {len(df)} filas.")
    df.columns = df.columns.str.strip()
    columns = df.columns.tolist()

    plantilla = st.selectbox("🧩 Columna plantilla:", columns)
    telefono_col = st.selectbox("📱 Teléfono:", columns)
    pais_col = st.selectbox("🌎 Código país:", columns)
    param1 = st.selectbox("🔢 Parámetro {{1}}:", ["(ninguno)"] + columns)
    param2 = st.selectbox("🔢 Parámetro {{2}} (opcional):", ["(ninguno)"] + columns)

    if st.button("🚀 Enviar mensajes"):
        if not api_key:
            st.error("⚠️ Falta API Key.")
            st.stop()

        for idx, row in df.iterrows():
            raw_number = f"{str(row[pais_col])}{str(row[telefono_col])}".replace(' ', '').replace('-', '')
            plantilla_nombre = str(row[plantilla]).strip()
            parameters = []

            # Manejo de mensaje según plantilla
            if plantilla_nombre == "recordatorio_24_hrs":
                mensaje_real = plantillas["recordatorio_24_hrs"]()
            else:
                if param1 != "(ninguno)":
                    param_text_1 = str(row[param1])
                    parameters.append({"type": "text", "text": param_text_1})
                else:
                    param_text_1 = ""

                if param2 != "(ninguno)":
                    parameters.append({"type": "text", "text": str(row[param2])})

                mensaje_real = plantillas.get(plantilla_nombre, lambda x: f"Mensaje enviado con parámetro: {x}")(param_text_1)

            # Construir payload de WhatsApp
            payload = {
                "messaging_product": "whatsapp",
                "to": raw_number,
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

            # Enviar mensaje a WhatsApp
            r = requests.post("https://waba-v2.360dialog.io/messages", headers=headers, json=payload)

            if r.status_code == 200:
                st.success(f"✅ WhatsApp OK: {raw_number}")

                # Solo reflejar en Chatwoot si hubo parámetros (para evitar duplicados)
                if parameters:
                    chatwoot_payload = {
                        "phone": raw_number,
                        "name": str(row[param1]) if param1 != "(ninguno)" else "Cliente WhatsApp",
                        "content": mensaje_real
                    }

                    try:
                        cw = requests.post("https://webhook-chatwoot.onrender.com/send-chatwoot-message", json=chatwoot_payload)
                        if cw.status_code == 200:
                            st.info(f"📥 Reflejado en Chatwoot: {raw_number}")
                        else:
                            st.warning(f"⚠️ Error al reflejar en Chatwoot ({raw_number}): {cw.text}")
                    except Exception as e:
                        st.error(f"❌ Error en la petición a Chatwoot: {e}")
            else:
                st.error(f"❌ WhatsApp error ({raw_number}): {r.text}")

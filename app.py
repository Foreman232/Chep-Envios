import streamlit as st
import pandas as pd
import requests
from io import BytesIO

st.set_page_config(page_title="WhatsApp Masivo", layout="centered")
st.title("📨 Envío Masivo de WhatsApp con Control Antiduplicado")

if "enviados" not in st.session_state:
    st.session_state["enviados"] = set()

api_key = st.text_input("🔐 API Key 360dialog", type="password")
file = st.file_uploader("📁 Sube tu archivo Excel", type=["xlsx"])

plantillas = {
    "mensaje_entre_semana_24_hrs": lambda localidad: f"""Buen día, te saludamos de CHEP (Tarimas azules), es un gusto en saludarte.

Te escribo para confirmar que el día de mañana tenemos programada la recolección de tarimas en tu localidad: {localidad}.

¿Me podrías indicar cuántas tarimas tienes para entregar? Así podremos coordinar la unidad.""",
    
    "recordatorio_24_hrs": lambda: "Buen día, estamos siguiendo tu solicitud, ¿Me ayudarías a confirmar si puedo validar la cantidad de tarimas que serán entregadas?"
}

if file:
    df = pd.read_excel(file)
    df.columns = df.columns.str.strip()
    st.success(f"Archivo cargado con {len(df)} filas.")

    plantilla = st.selectbox("🧩 Plantilla:", df.columns)
    telefono_col = st.selectbox("📱 Teléfono:", df.columns)
    pais_col = st.selectbox("🌎 Código país:", df.columns)
    param1 = st.selectbox("🔢 Parámetro {{1}}:", ["(ninguno)"] + df.columns.tolist())
    param2 = st.selectbox("🔢 Parámetro {{2}} (opcional):", ["(ninguno)"] + df.columns.tolist())

    if st.button("🚀 Enviar mensajes"):
        enviados_actual = []

        for idx, row in df.iterrows():
            raw_number = f"{str(row[pais_col])}{str(row[telefono_col])}".replace(" ", "").replace("-", "")

            # Verificación de duplicado por sesión
            if raw_number in st.session_state["enviados"]:
                continue

            # Verificación por columna Excel
            if str(row.get("enviado")).strip().lower() in ["true", "1", "yes"]:
                continue

            plantilla_nombre = str(row[plantilla]).strip()
            parameters = []

            if plantilla_nombre == "recordatorio_24_hrs":
                mensaje_real = plantillas["recordatorio_24_hrs"]()
            else:
                param_text_1 = str(row[param1]) if param1 != "(ninguno)" else ""
                parameters.append({"type": "text", "text": param_text_1})

                if param2 != "(ninguno)":
                    parameters.append({"type": "text", "text": str(row[param2])})

                mensaje_real = plantillas.get(plantilla_nombre, lambda x: f"Mensaje enviado con parámetro: {x}")(param_text_1)

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
                payload["template"]["components"].append({"type": "body", "parameters": parameters})

            headers = {
                "Content-Type": "application/json",
                "D360-API-KEY": api_key
            }

            r = requests.post("https://waba-v2.360dialog.io/messages", headers=headers, json=payload)

            if r.status_code == 200:
                st.success(f"✅ Enviado: {raw_number}")
                st.session_state["enviados"].add(raw_number)
                df.at[idx, "enviado"] = True
                enviados_actual.append(raw_number)

                # Reflejo Chatwoot
                requests.post("https://webhook-chatwoot.onrender.com/send-chatwoot-message", json={
                    "phone": raw_number,
                    "name": param_text_1 if param1 != "(ninguno)" else "Cliente WhatsApp",
                    "content": mensaje_real
                })
            else:
                st.error(f"❌ Error ({raw_number}): {r.text}")

        # Descarga de Excel actualizado
        output = BytesIO()
        df.to_excel(output, index=False)
        st.download_button("⬇️ Descargar archivo con marcados", data=output.getvalue(), file_name="enviados.xlsx")


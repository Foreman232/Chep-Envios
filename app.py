import streamlit as st
import pandas as pd
import requests
import datetime
import os
from io import BytesIO

st.set_page_config(page_title="📨 Envío Masivo WhatsApp", layout="centered")
st.title("📨 Envío Masivo de WhatsApp con Plantillas")

if "ya_ejecuto" not in st.session_state:
    st.session_state["ya_ejecuto"] = False

# API KEY fija
api_key = "I7yNB2t4EpJlPqxHF82mWXYTAK"

file = st.file_uploader("📁 Sube tu archivo Excel", type=["xlsx"])

plantillas = {
    "mensaje_entre_semana_24_hrs": lambda localidad: f"""Buen día, te saludamos de CHEP (Tarimas azules), es un gusto en saludarte.

Te escribo para confirmar que el día de mañana tenemos programada la recolección de tarimas en tu localidad: {localidad}.

¿Me podrías indicar cuántas tarimas tienes para entregar? Así podremos coordinar la unidad.""",

    "recordatorio_24_hrs": lambda: "Buen día, estamos siguiendo tu solicitud, ¿Me ayudarías a confirmar si puedo validar la cantidad de tarimas que serán entregadas?"
}

def normalizar_numero(phone):
    if phone.startswith("+52") and not phone.startswith("+521"):
        return "+521" + phone[3:]
    return phone

archivo_envios = "envios_hoy.xlsx"
if not os.path.exists(archivo_envios):
    pd.DataFrame(columns=["Fecha", "Número", "Nombre", "Estado"]).to_excel(archivo_envios, index=False)

if file:
    df = pd.read_excel(file)
    df.columns = df.columns.str.strip()
    st.success(f"Archivo cargado con {len(df)} registros.")
    columnas = df.columns.tolist()

    plantilla_col = st.selectbox("🧩 Columna plantilla:", columnas)
    telefono_col = st.selectbox("📱 Teléfono:", columnas)
    nombre_col = st.selectbox("📇 Nombre:", columnas)
    pais_col = st.selectbox("🌎 Código país:", columnas)
    param1_col = st.selectbox("🔢 Parámetro {{1}}:", ["(ninguno)"] + columnas)
    param2_col = st.selectbox("🔢 Parámetro {{2}} (opcional):", ["(ninguno)"] + columnas)

    if st.button("🚀 Enviar mensajes") and not st.session_state["ya_ejecuto"]:
        st.session_state["ya_ejecuto"] = True

        for idx, row in df.iterrows():
            if "enviado" in df.columns and row.get("enviado") == True:
                continue

            raw_number = f"{str(row[pais_col])}{str(row[telefono_col])}".replace(" ", "").replace("-", "")
            chatwoot_number = normalizar_numero(f"+{raw_number}")
            whatsapp_number = chatwoot_number
            nombre = str(row[nombre_col]).strip()
            plantilla_nombre = str(row[plantilla_col]).strip()

            parameters = []
            param1 = ""
            param2 = ""

            if plantilla_nombre == "recordatorio_24_hrs":
                mensaje_real = plantillas["recordatorio_24_hrs"]()
                param1 = nombre or "Cliente WhatsApp"
            else:
                if param1_col != "(ninguno)":
                    param1 = str(row[param1_col])
                    parameters.append({"type": "text", "text": param1})
                if param2_col != "(ninguno)":
                    param2 = str(row[param2_col])
                    parameters.append({"type": "text", "text": param2})
                mensaje_real = plantillas.get(plantilla_nombre, lambda x: f"Mensaje enviado con parámetro: {x}")(param1)

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

            hoy = datetime.date.today().strftime('%Y-%m-%d')
            estado = "✅ Enviado" if r.status_code == 200 else f"❌ Falló ({r.status_code})"

            nuevo_registro = pd.DataFrame([{
                "Fecha": hoy,
                "Número": whatsapp_number,
                "Nombre": nombre,
                "Estado": estado
            }])

            try:
                df_existente = pd.read_excel(archivo_envios)
                df_actualizado = pd.concat([df_existente, nuevo_registro], ignore_index=True)
                df_actualizado.to_excel(archivo_envios, index=False)
                st.info(f"📊 Registrado en {archivo_envios}")
            except Exception as e:
                st.warning(f"⚠️ No se pudo registrar el envío: {e}")

            if r.status_code == 200:
                st.success(f"✅ WhatsApp enviado: {whatsapp_number}")

                chatwoot_payload = {
                    "phone": chatwoot_number,
                    "name": nombre or "Cliente WhatsApp",
                    "content": mensaje_real
                }

                try:
                    cw = requests.post("https://webhook-chatwoots.onrender.com/send-chatwoot-message", json=chatwoot_payload)
                    if cw.status_code == 200:
                        st.info(f"📥 Reflejado en Chatwoot: {chatwoot_number}")
                    else:
                        st.warning(f"⚠️ Chatwoot error ({chatwoot_number}): {cw.text}")
                except Exception as e:
                    st.error(f"❌ Error al reflejar en Chatwoot: {e}")
            else:
                st.error(f"❌ WhatsApp error ({whatsapp_number}): {r.text}")

# 📥 Botón para descargar el Excel generado
if os.path.exists(archivo_envios):
    try:
        df_final = pd.read_excel(archivo_envios)
        output = BytesIO()
        df_final.to_excel(output, index=False)
        st.download_button(
            label="📥 Descargar Excel de envíos",
            data=output.getvalue(),
            file_name="envios_hoy.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        st.warning(f"⚠️ No se pudo preparar archivo para descargar: {e}")



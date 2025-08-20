import streamlit as st
import pandas as pd
import requests
import datetime
import os
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

st.set_page_config(page_title="📨 Envío Masivo WhatsApp", layout="centered")
st.title("📨 Envío Masivo de WhatsApp con Plantillas")

if "ya_ejecuto" not in st.session_state:
    st.session_state["ya_ejecuto"] = False

# Ingreso seguro de API KEY
api_key = st.text_input("🔐 Ingresa tu API Key de 360dialog", type="password")

# Plantillas disponibles
plantillas = {
    "mensaje_entre_semana_24_hrs": lambda localidad: f"""Buen día, te saludamos de CHEP (Tarimas azules), es un gusto en saludarte.

Te escribo para confirmar que el día de mañana tenemos programada la recolección de tarimas en tu localidad: {localidad}.

¿Me podrías indicar cuántas tarimas tienes para entregar? Así podremos coordinar la unidad.""",

    "recordatorio_24_hrs": lambda: "Buen día, estamos siguiendo tu solicitud, ¿Me ayudarías a confirmar si puedo validar la cantidad de tarimas que serán entregadas?"
}

# Normalizador de número para Chatwoot
def normalizar_numero(phone):
    if phone.startswith("+52") and not phone.startswith("+521"):
        return "+521" + phone[3:]
    return phone

# Archivo donde se guardan los resultados
archivo_envios = "envios_hoy.xlsx"
if not os.path.exists(archivo_envios):
    pd.DataFrame(columns=["Fecha", "Número", "Nombre", "Estado"]).to_excel(archivo_envios, index=False)

# --- Función de envío de un mensaje ---
def enviar_mensaje(row, api_key, plantilla_col, telefono_col, nombre_col, pais_col, param1_col, param2_col):
    try:
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

        # Payload para WhatsApp
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

        r = requests.post("https://waba-v2.360dialog.io/messages", headers=headers, json=payload, timeout=15)
        enviado = r.status_code == 200
        estado = "✅ Enviado" if enviado else f"❌ Falló ({r.status_code})"

        # Guardar en Excel
        hoy = datetime.date.today().strftime('%Y-%m-%d')
        nuevo_registro = pd.DataFrame([{
            "Fecha": hoy,
            "Número": f"'{whatsapp_number}",
            "Nombre": nombre,
            "Estado": estado
        }])
        df_existente = pd.read_excel(archivo_envios)
        df_actualizado = pd.concat([df_existente, nuevo_registro], ignore_index=True)
        df_actualizado.to_excel(archivo_envios, index=False)

        # Reflejar en Chatwoot (con 3 reintentos)
        chatwoot_payload = {
            "phone": chatwoot_number,
            "name": nombre or "Cliente WhatsApp",
            "content": mensaje_real
        }
        for intento in range(3):
            try:
                cw = requests.post("https://webhook-chatwoots.onrender.com/send-chatwoot-message", json=chatwoot_payload, timeout=15)
                if cw.status_code == 200:
                    break
                else:
                    time.sleep(1)  # esperar un poco y reintentar
            except Exception:
                time.sleep(1)

        return whatsapp_number, estado

    except Exception as e:
        return row.get(nombre_col, "Desconocido"), f"❌ Error general: {e}"

# --- Subida de archivo Excel ---
file = st.file_uploader("📁 Sube tu archivo Excel", type=["xlsx"])

if api_key and file:
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
        resultados = []

        with ThreadPoolExecutor(max_workers=10) as executor:  # hasta 10 en paralelo
            futures = [
                executor.submit(
                    enviar_mensaje,
                    row, api_key,
                    plantilla_col, telefono_col, nombre_col, pais_col,
                    param1_col, param2_col
                )
                for _, row in df.iterrows()
            ]

            for future in as_completed(futures):
                numero, estado = future.result()
                resultados.append((numero, estado))
                if "✅" in estado:
                    st.success(f"✅ WhatsApp enviado: {numero}")
                else:
                    st.error(f"{estado} -> {numero}")

# 📥 Botón para descargar el Excel de resultados
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




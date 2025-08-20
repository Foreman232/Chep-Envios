import streamlit as st
import pandas as pd
import requests
import datetime
import os
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import hashlib

st.set_page_config(page_title="📨 Envío Masivo WhatsApp", layout="centered")
st.title("📨 Envío Masivo de WhatsApp con Plantillas")

if "ya_ejecuto" not in st.session_state:
    st.session_state["ya_ejecuto"] = False

# ========= CONFIG =========
# Si tienes NGINX/subdominio, cámbialo por https://webhook.chep-tarimas.store/send-chatwoot-message
REFLECT_URL = "https://srv904439.hstgr.cloud:10000/send-chatwoot-message"
WHATSAPP_API_URL = "https://waba-v2.360dialog.io/messages"

api_key = st.text_input("🔐 Ingresa tu API Key de 360dialog", type="password")

plantillas = {
    "mensaje_entre_semana_24_hrs": lambda localidad: f"""Buen día, te saludamos de CHEP (Tarimas azules), es un gusto en saludarte.

Te escribo para confirmar que el día de mañana tenemos programada la recolección de tarimas en tu localidad: {localidad}.

¿Me podrías indicar cuántas tarimas tienes para entregar? Así podremos coordinar la unidad.""",
    "recordatorio_24_hrs": lambda: "Buen día, estamos siguiendo tu solicitud, ¿Me ayudarías a confirmar si puedo validar la cantidad de tarimas que serán entregadas?"
}

def normalizar_numero(phone: str) -> str:
    if phone.startswith("+52") and not phone.startswith("+521"):
        return "+521" + phone[3:]
    return phone

def gen_client_message_id(phone: str, content: str) -> str:
    base = f"{phone}|{content}|{datetime.datetime.utcnow().isoformat(timespec='seconds')}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()

def post_whatsapp(api_key: str, payload: dict) -> requests.Response:
    headers = {"Content-Type": "application/json", "D360-API-KEY": api_key}
    return requests.post(WHATSAPP_API_URL, headers=headers, json=payload, timeout=20)

def reflect_in_chatwoot(phone: str, name: str, content: str, client_message_id: str, max_retries: int = 3):
    body = {"phone": phone, "name": name or "Cliente WhatsApp", "content": content, "client_message_id": client_message_id}
    wait = 0.5; last_err = None
    for _ in range(max_retries):
        try:
            r = requests.post(REFLECT_URL, json=body, timeout=20)
            if r.ok:
                data = {}
                try: data = r.json()
                except Exception: pass
                if data.get("ok") and data.get("messageId"):
                    return True, data.get("messageId")
            last_err = r.text
        except Exception as e:
            last_err = str(e)
        time.sleep(wait); wait *= 1.6
    return False, last_err

archivo_envios = "envios_hoy.xlsx"
if not os.path.exists(archivo_envios):
    pd.DataFrame(columns=["Fecha", "Número", "Nombre", "Estado", "CW_MessageID"]).to_excel(archivo_envios, index=False)

def registrar_envio_excel(numero, nombre, estado, cw_msg_id=None):
    hoy = datetime.date.today().strftime('%Y-%m-%d')
    nuevo = pd.DataFrame([{"Fecha": hoy, "Número": f"'{numero}", "Nombre": nombre, "Estado": estado, "CW_MessageID": cw_msg_id or ""}])
    df = pd.read_excel(archivo_envios)
    pd.concat([df, nuevo], ignore_index=True).to_excel(archivo_envios, index=False)

def enviar_mensaje(row, api_key, plantilla_col, telefono_col, nombre_col, pais_col, param1_col, param2_col, pausa_entre_envios=0.25):
    try:
        raw_number = f"{str(row[pais_col])}{str(row[telefono_col])}".replace(" ", "").replace("-", "")
        chatwoot_number = normalizar_numero(f"+{raw_number}")
        whatsapp_number = chatwoot_number
        nombre = str(row[nombre_col]).strip() if pd.notna(row[nombre_col]) else ""
        plantilla_nombre = str(row[plantilla_col]).strip()

        if plantilla_nombre == "recordatorio_24_hrs":
            mensaje_real = plantillas["recordatorio_24_hrs"]()
            parameters = []
        else:
            p1 = str(row[param1_col]) if (param1_col != "(ninguno)" and pd.notna(row[param1_col])) else ""
            p2 = str(row[param2_col]) if (param2_col != "(ninguno)" and pd.notna(row[param2_col])) else ""
            mensaje_real = plantillas.get(plantilla_nombre, lambda x: f"Mensaje con parámetro: {x}")(p1)
            parameters = []
            if p1: parameters.append({"type": "text", "text": p1})
            if p2: parameters.append({"type": "text", "text": p2})

        payload = {
            "messaging_product": "whatsapp",
            "to": whatsapp_number.replace("+", ""),
            "type": "template",
            "template": { "name": plantilla_nombre, "language": {"code": "es_MX"}, "components": [] }
        }
        if parameters:
            payload["template"]["components"].append({ "type": "body", "parameters": parameters })

        r = post_whatsapp(api_key, payload)
        enviado = r.status_code == 200
        estado = "✅ WhatsApp enviado" if enviado else f"❌ WhatsApp falló ({r.status_code})"

        cw_msg_id = ""
        client_message_id = gen_client_message_id(whatsapp_number, mensaje_real)
        ok_reflect, info = reflect_in_chatwoot(chatwoot_number, nombre or "Cliente WhatsApp", mensaje_real, client_message_id)
        if ok_reflect:
            cw_msg_id = info
            estado += " | 🟦 Reflejado"
        else:
            estado += " | ⚠️ No reflejado: " + (str(info)[:140] + "..." if info else "sin detalle")

        registrar_envio_excel(whatsapp_number, nombre, estado, cw_msg_id)
        time.sleep(pausa_entre_envios)
        return whatsapp_number, estado

    except Exception as e:
        nombre = (str(row[nombre_col]).strip() if nombre_col in row else "Desconocido")
        estado = f"❌ Error general: {e}"
        registrar_envio_excel("N/D", nombre, estado)
        return nombre, estado

file = st.file_uploader("📁 Sube tu archivo Excel", type=["xlsx"])

if api_key and file:
    df = pd.read_excel(file)
    df.columns = df.columns.str.strip()
    st.success(f"Archivo cargado con {len(df)} registros.")
    columnas = df.columns.tolist()

    plantilla_col = st.selectbox("🧩 Columna plantilla:", columnas)
    telefono_col  = st.selectbox("📱 Teléfono:", columnas)
    nombre_col    = st.selectbox("📇 Nombre:", columnas)
    pais_col      = st.selectbox("🌎 Código país (sin '+'):", columnas)
    param1_col    = st.selectbox("🔢 Parámetro {{1}}:", ["(ninguno)"] + columnas)
    param2_col    = st.selectbox("🔢 Parámetro {{2}} (opcional):", ["(ninguno)"] + columnas)

    modo_seguro = st.toggle("🛡️ Modo seguro (serializar envíos)", value=True)
    max_workers = 1 if modo_seguro else st.slider("⚙️ Paralelismo (máx. 3 recomendado)", 1, 10, 3)
    pausa_entre_envios = st.slider("⏱️ Pausa entre envíos (seg)", 0.0, 1.0, 0.25, 0.05)

    if st.button("🚀 Enviar mensajes") and not st.session_state["ya_ejecuto"]:
        st.session_state["ya_ejecuto"] = True
        resultados = []

        if max_workers == 1:
            for _, row in df.iterrows():
                numero, estado = enviar_mensaje(row, api_key, plantilla_col, telefono_col, nombre_col, pais_col, param1_col, param2_col, pausa_entre_envios)
                resultados.append((numero, estado))
                (st.success if "✅" in estado else st.error)(f"{estado} -> {numero}")
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    executor.submit(enviar_mensaje, row, api_key, plantilla_col, telefono_col, nombre_col, pais_col, param1_col, param2_col, pausa_entre_envios)
                    for _, row in df.iterrows()
                ]
                for f in as_completed(futures):
                    numero, estado = f.result()
                    resultados.append((numero, estado))
                    (st.success if "✅" in estado else st.error)(f"{estado} -> {numero}")

if os.path.exists(archivo_envios):
    try:
        df_final = pd.read_excel(archivo_envios)
        output = BytesIO(); df_final.to_excel(output, index=False)
        st.download_button("📥 Descargar Excel de envíos", output.getvalue(), "envios_hoy.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception as e:
        st.warning(f"⚠️ No se pudo preparar archivo para descargar: {e}")

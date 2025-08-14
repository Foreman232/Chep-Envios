import streamlit as st
import pandas as pd
import requests
import datetime
import os
import time
from io import BytesIO
import decimal

st.set_page_config(page_title="📨 Envío Masivo WhatsApp", layout="centered")
st.title("📨 Envío Masivo de WhatsApp con Plantillas")

if "ya_ejecuto" not in st.session_state:
    st.session_state["ya_ejecuto"] = False

api_key = st.text_input("🔐 Ingresa tu API Key de 360dialog", type="password")

# ---- Plantillas (texto humano solo para reflejo/log) ----
plantillas = {
    "mensaje_entre_semana_24_hrs": lambda localidad: (
        "Buen día, te saludamos de CHEP (Tarimas azules), es un gusto en saludarte.\n\n"
        f"Te escribo para confirmar que el día de mañana tenemos programada la recolección de tarimas "
        f"en tu localidad: {localidad}.\n\n"
        "¿Me podrías indicar cuántas tarimas tienes para entregar? Así podremos coordinar la unidad."
    ),
    "recordatorio_24_hrs": lambda: (
        "Buen día, estamos siguiendo tu solicitud, ¿Me ayudarías a confirmar si puedo validar la cantidad de tarimas que serán entregadas?"
    )
}

# ---- Reglas de cuántos parámetros acepta cada plantilla ----
TEMPLATE_PARAM_COUNTS = {
    "mensaje_entre_semana_24_hrs": 1,
    "recordatorio_24_hrs": 0,
}

LANG_CODE = "es_MX"

# ================== Helpers ==================
def _clean_num_component(x):
    """Convierte 5.55e+09 / 5548917590.0 a '5548917590' (solo dígitos)."""
    if x is None:
        return ""
    s = str(x).strip()
    try:
        if "e" in s.lower():
            s = format(decimal.Decimal(s), "f")
    except Exception:
        pass
    if s.endswith(".0"):
        s = s[:-2]
    return "".join(ch for ch in s if ch.isdigit())

def normalizar_numero_e164(codigo_pais, telefono):
    pais = _clean_num_component(codigo_pais)
    fono = _clean_num_component(telefono)
    if not pais or not fono:
        return ""
    e164 = f"+{pais}{fono}"
    # MX -> +521
    if e164.startswith("+52") and not e164.startswith("+521"):
        e164 = "+521" + e164[3:]
    return e164

# ================== Archivos ==================
archivo_envios = "envios_hoy.xlsx"
archivo_errores = "errores_envio_chatwoot.txt"
if not os.path.exists(archivo_envios):
    pd.DataFrame(columns=["Fecha", "Número", "Nombre", "Estado"]).to_excel(archivo_envios, index=False)

file = st.file_uploader("📁 Sube tu archivo Excel", type=["xlsx"])

if api_key and file:
    df = pd.read_excel(file)
    df.columns = df.columns.str.strip()
    st.success(f"Archivo cargado con {len(df)} registros.")
    columnas = df.columns.tolist()

    plantilla_col = st.selectbox("🧩 Columna plantilla:", columnas)
    telefono_col = st.selectbox("📱 Teléfono:", columnas)
    nombre_col = st.selectbox("📗 Nombre:", columnas)
    pais_col = st.selectbox("🌎 Código país:", columnas)
    param1_col = st.selectbox("🔢 Parámetro {{1}}:", ["(ninguno)"] + columnas)
    param2_col = st.selectbox("🔢 Parámetro {{2}} (opcional):", ["(ninguno)"] + columnas)

    if st.button("🚀 Enviar mensajes") and not st.session_state["ya_ejecuto"]:
        st.session_state["ya_ejecuto"] = True

        if "enviado" not in df.columns:
            df["enviado"] = False

        for idx, row in df.iterrows():
            if row.get("enviado") is True:
                continue

            # --------- Número limpio y normalizado ---------
            chatwoot_number = normalizar_numero_e164(row[pais_col], row[telefono_col])
            if not chatwoot_number:
                st.error(f"❌ Número inválido en fila {idx+1}")
                continue
            whatsapp_number = chatwoot_number  # e164 con '+'
            to_number = whatsapp_number.replace("+", "")

            nombre = (str(row[nombre_col]).strip()
                      if pd.notna(row[nombre_col]) else "Cliente WhatsApp")
            plantilla_nombre = (str(row[plantilla_col]).strip()
                                if pd.notna(row[plantilla_col]) else "")

            # --------- Valida plantilla / parámetros ---------
            expected = TEMPLATE_PARAM_COUNTS.get(plantilla_nombre, None)
            if expected is None:
                st.error(f"❌ Plantilla desconocida '{plantilla_nombre}' en fila {idx+1}")
                continue

            parameters = []
            p1 = "" if param1_col == "(ninguno)" or pd.isna(row.get(param1_col)) else str(row[param1_col]).strip()
            p2 = "" if param2_col == "(ninguno)" or pd.isna(row.get(param2_col)) else str(row[param2_col]).strip()

            if expected >= 1 and p1:
                parameters.append({"type": "text", "text": p1})
            if expected >= 2 and p2:
                parameters.append({"type": "text", "text": p2})

            if expected > 0 and len(parameters) != expected:
                st.error(f"❌ La plantilla '{plantilla_nombre}' espera {expected} parámetro(s) y llegó {len(parameters)} (fila {idx+1}).")
                continue

            # --------- Mensaje "humano" solo para reflejo/log ---------
            if plantilla_nombre == "recordatorio_24_hrs":
                mensaje_real = plantillas["recordatorio_24_hrs"]()
            elif plantilla_nombre == "mensaje_entre_semana_24_hrs":
                # usa p1 como {{1}} (tú decides qué columna mapeas en la UI)
                mensaje_real = plantillas["mensaje_entre_semana_24_hrs"](p1 or "")
            else:
                # genérico
                mensaje_real = f"Plantilla {plantilla_nombre} enviada."

            # --------- Payload 360dialog ---------
            payload = {
                "messaging_product": "whatsapp",
                "to": to_number,                       # sin '+'
                "type": "template",
                "template": {
                    "name": plantilla_nombre,
                    "language": {"code": "es_MX"}
                }
            }
            if expected > 0:
                payload["template"]["components"] = [{"type": "body", "parameters": parameters}]
            # si expected == 0, NO se agrega components (esto evita el 400)

            headers = {
                "Content-Type": "application/json",
                "D360-API-KEY": api_key
            }

            # --------- Envío con 1 reintento simple ---------
            r = requests.post("https://waba-v2.360dialog.io/messages", headers=headers, json=payload)
            if r.status_code == 429:
                # respeta Retry-After si viene
                ra = r.headers.get("Retry-After")
                wait_s = int(ra) if ra and ra.isdigit() else 3
                time.sleep(wait_s)
                r = requests.post("https://waba-v2.360dialog.io/messages", headers=headers, json=payload)

            enviado = 200 <= r.status_code < 300
            df.at[idx, "enviado"] = enviado
            estado = "✅ Enviado" if enviado else f"❌ Falló ({r.status_code})"

            if enviado:
                st.success(f"✅ WhatsApp enviado: {whatsapp_number}")
            else:
                st.error(f"❌ WhatsApp error ({whatsapp_number}): {r.text}")
                # registra y sigue con la siguiente
                try:
                    hoy = datetime.date.today().strftime('%Y-%m-%d')
                    df_existente = pd.read_excel(archivo_envios)
                    nuevo_registro = pd.DataFrame([{
                        "Fecha": hoy, "Número": f"'{whatsapp_number}",
                        "Nombre": nombre, "Estado": estado + " | " + r.text[:500]
                    }])
                    pd.concat([df_existente, nuevo_registro], ignore_index=True).to_excel(archivo_envios, index=False)
                except Exception:
                    pass
                continue

            # --------- Registrar envío en Excel ---------
            try:
                hoy = datetime.date.today().strftime('%Y-%m-%d')
                df_existente = pd.read_excel(archivo_envios)
                nuevo_registro = pd.DataFrame([{
                    "Fecha": hoy,
                    "Número": f"'{whatsapp_number}",
                    "Nombre": nombre,
                    "Estado": estado
                }])
                pd.concat([df_existente, nuevo_registro], ignore_index=True).to_excel(archivo_envios, index=False)
                st.info(f"📊 Registrado en {archivo_envios}")
            except Exception as e:
                st.warning(f"⚠️ No se pudo registrar el envío: {e}")

            # --------- Reflejar en Chatwoot (opcional) ---------
            time.sleep(0.3)
            msg_reflejo = (mensaje_real or "").strip()
            if "[streamlit]" not in msg_reflejo:
                msg_reflejo += " [streamlit]"

            chatwoot_payload = {
                "phone": whatsapp_number,
                "name": nombre or "Cliente WhatsApp",
                "content": msg_reflejo
            }

            chatwoot_reflejado = False
            for intento in range(2):
                try:
                    # Usa tu server actual; si prefieres el viejo, cambia la URL
                    cw = requests.post("https://srv904439.hstgr.cloud:10000/send-chatwoot-message", json=chatwoot_payload, timeout=15)
                    if cw.status_code == 200:
                        st.info(f"📥 Reflejado en Chatwoot: {whatsapp_number}")
                        chatwoot_reflejado = True
                        break
                    else:
                        st.warning(f"⚠️ Chatwoot error ({whatsapp_number}): {cw.text}")
                except Exception:
                    time.sleep(0.5)

            if not chatwoot_reflejado:
                try:
                    with open(archivo_errores, "a") as f:
                        f.write(f"{datetime.datetime.now()} - Error al reflejar {whatsapp_number}: {msg_reflejo}\n")
                except Exception:
                    pass

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

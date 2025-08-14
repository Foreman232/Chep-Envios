import streamlit as st
import pandas as pd
import requests
import os
import time
import datetime
import math
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter, Retry
import hashlib
import json
import threading

# ===================== UI / CONFIG =====================
st.set_page_config(page_title="📨 Envío Masivo de WhatsApp — Plantillas ⚡", layout="wide")
st.title("📨 Envío Masivo de WhatsApp — Plantillas ⚡ Rápido y Estable")

colA, colB, colC = st.columns(3)
with colA:
    api_key = st.text_input("🔐 360dialog API Key", type="password")
with colB:
    max_workers = st.slider("🧵 Concurrencia (hilos)", min_value=2, max_value=32, value=16, step=2)
with colC:
    pause_on_429 = st.toggle("⏸️ Respetar Retry-After (429)", value=True)

ARCHIVO_ENV = "envios_hoy.xlsx"
ARCHIVO_FAIL = "fallidos.xlsx"
ARCHIVO_CHECK = "checkpoint_envios.json"

# ===================== Reglas por plantilla (AQUÍ defines cuántos params acepta cada una) =====================
TEMPLATE_PARAM_COUNTS = {
    "mensaje_entre_semana_24_hrs": 1,   # {{1}} = localidad
    "recordatorio_24_hrs": 0,           # no acepta parámetros
    # agrega aquí más plantillas: "nombre": número_de_parámetros
}

LANG_CODE = "es_MX"  # ajusta si tu plantilla está aprobada en otro idioma

# ===================== Helpers =====================
def normalizar_numero(phone: str) -> str:
    if not phone:
        return phone
    p = str(phone).strip().replace(" ", "").replace("-", "")
    if not p.startswith("+"):
        p = "+" + p
    if p.startswith("+52") and not p.startswith("+521"):
        p = "+521" + p[3:]
    return p

def idempotency_key(row_dict: dict) -> str:
    base = json.dumps(row_dict, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]

def build_session_360(api_key: str):
    s = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=0.8,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST"]
    )
    adapter = HTTPAdapter(pool_connections=200, pool_maxsize=200, max_retries=retries)
    s.mount("https://", adapter)
    s.headers.update({"Content-Type": "application/json", "D360-API-KEY": api_key})
    return s

def render_template_preview(name: str, p1: str = "", p2: str = "") -> str:
    name = (name or "").strip()

    if name == "mensaje_entre_semana_24_hrs":
        # p1 = localidad
        return (
            "Buen día, te saludamos de CHEP (Tarimas azules), es un gusto en saludarte.\n\n"
            f"Te escribo para confirmar que el día de mañana tenemos programada la recolección de tarimas "
            f"en tu localidad: {p1}.\n\n"
            "¿Me podrías indicar cuántas tarimas tienes para entregar? Así podremos coordinar la unidad."
        )

    if name == "recordatorio_24_hrs":
        return (
            "Buen día, estamos siguiendo tu solicitud, "
            "¿Me ayudarías a confirmar si puedo validar la cantidad de tarimas que serán entregadas?"
        )

    # Genérico si aparece otra plantilla
    cuerpo = "Plantilla enviada."
    if p1 and p2:
        cuerpo += f" Parámetros: {p1} | {p2}"
    elif p1:
        cuerpo += f" Parámetro: {p1}"
    return cuerpo

def send_360_template(session_360: requests.Session, to_number: str, template_name: str, params, pause_on_429=True):
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number.replace("+", ""),
        "type": "template",
        "template": {"name": template_name, "language": {"code": LANG_CODE}, "components": []}
    }
    if params:  # solo si hay params válidos
        payload["template"]["components"].append({"type": "body", "parameters": params})

    resp = session_360.post("https://waba-v2.360dialog.io/messages", json=payload, timeout=25)
    if pause_on_429 and resp.status_code == 429:
        ra = resp.headers.get("Retry-After")
        wait_s = int(ra) if ra and ra.isdigit() else 3
        time.sleep(wait_s)
        resp = session_360.post("https://waba-v2.360dialog.io/messages", json=payload, timeout=25)

    ok = 200 <= resp.status_code < 300
    return ok, resp.text, resp.status_code

def guardar_checkpoint(pendientes, enviados, fallidos):
    data = {"ts": time.time(), "pendientes": pendientes, "enviados": enviados, "fallidos": fallidos}
    with open(ARCHIVO_CHECK, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

def cargar_checkpoint():
    if not os.path.exists(ARCHIVO_CHECK):
        return None
    try:
        with open(ARCHIVO_CHECK, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return None

def registrar_excel(numero, nombre, estado):
    try:
        hoy = datetime.date.today().strftime('%Y-%m-%d')
        if not os.path.exists(ARCHIVO_ENV):
            pd.DataFrame(columns=["Fecha", "Número", "Nombre", "Estado"]).to_excel(ARCHIVO_ENV, index=False)
        df_exist = pd.read_excel(ARCHIVO_ENV)
        nuevo = pd.DataFrame([{"Fecha": hoy, "Número": f"'{numero}", "Nombre": nombre, "Estado": estado}])
        pd.concat([df_exist, nuevo], ignore_index=True).to_excel(ARCHIVO_ENV, index=False)
    except:
        pass

def expected_params_for_template(template_name: str) -> int:
    return TEMPLATE_PARAM_COUNTS.get((template_name or "").strip(), 0)

# ===================== Carga de archivo =====================
file = st.file_uploader("📁 Sube tu Excel (con columnas de país, teléfono, plantilla y parámetros)", type=["xlsx"])

if file and api_key:
    df = pd.read_excel(file)
    df.columns = df.columns.str.strip()
    st.success(f"Archivo cargado con {len(df)} registros.")

    cols = df.columns.tolist()
    c1, c2, c3, c4 = st.columns(4)
    with c1: plantilla_col = st.selectbox("🧩 Columna plantilla", cols)
    with c2: tel_col = st.selectbox("📱 Teléfono", cols)
    with c3: nombre_col = st.selectbox("📗 Nombre", cols)
    with c4: pais_col = st.selectbox("🌎 Código país", cols)

    c5, c6 = st.columns(2)
    with c5: p1_col = st.selectbox("🔢 Parámetro {{1}}", ["(ninguno)"] + cols)
    with c6: p2_col = st.selectbox("🔢 Parámetro {{2}}", ["(ninguno)"] + cols)

    if st.button("🚀 Enviar (rápido y tolerante a fallas)"):
        start_time = time.time()
        session_360 = build_session_360(api_key)

        # Estado compartido
        lock = threading.Lock()
        stats = {"enviados_ok": 0, "fallidos_cnt": 0, "completed": 0}

        total = len(df)
        trabajos = []
        fallidos_rows = []
        enviados_set = set()

        # Preparar trabajos
        for _, row in df.iterrows():
            tel = normalizar_numero(f"+{str(row[pais_col])}{str(row[tel_col])}")
            nombre = str(row[nombre_col]).strip() if pd.notna(row[nombre_col]) else "Cliente WhatsApp"
            plantilla = str(row[plantilla_col]).strip()

            # Lee p1/p2 desde columnas, pero NO los mandes aún
            p1_raw = "" if p1_col == "(ninguno)" or pd.isna(row.get(p1_col)) else str(row[p1_col]).strip()
            p2_raw = "" if p2_col == "(ninguno)" or pd.isna(row.get(p2_col)) else str(row[p2_col]).strip()

            # Cuántos parámetros acepta esta plantilla
            needed = expected_params_for_template(plantilla)

            # Construye params solo hasta 'needed', ignora extras (compatibilidad con tu app original)
            params = []
            if needed >= 1 and p1_raw:
                params.append({"type": "text", "text": p1_raw})
            if needed >= 2 and p2_raw:
                params.append({"type": "text", "text": p2_raw})

            # Validación por fila
            present = len(params)
            if present != needed:
                # Si falta alguno requerido -> marcar fallido con mensaje claro
                fallidos_rows.append({
                    "Número": tel, "Nombre": nombre, "Plantilla": plantilla,
                    "Respuesta": f"La plantilla '{plantilla}' espera {needed} parámetro(s) y se recibieron {present}.",
                    "Code": 0
                })
                registrar_excel(tel, nombre, f"❌ Configuración inválida: espera {needed}, llegó {present}")
                continue

            # Texto humano para preview (tu Node ya lo renderiza en Chatwoot)
            p1 = p1_raw if needed >= 1 else ""
            p2 = p2_raw if needed >= 2 else ""
            mensaje_humano = render_template_preview(plantilla, p1, p2)

            job = {"tel": tel, "nombre": nombre, "plantilla": plantilla,
                   "params": params, "p1": p1, "p2": p2, "mensaje": mensaje_humano}
            job["key"] = idempotency_key({"to": tel, "tpl": plantilla, "p1": p1, "p2": p2})
            trabajos.append(job)

        # Reanudar si hay checkpoint
        cp = cargar_checkpoint()
        if cp and "enviados" in cp:
            ya = set(cp["enviados"])
            trabajos = [t for t in trabajos if t["key"] not in ya]
            enviados_set |= ya
            st.info(f"🔁 Reanudando: {len(ya)} ya enviados, {len(trabajos)} pendientes.")

        pendientes_keys = [t["key"] for t in trabajos]

        progress = st.progress(0.0)
        status = st.empty()

        def tarea(job):
            tel = job["tel"]; nombre = job["nombre"]
            plantilla = job["plantilla"]; params = job["params"]
            key = job["key"]

            ok, txt, code = send_360_template(session_360, tel, plantilla, params, pause_on_429)
            if ok:
                registrar_excel(tel, nombre, "✅ Enviado")
                with lock:
                    stats["enviados_ok"] += 1
                    enviados_set.add(key)
            else:
                with lock:
                    stats["fallidos_cnt"] += 1
                    fallidos_rows.append({"Número": tel, "Nombre": nombre, "Plantilla": plantilla, "Respuesta": txt, "Code": code})
                registrar_excel(tel, nombre, f"❌ Falló ({code})")

        checkpoint_every = max(20, math.ceil(total * 0.02))
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = [ex.submit(tarea, job) for job in trabajos]
            for fut in as_completed(futures):
                with lock:
                    stats["completed"] += 1
                    completed = stats["completed"]

                if completed % checkpoint_every == 0:
                    try:
                        guardar_checkpoint(pendientes_keys, list(enviados_set), [f["Número"] for f in fallidos_rows])
                    except:
                        pass

                pct = (len(enviados_set)) / total if total else 1.0
                elapsed = max(1, time.time() - start_time)
                tasa = (len(enviados_set) / elapsed) if elapsed else 0
                progress.progress(min(1.0, pct))
                status.markdown(
                    f"**Progreso:** {pct:.0%} | ⏱️ {elapsed:.0f}s | ⚡ {tasa:.2f} msg/s  \n"
                    f"✅ Enviados: {stats['enviados_ok']} | ❌ Fallidos: {stats['fallidos_cnt']}"
                )

        if fallidos_rows:
            pd.DataFrame(fallidos_rows).to_excel(ARCHIVO_FAIL, index=False)

        try:
            guardar_checkpoint(pendientes_keys, list(enviados_set), [f["Número"] for f in fallidos_rows])
        except:
            pass

        st.success("🎉 Proceso terminado.")
        if os.path.exists(ARCHIVO_ENV):
            with open(ARCHIVO_ENV, "rb") as f:
                st.download_button("📥 Descargar envíos (Excel)", f, file_name="envios_hoy.xlsx")
        if os.path.exists(ARCHIVO_FAIL):
            with open(ARCHIVO_FAIL, "rb") as f:
                st.download_button("⚠️ Descargar fallidos (Excel)", f, file_name="fallidos.xlsx")

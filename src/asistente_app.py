"""Asistente de licitaciones (IA local): chat, alerta del día, competidores probables y configuración.

Se muestra dentro del tablero (botón «🤖 Asistente IA») y también suelto:
    python -m streamlit run src/asistente_app.py

El chat es lo principal. Todo lo que se ajusta (modelo, dispositivo, descargas) vive aparte, en
«⚙️ Configuración», junto a las especificaciones del computador.
"""
import html
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

RAIZ = Path(__file__).resolve().parent.parent
for sub in ("", "ia", "ml"):
    if str(RAIZ / "src" / sub) not in sys.path:
        sys.path.insert(0, str(RAIZ / "src" / sub))
import cliente, consultas, equipo, estilo  # noqa: E402

VISTAS = ["💬 Chat", "📬 Alerta de hoy", "🎯 Competidores", "⚙️ Configuración"]
CHAT, ALERTA, RIVALES, CONFIG = VISTAS

# Globitos de sugerencia: texto corto en el globo -> pregunta completa que se envía.
IDEAS = {
    "Sobre Brighter y el mercado": {
        "¿Qué es Brighter?": "¿Qué es Brighter?",
        "¿Qué es BTOUCH?": "¿Qué es BTOUCH?",
        "¿Qué es el SEACE?": "¿Qué es el SEACE?",
        "Principales competidores": "¿Cuáles son los principales competidores?",
    },
    "Sobre tus datos": {
        "Licitaciones vigentes": "¿Cuántas licitaciones hay vigentes?",
        "Postores en Arequipa": "¿Qué empresas se presentaron más veces en Arequipa?",
        "Postores de pizarras": "¿Cuáles son los postores de pizarras?",
    },
}
IDEAS_PLANAS = {k: v for grupo in IDEAS.values() for k, v in grupo.items()}
AVATAR = {"user": "user", "assistant": "🤖"}


# --------------------------------------------------------------------------- utilidades
def _db() -> Path:
    return RAIZ / "data" / "analisis.db"


@st.cache_data(ttl=300, show_spinner=False)
def _equipo() -> dict:
    return equipo.especificaciones()


def _estado() -> dict:
    return cliente.estado()


def _ir_a_config():
    st.session_state["ia_vista"] = CONFIG


def _navegacion() -> str:
    st.session_state.setdefault("ia_vista", CHAT)
    if hasattr(st, "segmented_control"):
        v = st.segmented_control("Sección", VISTAS, key="ia_vista", label_visibility="collapsed")
    else:                                                        # Streamlit antiguo
        v = st.radio("Sección", VISTAS, key="ia_vista", horizontal=True, label_visibility="collapsed")
    return v or CHAT                                              # tocar la opción activa la deselecciona


# --------------------------------------------------------------------------- cabecera
def _cabecera(e: dict):
    c1, c2 = st.columns([5, 3], vertical_alignment="center")
    with c1:
        st.markdown("### 🤖 Asistente de licitaciones")
        st.markdown('<span class="sub">IA local: tus datos no salen de este computador.</span>',
                    unsafe_allow_html=True)
    with c2:
        if e["servidor"] and e["modelo"]:
            st.markdown(f'<div style="text-align:right">{estilo.pastilla("● IA lista · " + e["elegido"], "ok")}</div>',
                        unsafe_allow_html=True)
        elif e["servidor"]:
            st.markdown(f'<div style="text-align:right">{estilo.pastilla("● Ollama sin modelo", "warn")}</div>',
                        unsafe_allow_html=True)
        else:
            st.markdown(f'<div style="text-align:right">{estilo.pastilla("● Ollama apagado", "off")}</div>',
                        unsafe_allow_html=True)


# --------------------------------------------------------------------------- chat
def _elegir_idea():
    """Se ejecuta al tocar un globo: manda esa pregunta al chat y deja el globo sin marcar."""
    for k in [k for k in st.session_state if str(k).startswith("idea_")]:
        v = st.session_state.get(k)
        if v:
            st.session_state["pregunta_pendiente"] = IDEAS_PLANAS.get(v, v)
            st.session_state[k] = None


def _globos(grupo: str, opciones: list[str]):
    clave = f"idea_{grupo}"
    if hasattr(st, "pills"):
        st.pills(grupo, opciones, key=clave, label_visibility="collapsed", on_change=_elegir_idea)
    else:                                                        # Streamlit antiguo: botones comunes
        cols = st.columns(len(opciones))
        for i, (col, o) in enumerate(zip(cols, opciones)):
            col.button(o, key=f"chip_{clave}_{i}", on_click=lambda o=o: st.session_state.update(
                pregunta_pendiente=IDEAS_PLANAS.get(o, o)))


def _bienvenida():
    st.markdown("## ¿En qué te ayudo?")
    st.markdown('<span class="sub">Pregunta por empresas, marcas, procesos y postores. '
                'Respondo con los datos que ya tienes cargados; si no tengo información, te lo digo.</span>',
                unsafe_allow_html=True)
    st.write("")
    for grupo, ideas in IDEAS.items():
        st.caption(grupo)
        _globos(grupo, list(ideas))


def _respuesta(m: dict, i: int):
    """Dibuja una respuesta del asistente (la guardada en el historial del chat)."""
    r = m["r"]
    if m.get("error"):
        st.error(m["error"])
        return
    if not r["ok"]:
        st.markdown(f"No pude responder con estos datos. {r['motivo']}")
        if r.get("sql"):
            with st.expander("Ver la consulta que intenté"):
                st.code(r["sql"], language="sql")
        return
    if r.get("resumen"):
        st.markdown(r["resumen"])
    if r["filas"]:
        tabla = pd.DataFrame(r["filas"], columns=r["columnas"])
        if r.get("origen") == "conocimiento" and r.get("resumen"):
            with st.expander("Datos de origen"):               # el texto ya lo dice; la tabla es para verificar
                st.dataframe(tabla, hide_index=True, **estilo.ANCHO)
        else:
            st.dataframe(tabla, hide_index=True, **estilo.ANCHO)
        if r["truncado"]:
            st.caption(f"Se muestran las primeras {consultas.MAX_FILAS} filas.")
    if r.get("origen") == "conocimiento":
        # sin SQL: salió del glosario, las marcas o el ranking de empresas del estudio de mercado
        st.caption("📚 Respuesta de tu base de conocimiento (glosario, marcas y empresas del estudio de mercado).")
        if r.get("nota"):
            st.caption(r["nota"])
    else:
        with st.expander("Cómo lo obtuve"):
            st.code(r["sql"], language="sql")
            if r.get("nota"):
                st.caption(r["nota"])
            if st.button("✅ Es correcta: aprender esta consulta", key=f"aprender_{i}"):
                st.toast("Guardada." if consultas.aprender(m["pregunta"], r["sql"]) else "Ya la tenía.")
            st.caption("Las consultas confirmadas se usan como ejemplo en preguntas parecidas.")


def _responder(q: str) -> dict:
    try:
        return {"rol": "assistant", "pregunta": q, "r": consultas.preguntar(q)}
    except cliente.IAError as err:
        if "timed out" in str(err):
            msg = ("El modelo no respondió a tiempo. Prueba otro dispositivo o un modelo más chico en "
                   f"«⚙️ Configuración».\n\nDetalle: {err}")
        else:
            msg = (f"La IA no pudo contestar. Si Ollama está apagado, ábrelo; las preguntas sobre empresas y "
                   f"marcas igual se responden con tu base de conocimiento.\n\nDetalle: {err}")
        return {"rol": "assistant", "pregunta": q, "r": {"ok": False, "motivo": ""}, "error": msg}


def _chat(q: str | None):
    """Historial + respuesta a `q`. La caja de texto se crea aparte, fuera de las columnas, para que
    Streamlit la deje fija abajo (dentro de un contenedor se queda en medio de la página)."""
    hist = st.session_state.setdefault("chat", [])
    if q:
        hist.append({"rol": "user", "texto": q})
    if not hist:
        _bienvenida()
    else:
        b1, b2, _ = st.columns([2, 2, 6])
        if b1.button("🗑️ Nueva conversación", key="chat_nuevo"):
            st.session_state["chat"] = []
            st.rerun()
        with b2.popover("💡 Ideas"):
            for grupo, ideas in IDEAS.items():
                st.caption(grupo)
                _globos(grupo, list(ideas))
    for i, m in enumerate(hist):
        with st.chat_message(m["rol"], avatar=AVATAR[m["rol"]]):
            if m["rol"] == "user":
                st.markdown(m["texto"])
            else:
                _respuesta(m, i)
    if q:
        with st.chat_message("assistant", avatar=AVATAR["assistant"]):
            with st.spinner("Pensando…"):
                m = _responder(q)
            hist.append(m)
            _respuesta(m, len(hist) - 1)


# --------------------------------------------------------------------------- alerta
def _alerta():
    alertas = sorted((RAIZ / "data" / "alertas").glob("alerta_*.md"))
    if not alertas:
        st.info("Aún no hay alertas. Genera una con:  `python src/alerta_diaria.py --actualizar`")
        return
    with estilo.tarjeta("alerta"):
        st.markdown(alertas[-1].read_text(encoding="utf-8"))
    st.caption(f"Archivo: {alertas[-1].name}. Se genera con `iniciar.bat alerta`.")


# --------------------------------------------------------------------------- competidores
def _rivales():
    import historial, predictor
    db = _db()
    if not db.exists():
        st.info("Falta data/analisis.db. Genera el historial con "
                "`python src/postores.py --anios 2023 2024 2025 2026 --solo INTERACTIVA`.")
        return

    @st.cache_resource
    def _modelo():
        h = historial.Historial(historial.cargar(db))
        return h, predictor.entrenar(h)

    h, modelo = _modelo()
    st.markdown('<span class="sub">¿Quién se presentaría a un proceso parecido? Completa lo que sepas.</span>',
                unsafe_allow_html=True)
    with estilo.tarjeta("rivales"):
        c = st.columns(3)
        entidad = c[0].text_input("Entidad (como figura en SEACE)")
        depto = c[1].text_input("Departamento")
        fecha = c[2].date_input("Fecha del proceso")
        conocidos = st.multiselect("¿Ya sabes que alguna empresa se presentó?", h.rucs,
                                   format_func=lambda r: f"{h.nombres.get(r, r)} ({r})")
    out = predictor.predecir(modelo, h, pd.Timestamp(fecha), entidad, depto, conocidos, top=12)
    st.dataframe(out.assign(prob=(out["prob"] * 100).round(1)).rename(columns={"prob": "prob. %"}),
                 hide_index=True, **estilo.ANCHO)
    st.caption("Estimación a partir del historial. No es una afirmación sobre ninguna empresa: sirve para "
               "priorizar qué expediente leer. Compruébala con `python src/ml/validar.py`.")


# --------------------------------------------------------------------------- configuración
def _datos_conocidos() -> dict:
    """Cuántas cosas tiene cargadas la IA para responder (solo lectura)."""
    out = {}
    try:
        glosario = RAIZ / "docs" / "conocimiento" / "glosario.jsonl"
        out["Términos del glosario"] = sum(1 for linea in glosario.read_text(encoding="utf-8").splitlines()
                                           if linea.strip())
    except OSError:
        pass
    try:
        con = sqlite3.connect(f"file:{_db().as_posix()}?mode=ro", uri=True)
    except sqlite3.Error:
        return out
    try:
        for etiqueta, tabla in (("Empresas del ranking", "ranking_empresas"), ("Marcas", "marcas"),
                                ("Participaciones de postores", "postores")):
            try:
                out[etiqueta] = con.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
            except sqlite3.Error:
                pass
    finally:
        con.close()
    return out


def _seccion_equipo(e: dict):
    st.markdown("#### 🖥️ Tu equipo")
    s = _equipo()
    with estilo.tarjeta("equipo"):
        a, b, c, d = st.columns(4)
        a.metric("Procesador", f"{s['nucleos']} núcleos" if s["nucleos"] else "—")
        if s["ram_total_gb"]:
            b.metric("Memoria libre / total",
                     f"{s['ram_libre_gb']} / {s['ram_total_gb']} GB" if s["ram_libre_gb"] else f"{s['ram_total_gb']} GB")
        else:
            b.metric("Memoria RAM", "—")
        gpu = s["gpus"][0] if s["gpus"] else None
        c.metric("Memoria de video", f"{gpu['vram_gb']} GB" if gpu and gpu.get("vram_gb") else
                 ("No dedicada" if not gpu else "Compartida"))
        d.metric("Disco libre", f"{s['disco_libre_gb']} GB" if s["disco_libre_gb"] else "—")
        detalle = [f"**CPU:** {s['cpu'] or 'no detectado'}",
                   "**Video:** " + (", ".join(g["nombre"] for g in s["gpus"]) or "no detectada"),
                   f"**Sistema:** {s['sistema']}"]
        st.caption("  ·  ".join(detalle))
    nombre, motivo = equipo.recomendar(s)
    st.info(f"Modelo recomendado para este equipo: **{nombre}** — {motivo}.")
    if not s["gpus"] or not s.get("vram_gb"):
        st.caption("Sin tarjeta de video dedicada la IA corre en el procesador: es normal que tarde unos "
                   "segundos. Un modelo más chico responde más rápido.")


def _seccion_modelo(e: dict, listo: bool):
    st.markdown("#### 🧠 Modelo y rendimiento")
    cfg = cliente.config()
    nombres = [n for n in e.get("disponibles", []) if not any(x in n.lower() for x in cliente._NO_CHAT)]
    modos = {"auto": "Automático (Ollama reparte)", "gpu": "100 % tarjeta de video (GPU)",
             "cpu": "Solo procesador (CPU)"}
    perfiles = {"Rápido (4096)": 4096, "Normal (8192)": 8192, "Amplio (16384)": 16384}
    act = next((k for k, v in perfiles.items() if v == cfg["contexto_tokens"]), "Normal (8192)")
    izq, der = st.columns([3, 2])
    with izq, estilo.tarjeta("modelo"):
        opciones_modelo = ["auto"] + nombres
        mod = st.selectbox("Modelo", opciones_modelo,
                           index=opciones_modelo.index(cfg["modelo"]) if cfg["modelo"] in opciones_modelo else 0,
                           help="Uno más chico responde más rápido; uno más grande escribe mejor el SQL.")
        c1, c2 = st.columns(2)
        disp = c1.selectbox("Dispositivo", list(modos), format_func=modos.get,
                            index=list(modos).index(cfg.get("dispositivo", "auto"))
                            if cfg.get("dispositivo", "auto") in modos else 0,
                            help="Si con GPU falla por memoria de video, usa Automático o CPU.")
        per = c2.selectbox("Memoria de contexto", list(perfiles), index=list(perfiles).index(act),
                           help="Menos contexto = menos memoria y respuestas más rápidas.")
        b1, b2 = st.columns(2)
        if b1.button("Guardar ajustes", type="primary", **estilo.ANCHO):
            cliente.guardar_ajustes(dispositivo=disp, modelo=mod, contexto_tokens=perfiles[per])
            st.success("Guardado. Se aplica en la próxima consulta.")
        if b2.button("Probar velocidad", disabled=not listo, **estilo.ANCHO):
            import time
            cliente.guardar_ajustes(dispositivo=disp, modelo=mod, contexto_tokens=perfiles[per])
            t0 = time.time()
            try:
                with st.spinner("Midiendo…"):
                    cliente.chat("Responde solo con una palabra.", "Di: listo",
                                 cfg={**cliente.config(), "timeout_s": 120})
                st.success(f"Respondió en {time.time() - t0:.1f} s con «{modos[disp]}».")
            except cliente.IAError as err:
                st.error(f"No respondió en 120 s con «{modos[disp]}». Prueba otro dispositivo o modelo. {err}")
    with der, estilo.tarjeta("estado"):
        st.markdown("**Estado ahora**")
        if not e["servidor"]:
            st.markdown(estilo.pastilla("● Ollama apagado", "off"), unsafe_allow_html=True)
            st.caption("Abre Ollama (ícono en la bandeja de Windows) o ejecuta `ollama serve`. "
                       "Sin él, el chat solo responde lo que está en la base de conocimiento.")
        else:
            st.markdown(estilo.pastilla("● Ollama en marcha", "ok"), unsafe_allow_html=True)
            st.caption(f"Modelo elegido: **{e.get('elegido') or 'ninguno'}**")
            cargados = equipo.en_memoria(cfg["url"])
            if cargados:
                for m in cargados:
                    donde = "tarjeta de video" if m["gpu_pct"] >= 90 else (
                        "procesador" if m["gpu_pct"] == 0 else f"{m['gpu_pct']} % en la tarjeta de video")
                    st.caption(f"En memoria: **{m['nombre']}** ({m['tam_gb']} GB) · corre en {donde}")
            else:
                st.caption("Ningún modelo está cargado en memoria: se carga al primer mensaje.")


def _seccion_descargas(e: dict):
    st.markdown("#### ⬇️ Modelos")
    s = _equipo()
    instalados = set(e.get("disponibles", []))
    marcas = {"ok": "✅ Cómodo", "justo": "⚠️ Justo", "no": "⛔ Pesado", "?": "—"}
    filas = []
    for nombre in sorted(cliente.RECOMENDADOS, key=lambda n: equipo.REQUISITOS.get(n, (99, 99))[1]):
        nota = cliente.RECOMENDADOS[nombre]
        disco, ram = equipo.REQUISITOS.get(nombre, (None, None))
        filas.append({"Modelo": nombre, "Descargado": "Sí" if nombre in instalados else "No",
                      "Disco": f"{disco} GB" if disco else "—", "Memoria": f"{ram} GB" if ram else "—",
                      "En tu equipo": marcas[equipo.ajuste(nombre, s)], "Para qué sirve": nota})
    with estilo.tarjeta("modelos"):
        st.dataframe(pd.DataFrame(filas), hide_index=True, **estilo.ANCHO)
        d1, d2 = st.columns([3, 1], vertical_alignment="bottom")
        dm = d1.selectbox("Modelo a descargar", [f["Modelo"] for f in filas],
                          format_func=lambda n: f"{n} · {cliente.RECOMENDADOS[n]}", key="modelo_descarga")
        if d2.button("⬇️ Descargar", disabled=not e["servidor"], **estilo.ANCHO):
            barra, txt = st.progress(0.0), st.empty()
            try:
                for est, frac in cliente.descargar(dm):
                    txt.caption(est)
                    if frac is not None:
                        barra.progress(min(frac, 1.0))
                barra.progress(1.0)
                cliente.guardar_ajustes(modelo=dm)
                st.success(f"Listo: {dm} descargado y elegido. Recarga la página para verlo en la lista.")
            except cliente.IAError as err:
                st.error(str(err))
        st.caption("Necesita internet y Ollama abierto; el modelo se baja una sola vez."
                   if e["servidor"] else "Abre Ollama para poder descargar modelos desde aquí.")


def _seccion_conocimiento():
    datos = _datos_conocidos()
    if not datos:
        return
    st.markdown("#### 📚 Lo que la IA conoce")
    with estilo.tarjeta("conocimiento"):
        for col, (k, v) in zip(st.columns(len(datos)), datos.items()):
            col.metric(k, f"{v:,}")
        st.caption("Se cargan con `iniciar.bat importar` a partir de tus Excel de estudio de mercado.")


def _configuracion(e: dict, listo: bool):
    _seccion_equipo(e)
    _seccion_modelo(e, listo)
    _seccion_descargas(e)
    _seccion_conocimiento()


# --------------------------------------------------------------------------- entrada
def render():
    estilo.aplicar()
    e = _estado()
    listo = bool(e["servidor"] and e["modelo"])
    vista = st.session_state.get("ia_vista") or CHAT
    q = None
    if vista == CHAT:                              # fuera de cualquier columna: así queda fija abajo
        escrito = st.chat_input("Escribe tu pregunta…")
        q = escrito or st.session_state.pop("pregunta_pendiente", None)
    with estilo.columna_chat():
        _cabecera(e)
        vista = _navegacion()
        if vista != CHAT:
            q = None
        if not listo and vista == CHAT:
            c1, c2 = st.columns([5, 2], vertical_alignment="center")
            c1.caption("Sin IA activa sigo respondiendo sobre empresas, marcas y términos. "
                       "Para consultar tus datos abre Ollama.")
            c2.button("⚙️ Configuración", on_click=_ir_a_config, key="ir_config", type="tertiary")
        if vista == CHAT:
            _chat(q)
        elif vista == ALERTA:
            _alerta()
        elif vista == RIVALES:
            _rivales()
        else:
            _configuracion(e, listo)


if __name__ == "__main__":
    st.set_page_config(page_title="Asistente de licitaciones", layout="wide")
    render()

"""Asistente de licitaciones (IA local): preguntar a los datos, alerta del día y competidores.

Se muestra dentro del tablero (botón «🤖 Asistente IA») y también suelto:
    python -m streamlit run src/asistente_app.py
"""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

RAIZ = Path(__file__).resolve().parent.parent
for sub in ("ia", "ml"):
    if str(RAIZ / "src" / sub) not in sys.path:
        sys.path.insert(0, str(RAIZ / "src" / sub))
import cliente, consultas  # noqa: E402


def render():
    st.subheader("🤖 Asistente de licitaciones · IA local")

    e = cliente.estado()
    listo = bool(e["servidor"] and e["modelo"])
    if listo:
        st.caption(f"Modelo local en uso: **{e['elegido']}**")
    else:
        st.warning("Ollama no responde o no hay modelo de chat. Ábrelo y corre "
                   "`python src/ia/comprobar_ia.py`. Las pestañas sin IA siguen funcionando.")

    with st.expander("⚙️ Ajustes de IA (dispositivo, modelo, velocidad)", expanded=not listo):
        cfg = cliente.config()
        nombres = [n for n in e.get("disponibles", []) if not any(x in n.lower() for x in cliente._NO_CHAT)]
        c1, c2, c3 = st.columns(3)
        modos = {"auto": "Automático (Ollama reparte)", "gpu": "100 % tarjeta de video (GPU)",
                 "cpu": "Solo procesador (CPU)"}
        disp = c1.selectbox("Dispositivo", list(modos), format_func=modos.get,
                            index=list(modos).index(cfg.get("dispositivo", "auto"))
                            if cfg.get("dispositivo", "auto") in modos else 0)
        opciones_modelo = ["auto"] + nombres
        mod = c2.selectbox("Modelo", opciones_modelo,
                           index=opciones_modelo.index(cfg["modelo"]) if cfg["modelo"] in opciones_modelo else 0,
                           help="Uno más chico responde más rápido; uno más grande escribe mejor el SQL.")
        perfiles = {"Rápido (4096)": 4096, "Normal (8192)": 8192, "Amplio (16384)": 16384}
        act = next((k for k, v in perfiles.items() if v == cfg["contexto_tokens"]), "Normal (8192)")
        per = c3.selectbox("Memoria de contexto", list(perfiles), index=list(perfiles).index(act),
                           help="Menos contexto = menos memoria y respuestas más rápidas.")
        b1, b2 = st.columns(2)
        if b1.button("Guardar ajustes"):
            cliente.guardar_ajustes(dispositivo=disp, modelo=mod, contexto_tokens=perfiles[per])
            st.success("Guardado. Se aplica en la próxima consulta.")
        if b2.button("Probar velocidad", disabled=not listo):
            import time
            cliente.guardar_ajustes(dispositivo=disp, modelo=mod, contexto_tokens=perfiles[per])
            t0 = time.time()
            try:
                cliente.chat("Responde solo con una palabra.", "Di: listo", cfg={**cliente.config(), "timeout_s": 120})
                st.success(f"Respondió en {time.time() - t0:.1f} s con «{modos[disp]}».")
            except cliente.IAError as err:
                st.error(f"No respondió en 120 s con «{modos[disp]}». Prueba otro dispositivo o modelo. {err}")
        st.markdown("**Descargar un modelo** (necesita internet; se baja una sola vez)")
        d1, d2 = st.columns([3, 1])
        dm = d1.selectbox("Modelo a descargar", list(cliente.RECOMENDADOS),
                          format_func=lambda n: f"{n} · {cliente.RECOMENDADOS[n]}",
                          key="modelo_descarga")
        if d2.button("⬇️ Descargar", disabled=not e["servidor"]):
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
        if not e["servidor"]:
            st.caption("Abre Ollama para poder descargar modelos desde aquí.")
        st.caption("Si con GPU falla por memoria de video, usa Automático o CPU.")

    tab_pregunta, tab_alerta, tab_rivales = st.tabs(["Preguntar", "Alerta de hoy", "Competidores probables"])

    # ------------------------------------------------------------------ preguntar
    with tab_pregunta:
        q = st.text_input("Pregunta sobre tus licitaciones y postores",
                          placeholder="¿Qué empresas se presentaron más veces en Arequipa?")
        if st.button("Consultar", type="primary", disabled=not (listo and q)):
            with st.spinner("Pensando…"):
                try:
                    st.session_state["resp"] = (q, consultas.preguntar(q))
                except cliente.IAError as err:
                    st.session_state.pop("resp", None)
                    if "timed out" in str(err):
                        st.error("El modelo no respondió a tiempo. Prueba otro dispositivo o un modelo más "
                                 f"chico en «⚙️ Ajustes de IA».\n\nDetalle: {err}")
                    else:
                        st.error(f"La IA no pudo contestar. {err}")
        if "resp" in st.session_state:
            pregunta, r = st.session_state["resp"]
            if not r["ok"]:
                st.error(r["motivo"])
                if r.get("sql"):
                    st.code(r["sql"], language="sql")
            else:
                st.markdown(f"**{r['resumen']}**")
                st.dataframe(pd.DataFrame(r["filas"], columns=r["columnas"]),
                             use_container_width=True, hide_index=True)
                if r["truncado"]:
                    st.caption(f"Se muestran las primeras {consultas.MAX_FILAS} filas.")
                with st.expander("Ver la consulta SQL"):
                    st.code(r["sql"], language="sql")
                    st.caption(r.get("nota", ""))
                c1, c2 = st.columns(2)
                if c1.button("✅ Correcta: aprender esta consulta"):
                    st.success("Guardada." if consultas.aprender(pregunta, r["sql"]) else "Ya la tenía.")
                c2.caption("Las consultas confirmadas se usan como ejemplo en preguntas parecidas.")

    # --------------------------------------------------------------------- alerta
    with tab_alerta:
        alertas = sorted((RAIZ / "data" / "alertas").glob("alerta_*.md"))
        if alertas:
            st.markdown(alertas[-1].read_text(encoding="utf-8"))
        else:
            st.info("Aún no hay alertas. Genera una con:  `python src/alerta_diaria.py --actualizar`")

    # -------------------------------------------------------------------- rivales
    with tab_rivales:
        import historial, predictor
        db = RAIZ / "data" / "analisis.db"
        if not db.exists():
            st.info("Falta data/analisis.db. Genera el historial con "
                    "`python src/postores.py --anios 2023 2024 2025 2026 --solo INTERACTIVA`.")
        else:
            @st.cache_resource
            def _modelo():
                h = historial.Historial(historial.cargar(db))
                return h, predictor.entrenar(h)
            h, modelo = _modelo()
            c = st.columns(3)
            entidad = c[0].text_input("Entidad (como figura en SEACE)")
            depto = c[1].text_input("Departamento")
            fecha = c[2].date_input("Fecha del proceso")
            conocidos = st.multiselect(
                "¿Ya sabes que alguna empresa se presentó?", h.rucs,
                format_func=lambda r: f"{h.nombres.get(r, r)} ({r})")
            out = predictor.predecir(modelo, h, pd.Timestamp(fecha), entidad, depto, conocidos, top=12)
            st.dataframe(out.assign(prob=(out["prob"] * 100).round(1)).rename(columns={"prob": "prob. %"}),
                         use_container_width=True, hide_index=True)
            st.caption("Estimación a partir del historial. No es una afirmación sobre ninguna empresa: "
                       "sirve para priorizar qué expediente leer. Compruébala con `python src/ml/validar.py`.")


if __name__ == "__main__":
    st.set_page_config(page_title="Asistente de licitaciones", layout="wide")
    render()

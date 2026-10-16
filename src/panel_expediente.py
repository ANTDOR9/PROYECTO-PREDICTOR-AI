"""
Panel de expediente para el tablero: la comparación contra BTOUCH con un botón.

Está organizado en dos capas, y la separación es deliberada.

La **capa 1** muestra lo que ya está en la base y aparece al instante: entidad,
fecha, monto adjudicado, proveedor ganador, categoría de producto y enlace a la
ficha del SEACE. No descarga nada.

La **capa 2** es el análisis del expediente, y es cara: descargar puede tardar
hasta un minuto, y el reconocimiento óptico unos cinco segundos por página
escaneada. Por eso va detrás de un botón, informa en qué paso está, y guarda el
resultado para no repetirlo.

La capa 2 falla seguido, y eso no es un defecto del panel. Solo cuatro de cada
veintitrés expedientes entregan un requerimiento legible: el resto son escaneos
de los que no se puede aislar la sección técnica. Cuando no se puede, el panel
dice en qué paso se detuvo y por qué, en lugar de quedarse en blanco.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

import streamlit as st

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "ia"))

TMP = RAIZ / "tmp" / "panel"


def ruta_analisis(db_principal: Path | str) -> str:
    """
    Las tablas derivadas viven en data/analisis.db, no en licitaciones.db.

    Se acepta igual la base principal si el analisis esta ahi: las versiones
    anteriores lo guardaban junto y no tiene sentido romper una instalacion
    existente por eso.
    """
    analisis = Path(db_principal).parent / "analisis.db"
    if analisis.exists():
        return str(analisis)
    return str(db_principal)

COLORES = {"CUMPLE": "#C6E0B4", "OBSERVADO": "#FFF2CC", "NO CUMPLE": "#F8CBAD",
           "SIN DATO": "#EDEDED", "REVISIÓN MANUAL": "#FFF2CC"}

#: Orden en que conviene intentar los documentos PARA ESTE USO.
#:
#: No es el mismo orden que usa `contenedores.clasificar`. Allá el acta de
#: adjudicación pesa casi tanto como las especificaciones, porque se la buscaba
#: para identificar la marca del ganador. Acá lo que hace falta es el
#: requerimiento técnico —lo que la entidad EXIGIÓ— y eso está en las bases,
#: no en el acta. El acta, además, se verificó que no nombra ninguna marca.
PRIORIDAD_PANEL = {
    "especificaciones": 100,
    "bases": 90,
    "pliego": 70,
    "costos": 40,
    "evaluacion": 30,
    "desierto": 25,
    "documento": 25,
    "otro": 20,
    "ruido": 5,
    "ilegible": 0,
}


# --------------------------------------------------------------------------- #
# Lectura del índice
# --------------------------------------------------------------------------- #

def hay_indice(db: Path | str) -> bool:
    try:
        con = sqlite3.connect(f"file:{ruta_analisis(db)}?mode=ro", uri=True)
        n = con.execute("select count(*) from documentos").fetchone()[0]
        con.close()
        return n > 0
    except sqlite3.Error:
        return False


def documentos_de(db: Path | str, ocid: str) -> list[dict]:
    """Documentos indexados de un proceso, del más al menos relevante."""
    if not ocid:
        return []
    try:
        con = sqlite3.connect(f"file:{ruta_analisis(db)}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        filas = [dict(r) for r in con.execute(
            "select * from documentos where ocid = ? order by etapa", (ocid,))]
        con.close()
    except sqlite3.Error:
        return []

    from contenedores import clasificar                          # noqa: PLC0415
    for f in filas:
        clase, _, _ = clasificar(f"{f['titulo']} {f['tipo_doc']}")
        f["clase"] = clase
        f["prioridad"] = PRIORIDAD_PANEL.get(clase, 20)
    return sorted(filas, key=lambda f: -f["prioridad"])


# --------------------------------------------------------------------------- #
# El análisis, sin Streamlit: así se puede probar desde la consola
# --------------------------------------------------------------------------- #

def analizar(filecode: str, nombre_doc: str = "", avisar=lambda paso: None,
             usar_ia: bool = False) -> dict:
    """
    Descarga, abre, lee y evalúa un documento del expediente.

    `avisar` recibe el nombre de cada paso, para que la interfaz pueda mostrar
    el progreso sin que este módulo dependa de Streamlit.
    """
    from contenedores import abrir                               # noqa: PLC0415
    from descargar_documento import descargar                    # noqa: PLC0415

    salida = {"ok": False, "paso": "", "motivo": "", "filecode": filecode}

    # --- 1. descargar -------------------------------------------------------
    avisar("Descargando el documento del SEACE")
    salida["paso"] = "descarga"
    try:
        res = descargar(filecode)
    except Exception as e:                                       # noqa: BLE001
        salida["motivo"] = f"No se pudo descargar: {type(e).__name__}: {e}"
        return salida
    if not res["ok"]:
        salida["motivo"] = (f"El servidor no devolvió un documento válido "
                            f"({res['tipo']}, {res['bytes']:,} bytes). "
                            f"El código de archivo puede haber vencido.")
        return salida
    salida["bytes"] = res["bytes"]
    salida["tipo"] = res["tipo"]
    salida["nombre"] = res["nombre"] or nombre_doc

    # --- 2. abrir -----------------------------------------------------------
    avisar(f"Abriendo el contenedor ({res['tipo']}, {res['bytes'] / 1e6:.1f} MB)")
    salida["paso"] = "apertura"
    destino = TMP / filecode[:8]
    abierto = abrir(res["datos"], destino, nombre=res["nombre"])
    if not abierto.ok:
        salida["motivo"] = abierto.mensaje
        return salida
    salida["archivos"] = [d.nombre for d in abierto.documentos]

    doc = abierto.mejor
    if doc is None or doc.tipo != "pdf":
        salida["motivo"] = ("El expediente no trae ningún PDF legible. "
                            f"Contiene: {', '.join(salida['archivos'][:6]) or 'nada'}")
        return salida
    salida["documento"] = doc.nombre
    salida["clase"] = doc.clase

    # --- 3. leer ------------------------------------------------------------
    avisar(f"Leyendo «{doc.nombre[:48]}»")
    salida["paso"] = "lectura"
    try:
        from extractor import localizar                          # noqa: PLC0415
        bloque = localizar(doc.ruta)
    except ImportError as e:
        salida["motivo"] = (f"Falta una librería para leer PDF ({e.name}). "
                            f"Instalá:  pip install pypdf pdfplumber")
        return salida
    except Exception as e:                                       # noqa: BLE001
        salida["motivo"] = f"No se pudo leer el PDF: {type(e).__name__}: {e}"
        return salida

    salida["origen"] = getattr(bloque, "origen", "?")
    salida["paginas"] = list(getattr(bloque, "paginas", []) or [])
    if not getattr(bloque, "texto", ""):
        salida["motivo"] = (
            "No se localizó la sección de especificaciones técnicas dentro del "
            "documento. Suele pasar con escaneos de baja calidad o cuando el "
            "requerimiento está en un archivo aparte que el expediente no incluye.")
        return salida

    # --- 4. extraer ---------------------------------------------------------
    avisar("Extrayendo el requerimiento técnico")
    salida["paso"] = "extracción"
    from dataclasses import asdict                               # noqa: PLC0415
    from extractor import extraer                                # noqa: PLC0415
    specs = extraer(bloque.texto)
    salida["specs"] = {k: v for k, v in asdict(specs).items() if v is not None}
    salida["ia_aporto"] = []
    if usar_ia:
        # La IA solo COMPLETA lo que las reglas no encontraron; nunca pisa un
        # dato de las reglas, y todo lo que aporta debe figurar en el texto.
        avisar("Completando con el modelo local")
        try:
            from extraer_llm import extraer as extraer_ia       # noqa: PLC0415
            ia, _ = extraer_ia(bloque.texto)
            for k, v in asdict(ia).items():
                if v is not None and k not in salida["specs"]:
                    salida["specs"][k] = v
                    salida["ia_aporto"].append(k)
                    setattr(specs, k, v)
        except Exception as e:                                   # noqa: BLE001
            salida["aviso_ia"] = f"La IA local no respondió ({e}); se usaron solo las reglas."
    salida["cobertura"] = specs.cobertura()
    if not salida["specs"]:
        salida["motivo"] = ("Se leyó el documento pero no se reconoció ningún "
                            "parámetro técnico en la sección localizada.")
        return salida

    # --- 5. evaluar ---------------------------------------------------------
    avisar("Comparando contra las fichas BTOUCH y de la competencia")
    salida["paso"] = "evaluación"
    from evaluar_licitacion import evaluar_todas, NO_CUMPLE      # noqa: PLC0415
    resultados = []
    explicables = 0
    for r in evaluar_todas(salida["specs"]):
        c = r.cuenta
        explicacion = ""
        if usar_ia and r.concluyente and explicables < 4 and "aviso_ia" not in salida:
            explicables += 1
            avisar(f"Redactando explicación: {r.ficha.marca} {r.ficha.modelo}")
            try:
                from explicar import explicar as explicar_ia     # noqa: PLC0415
                explicacion = explicar_ia(r)
            except Exception as e:                               # noqa: BLE001
                salida["aviso_ia"] = f"La IA local no respondió ({e})."
        resultados.append({
            "marca": r.ficha.marca, "modelo": r.ficha.modelo,
            "dictamen": r.dictamen, "concluyente": r.concluyente,
            "explicacion": explicacion,
            "verde": c["CUMPLE"], "amarillo": c["OBSERVADO"] + c["REVISIÓN MANUAL"],
            "rojo": c[NO_CUMPLE], "sin_dato": c["SIN DATO"],
            "comparables": r.comparables, "medido": r.medido,
            "detalle": [{"parametro": v.etiqueta, "exigido": v.exigido,
                         "ofrecido": v.ofrecido, "resultado": v.resultado,
                         "nota": v.nota} for v in r.veredictos],
        })
    salida["resultados"] = resultados
    salida["ok"] = True
    salida["paso"] = "listo"
    return salida


# --------------------------------------------------------------------------- #
# Interfaz
# --------------------------------------------------------------------------- #

def _ia_lista() -> bool:
    try:
        from cliente import estado                                # noqa: PLC0415
        e = estado()
        return bool(e["servidor"] and e["modelo"])
    except Exception:                                            # noqa: BLE001
        return False


def _capa1(fila: dict) -> None:
    c = st.columns([2, 1, 1, 1])
    c[0].markdown(f"**{(fila.get('entidad') or '—')[:60]}**")
    c[0].caption(fila.get("nomenclatura") or "")
    c[1].metric("Fecha", (fila.get("fecha") or "—")[:10])
    # Ojo con NaN: `if monto` da verdadero para NaN y la métrica mostraba
    # "S/ nan". 121 de las 436 licitaciones no tienen monto adjudicado.
    monto = fila.get("monto_adjudicado")
    try:
        import math
        vacio = monto is None or (isinstance(monto, float) and math.isnan(monto))
    except Exception:                                            # noqa: BLE001
        vacio = monto is None
    c[2].metric("Monto adjudicado", "—" if vacio else f"S/ {float(monto):,.0f}")
    c[3].metric("Categoría", fila.get("_categoria_prod") or "—")

    g = fila.get("proveedor_ganador")
    if g and str(g).strip() not in ("", "-"):
        st.markdown(f"Ganador: **{g}**")
    if fila.get("enlace"):
        st.markdown(f"[Ver la ficha en SEACE]({fila['enlace']})")
    st.caption(fila.get("objeto", "")[:300])


def _tabla_resultados(resultados: list[dict]) -> None:
    import pandas as pd                                          # noqa: PLC0415

    utiles = [r for r in resultados if r["concluyente"]]
    otros = [r for r in resultados if not r["concluyente"]]

    if not utiles:
        st.warning("Ninguna ficha permite verificar lo suficiente de lo exigido "
                   "como para emitir un dictamen.")
    else:
        df = pd.DataFrame([{
            "Marca": r["marca"], "Modelo": r["modelo"], "Dictamen": r["dictamen"],
            "Cumple": r["verde"], "Observado": r["amarillo"],
            "No cumple": r["rojo"], "Sin dato": r["sin_dato"],
        } for r in sorted(utiles, key=lambda r: (r["rojo"], -r["comparables"]))])
        st.dataframe(df, use_container_width=True, hide_index=True)

    for r in sorted(utiles, key=lambda r: (r["rojo"], -r["comparables"])):
        bloq = [d for d in r["detalle"] if d["resultado"] == "NO CUMPLE"]
        titulo = f"{r['marca']} · {r['modelo']} — {r['dictamen']}"
        with st.expander(titulo, expanded=bool(bloq) and r["marca"] == "BTOUCH"):
            for d in r["detalle"]:
                if d["resultado"] == "CUMPLE":
                    continue
                color = COLORES.get(d["resultado"], "#EDEDED")
                st.markdown(
                    f"<div style='background:{color};padding:6px 10px;"
                    f"border-radius:4px;margin-bottom:4px'>"
                    f"<b>{d['parametro']}</b> — {d['resultado']}<br>"
                    f"<small>exige: {d['exigido'][:70]} · ofrece: {d['ofrecido'][:50]}</small>"
                    + (f"<br><small><i>{d['nota'][:160]}</i></small>" if d["nota"] else "")
                    + "</div>", unsafe_allow_html=True)
            if r.get("explicacion"):
                st.info("🤖 " + r["explicacion"])
            verdes = sum(1 for d in r["detalle"] if d["resultado"] == "CUMPLE")
            st.caption(f"{verdes} parámetro(s) cumplen sin observación.")

    if otros:
        st.caption("Sin medir: " + ", ".join(
            f"{r['marca']} ({r['medido']:.0%} de lo exigido verificable)" for r in otros)
            + ". Una ficha que no publica datos no es competitiva ni incompetitiva: "
              "es desconocida.")


def _pie_manual() -> None:
    from evaluar_licitacion import PENDIENTES_MANUALES           # noqa: PLC0415
    with st.expander("Puntos que las reglas de Brighter piden revisar a mano"):
        for titulo, detalle in PENDIENTES_MANUALES:
            st.markdown(f"**{titulo}** — {detalle}")


def render(fila: dict, db: Path | str) -> None:
    """Panel completo para una licitación."""
    _capa1(fila)
    st.divider()

    ocid = fila.get("ocid") or ""
    if not hay_indice(db):
        st.info("Los documentos del expediente todavía no están indexados. "
                "Corré una vez:  `python src/indexar_documentos.py`")
        return

    docs = documentos_de(db, ocid)
    if not docs:
        st.info(
            "**Este proceso no tiene documentos indexados.**\n\n"
            "La causa más común no es que no publique expediente, sino que el "
            "proceso es más nuevo que el paquete OCDS descargado: el índice solo "
            "ve lo que hay en `data/*.jsonl.gz`, y esos archivos son una foto del "
            "día en que se bajaron.\n\n"
            "Para incorporarlo:\n\n"
            "```\npython src/extract.py          # vuelve a bajar el paquete del año\n"
            "python src/indexar_documentos.py\n```\n\n"
            "Si tras eso sigue sin documentos, el proceso efectivamente no publica "
            "expediente descargable.")
        return

    _seccion_analisis(docs, ocid)


# --------------------------------------------------------------------------- #
# Sección de análisis (la comparten el histórico y los procesos vigentes)
# --------------------------------------------------------------------------- #

CACHE_ANALISIS = RAIZ / "data" / "cache_analisis"


def _ruta_cache(filecode: str) -> Path | None:
    # el fileCode es un UUID; se valida para que nunca arme una ruta fuera de la carpeta
    return CACHE_ANALISIS / f"{filecode}.json" if re.fullmatch(r"[A-Za-z0-9_-]{8,64}", filecode or "") else None


def _leer_cache(filecode: str) -> dict | None:
    """Resultado guardado de un análisis, o None. Una copia a la que le falten campos (de una
    versión anterior o dañada) se ignora en lugar de romper el panel."""
    ruta = _ruta_cache(filecode)
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8")) if ruta and ruta.exists() else None
    except (OSError, ValueError):
        return None
    necesarios = {"ok", "filecode", "specs", "cobertura", "resultados"}
    return datos if isinstance(datos, dict) and datos.get("ok") and necesarios <= datos.keys() else None


def _guardar_cache(resultado: dict) -> None:
    """Solo se guardan los análisis completos: un fallo (red, escaneo ilegible) se reintenta."""
    ruta = _ruta_cache(resultado.get("filecode", ""))
    if not (ruta and resultado.get("ok")):
        return
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(resultado, ensure_ascii=False, default=str), encoding="utf-8")
    except OSError:
        pass


def _seccion_analisis(docs: list[dict], clave_ui: str) -> None:
    etiquetas = [f"[{d['clase']}] {d['titulo'] or d['tipo_doc']} ({d['etapa']})"
                 for d in docs]
    i = st.selectbox("Documento del expediente", range(len(docs)),
                     format_func=lambda i: etiquetas[i], key=f"doc_{clave_ui}")
    elegido = docs[i]

    clave = f"analisis_{elegido['filecode']}"
    ia_lista = _ia_lista()
    usar_ia = st.checkbox(
        "Usar IA local (Ollama) para completar y explicar",
        value=ia_lista, disabled=not ia_lista, key=f"ia_{clave_ui}",
        help="Las reglas dictaminan siempre; la IA completa datos y redacta."
             if ia_lista else "Ollama no responde. Ábrelo y corre src/ia/comprobar_ia.py")
    if st.button("Analizar expediente y comparar con BTOUCH", key=f"btn_{clave_ui}",
                 type="primary"):
        with st.status("Analizando…", expanded=True) as estado:
            def avisar(paso):
                estado.update(label=paso)
                st.write(paso)
            resultado = analizar(elegido["filecode"], elegido["titulo"], avisar, usar_ia)
            estado.update(
                label="Análisis completo" if resultado["ok"] else
                      f"Se detuvo en: {resultado['paso']}",
                state="complete" if resultado["ok"] else "error", expanded=False)
        st.session_state[clave] = resultado
        _guardar_cache(resultado)

    resultado = st.session_state.get(clave)
    if not resultado:
        resultado = _leer_cache(elegido["filecode"])
        if resultado:
            st.caption("Resultado guardado de un análisis anterior de este documento. "
                       "Pulsa el botón para volver a analizarlo.")
    if not resultado:
        st.caption("El análisis descarga el expediente y lo lee. Puede tardar entre "
                   "unos segundos y varios minutos según el tamaño y si hace falta "
                   "reconocimiento óptico. El resultado queda guardado.")
        return

    if not resultado["ok"]:
        st.error(f"**No se pudo completar ({resultado['paso']}).**\n\n{resultado['motivo']}")
        if resultado.get("archivos"):
            st.caption("El expediente contenía: " + ", ".join(resultado["archivos"][:8]))
        return

    origen = resultado.get("origen", "?")
    st.success(
        f"Leído **{resultado.get('documento', '')}** "
        f"({'texto nativo' if origen == 'nativo' else 'reconocimiento óptico'}"
        + (f", páginas {resultado['paginas']}" if resultado.get("paginas") else "")
        + f"). Se reconocieron {len(resultado['specs'])} parámetros "
          f"({resultado['cobertura']:.0%} de cobertura).")

    with st.expander("Requerimiento extraído"):
        for k, v in resultado["specs"].items():
            st.markdown(f"- **{k}**: {str(v)[:120]}")

    if resultado.get("ia_aporto"):
        st.caption("La IA completó: " + ", ".join(resultado["ia_aporto"]))
    if resultado.get("aviso_ia"):
        st.warning(resultado["aviso_ia"])
    _tabla_resultados(resultado["resultados"])
    _pie_manual()


# --------------------------------------------------------------------------- #
# Procesos VIGENTES: la ficha se consulta al elegir el proceso (sin índice ni paquetes anuales)
# --------------------------------------------------------------------------- #

def documentos_de_ficha(ficha: dict) -> list[dict]:
    """Documentos de la ficha del SEACE, del más al menos útil para comparar contra BTOUCH."""
    from contenedores import clasificar                          # noqa: PLC0415
    import ficha_seace                                           # noqa: PLC0415

    docs = ficha_seace.documentos(ficha)
    for f in docs:
        clase, _, _ = clasificar(f"{f['titulo']} {f['tipo_doc']}")
        f["clase"] = clase
        f["prioridad"] = PRIORIDAD_PANEL.get(clase, 20)
    return sorted(docs, key=lambda f: -f["prioridad"])


def _capa1_vigente(fila: dict) -> None:
    import pandas as pd                                          # noqa: PLC0415

    c = st.columns([2, 1, 1, 1])
    c[0].markdown(f"**{(fila.get('entidad') or '—')[:70]}**")
    c[0].caption(fila.get("nomenclatura") or "")
    c[1].metric("Cierra inscripción", str(fila.get("fecha_fin_inscripcion") or "—")[:10])
    c[2].metric("Presentación", str(fila.get("fecha_presentacion") or "—")[:10])
    vr = fila.get("valor_referencial")
    c[3].metric("Valor referencial", "—" if vr is None or pd.isna(vr) else f"S/ {float(vr):,.0f}")
    if fila.get("enlace"):
        st.markdown(f"[Ver la ficha en SEACE]({fila['enlace']})")
    st.caption(str(fila.get("descripcion") or fila.get("objeto") or "")[:300])


def render_vigente(fila: dict) -> None:
    """Panel de un proceso de la lista de vigentes. Al mostrarlo solo se consulta su ficha
    (unos KB); el documento se descarga únicamente cuando se pulsa «Analizar»."""
    import pandas as pd                                          # noqa: PLC0415
    import ficha_seace as fs                                     # noqa: PLC0415

    _capa1_vigente(fila)
    st.divider()

    try:
        idp = int(fila.get("id"))
    except (TypeError, ValueError):
        st.error("Este proceso no tiene un identificador válido en la lista.")
        return

    forzar = st.button("↻ Refrescar ficha", key=f"fic_{idp}",
                       help="La ficha se guarda 24 horas. Refréscala si esperas documentos nuevos.")
    try:
        with st.spinner("Consultando la ficha de este proceso en el SEACE…"):
            ficha = fs.obtener_ficha(idp, forzar=forzar)
    except fs.FichaError as e:
        st.error(str(e))
        st.caption("Puedes abrir la ficha a mano con el enlace de arriba.")
        return
    if ficha.get("_desactualizada"):
        st.warning("No hay conexión con el SEACE: se muestra la última copia guardada de la ficha.")

    its = fs.items(ficha)
    if its:
        with st.expander(f"Qué se compra ({len(its)} ítem{'s' if len(its) != 1 else ''})"):
            st.dataframe(pd.DataFrame(its).rename(columns={
                "nro": "N.º", "descripcion": "Descripción", "producto": "Producto (catálogo)",
                "cantidad": "Cantidad", "unidad": "Unidad", "departamento": "Departamento"}),
                use_container_width=True, hide_index=True)
    crono = fs.cronograma(ficha)
    if crono:
        with st.expander("Cronograma del proceso"):
            st.dataframe(pd.DataFrame(crono).rename(columns={
                "etapa": "Etapa", "inicio": "Desde", "fin": "Hasta"}),
                use_container_width=True, hide_index=True)

    docs = documentos_de_ficha(ficha)
    if not docs:
        st.info("Este proceso todavía no publica documentos descargables. Las bases aparecen en la "
                "etapa de convocatoria; vuelve a revisar más tarde.")
        return
    st.caption(f"{len(docs)} documento(s) publicado(s). Solo se descarga el que analices.")
    _seccion_analisis(docs, f"v{idp}")

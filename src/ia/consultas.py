"""Preguntas en español sobre tus datos, respondidas con SQL generado por el modelo local.

Seguridad: la base se abre en solo lectura, un autorizador de SQLite bloquea
todo lo que no sea SELECT, y el resultado se limita en filas. El modelo nunca
escribe en tus datos.

"Apartado aprendido": cada consulta que confirmas como correcta se guarda en
data/consultas_aprendidas.jsonl y se usa como ejemplo en preguntas futuras
parecidas. No reentrena el modelo; le muestra tus propios aciertos.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import unicodedata
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cliente import RAIZ, chat  # noqa: E402
import conocimiento  # noqa: E402
import procesos  # noqa: E402

DB_LIC = RAIZ / "data" / "licitaciones.db"
DB_AN = RAIZ / "data" / "analisis.db"
APRENDIDAS = RAIZ / "data" / "consultas_aprendidas.jsonl"
SEMILLA = RAIZ / "docs" / "consultas_semilla.jsonl"
MAX_FILAS = 200


# ------------------------------------------------------------------ conexión
def conectar() -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{DB_LIC}?mode=ro", uri=True)
    if DB_AN.exists():
        con.execute(f"ATTACH DATABASE 'file:{DB_AN.as_posix()}?mode=ro' AS an")
        for (t,) in con.execute("select name from an.sqlite_master where type='table'").fetchall():
            if not con.execute("select 1 from main.sqlite_master where name=?", (t,)).fetchone():
                con.execute(f'CREATE TEMP VIEW "{t}" AS SELECT * FROM an."{t}"')
    permitidos = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION,
                  getattr(sqlite3, 'SQLITE_RECURSIVE', 33)}

    def autorizador(accion, *_):
        return sqlite3.SQLITE_OK if accion in permitidos else sqlite3.SQLITE_DENY
    con.set_authorizer(autorizador)
    return con


def esquema(con: sqlite3.Connection) -> str:
    """Tablas, columnas y valores típicos de las columnas de pocas categorías."""
    # El autorizador bloquea PRAGMA; se lee sqlite_master con SELECT.
    partes = []
    objetos = con.execute(
        "select name, sql from sqlite_master where type in ('table','view') "
        "and name not like 'sqlite_%' union all "
        "select name, sql from temp.sqlite_master where type='view'").fetchall()
    for nombre, ddl in objetos:
        try:
            n = con.execute(f'select count(*) from "{nombre}"').fetchone()[0]
            cols_nombres = [d[0] for d in con.execute(f'select * from "{nombre}" limit 0').description]
        except sqlite3.Error:
            continue
        lineas = [f"TABLA {nombre} ({n} filas): " + ", ".join(cols_nombres)]
        for c in cols_nombres:
            if c in ("categoria", "estado", "tipo_proceso", "anio", "departamento", "gano", "tipo"):
                try:
                    vals = [str(v[0]) for v in con.execute(
                        f'select distinct "{c}" from "{nombre}" where "{c}" is not null limit 14')]
                    if len(vals) < 14:
                        lineas.append(f"   {c} toma valores: {', '.join(vals)}")
                except sqlite3.Error:
                    pass
        partes.append("\n".join(lineas))
    return "\n".join(partes)


# --------------------------------------------------------------- aprendizaje
def _tokens(s: str) -> set[str]:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return {t for t in re.findall(r"[a-z0-9]{3,}", s)}


def _leer(ruta: Path) -> list[dict]:
    if not ruta.exists():
        return []
    out = []
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(linea))
        except json.JSONDecodeError:
            pass
    return out


def ejemplos_para(pregunta: str, n: int = 3) -> list[dict]:
    todos = _leer(SEMILLA) + _leer(APRENDIDAS)
    q = _tokens(pregunta)

    def sim(e):
        t = _tokens(e["pregunta"])
        return len(q & t) / (len(q | t) or 1)
    # los aprendidos pesan un poco más que las semillas ante empate
    todos.sort(key=lambda e: (sim(e), e.get("origen") == "aprendida"), reverse=True)
    return [e for e in todos[:n] if sim(e) > 0]


def aprender(pregunta: str, sql: str) -> bool:
    """Guarda una consulta confirmada. Devuelve False si ya estaba."""
    if any(e["pregunta"].strip().lower() == pregunta.strip().lower() and e["sql"] == sql
           for e in _leer(APRENDIDAS)):
        return False
    APRENDIDAS.parent.mkdir(parents=True, exist_ok=True)
    with APRENDIDAS.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"pregunta": pregunta, "sql": sql, "origen": "aprendida"},
                           ensure_ascii=False) + "\n")
    return True


# ------------------------------------------------------------------ consulta
SISTEMA = """Eres analista de datos de una empresa peruana que vende paneles interactivos. \
Conviertes preguntas en español en UNA consulta SQLite de solo lectura.
Responde SOLO JSON: {{"sql": "...", "nota": "una frase sobre cómo interpretaste la pregunta"}}.
Reglas: usa únicamente las tablas y columnas listadas; una sola sentencia SELECT; \
compara texto con UPPER(...) LIKE '%...%'; fechas como texto 'YYYY-MM-DD'; \
si la pregunta no se puede responder con estas tablas, devuelve {{"sql": "", "nota": "motivo"}}.

HOY: {hoy}

GUÍA DE TABLAS (elige la correcta según la pregunta):
- vigentes = procesos ABIERTOS ahora, a los que todavía se puede postular (SEACE). Columnas: id, nomenclatura, \
entidad, objeto, tipo_proceso, descripcion, valor_referencial, moneda, fecha_convocatoria, fecha_fin_inscripcion, \
fecha_presentacion, ubigeo, enlace. NO tiene ocid: un proceso se identifica por nomenclatura. Sus fechas son texto \
'DD/MM/YYYY HH:MM:SS'; para comparar con fechas conviértelas: \
substr(fecha_fin_inscripcion,7,4)||'-'||substr(fecha_fin_inscripcion,4,2)||'-'||substr(fecha_fin_inscripcion,1,2). \
"Disponible para postular" = esa fecha convertida >= HOY. El texto del objeto está en la columna descripcion.
- licitaciones = HISTÓRICO de procesos ya convocados/adjudicados (tiene ocid, estado, proveedor_ganador). \
No sirve para saber qué está abierto hoy.
- perucompras = órdenes de compra por Acuerdo Marco; petroperu y bnacion = avisos de esas dos entidades.
- postores/documentos (si existen) = historial de empresas que se presentaron.
- Para "pantallas interactivas" busca en descripcion/objeto varias palabras con OR: \
UPPER(descripcion) LIKE '%PANTALLA%' OR LIKE '%INTERACTIV%' OR LIKE '%PIZARRA%'.

ESQUEMA:
{esquema}
{ejemplos}"""


def _limpiar(sql: str) -> str:
    sql = sql.strip().rstrip(";").strip()
    if not re.match(r"(?is)^(select|with)\b", sql) or ";" in sql:
        raise ValueError("solo se permite una consulta SELECT")
    return sql


def _ejecutar(con, sql: str):
    sql = _limpiar(sql)
    cur = con.execute(f"SELECT * FROM ({sql}) LIMIT {MAX_FILAS}")
    cols = [d[0] for d in cur.description]
    return sql, cols, cur.fetchall()


# ------------------------------------------- competidores de un proceso concreto
_PIDE_RIVALES = re.compile(r"competidor|rival|postor|se present|quien(es)? (va|van|podr)|participar", re.I)


def _proceso_citado(con, pregunta: str):
    """(nomenclatura, entidad, descripcion, fecha_presentacion) del proceso vigente citado, o None."""
    return procesos.proceso_citado(con, pregunta)


def _rivales_de_proceso(con, pregunta: str):
    """Pregunta tipo «¿qué competidores se presentarán en <nomenclatura>?». No usa el
    modelo para escribir SQL (inventaba columnas): usa el predictor si hay historial y,
    si no, el histórico de ganadores de esa entidad. Devuelve None si no aplica."""
    if not _PIDE_RIVALES.search(pregunta):
        return None
    proc = _proceso_citado(con, pregunta)
    if not proc:
        return None
    nomen, entidad, desc, f_pres = proc
    cab = f"{nomen} · {entidad} · {str(desc)[:80]}"
    if DB_AN.exists():
        try:
            sys.path.insert(0, str(RAIZ / "src" / "ml"))
            import historial, predictor
            import pandas as pd
            h = historial.Historial(historial.cargar(DB_AN))
            if h.n_procesos >= 15:
                m = predictor.entrenar(h)
                out = predictor.predecir(m, h, pd.Timestamp.today().normalize(), entidad, "", [], top=10)
                out = out.assign(prob=(out["prob"] * 100).round(1))
                return {"ok": True, "origen": procesos.ORIGEN, "sql": "(estimación del predictor, no es SQL)",
                        "nota": "Modelo entrenado con el historial de postores.",
                        "columnas": list(out.columns), "filas": out.values.tolist(),
                        "resumen": f"Competidores probables para {cab}. Son probabilidades estimadas "
                                   "con el historial; sirven para priorizar, no son una certeza.",
                        "truncado": False}
        except Exception:   # sin sklearn o historial roto: cae al histórico
            pass
    sql = ("SELECT proveedor_ganador AS empresa, COUNT(*) AS veces_ganadora, "
           "MAX(fecha) AS ultima_vez FROM licitaciones "
           "WHERE entidad = ? AND proveedor_ganador IS NOT NULL AND proveedor_ganador <> '' "
           "GROUP BY proveedor_ganador ORDER BY veces_ganadora DESC LIMIT 10")
    filas = con.execute(sql, (entidad,)).fetchall()
    tipo = "ganadores previos de esa misma entidad"
    if not filas:
        sql = ("SELECT proveedor_ganador AS empresa, COUNT(*) AS veces_ganadora, MAX(fecha) AS ultima_vez "
               "FROM licitaciones WHERE proveedor_ganador IS NOT NULL AND proveedor_ganador <> '' "
               "GROUP BY proveedor_ganador ORDER BY veces_ganadora DESC LIMIT 10")
        filas = con.execute(sql).fetchall()
        tipo = "empresas que más han ganado procesos de este rubro (esa entidad no tiene histórico)"
    return {"ok": True, "origen": procesos.ORIGEN, "sql": sql,
            "nota": "Falta data/analisis.db, por eso no hay probabilidades por empresa.",
            "columnas": ["empresa", "veces_ganadora", "ultima_vez"], "filas": filas,
            "resumen": f"{cab}. Sin historial de postores no puedo estimar quién se presentará; "
                       f"te muestro {tipo}. Para probabilidades reales copia data/analisis.db.",
            "truncado": False}


def preguntar(pregunta: str, con: sqlite3.Connection | None = None, cfg: dict | None = None) -> dict:
    propia = con is None
    con = con or conectar()
    try:
        # un proceso citado por su nomenclatura («¿cuántos días quedan en LP-SM-14-2026-MDCC-1?»): se
        # contesta con una cuenta de calendario sobre `vigentes`, sin que el modelo escriba SQL.
        directo = procesos.responder(con, pregunta, db=DB_LIC)
        if directo:
            return directo
        directo = _rivales_de_proceso(con, pregunta)
        if directo:
            return directo
        # «¿qué es X?», «¿quién ofrece tal marca?», ranking general: no son preguntas de datos,
        # se responden desde la base de conocimiento (sin SQL inventado por el modelo).
        saber = conocimiento.responder(con, pregunta, cfg)
        if saber:
            return saber
        ej = ejemplos_para(pregunta)
        bloque = ""
        if ej:
            bloque = "\nEJEMPLOS YA VERIFICADOS:\n" + "\n".join(
                f"P: {e['pregunta']}\nSQL: {e['sql']}" for e in ej)
        sistema = SISTEMA.format(hoy=date.today().isoformat(), esquema=esquema(con), ejemplos=bloque)
        usuario, error = f"Pregunta: {pregunta}", None
        for intento in range(2):                      # un reintento mostrando el error
            r = chat(sistema, usuario if not error else
                     f"{usuario}\nTu SQL anterior falló: {error}. Corrígelo.", json_modo=True, cfg=cfg)
            sql = (r.get("sql") or "").strip()
            if not sql:
                return {"ok": False, "motivo": r.get("nota", "no se pudo responder con estos datos")}
            try:
                sql, cols, filas = _ejecutar(con, sql)
                break
            except (sqlite3.Error, ValueError) as e:
                error = str(e)
        else:
            return {"ok": False, "sql": sql,
                    "motivo": "No logré armar una consulta válida con estos datos "
                              f"({error}). Prueba reformulando la pregunta, o citando la nomenclatura "
                              "completa del proceso, por ejemplo LP-SM-14-2026-MDCC-1."}
        resumen = ""
        if filas:
            tabla = "\n".join(" | ".join(str(x) for x in f) for f in filas[:30])
            resumen = chat(
                "Resume en español, en 1 a 3 frases, el resultado de una consulta. "
                "Usa SOLO las cifras de la tabla; no agregues causas ni datos externos. "
                "Si la tabla se cortó, dilo.",
                f"Pregunta: {pregunta}\nColumnas: {' | '.join(cols)}\n{tabla}", cfg=cfg).strip()
        return {"ok": True, "sql": sql, "nota": r.get("nota", ""), "columnas": cols,
                "filas": filas, "resumen": resumen or "La consulta no devolvió filas.",
                "truncado": len(filas) >= MAX_FILAS}
    finally:
        if propia:
            con.close()

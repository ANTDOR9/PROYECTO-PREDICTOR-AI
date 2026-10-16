"""Preguntas sobre UN proceso concreto («¿cuántos días quedan en CONV-PROC-23-2026-UNSA.-1?»).

Es una cuenta de calendario sobre la tabla `vigentes`, no una tarea para el modelo: un modelo
chico escribía SQL con columnas que no existen (`ocid` es del histórico, no de `vigentes`) y
las fechas del SEACE vienen como texto «DD/MM/AAAA HH:MM:SS». Aquí se busca el proceso por su
nomenclatura, se calcula con la fecha de hoy y se contesta con los datos de la ficha. La IA no
interviene, así que la respuesta es la misma siempre y no puede inventar un plazo.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from pathlib import Path

import conocimiento

ORIGEN = "proceso"
FORMATO = "%d/%m/%Y %H:%M:%S"
SEMANA = 7                                    # una lista de vigentes más vieja que esto se avisa

# lo que se pregunta de un proceso (se compara sobre el texto sin tildes ni mayúsculas)
_PLAZO = re.compile(
    r"\b(cuantos?|cuanto)\s+(dias|tiempo|horas)\b|\bdias?\s+(quedan|faltan|restan|para)\b"
    r"|\bcuando\s+(cierra|vence|termina|se\s+cierra|es\s+el\s+cierre)\b|\bhasta\s+cuando\b"
    r"|\bfecha\s+(limite|de\s+cierre|de\s+presentacion|fin|de\s+inscripcion)\b|\bplazo\b"
    r"|\bcuando\b|\bfecha\b|\bvenc\w*|\bcierr\w*|\bquedan?\b|\bfaltan?\b|\bpostul\w*|\binscrib\w*|\binscripcion\b"
    r"|\bpresentarse\b|\bpresentar\s+(la\s+|una\s+)?(oferta|propuesta|cotizacion)\b|\bcronograma\b")
_INFO = re.compile(
    r"\bde\s+que\s+(trata|se\s+trata)\b|\bque\s+(se\s+)?(compra|adquiere|piden|pide|solicita|requiere)\b"
    r"|\bvalor\s+referencial\b|\bmonto\b|\bcuanto\s+(cuesta|vale|es\s+el\s+valor)\b|\bentidad\b"
    r"|\bquien\s+(convoca|compra)\b|\bobjeto\b|\bdescripcion\b|\binformacion\b|\bdatos\b|\bdetalles?\b"
    r"|\bresumen\b|\bficha\b")
_OFERTA = re.compile(r"\b(propuestas?|ofertas?|cotizacion|cotizar)\b")
_QUIERE_RIVALES = re.compile(r"competidor|rival|postor|se present(o|a|e|aron|ara|ar[ae]n)|quien(es)? (va|van|podr)")
#: algo con forma de nomenclatura SEACE: letras-números-año-siglas (al menos tres bloques con guion)
_CODIGO = re.compile(r"[A-Za-z]{1,8}(?:-[A-Za-z0-9./]+){2,}")


def _compacto(s) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


def _fecha(txt) -> datetime | None:
    try:
        return datetime.strptime(str(txt).strip(), FORMATO)
    except (ValueError, TypeError):
        return None


# ------------------------------------------------------------------------ búsqueda
def _filas(con, tabla: str, cols: str):
    try:
        return con.execute(f"select {cols} from {tabla} where nomenclatura is not null").fetchall()
    except sqlite3.Error:
        return []


def _buscar(candidatas: list[tuple], pregunta: str):
    """La candidata cuya nomenclatura aparece en la pregunta (ignorando espacios, guiones y
    mayúsculas, así «lp sm 14 2026 mdcc 1» también sirve). Gana la más larga. Si la pregunta
    trae el código incompleto («LP-SM-14-2026-MDCC»), se acepta solo si es un único proceso."""
    q = _compacto(pregunta)
    exactas = [c for c in candidatas if len(_compacto(c[0])) >= 8 and _compacto(c[0]) in q]
    if exactas:
        return max(exactas, key=lambda c: len(_compacto(c[0])))
    for cod in _CODIGO.findall(pregunta):
        k = _compacto(cod)
        if len(k) < 8:
            continue
        parecidas = [c for c in candidatas if _compacto(c[0]).startswith(k)]
        if len(parecidas) == 1:
            return parecidas[0]
    return None


def _vigente(con, pregunta: str) -> dict | None:
    try:
        cur = con.execute("select * from vigentes where nomenclatura is not null")
    except sqlite3.Error:
        return None
    cols = [d[0] for d in cur.description]
    filas = cur.fetchall()
    i = cols.index("nomenclatura")
    hallada = _buscar([(f[i], *f) for f in filas], pregunta)     # (nomenclatura, *fila completa)
    return dict(zip(cols, hallada[1:])) if hallada else None


def proceso_citado(con, pregunta: str):
    """(nomenclatura, entidad, descripcion, fecha_presentacion) del proceso vigente citado, o None.
    Es lo que usa el estimador de competidores."""
    f = _vigente(con, pregunta)
    return (f["nomenclatura"], f["entidad"], f["descripcion"], f["fecha_presentacion"]) if f else None


# ------------------------------------------------------------------------ calendario
def faltante(fin: datetime | None, ahora: datetime) -> str:
    """«faltan 3 días», «hoy, faltan 4 h 38 min», «mañana», «ya venció hace 2 días»…"""
    if fin is None:
        return "sin fecha publicada"
    seg = (fin - ahora).total_seconds()
    dias = (fin.date() - ahora.date()).days
    if seg < 0:
        return "ya venció hoy" if dias == 0 else f"ya venció hace {-dias} día{'s' if dias != -1 else ''}"
    if dias == 0:
        return f"hoy, faltan {int(seg // 3600)} h {int(seg % 3600 // 60):02d} min"
    return "mañana" if dias == 1 else f"faltan {dias} días"


def con_fecha(fin: datetime | None, ahora: datetime) -> str:
    """«16/10/2026 17:30 (hoy, faltan 4 h 38 min)»."""
    return "sin fecha publicada" if fin is None else f"{fin:%d/%m/%Y %H:%M} ({faltante(fin, ahora)})"


def _dias(fin: datetime | None, ahora: datetime):
    return None if fin is None else (fin.date() - ahora.date()).days


def _dinero(f: dict) -> str | None:
    v = f.get("valor_referencial")
    if v in (None, ""):
        return None
    try:
        return f"{float(v):,.0f} ({f.get('moneda') or 'soles'})"
    except (TypeError, ValueError):
        return None


def _actualizacion(ruta: Path | None) -> datetime | None:
    try:
        return datetime.fromtimestamp(ruta.stat().st_mtime) if ruta else None
    except OSError:
        return None


# ------------------------------------------------------------------------ respuesta
def responder(con: sqlite3.Connection, pregunta: str, ahora: datetime | None = None,
              actualizado: datetime | None = None, db: Path | None = None):
    """Respuesta (mismo formato que consultas.preguntar) o None si la pregunta no es de este tipo."""
    q = conocimiento.norm(pregunta)
    plazo, info = bool(_PLAZO.search(q)), bool(_INFO.search(q))
    if not (plazo or info):
        return None
    if _QUIERE_RIVALES.search(q) and not plazo:
        return None                                  # «quién se presentará en X»: lo contesta el predictor
    ahora = ahora or datetime.now()
    f = _vigente(con, pregunta)
    if not f:
        return _no_vigente(con, pregunta)

    cierre, propuestas = _fecha(f.get("fecha_fin_inscripcion")), _fecha(f.get("fecha_presentacion"))
    nomen, entidad = f["nomenclatura"], f.get("entidad") or "entidad no indicada"
    if plazo:
        partes = [f"Cierre de inscripción: {con_fecha(cierre, ahora)}",
                  f"Presentación de propuestas: {con_fecha(propuestas, ahora)}"]
        if _OFERTA.search(q):
            partes.reverse()                             # preguntó por las propuestas: primero lo suyo
        resumen = f"{nomen} ({entidad}). " + ". ".join(partes) + "."
    else:
        resumen = (f"{nomen} es un proceso de {entidad}: {str(f.get('descripcion') or 'sin descripción').strip()}. "
                   + (f"Valor referencial: {_dinero(f)}. " if _dinero(f) else "")
                   + f"Cierre de inscripción: {con_fecha(cierre, ahora)}.")

    filas = [("Proceso", nomen), ("Entidad", entidad),
             ("Qué se compra", str(f.get("descripcion") or "—").strip()),
             ("Tipo de proceso", f.get("tipo_proceso") or "—")]
    if _dinero(f):
        filas.append(("Valor referencial", _dinero(f)))
    filas += [("Cierre de inscripción", f.get("fecha_fin_inscripcion") or "—"),
              ("Días para inscribirse", "—" if cierre is None else str(_dias(cierre, ahora))),
              ("Presentación de propuestas", f.get("fecha_presentacion") or "—"),
              ("Días para las propuestas", "—" if propuestas is None else str(_dias(propuestas, ahora))),
              ("Ficha en el SEACE", f.get("enlace") or "—")]

    actualizado = actualizado or _actualizacion(db)
    nota = f"Calculado con la fecha de hoy ({ahora:%d/%m/%Y %H:%M})."
    if actualizado:
        nota += f" Lista de vigentes actualizada el {actualizado:%d/%m/%Y %H:%M}."
        if (ahora - actualizado).days >= SEMANA:
            nota += " Tiene más de una semana: actualízala con «iniciar.bat vigentes» antes de decidir."
    sql = "SELECT * FROM vigentes WHERE nomenclatura = '" + str(nomen).replace("'", "''") + "'"
    return {"ok": True, "origen": ORIGEN, "sql": sql, "nota": nota, "columnas": ["campo", "valor"],
            "filas": filas, "resumen": resumen, "truncado": False}


def _no_vigente(con, pregunta: str):
    """Citó algo con forma de nomenclatura que no está entre los vigentes."""
    if not _CODIGO.search(pregunta):
        return None
    hist = _buscar(_filas(con, "licitaciones", "nomenclatura, entidad, estado, fecha"), pregunta)
    if hist:
        nomen, entidad, estado, fecha = hist
        return {"ok": True, "origen": ORIGEN, "sql": "(búsqueda en el histórico)", "nota": "",
                "columnas": ["campo", "valor"],
                "filas": [("Proceso", nomen), ("Entidad", entidad), ("Fecha", fecha or "—"),
                          ("Estado", estado or "—")],
                "resumen": f"{nomen} ya no está entre los procesos vigentes: figura en el histórico "
                           f"({entidad}, {fecha or 'sin fecha'}), así que ya no se puede postular.",
                "truncado": False}
    cod = _CODIGO.search(pregunta).group(0)
    return {"ok": False, "origen": ORIGEN,
            "motivo": f"No encuentro «{cod}» entre los procesos vigentes ni en el histórico. Revisa que la "
                      "nomenclatura esté completa (por ejemplo LP-SM-14-2026-MDCC-1). Si es un proceso "
                      "reciente, actualiza la lista con «iniciar.bat vigentes»."}

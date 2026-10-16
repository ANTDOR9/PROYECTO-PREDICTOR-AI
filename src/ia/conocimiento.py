"""Preguntas de conocimiento («¿qué es Brighter?», «¿quién es STANDAR?», «¿quién ofrece
TRIUMPH BOARD?», «¿cuáles son los principales competidores?»).

No son preguntas de datos y un modelo pequeño no debe responderlas con SQL inventado.
Aquí el código busca la entidad por nombre en la base de conocimiento (glosario,
marcas, empresas) y arma los hechos. El modelo, si responde, solo redacta esos hechos,
y su texto se descarta si trae una cifra que no estaba en ellos.

Regla del proyecto, igual que en el resto de la capa de IA: el modelo no decide ni
aporta datos; lee y redacta.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cliente import RAIZ, IAError, chat  # noqa: E402

GLOSARIO = RAIZ / "docs" / "conocimiento" / "glosario.jsonl"
ORIGEN = "conocimiento"
SQL_NA = "(búsqueda en la base de conocimiento, no es SQL)"

# --------------------------------------------------------------------- texto
SUFIJOS = {"s", "a", "c", "sac", "sa", "srl", "eirl", "scrl", "ei", "e", "i", "r", "l", "ltda", "sociedad",
           "anonima", "cerrada", "limitada", "responsabilidad", "individual", "civil", "comercial",
           "de", "del", "la", "el", "los", "las", "y"}
GENERICAS = {"soluciones", "servicios", "sistemas", "tecnologia", "tecnologias", "inversiones", "grupo",
             "corporacion", "importaciones", "multiples", "generales", "industrias", "industria",
             "electronica", "computo", "informatica", "peru", "consorcio", "empresa", "negocios",
             "contratistas", "ingenieros", "representaciones", "distribuciones", "comercializadora"}


def norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def tokens(s) -> list[str]:
    return re.findall(r"[a-z0-9]+", norm(s))


_INTENCION = re.compile(
    r"\b(que|quien|quienes)\s+(es|son|era|fue|significa|significan)\b"
    r"|\bque\s+(quiere decir|hace|vende|ofrece|ofrecen|venden)\b"
    r"|\bquien(es)?\s+(ofrece|ofrecen|vende|venden|distribuye|distribuyen|importa|importan|trae|traen)\b"
    r"|\b(define|definicion|definir|explica|explicame|cuentame|hablame|describe|describeme)\b"
    r"|\binformacion\s+(de|del|sobre|acerca)\b|\bperfil\s+(de|del)\b|\ba que se dedica\b"
    r"|\bde que (trata|se trata)\b|\bsignificado\b")

#: palabras que pueden acompañar al nombre sin cambiar la pregunta («la empresa STANDAR»)
RELLENO = {"un", "una", "unos", "unas", "empresa", "marca", "termino", "sobre", "acerca", "con", "por",
           "para", "en", "mi", "su", "que", "es", "son"}

#: «ficha técnica / especificaciones / modelos de <empresa>»: la base no guarda productos de los postores
_PIDE_FICHA = re.compile(r"\b(fichas?\s+tecnicas?|especificaciones?(\s+tecnicas?)?|caracteristicas|datasheet|"
                         r"que\s+modelos?|cual(es)?\s+(es\s+)?(el|los|su|sus)\s+modelos?)\b")

_PIDE_RANKING = re.compile(
    r"(principales|mejores|mas\s+(probables|fuertes|activos|importantes|fuerte|activo))\s+(competidor|rival|empresa|postor)"
    r"|competidores?\s+(mas|principales|probables|importantes|fuertes)"
    r"|ranking\s+de\s+(competidor|empresa|postor)"
    r"|quienes\s+son\s+(los|mis|nuestros)\s+(competidor|rival)"
    r"|\btop\s*\d*\s+(de\s+)?(competidor|empresa)")


def _glosario() -> list[dict]:
    if not GLOSARIO.exists():
        return []
    out = []
    for linea in GLOSARIO.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if e.get("termino") and e.get("definicion"):
            out.append(e)
    return out


def _tabla(con, nombre: str) -> bool:
    try:
        con.execute(f'select 1 from "{nombre}" limit 1')
        return True
    except sqlite3.Error:
        return False


# ------------------------------------------------------------------ búsqueda
def _puntuar(nombre: str, q: set[str]):
    """(cobertura, tokens_acertados) o None. Las palabras de forma jurídica (S.A.C., E.I.R.L.)
    no cuentan; las genéricas (SOLUCIONES, SERVICIOS) cuentan poco: no bastan para acertar."""
    toks = [t for t in tokens(nombre) if t not in SUFIJOS]
    if not toks:
        return None
    sig = [t for t in toks if t not in GENERICAS]
    if sig:
        ac = [t for t in sig if t in q]
        if not ac or len(ac) / len(sig) < 0.6:
            return None
        if not (any(len(t) >= 3 for t in ac) or len(ac) >= 2):
            return None
        return len(ac) / len(sig), len(ac)
    ac = [t for t in toks if t in q]           # solo palabras genéricas: debe estar todo
    return (1.0, len(ac)) if len(toks) >= 2 and len(ac) == len(toks) else None


def _alias_marca(marca: str) -> list[str]:
    base = re.sub(r"\(.*?\)", "", marca).strip()
    out = [marca, base]
    for p in re.findall(r"\((.*?)\)", marca):
        if len(tokens(p)) == 1:
            out.append(p)
    return [x for x in out if x]


def _buscar(con, pregunta: str):
    """Mejor coincidencia: (tipo, clave, nombre_mostrado, otras) o None."""
    q = set(tokens(pregunta))
    cand = []   # (cobertura, n, prioridad, tipo, clave, nombre)
    for e in _glosario():
        for nombre in [e["termino"], *e.get("alias", [])]:
            p = _puntuar(nombre, q)
            if p:
                cand.append((*p, 3, "glosario", e["termino"], e["termino"]))
    if _tabla(con, "marcas"):
        for (m,) in con.execute("select marca from marcas where marca not like 'Sin %'"):
            for nombre in _alias_marca(m):
                p = _puntuar(nombre, q)
                if p:
                    cand.append((*p, 2, "marca", m, m))
    for ruc in re.findall(r"\b\d{11}\b", pregunta):
        for t in ("ranking_empresas", "perfiles_empresas"):
            if _tabla(con, t):
                f = con.execute(f"select ruc, empresa from {t} where ruc = ?", (ruc,)).fetchone()
                if f:
                    cand.append((1.0, 99, 4, "empresa", f[0], f[1]))
                    break
    if _tabla(con, "ranking_empresas"):
        for ruc, emp in con.execute("select ruc, empresa from ranking_empresas"):
            p = _puntuar(emp, q)
            if p:
                cand.append((*p, 1, "empresa", ruc, emp))
    if not cand:
        return None
    cand.sort(key=lambda c: (c[0], c[1], c[2]), reverse=True)
    mejor = cand[0]
    otras = []
    for c in cand[1:]:
        if c[4] != mejor[4] and c[5] not in otras and len(otras) < 3 and c[0] == mejor[0] and c[1] == mejor[1]:
            otras.append(c[5])
    return mejor[3], mejor[4], mejor[5], otras


# --------------------------------------------------------------------- hechos
def _fila(con, sql: str, args=()) -> dict | None:
    try:
        cur = con.execute(sql, args)
    except sqlite3.Error:
        return None
    f = cur.fetchone()
    return dict(zip([d[0] for d in cur.description], f)) if f else None


def _limpio(v) -> str | None:
    if v is None:
        return None
    v = str(v).strip()
    return None if v in ("", "nan", "None") else v


def _hechos_empresa(con, ruc: str) -> tuple[list[tuple[str, str]], str]:
    r = _fila(con, "select * from ranking_empresas where ruc = ?", (ruc,)) or {}
    p = _fila(con, "select * from perfiles_empresas where ruc = ?", (ruc,)) or {}
    i = _fila(con, "select * from indicadores_empresas where ruc = ?", (ruc,)) or {}
    nombre = _limpio(r.get("empresa")) or _limpio(p.get("empresa")) or ruc
    h: list[tuple[str, str]] = [("Empresa", nombre), ("RUC", ruc)]
    if r:
        part, adj = r.get("participaciones"), r.get("adjudicadas")
        if part is not None:
            h.append(("Participaciones (2023-2026)", f"{int(part)}"))
        if adj is not None and part:
            h.append(("Adjudicadas", f"{int(adj)} ({adj / part:.0%})"))
        for k, et in (("puntaje", "Puntaje en el ranking"), ("anios_activos", "Años activos"),
                      ("zonas", "Zonas distintas"), ("entidades", "Entidades distintas"),
                      ("procesos_2026", "Procesos en 2026"), ("procesos_sur", "Procesos en el sur")):
            if r.get(k) is not None:
                h.append((et, f"{int(r[k])}"))
        for k, et in (("primera_aparicion", "Primera aparición"), ("ultima_aparicion", "Última aparición")):
            if _limpio(r.get(k)):
                h.append((et, _limpio(r[k])))
    for k, et in (("tipo_relacion", "Tipo de relación"), ("ciudad", "Ciudad"), ("rubro", "Rubro principal"),
                  ("marcas", "Marca(s) de pantalla"), ("web", "Web")):
        v = _limpio(p.get(k)) or (_limpio(r.get(k)) if k in r else None) or \
            (_limpio(r.get("marca_pantalla")) if k == "marcas" else None)
        if v:
            h.append((et, v))
    if _limpio(i.get("socio_frecuente")):
        h.append(("Socio con el que más coincide", f"{i['socio_frecuente']} ({int(i['veces_con_socio'])} veces)"))
    if _limpio(p.get("observacion")):
        h.append(("Observación", _limpio(p["observacion"])))
    if _limpio(p.get("evidencia")):
        h.append(("Evidencia", _limpio(p["evidencia"])))
    if not r and not p and not i:
        h.append(("Nota", "Solo figura el nombre; no hay datos del ranking."))
    ganados = []
    try:
        ganados = con.execute(
            "select fecha, entidad, monto from postores where ruc = ? and gano = 1 "
            "order by fecha desc limit 3", (ruc,)).fetchall()
    except sqlite3.Error:
        pass
    for fecha, entidad, monto in ganados:
        h.append(("Proceso ganado", f"{fecha} · {entidad}" + (f" · S/ {monto:,.0f}" if monto else "")))
    texto = _texto_empresa(h)
    return h, texto


def _texto_empresa(h: list[tuple[str, str]]) -> str:
    d: dict[str, list[str]] = {}
    for k, v in h:
        d.setdefault(k, []).append(v)
    g = lambda k: d.get(k, [None])[0]   # noqa: E731
    s = [f"{g('Empresa')} (RUC {g('RUC')})."]
    if g("Participaciones (2023-2026)"):
        s.append(f"Se presentó a {g('Participaciones (2023-2026)')} procesos de pantallas o pizarras "
                 f"interactivas entre 2023 y 2026 y resultó adjudicada en {g('Adjudicadas')}.")
    if g("Años activos"):
        s.append(f"Estuvo activa {g('Años activos')} años, en {g('Zonas distintas')} zonas y "
                 f"{g('Entidades distintas')} entidades.")
    pf = [x for x in (g("Tipo de relación"), g("Rubro principal")) if x]
    if pf:
        s.append("Perfil: " + "; ".join(pf) + ".")
    if g("Ciudad"):
        s.append(f"Ciudad: {g('Ciudad')}.")
    if g("Marca(s) de pantalla"):
        s.append(f"Marca de pantalla: {g('Marca(s) de pantalla')}.")
    if g("Socio con el que más coincide"):
        s.append(f"Suele presentarse junto a {g('Socio con el que más coincide')}.")
    if g("Observación"):
        s.append(f"Observación: {g('Observación')}")
    return " ".join(s)


def _hechos_marca(con, marca: str) -> tuple[list[tuple[str, str]], str]:
    m = _fila(con, "select * from marcas where marca = ?", (marca,)) or {}
    h = [("Marca", marca)]
    for k, et in (("origen", "Origen"), ("empresas", "Empresa(s) que la ofrecen"),
                  ("calidad_evidencia", "Calidad de la evidencia"), ("comentario", "Comentario")):
        if _limpio(m.get(k)):
            h.append((et, _limpio(m[k])))
    d = dict(h)
    texto = f"{marca} es una marca" + (f" de origen {d['Origen']}" if d.get("Origen") else "")
    if d.get("Empresa(s) que la ofrecen"):
        texto += f", ofrecida por {d['Empresa(s) que la ofrecen'].rstrip('.')}"
    texto += "."
    if d.get("Calidad de la evidencia"):
        texto += f" Calidad de la evidencia: {d['Calidad de la evidencia']}."
    if d.get("Comentario"):
        texto += f" {d['Comentario']}"
    return h, texto


# ------------------------------------------------------------------ redacción
def _numeros(s: str) -> set[str]:
    return {x.replace(",", "").replace(".", "") for x in re.findall(r"\d[\d.,]*", s or "")}


def redactar(hechos_texto: str, pregunta: str, cfg: dict | None = None) -> str:
    """Pide al modelo que redacte SOLO con los hechos. Si no responde, o trae una cifra que
    no estaba en ellos, se devuelve el texto armado por el código."""
    try:
        r = chat("Responde en español, en 2 a 4 frases, usando SOLO los datos dados. "
                 "No agregues cifras, nombres ni explicaciones que no estén en los datos. "
                 "Si algo no está en los datos, no lo menciones.",
                 f"Pregunta: {pregunta}\nDatos: {hechos_texto}", cfg=cfg).strip()
    except IAError:
        return hechos_texto
    if not r or len(r) > 900 or not _numeros(r) <= _numeros(hechos_texto) | _numeros(pregunta):
        return hechos_texto
    return r


def _respuesta(columnas, filas, resumen, nota="") -> dict:
    return {"ok": True, "origen": ORIGEN, "sql": SQL_NA, "nota": nota, "columnas": columnas,
            "filas": filas, "resumen": resumen, "truncado": False}


def _sin_ficha(con, ruc: str, otras: list[str]) -> dict:
    """Piden la ficha técnica de los equipos de una empresa. No existe en la base: se dice, con lo
    que sí se sabe de ella y dónde buscarlo, en vez de dejar que un modelo pequeño invente."""
    h, _ = _hechos_empresa(con, ruc)
    d = dict(h)
    texto = (f"No tengo la ficha técnica de los equipos que presenta {d['Empresa']}: mi base de datos guarda "
             "quién se presentó, cuántas veces y quién ganó, pero no las especificaciones de los productos "
             "que ofertan los postores.")
    marca = d.get("Marca(s) de pantalla")
    if marca and norm(marca).startswith("sin evidencia"):
        texto += " Tampoco hay evidencia pública de qué marca de pantalla ofrece."
    elif marca:
        texto += f" Solo consta que trabaja con la marca: {marca}."
    if d.get("Participaciones (2023-2026)"):
        texto += (f" Sí sé que se presentó a {d['Participaciones (2023-2026)']} procesos y fue adjudicada "
                  f"en {d.get('Adjudicadas', '0')}.")
    texto += (" Para saber qué modelo ofrece, hay que revisar su oferta o el acta de otorgamiento de la "
              "buena pro en el expediente de un proceso en el que participó.")
    claves = ("Empresa", "RUC", "Marca(s) de pantalla", "Participaciones (2023-2026)", "Adjudicadas",
              "Evidencia", "Observación")
    filas = [(k, d[k]) for k in claves if k in d]
    nota = ("También podría referirse a: " + "; ".join(otras)) if otras else ""
    return _respuesta(["campo", "valor"], filas, texto, nota)


# ----------------------------------------------------------------------- API
def ranking_general(con) -> dict | None:
    if _tabla(con, "ranking_empresas"):
        filas = con.execute(
            "select empresa, puntaje, participaciones, adjudicadas, marca_pantalla "
            "from ranking_empresas order by puntaje desc, participaciones desc limit 10").fetchall()
        if filas:
            return _respuesta(
                ["empresa", "puntaje", "participaciones", "adjudicadas", "marca_pantalla"], filas,
                "Las 10 empresas con mayor puntaje en el ranking de competidores de pantallas "
                "interactivas 2023-2026. Es un ranking del historial, no una predicción para un proceso "
                "concreto: para eso cita la nomenclatura de un proceso vigente.")
    if _tabla(con, "postores"):
        filas = con.execute(
            "select nombre as empresa, count(*) as participaciones, sum(gano) as ganadas from postores "
            "group by ruc order by participaciones desc limit 10").fetchall()
        if filas:
            return _respuesta(["empresa", "participaciones", "ganadas"], filas,
                              "Las 10 empresas que más veces se presentaron según el historial de postores. "
                              "Es un conteo histórico, no una predicción para un proceso concreto.")
    return None


def responder(con: sqlite3.Connection, pregunta: str, cfg: dict | None = None, usar_llm: bool = True):
    """Devuelve la respuesta (mismo formato que consultas.preguntar), o None si la pregunta
    no es de conocimiento y debe seguir su camino normal."""
    q = norm(pregunta)
    if _PIDE_RANKING.search(q):
        r = ranking_general(con)
        if r:
            return r
    pide = bool(_INTENCION.search(q))
    hallado = _buscar(con, pregunta)
    if not hallado:
        if not pide:
            return None
        return {"ok": False, "origen": ORIGEN,
                "motivo": "No tengo información sobre eso en mi base de conocimiento (glosario, marcas y "
                          "empresas del ranking). Puedo explicar términos como SEACE, Acuerdo Marco o "
                          "Buena pro, y decirte quién es una empresa o marca del estudio de mercado. "
                          "Si buscas datos (montos, fechas, procesos), reformula la pregunta."}
    tipo, clave, nombre, otras = hallado
    if tipo == "empresa" and _PIDE_FICHA.search(q):
        return _sin_ficha(con, clave, otras)
    if not pide:
        # sin «qué es…» solo se acepta si la pregunta ES el nombre («brighter», «la empresa STANDAR»);
        # si sobran palabras («¿cuántas licitaciones hay vigentes?») es una pregunta de datos.
        resto = set(tokens(pregunta)) - set(tokens(nombre)) - SUFIJOS - RELLENO
        if resto:
            return None
    nota = ("También podría referirse a: " + "; ".join(otras)) if otras else ""
    if tipo == "glosario":
        e = next(x for x in _glosario() if x["termino"] == clave)
        filas = [("Término", e["termino"]), ("Definición", e["definicion"])]
        if e.get("revisar"):
            filas.append(("Nota", "Texto pendiente de confirmar por la empresa."))
        extra = _fila(con, "select * from marcas where upper(marca) = upper(?)", (clave,)) \
            if _tabla(con, "marcas") else None
        if extra:
            h, _ = _hechos_marca(con, extra["marca"])
            filas += [x for x in h if x[0] != "Marca"]
        return _respuesta(["campo", "valor"], filas, e["definicion"], nota)
    h, texto = _hechos_empresa(con, clave) if tipo == "empresa" else _hechos_marca(con, clave)
    resumen = redactar(texto, pregunta, cfg) if usar_llm else texto
    return _respuesta(["campo", "valor"], h, resumen, nota)

"""Prueba los importadores de Excel y el camino de conocimiento del asistente.
No usa tus datos reales ni un modelo: arma Excel de juguete y simula la respuesta del modelo.
Ejecutar:  python tests/test_conocimiento.py"""
import sqlite3
import sys
import tempfile
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(RAIZ / "src"), str(RAIZ / "src" / "ia")]

import conocimiento  # noqa: E402
import importar_conocimiento as imp_c  # noqa: E402
import importar_postores as imp_p  # noqa: E402
from cliente import IAError  # noqa: E402

tmp = Path(tempfile.mkdtemp())

# ---------------------------------------------------------------- Excel de juguete
part = pd.DataFrame([
    # proceso 1 (con idProceso): 3 postores, gana ALFA
    ["2025-03-01", "2025", "ISLAY", "MUNICIPALIDAD X", "LP-1-2025", "PANTALLAS INTERACTIVAS", "20111111111", "ALFA TECH S.A.C.", "SI", "50000", "111"],
    ["2025-03-01", "2025", "ISLAY", "MUNICIPALIDAD X", "LP-1-2025", "PANTALLAS INTERACTIVAS", "20222222222", "BETA SERVICIOS E.I.R.L.", None, "50000", "111"],
    ["2025-03-01", "2025", "ISLAY", "MUNICIPALIDAD X", "LP-1-2025", "PANTALLAS INTERACTIVAS", "1796188", "CONSORCIO GAMMA", None, "50000", "111"],
    # misma participación de ALFA repetida SIN idProceso: debe unirse al proceso 111, no duplicarse
    ["2025-03-01", "2025", "ISLAY", "MUNICIPALIDAD X", "LP-1-2025", "PANTALLAS INTERACTIVAS", "20111111111", "ALFA TECH S.A.C.", "SI", "50000", None],
    # proceso 2 sin idProceso y en una zona que no está en la tabla
    ["2026-01-10", "2026", "ZONALIBRE", "COLEGIO Y", "AS-2-2026", "PIZARRA INTERACTIVA", "20222222222", "BETA SERVICIOS E.I.R.L.", None, None, None],
], columns=["Fecha", "Año", "Zona", "Entidad", "Nomenclatura", "Objeto", "RUC", "Empresa", "¿Ganó?",
            "Monto adjudicado del proceso (S/)", "idProceso"])
indic = pd.DataFrame([["20111111111", "ALFA TECH S.A.C.", "2", "1", None, "BETA SERVICIOS E.I.R.L.", "2", "coincide con BETA"]],
                     columns=["RUC", "Empresa", "Participaciones", "Adjudicadas", "Tasa de adjudicación",
                              "Socio recurrente más frecuente", "Veces con ese socio", "Observación (patrón, no conclusión)"])
d1 = tmp / "D1 Inteligencia competitiva - historial de postores 2023-2026.xlsx"
with pd.ExcelWriter(d1) as w:
    part.to_excel(w, sheet_name="02 PARTICIPACIONES", index=False)
    indic.to_excel(w, sheet_name="05 INDICADORES", index=False)

rank = pd.DataFrame([
    [1, "20111111111", "ALFA TECH S.A.C.", 90, 12, 3, None, 4, 2, 5, 6, 7, "2023-01-01", "2026-05-01", "TRIUMPH BOARD", "Revendedor", "Arequipa", "sí"],
    [2, "20222222222", "BETA SERVICIOS E.I.R.L.", 80, 8, 0, None, 3, 1, 2, 3, 4, "2023-02-01", "2026-04-01", "sin evidencia", "Multimarca", "Lima", "sí"],
    [3, "20333333333", "SOLUCIONES TI S.A.C.", 10, 1, 0, None, 1, 0, 0, 1, 1, "2025-02-01", "2025-04-01", None, None, None, "no"],
], columns=["N.º", "RUC", "Empresa", "Puntaje", "Participaciones", "Adjudicadas", "Tasa de adjudicación", "Años activos",
            "Procesos en 2026", "Procesos en el sur", "Zonas", "Entidades", "Primera aparición", "Última aparición",
            "Marca de pantalla", "Tipo de relación", "Ciudad", "¿Investigada?"])
perf = pd.DataFrame([[90, "20111111111", "ALFA TECH S.A.C.", "Arequipa", "alfa.pe", "TRIUMPH BOARD", "Revendedor de marca",
                      "Oficina y cómputo", "OC 2024", "El postor más activo."]],
                    columns=["Puntaje", "RUC", "Empresa", "Ciudad", "Web", "Marca(s) de pantalla", "Tipo de relación",
                             "Rubro principal", "Evidencia", "Observación"])
marc = pd.DataFrame([["TRIUMPH BOARD", "República Checa", "ALFA TECH S.A.C.", "Alta", "Marca rival."],
                     ["Dahua (Hiboard)", "China", "BETA SERVICIOS E.I.R.L.", "Media", "Línea de paneles."],
                     ["Sin marca identificada", "—", "Las demás", "—", "—"]],
                    columns=["Marca", "Origen", "Empresa(s) que la ofrecen", "Calidad de la evidencia", "Comentario"])
rk = tmp / "Competidores en pantallas interactivas - ranking y marcas 2023-2026.xlsx"
with pd.ExcelWriter(rk) as w:
    rank.to_excel(w, sheet_name="01 RANKING", index=False)
    perf.to_excel(w, sheet_name="02 PERFILES", index=False)
    marc.to_excel(w, sheet_name="03 MARCAS", index=False)

# ------------------------------------------------------------ importar postores
db = tmp / "analisis.db"
filas, inf = imp_p.transformar(imp_p.leer(d1))
assert inf["procesos"] == 2, inf                       # la fila sin id se unió al proceso 111
assert inf["filas"] == 4, inf                          # ALFA no se duplicó
assert inf["ganadores"] == 1 and inf["ruc_cortos"] == 1, inf
assert inf["zonas_desconocidas"] == ["ZONALIBRE"], inf
assert imp_p.departamento_de("ISLAY") == ("AREQUIPA", True)
assert imp_p.departamento_de("Cotabambas")[0] == "APURIMAC"
assert imp_p.guardar(filas, db) == 4
assert imp_p.guardar(filas, db) == 4                   # reimportar no duplica
con = sqlite3.connect(db)
assert con.execute("select departamento, monto from postores where ruc='20111111111'").fetchone() == ("AREQUIPA", 50000.0)

# --------------------------------------------------------- importar conocimiento
n = imp_c.importar(rk, d1, db)
assert n == {"ranking_empresas": 3, "perfiles_empresas": 1, "marcas": 3, "indicadores_empresas": 1}, n
assert con.execute("select tasa_adjudicacion from ranking_empresas where ruc='20111111111'").fetchone()[0] == 0.25

# ------------------------------------------------------------------ enrutador
# (pregunta, esperado) con esperado: "OK" responde, "NO" dice que no sabe, "SQL" sigue al texto-a-SQL
BANCO = [
    ("¿Qué es Brighter?", "OK"), ("que es btouch", "OK"), ("qué es SEACE", "OK"),
    ("que significa acuerdo marco", "OK"), ("¿qué es la buena pro?", "OK"),
    ("qué es ALFA TECH", "OK"), ("quien es alfa tech sac", "OK"), ("brighter", "OK"),
    ("quién ofrece TRIUMPH BOARD", "OK"), ("que es hiboard", "OK"),
    ("quien es la empresa 20222222222", "OK"),
    ("cuales son los competidores mas probables", "OK"), ("principales competidores", "OK"),
    ("qué es la empresa fantasma xyz", "NO"), ("qué es el monto promedio", "NO"),
    ("cuántas licitaciones hay vigentes?", "SQL"),                    # dato, no definición
    ("qué empresas se presentaron más veces en Arequipa?", "SQL"),
    ("cuales son los postores de pizarras", "SQL"),
    ("qué es SOLUCIONES", "NO"),                                       # palabra genérica sola no identifica empresa
]
for pregunta, esperado in BANCO:
    r = conocimiento.responder(con, pregunta, usar_llm=False)
    obtuvo = "SQL" if r is None else ("OK" if r["ok"] else "NO")
    assert obtuvo == esperado, f"{pregunta!r}: esperaba {esperado}, obtuvo {obtuvo}"

r = conocimiento.responder(con, "qué es ALFA TECH", usar_llm=False)
assert "RUC 20111111111" in r["resumen"] and "12 procesos" in r["resumen"] and "Proceso ganado" in dict(r["filas"]).keys() | {x[0] for x in r["filas"]}
assert r["sql"].startswith("(") and r["origen"] == "conocimiento"       # la interfaz no muestra SQL ni «aprender»
r = conocimiento.responder(con, "cuales son los competidores mas probables", usar_llm=False)
assert r["filas"][0][0] == "ALFA TECH S.A.C."                           # el de mayor puntaje primero

# --------------------------------------------- el texto del modelo se verifica
HECHOS = "ALFA TECH S.A.C. (RUC 20111111111). Se presentó a 12 procesos y resultó adjudicada en 3."
cadena = {"msg": "", "error": False}


def falso_chat(*a, **k):
    if cadena["error"]:
        raise IAError("sin modelo")
    return cadena["msg"]


conocimiento.chat = falso_chat
cadena["msg"] = "ALFA TECH se presentó a 12 procesos y ganó 3."
assert conocimiento.redactar(HECHOS, "q") == cadena["msg"]                # fiel: se usa
cadena["msg"] = "ALFA TECH se presentó a 40 procesos."
assert conocimiento.redactar(HECHOS, "q") == HECHOS                       # cifra inventada: se descarta
cadena["msg"] = ""
assert conocimiento.redactar(HECHOS, "q") == HECHOS                       # vacío: texto del código
cadena["error"] = True
assert conocimiento.redactar(HECHOS, "q") == HECHOS                       # sin Ollama: texto del código

# la integración con consultas.py importa sin error
import consultas  # noqa: E402
assert consultas.conocimiento is conocimiento

con.close()
print("OK: importadores y base de conocimiento verificados")

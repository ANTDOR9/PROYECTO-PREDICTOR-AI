"""Preguntas sobre un proceso concreto: plazos, ficha y proceso que no existe.
No usa Ollama: la respuesta es una cuenta de calendario sobre la tabla `vigentes`.
Ejecutar:  python tests/test_procesos.py"""
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(RAIZ / "src"), str(RAIZ / "src" / "ia")]

import consultas  # noqa: E402
import procesos  # noqa: E402

COLS = ("id, nomenclatura, entidad, objeto, tipo_proceso, descripcion, valor_referencial, moneda, "
        "fecha_convocatoria, fecha_fin_inscripcion, fecha_presentacion, ubigeo, enlace")
con = sqlite3.connect(":memory:")
con.execute(f"create table vigentes ({COLS})")
con.execute("create table licitaciones (ocid, nomenclatura, entidad, estado, fecha)")
FILAS = [
    (1, "CONV-PROC-23-2026-UNSA.-1", "UNIVERSIDAD NACIONAL SAN AGUSTIN", "Bien", "Convenio",
     "PANTALLA LED DE GRAN FORMATO", 125715.0, "Nuevos Soles", "06/10/2026 20:59:00",
     "16/10/2026 17:30:00", "19/10/2026 08:30:00", 552, "https://x/1"),
    (2, "LP-SM-14-2026-MDCC-1", "MUNICIPALIDAD DISTRITAL DE CERRO COLORADO", "Bien", "Licitación Pública",
     "ADQUISICIÓN DE PANTALLAS INTERACTIVAS", None, "Nuevos Soles", "01/10/2026 10:00:00",
     "25/10/2026 23:59:00", "26/10/2026 00:01:00", 1, "https://x/2"),
    (3, "AS-SM-5-2026-GRA-1", "GOBIERNO REGIONAL AREQUIPA", "Bien", "Adjudicación Simplificada",
     "PIZARRAS INTERACTIVAS", 1000.0, "Nuevos Soles", "01/10/2026 10:00:00",
     "10/10/2026 23:59:00", "11/10/2026 00:01:00", 1, "https://x/3"),
    (4, "AS-SM-5-2026-GRA-11", "GOBIERNO REGIONAL AREQUIPA", "Bien", "Adjudicación Simplificada",
     "OTRA COSA", 1000.0, "Nuevos Soles", "01/10/2026 10:00:00",
     "17/10/2026 15:00:00", "18/10/2026 00:01:00", 1, "https://x/4"),
    (5, "LP-ABR-4-2026-MINSA-1", "MINISTERIO DE SALUD", "Bien", "LP Abreviada", "VIDEO WALL", None, "Nuevos Soles",
     "01/10/2026 10:00:00", "20/10/2026 23:59:00", None, 1, "https://x/5"),
    (6, "LP-ABR-4-2026-MINSA-2", "MINISTERIO DE SALUD", "Bien", "LP Abreviada", "OTRO", None, "Nuevos Soles",
     "01/10/2026 10:00:00", "21/10/2026 23:59:00", None, 1, "https://x/6"),
]
con.executemany("insert into vigentes values (?,?,?,?,?,?,?,?,?,?,?,?,?)", FILAS)
con.execute("insert into licitaciones values ('o1','CP-ABR-2-2025-OECE-MDSJB-1','MUNICIPALIDAD DE SAN JUAN','', '2025-06-27')")
HOY = datetime(2026, 10, 16, 12, 52)


def r(pregunta, ahora=HOY, **kw):
    return procesos.responder(con, pregunta, ahora=ahora, **kw)


# --- la pregunta que falló: ocid no existe en vigentes; ahora se calcula con la fecha
x = r('en la ficha "CONV-PROC-23-2026-UNSA.-1" cuantos dias quedan para presentarse a dicha licitacion?')
assert x["ok"] and x["origen"] == "proceso"
assert "16/10/2026 17:30 (hoy, faltan 4 h 38 min)" in x["resumen"], x["resumen"]
assert "19/10/2026 08:30 (faltan 3 días)" in x["resumen"], x["resumen"]
d = dict(x["filas"])
assert d["Días para inscribirse"] == "0" and d["Días para las propuestas"] == "3"
assert d["Valor referencial"].startswith("125,715") and d["Ficha en el SEACE"] == "https://x/1"
assert "ocid" not in x["sql"] and x["sql"].startswith("SELECT * FROM vigentes WHERE nomenclatura = ")
assert "16/10/2026 12:52" in x["nota"]

# --- cómo lo escriba la persona
assert r("hasta cuando puedo postular a conv proc 23 2026 unsa 1")["filas"][0][1] == "CONV-PROC-23-2026-UNSA.-1"
assert r("cuándo cierra «LP-SM-14-2026-MDCC-1»?")["filas"][0][1] == "LP-SM-14-2026-MDCC-1"
assert r("cuantos dias quedan en lp-sm-14-2026-mdcc")["filas"][0][1] == "LP-SM-14-2026-MDCC-1"   # código incompleto, único
# el más largo gana: «...-11» también contiene «...-1»
assert r("cuantos dias quedan en AS-SM-5-2026-GRA-11")["filas"][0][1] == "AS-SM-5-2026-GRA-11"
# código incompleto y ambiguo (MINSA-1 y MINSA-2 empiezan igual): no se adivina
amb = r("cuantos dias quedan en LP-ABR-4-2026-MINSA")
assert not amb["ok"] and "No encuentro" in amb["motivo"]

# --- calendario
p = r("cuando se presentan las propuestas de LP-SM-14-2026-MDCC-1")
assert p["resumen"].index("Presentación de propuestas") < p["resumen"].index("Cierre de inscripción")   # primero lo preguntado
assert "faltan 10 días" in p["resumen"] and "faltan 9 días" in p["resumen"]
assert "ya venció hace 6 días" in r("cuantos dias quedan en AS-SM-5-2026-GRA-1")["resumen"]
assert "(mañana)" in r("cuantos dias quedan en AS-SM-5-2026-GRA-11")["resumen"]
assert "ya venció hoy" in r("cuando cierra CONV-PROC-23-2026-UNSA.-1", ahora=datetime(2026, 10, 16, 18, 0))["resumen"]
assert "sin fecha publicada" in r("cuantos dias quedan en LP-ABR-4-2026-MINSA-1")["resumen"]    # no hay fecha de propuestas
assert procesos.faltante(datetime(2026, 10, 16, 12, 52), HOY) == "hoy, faltan 0 h 00 min"

# --- ficha: de qué trata
t = r("de que trata LP-SM-14-2026-MDCC-1?")
assert "PANTALLAS INTERACTIVAS" in t["resumen"] and "Valor referencial" not in t["resumen"]    # no hay valor: no se inventa
assert "Valor referencial" not in dict(t["filas"])
assert "Valor referencial: 125,715" in r("de que trata CONV-PROC-23-2026-UNSA.-1")["resumen"]

# --- lista vieja: se avisa
v = r("cuando cierra LP-SM-14-2026-MDCC-1", actualizado=HOY - timedelta(days=10))
assert "más de una semana" in v["nota"] and "iniciar.bat vigentes" in v["nota"]
assert "más de una semana" not in r("cuando cierra LP-SM-14-2026-MDCC-1", actualizado=HOY - timedelta(days=1))["nota"]

# --- procesos que no están vigentes
h = r("cuantos dias quedan en CP-ABR-2-2025-OECE-MDSJB-1")
assert h["ok"] and "ya no está entre los procesos vigentes" in h["resumen"] and "ya no se puede postular" in h["resumen"]
n = r("cuantos dias quedan en LP-SM-99-2026-XXXX-1")
assert not n["ok"] and "LP-SM-99-2026-XXXX-1" in n["motivo"] and "iniciar.bat vigentes" in n["motivo"]

# --- lo que NO le toca: se devuelve None para que siga su camino
for q in ("cuantas licitaciones hay vigentes?",                         # dato agregado, sin proceso
          "que empresas se presentaron mas veces en Arequipa?",
          "que competidores se presentaran en LP-SM-14-2026-MDCC-1",    # lo contesta el predictor
          "quien se presentaria a LP-SM-14-2026-MDCC-1",
          "hola", "que es brighter"):
    assert r(q) is None, q
assert consultas._proceso_citado(con, "competidores de lp-sm-14-2026-mdcc-1")[0] == "LP-SM-14-2026-MDCC-1"

# --- integración: consultas.preguntar contesta sin llamar al modelo
def sin_modelo(*a, **k):
    raise AssertionError("la IA no debe intervenir en una cuenta de calendario")


consultas.chat = sin_modelo
y = consultas.preguntar('en la ficha "CONV-PROC-23-2026-UNSA.-1" cuantos dias quedan para presentarse?', con=con)
assert y["ok"] and y["origen"] == "proceso" and "CONV-PROC-23-2026-UNSA.-1" in y["resumen"]

# --- la guía del modelo ya no lo deja inventar `ocid` en vigentes, y hay ejemplos de fechas
assert "NO tiene ocid" in consultas.SISTEMA
ejemplos = consultas.ejemplos_para("cuantos dias quedan para que cierre un proceso vigente")
assert any("julianday" in e["sql"] and "FROM vigentes" in e["sql"] for e in ejemplos), ejemplos

print("OK: preguntas sobre un proceso concreto verificadas")

"""Pruebas del módulo de ML y del asistente de preguntas (sin modelo de lenguaje real).
Ejecutar:  python tests/test_ml.py"""
import sqlite3, sys, tempfile, shutil
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(RAIZ / "src"), str(RAIZ / "src" / "ml"), str(RAIZ / "src" / "ia")]
import asociaciones, historial, predictor, sintetico, validar  # noqa: E402
import consultas as P  # noqa: E402

tmp = Path(tempfile.mkdtemp())

# --- asociaciones: el grupo sembrado (empresas 5..10) debe aparecer
db = tmp / "est.db"; sintetico.generar(db, estructura=True, procesos_por_anio=45)
h = historial.Historial(historial.cargar(db))
t = asociaciones.pares(h)
grupo = {f"20{100000000 + i}" for i in range(5, 11)}
fuertes = t[(t.q <= 0.05) & (t.lift > 1)]
en_grupo = fuertes[fuertes.ruc_a.isin(grupo) & fuertes.ruc_b.isin(grupo)]
assert len(en_grupo) >= 8, f"el grupo sembrado casi no se detecta: {len(en_grupo)} de {len(fuertes)}"
assert len(en_grupo) / len(fuertes) > 0.5, "la mayoría de los pares fuertes deberían ser del grupo"

# --- sin estructura casi no debe haber pares significativos (falsos positivos controlados)
db0 = tmp / "azar.db"; sintetico.generar(db0, estructura=False, procesos_por_anio=45)
h0 = historial.Historial(historial.cargar(db0))
t0 = asociaciones.pares(h0)
assert (t0.q <= 0.05).sum() <= 3, f"demasiados falsos positivos: {(t0.q <= 0.05).sum()}"

# --- no hay fuga del futuro: features de un proceso no ven procesos de su misma fecha ni posteriores
i = h.n_procesos // 2
X, cand = predictor.features(h, h.fechas[i], "", "")
assert cand.sum() == (h.M[:h.antes_de(h.fechas[i])].any(0)).sum()

# --- predecir devuelve probabilidades ordenadas y excluye a los conocidos
m = predictor.entrenar(h, "2026-01-01")
conocido = h.rucs[0]
r = predictor.predecir(m, h, "2026-06-01", "MUNICIPALIDAD DE Cusco 1", "CUSCO", [conocido], top=5)
assert len(r) == 5 and r.prob.is_monotonic_decreasing and conocido not in set(r.ruc)

# --- validación honesta: con azar puro nunca declara MEJORA REAL
res = validar.evaluar(h0, pd.Timestamp("2026-01-01"))
for esc, v in res.items():
    assert not (v and v["ic95"][0] > 0), f"declaró mejora sobre azar puro en {esc}"

# --- preguntar: seguridad y aprendizaje
P.DB_AN = tmp / "est.db"
P.APRENDIDAS = tmp / "aprendidas.jsonl"
con = P.conectar()
sql, cols, filas = P._ejecutar(con, "select ruc, count(*) n from postores group by ruc order by n desc")
assert cols == ["ruc", "n"] and filas
for malo in ("DROP TABLE postores", "delete from postores", "select 1; select 2",
             "insert into postores(ocid,ruc) values('x','y')", "attach database 'x.db' as z"):
    try:
        P._ejecutar(con, malo); raise SystemExit(f"debió bloquearse: {malo}")
    except (sqlite3.Error, ValueError):
        pass
assert "TABLA postores" in P.esquema(con) and "TABLA licitaciones" in P.esquema(con)
con.close()
assert P.aprender("¿Cuántas empresas hay?", "select count(distinct ruc) from postores") is True
assert P.aprender("¿Cuántas empresas hay?", "select count(distinct ruc) from postores") is False
assert P.ejemplos_para("cuantas empresas existen")[0]["origen"] == "aprendida"
for e in P._leer(P.SEMILLA):             # las semillas deben ser SQL válido sobre el esquema real
    con = P.conectar()
    try:
        P._ejecutar(con, e["sql"])
    finally:
        con.close()

# --- preguntar de punta a punta con un modelo simulado
import json as _j
llamadas = []
def falso(sistema, usuario, json_modo=False, cfg=None):
    llamadas.append(usuario)
    if json_modo:
        return {"sql": "select count(distinct ruc) as empresas from postores", "nota": "conteo"}
    return "Hay 70 empresas."
P.chat = falso
r = P.preguntar("¿Cuántas empresas hay?")
assert r["ok"] and r["filas"] == [(70,)] and r["resumen"] == "Hay 70 empresas."
print("OK: ML y asistente verificados")

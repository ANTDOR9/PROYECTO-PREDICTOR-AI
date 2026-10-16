"""Datos sintéticos con la misma forma que `postores`, para probar sin la base real.

Siembra tres cosas, para que la validación tenga algo que encontrar:
  * empresas que se presentan mucho más que otras (frecuencia),
  * afinidad regional (cada empresa opera sobre todo en un departamento),
  * un grupo de empresas que tienden a presentarse juntas.
Con `estructura=False` todo es azar puro: ahí el modelo NO debe ganar.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np


ESQUEMA = """CREATE TABLE IF NOT EXISTS postores (
 ocid TEXT, idproceso TEXT, anio INTEGER, fecha TEXT, categoria TEXT, entidad TEXT,
 departamento TEXT, nomenclatura TEXT, descripcion TEXT, ruc TEXT, nombre TEXT,
 gano INTEGER, monto REAL, PRIMARY KEY (ocid, ruc))"""

DEPTOS = ["AREQUIPA", "CUSCO", "LIMA", "PUNO", "PIURA", "LORETO"]


def generar(destino: Path | str, semilla: int = 7, estructura: bool = True,
            procesos_por_anio: int = 14) -> Path:
    rng = np.random.default_rng(semilla)
    n_emp = 70
    rucs = [f"20{100000000 + i}" for i in range(n_emp)]
    peso = rng.pareto(2.0, n_emp) + 0.3 if estructura else np.ones(n_emp)
    depto_emp = rng.integers(0, len(DEPTOS), n_emp)
    grupo = set(range(5, 11)) if estructura else set()
    entidades = [(f"MUNICIPALIDAD DE {d.title()} {k}", d)
                 for d in DEPTOS for k in range(1, 5)]
    con = sqlite3.connect(destino)
    con.execute("DROP TABLE IF EXISTS postores")
    con.execute(ESQUEMA)
    k = 0
    for anio in (2023, 2024, 2025, 2026):
        for _ in range(procesos_por_anio):
            k += 1
            mes, dia = int(rng.integers(1, 13)), int(rng.integers(1, 28))
            ent, depto = entidades[int(rng.integers(len(entidades)))]
            p = np.full(n_emp, 0.0)
            for i in range(n_emp):
                base = min(0.55, 0.05 * peso[i] * 3)
                if estructura and DEPTOS[depto_emp[i]] == depto:
                    base = min(0.9, base * 3)
                p[i] = base
            elegidos = set(np.flatnonzero(rng.random(n_emp) < p))
            if estructura and rng.random() < 0.35:
                elegidos |= {g for g in grupo if rng.random() < 0.8}
            if len(elegidos) < 2:
                elegidos |= set(rng.choice(n_emp, 3, replace=False))
            ganador = int(rng.choice(sorted(elegidos)))
            for i in sorted(elegidos):
                con.execute(
                    "insert into postores values (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (f"ocds-sint-{k}", str(k), anio, f"{anio}-{mes:02d}-{dia:02d}",
                     "INTERACTIVA", ent, depto, f"AS-{k}-{anio}", "PANEL INTERACTIVO",
                     rucs[i], f"EMPRESA {i} S.A.C.", int(i == ganador), None))
    con.commit()
    con.close()
    return Path(destino)

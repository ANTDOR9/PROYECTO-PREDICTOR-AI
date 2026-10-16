"""Historial de participación como matrices (proceso x empresa).

Todo lo que se calcula "a la fecha" mira SOLO procesos estrictamente
anteriores: es la regla que impide que la validación haga trampa usando el
futuro.
"""
from __future__ import annotations

import sqlite3
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent.parent
DB = RAIZ / "data" / "analisis.db"


def norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).upper().strip()


def cargar(db: Path | str = DB, categoria: str = "INTERACTIVA") -> pd.DataFrame:
    con = sqlite3.connect(db)
    q = ("select ocid, fecha, anio, entidad, departamento, ruc, nombre, gano "
         "from postores")
    args: tuple = ()
    if categoria:
        q += " where categoria = ?"
        args = (categoria.upper(),)
    df = pd.read_sql_query(q, con, params=args)
    con.close()
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    return df.dropna(subset=["fecha", "ruc"]).reset_index(drop=True)


class Historial:
    def __init__(self, df: pd.DataFrame):
        p = (df.groupby("ocid")
               .agg(fecha=("fecha", "min"), entidad=("entidad", "first"),
                    depto=("departamento", "first"))
               .reset_index().sort_values(["fecha", "ocid"]).reset_index(drop=True))
        self.procs = p
        self.rucs = sorted(df["ruc"].unique())
        self.col = {r: i for i, r in enumerate(self.rucs)}
        row = {o: i for i, o in enumerate(p["ocid"])}
        self.M = np.zeros((len(p), len(self.rucs)), dtype=bool)
        self.W = np.zeros_like(self.M)
        for o, r, g in zip(df["ocid"], df["ruc"], df["gano"]):
            self.M[row[o], self.col[r]] = True
            if g:
                self.W[row[o], self.col[r]] = True
        self.fechas = p["fecha"].values.astype("datetime64[D]")
        self.entidad = np.array([norm(x) for x in p["entidad"]])
        self.depto = np.array([norm(x) for x in p["depto"]])
        self.nombres = (df.sort_values("fecha").groupby("ruc")["nombre"].last().to_dict())

    @property
    def n_procesos(self) -> int:
        return len(self.procs)

    def antes_de(self, fecha) -> int:
        """Cuántos procesos son estrictamente anteriores a `fecha`."""
        return int(np.searchsorted(self.fechas, np.datetime64(pd.Timestamp(fecha), "D"), "left"))

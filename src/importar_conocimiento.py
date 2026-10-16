"""Importa a data/analisis.db el conocimiento sobre competidores y marcas.

Lee dos Excel (los mismos que usa el estudio de mercado):
  * «Competidores en pantallas interactivas - ranking y marcas 2023-2026.xlsx»
        01 RANKING   -> tabla ranking_empresas   (589 empresas, con puntaje)
        02 PERFILES  -> tabla perfiles_empresas  (las investigadas una por una)
        03 MARCAS    -> tabla marcas
  * «D1 Inteligencia competitiva - historial de postores 2023-2026.xlsx» (opcional)
        05 INDICADORES -> tabla indicadores_empresas (con quién suele presentarse cada empresa)

Con estas tablas el asistente responde «¿qué es STANDAR S.R.L.?» o «¿quién ofrece
TRIUMPH BOARD?» sin pedirle al modelo que invente SQL. Son tablas derivadas: se
borran y se vuelven a crear en cada importación.

Uso:
    python src/importar_conocimiento.py                  # busca los Excel en data/fuentes/
    python src/importar_conocimiento.py ranking.xlsx [d1.xlsx]
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import unicodedata
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
DB = RAIZ / "data" / "analisis.db"
FUENTES = RAIZ / "data" / "fuentes"
PATRON_RANKING = "Competidores en pantallas interactivas*.xlsx"
PATRON_D1 = "D1 Inteligencia competitiva*2023-2026*.xlsx"

#: tabla -> (hoja, {columna_nueva: inicio del nombre original}, columnas numéricas)
TABLAS = {
    "ranking_empresas": ("01 RANKING", {
        "ruc": "RUC", "empresa": "Empresa", "puntaje": "Puntaje",
        "participaciones": "Participaciones", "adjudicadas": "Adjudicadas",
        "tasa_adjudicacion": "Tasa de adjudic", "anios_activos": "Años activos",
        "procesos_2026": "Procesos en 2026", "procesos_sur": "Procesos en el sur",
        "zonas": "Zonas", "entidades": "Entidades",
        "primera_aparicion": "Primera aparici", "ultima_aparicion": "Última aparici",
        "marca_pantalla": "Marca de pantalla", "tipo_relacion": "Tipo de relaci",
        "ciudad": "Ciudad", "investigada": "¿Investigada"},
        ["puntaje", "participaciones", "adjudicadas", "tasa_adjudicacion", "anios_activos",
         "procesos_2026", "procesos_sur", "zonas", "entidades"]),
    "perfiles_empresas": ("02 PERFILES", {
        "ruc": "RUC", "empresa": "Empresa", "puntaje": "Puntaje", "ciudad": "Ciudad",
        "web": "Web", "marcas": "Marca(s)", "tipo_relacion": "Tipo de relaci",
        "rubro": "Rubro", "evidencia": "Evidencia", "observacion": "Observaci"},
        ["puntaje"]),
    "marcas": ("03 MARCAS", {
        "marca": "Marca", "origen": "Origen", "empresas": "Empresa(s)",
        "calidad_evidencia": "Calidad", "comentario": "Comentario"}, []),
}
TABLAS_D1 = {
    "indicadores_empresas": ("05 INDICADORES", {
        "ruc": "RUC", "empresa": "Empresa", "participaciones": "Participaciones",
        "adjudicadas": "Adjudicadas", "socio_frecuente": "Socio recurrente m",
        "veces_con_socio": "Veces con ese socio", "observacion": "Observaci"},
        ["participaciones", "adjudicadas", "veces_con_socio"]),
}


def _n(s) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def _cargar(excel: Path, hoja: str, mapa: dict, numericas: list[str]) -> pd.DataFrame:
    df = pd.read_excel(excel, sheet_name=hoja, dtype=str)
    out = pd.DataFrame(index=df.index)
    for nueva, inicio in mapa.items():
        col = next((c for c in df.columns if _n(c).startswith(_n(inicio))), None)
        out[nueva] = df[col].str.strip() if col is not None else None
    for c in numericas:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.dropna(how="all")
    # ranking/perfiles/indicadores: la clave de lectura es el nombre; sin él no sirve la fila
    clave = "marca" if "marca" in out.columns else "empresa"
    return out[out[clave].notna()].reset_index(drop=True)


def _buscar(patron: str, explicito: str | None) -> Path | None:
    if explicito:
        p = Path(explicito)
        if not p.exists():
            raise SystemExit(f"No existe el archivo: {p}")
        return p
    h = sorted(FUENTES.glob(patron))
    return h[-1] if h else None


def _escribir(con: sqlite3.Connection, tabla: str, df: pd.DataFrame) -> None:
    con.execute(f'DROP TABLE IF EXISTS "{tabla}"')
    df.to_sql(tabla, con, index=False)


def importar(ranking: Path, d1: Path | None, db: Path) -> dict:
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    cuenta = {}
    try:
        for tabla, (hoja, mapa, num) in TABLAS.items():
            df = _cargar(ranking, hoja, mapa, num)
            if tabla == "ranking_empresas":   # la tasa puede venir como fórmula sin valor guardado
                df["tasa_adjudicacion"] = (df["adjudicadas"] / df["participaciones"]).round(3)
            _escribir(con, tabla, df)
            cuenta[tabla] = len(df)
        if d1:
            for tabla, (hoja, mapa, num) in TABLAS_D1.items():
                df = _cargar(d1, hoja, mapa, num)
                _escribir(con, tabla, df)
                cuenta[tabla] = len(df)
        con.commit()
    finally:
        con.close()
    return cuenta


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ranking", nargs="?")
    ap.add_argument("d1", nargs="?")
    ap.add_argument("--db", default=str(DB))
    a = ap.parse_args(argv)
    ranking = _buscar(PATRON_RANKING, a.ranking)
    if not ranking:
        raise SystemExit(f"No encontré el Excel de ranking. Cópialo a {FUENTES} o pásalo como argumento.")
    d1 = _buscar(PATRON_D1, a.d1)
    print(f"Ranking: {ranking.name}\nD1:      {d1.name if d1 else '(no encontrado; se omiten los indicadores)'}")
    for t, n in importar(ranking, d1, Path(a.db)).items():
        print(f"  {t}: {n} filas")
    return 0


if __name__ == "__main__":
    sys.exit(main())

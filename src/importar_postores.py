"""Importa el historial de postores desde el Excel «D1 Inteligencia competitiva».

Llena la tabla `postores` de data/analisis.db, que es la que usan el predictor
de competidores y el asistente. Sirve cuando no se puede (o no se quiere)
reconstruir el historial desde los paquetes OCDS con src/postores.py.

Uso:
    python src/importar_postores.py                       # busca el Excel en data/fuentes/
    python src/importar_postores.py "ruta/al/D1.xlsx"
    python src/importar_postores.py --db otra.db

Decisiones (para poder explicarlas):
  * Clave de proceso (`ocid`): el idProceso de SEACE cuando existe. En las filas
    que no lo traen se usa el de otra fila con la misma nomenclatura y entidad;
    si tampoco hay, «N:<nomenclatura>|<entidad>». Así un mismo proceso no se parte.
  * `departamento`: la columna «Zona» del Excel mezcla departamentos y provincias
    (AREQUIPA, ISLAY, COTABAMBAS...). Se lleva todo a departamento con ZONA_A_DEPARTAMENTO.
    Una zona que no esté en la tabla se conserva tal cual y se avisa.
  * RUC de 6-7 dígitos (consorcios sin RUC propio) se conservan; solo se cuentan en el informe.
  * Las filas importadas se marcan con fuente = 'D1_excel'. Volver a importar
    reemplaza únicamente esas filas y no toca lo que venga de otra fuente.
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
PATRON_EXCEL = "D1 Inteligencia competitiva*2023-2026*.xlsx"
HOJA = "02 PARTICIPACIONES"
FUENTE = "D1_excel"
CATEGORIA = "INTERACTIVA"   # el Excel solo trae pantallas y pizarras interactivas

ESQUEMA = """
CREATE TABLE IF NOT EXISTS postores (
    ocid         TEXT NOT NULL,
    idproceso    TEXT,
    anio         INTEGER,
    fecha        TEXT,
    categoria    TEXT,
    entidad      TEXT,
    departamento TEXT,
    nomenclatura TEXT,
    descripcion  TEXT,
    ruc          TEXT NOT NULL,
    nombre       TEXT,
    gano         INTEGER NOT NULL DEFAULT 0,
    monto        REAL,
    PRIMARY KEY (ocid, ruc)
);
CREATE INDEX IF NOT EXISTS idx_postores_ruc ON postores(ruc);
CREATE INDEX IF NOT EXISTS idx_postores_cat ON postores(categoria);
CREATE INDEX IF NOT EXISTS idx_postores_anio ON postores(anio);
"""

#: zona del Excel (provincia o departamento) -> departamento. Sin tildes y en mayúsculas.
ZONA_A_DEPARTAMENTO = {
    "ANGARAES": "HUANCAVELICA", "AREQUIPA (REGION)": "AREQUIPA", "CAJATAMBO": "LIMA",
    "CALCA": "CUSCO", "CALLAO": "CALLAO", "CANCHIS": "CUSCO", "CANDARAVE": "TACNA",
    "CARAVELI": "AREQUIPA", "CHACHAPOYAS": "AMAZONAS", "CHICLAYO": "LAMBAYEQUE",
    "CHUCUITO": "PUNO", "CHUMBIVILCAS": "CUSCO", "CONDESUYOS": "AREQUIPA",
    "COTABAMBAS": "APURIMAC", "CUSCO": "CUSCO", "ESPINAR": "CUSCO",
    "HUANCAVELICA": "HUANCAVELICA", "HUANCAYO": "JUNIN", "HUANUCO": "HUANUCO",
    "HUARI": "ANCASH", "ISLAY": "AREQUIPA", "LA CONVENCION": "CUSCO", "LIMA": "LIMA",
    "MAYNAS": "LORETO", "MOYOBAMBA": "SAN MARTIN", "PARURO": "CUSCO",
    "PAUCAR DEL SARA SARA": "AYACUCHO", "PIURA": "PIURA", "PUNO": "PUNO",
    "QUISPICANCHI": "CUSCO", "SAN ROMAN": "PUNO", "TALARA": "PIURA",
    "TAMBOPATA": "MADRE DE DIOS", "TAYACAJA": "HUANCAVELICA", "TRUJILLO": "LA LIBERTAD",
    "URUBAMBA": "CUSCO", "YAULI": "JUNIN",
}


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).upper().strip()


def departamento_de(zona) -> tuple[str, bool]:
    """(departamento, conocido). Si la zona no está en la tabla se devuelve tal cual."""
    z = _norm(zona)
    return ZONA_A_DEPARTAMENTO.get(z, z), z in ZONA_A_DEPARTAMENTO


def buscar_excel(ruta: str | None) -> Path:
    if ruta:
        p = Path(ruta)
        if not p.exists():
            raise SystemExit(f"No existe el archivo: {p}")
        return p
    hallados = sorted(FUENTES.glob(PATRON_EXCEL))
    if not hallados:
        raise SystemExit(f"No encontré el Excel D1 (2023-2026). Cópialo a {FUENTES} "
                         "o pásalo como argumento.")
    return hallados[-1]


def _columna(df: pd.DataFrame, *candidatas: str) -> str | None:
    """La versión nueva del Excel renombró «Monto adjudicado (S/)»; se aceptan ambas."""
    for c in df.columns:
        if any(_norm(c).startswith(_norm(x)) for x in candidatas):
            return c
    return None


def leer(excel: Path) -> pd.DataFrame:
    d = pd.read_excel(excel, sheet_name=HOJA, dtype=str)
    falta = {"Fecha", "Año", "Zona", "Entidad", "Nomenclatura", "Objeto", "RUC", "Empresa"} - set(d.columns)
    if falta:
        raise SystemExit(f"A la hoja «{HOJA}» le faltan columnas: {sorted(falta)}")
    return d


def transformar(d: pd.DataFrame) -> tuple[list[tuple], dict]:
    """Devuelve (filas para INSERT, informe)."""
    d = d.copy()
    for c in ("Entidad", "Nomenclatura", "Empresa", "RUC", "Objeto"):
        d[c] = d[c].fillna("").str.strip()
    col_gano = _columna(d, "¿Ganó?", "Gano")
    col_monto = _columna(d, "Monto adjudicado")
    d["id_"] = d["idProceso"].where(d["idProceso"].notna(), None) if "idProceso" in d else None
    d["clave"] = d["Nomenclatura"] + "|" + d["Entidad"]

    # idProceso por (nomenclatura, entidad) cuando es único en el archivo
    ids = d.dropna(subset=["id_"]).groupby("clave")["id_"].agg(lambda s: set(s))
    unico = {k: next(iter(v)) for k, v in ids.items() if len(v) == 1}

    def ocid(fila):
        if pd.notna(fila["id_"]):
            return str(fila["id_"]).strip()
        return unico.get(fila["clave"], "N:" + fila["clave"])

    d["ocid"] = d.apply(ocid, axis=1)
    desconocidas: set[str] = set()
    filas: dict[tuple, list] = {}
    for _, f in d.iterrows():
        ruc = f["RUC"].strip()
        if not ruc:
            continue
        k = (f["ocid"], ruc)
        if k in filas:        # misma empresa dos veces en el mismo proceso
            continue
        dep, conocida = departamento_de(f["Zona"])
        if not conocida:
            desconocidas.add(str(f["Zona"]))
        gano = 1 if col_gano and str(f[col_gano]).strip().upper() in ("SI", "SÍ") else 0
        monto = None
        if col_monto and pd.notna(f[col_monto]):
            try:
                monto = float(f[col_monto])
            except ValueError:
                pass
        filas[k] = [f["ocid"], None if f["ocid"].startswith("N:") else f["ocid"],
                    int(f["Año"]), str(f["Fecha"])[:10], CATEGORIA, f["Entidad"], dep,
                    f["Nomenclatura"], f["Objeto"], ruc, f["Empresa"], gano, monto]
    filas = list(filas.values())
    inf = {
        "filas": len(filas),
        "procesos": len({r[0] for r in filas}),
        "empresas": len({r[9] for r in filas}),
        "ganadores": sum(r[11] for r in filas),
        "procesos_sin_ganador": len({r[0] for r in filas}) - len({r[0] for r in filas if r[11]}),
        "procesos_sin_idproceso": sum(1 for o in {r[0] for r in filas} if o.startswith("N:")),
        "ruc_cortos": len({r[9] for r in filas if len(r[9]) < 11}),
        "zonas_desconocidas": sorted(desconocidas),
        "anios": sorted({r[2] for r in filas}),
    }
    return [tuple(r) for r in filas], inf


def guardar(filas: list[tuple], db: Path) -> int:
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    con.executescript(ESQUEMA)
    cols = {r[1] for r in con.execute("PRAGMA table_info(postores)")}
    for col in ("departamento", "fuente"):
        if col not in cols:
            con.execute(f"ALTER TABLE postores ADD COLUMN {col} TEXT")
    con.execute("DELETE FROM postores WHERE fuente = ?", (FUENTE,))
    con.executemany(
        "INSERT OR REPLACE INTO postores (ocid, idproceso, anio, fecha, categoria, entidad, "
        "departamento, nomenclatura, descripcion, ruc, nombre, gano, monto, fuente) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [f + (FUENTE,) for f in filas])
    con.commit()
    n = con.execute("SELECT COUNT(*) FROM postores WHERE fuente = ?", (FUENTE,)).fetchone()[0]
    otras = con.execute("SELECT COUNT(*) FROM postores WHERE fuente IS NULL OR fuente <> ?",
                        (FUENTE,)).fetchone()[0]
    con.close()
    if otras:
        print(f"  Aviso: la base ya tenía {otras} filas de otra fuente (p. ej. OCDS). Si cubren los "
              "mismos procesos habrá duplicados; usa una fuente o la otra.", file=sys.stderr)
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("excel", nargs="?", help="Excel D1 (por defecto, el de data/fuentes/)")
    ap.add_argument("--db", default=str(DB))
    a = ap.parse_args(argv)
    excel = buscar_excel(a.excel)
    print(f"Leyendo {excel.name} ...")
    filas, inf = transformar(leer(excel))
    n = guardar(filas, Path(a.db))
    print(f"Importadas {n} participaciones en {a.db}")
    print(f"  procesos: {inf['procesos']}  empresas: {inf['empresas']}  años: {inf['anios']}")
    print(f"  ganadores registrados: {inf['ganadores']}  procesos sin ganador: {inf['procesos_sin_ganador']}")
    print(f"  procesos sin idProceso en el Excel: {inf['procesos_sin_idproceso']}  "
          f"RUC cortos (consorcios): {inf['ruc_cortos']}")
    if inf["zonas_desconocidas"]:
        print(f"  Zonas sin departamento asignado (agrégalas a ZONA_A_DEPARTAMENTO): "
              f"{inf['zonas_desconocidas']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

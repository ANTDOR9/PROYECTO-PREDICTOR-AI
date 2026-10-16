"""Gráficos del «ruido» de los datos (SEACE, Perú Compras, PetroPerú, Banco de la Nación).

    python src/ruido_datos.py                 # genera data/graficos/*.png
    python src/ruido_datos.py --salida carpeta

Ruido = datos que estorban al análisis: campos vacíos o con marcadores («---»),
columnas sin información, contradicciones (adjudicado mayor que el referencial),
duplicados, filtros que dejan pasar lo que no es del rubro. Cada gráfico dice en
su título qué encontró; todo se calcula de las bases, nada está escrito a mano.
Si existe data/analisis.db se añade la cobertura de la lista de postores.
"""
import argparse
import re
import sqlite3
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

# Paleta de referencia (dataviz): azul = dato útil / foco, naranja = ruido
SUP, TXT, TXT2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
AZUL, NARANJA, NEUTRO = "#2a78d6", "#eb6834", "#b9b8b1"

plt.rcParams.update({
    "figure.facecolor": SUP, "axes.facecolor": SUP, "savefig.facecolor": SUP,
    "axes.edgecolor": GRID, "axes.labelcolor": TXT2, "xtick.color": TXT2, "ytick.color": TXT2,
    "text.color": TXT, "font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
})


def titulo(fig, t, sub):
    fig.text(0.02, 0.965, t, fontsize=14, fontweight="bold", va="top", ha="left")
    fig.text(0.02, 0.905, sub, fontsize=9.5, color=TXT2, va="top", ha="left")


def guardar(fig, carpeta: Path, nombre: str, pie: str = ""):
    if pie:
        fig.text(0.02, 0.012, pie, fontsize=8, color=TXT2, ha="left")
    ruta = carpeta / nombre
    fig.savefig(ruta, dpi=150)
    plt.close(fig)
    print("  ✓", ruta.name)


def abrev(v):
    """1 000 -> 1 mil, 1 000 000 -> 1 M"""
    return f"{v / 1e6:g} M" if v >= 1e6 else f"{v / 1e3:g} mil" if v >= 1e3 else f"{v:g}"


def miles(n):
    return f"{n:,.0f}".replace(",", " ")


# ---------------------------------------------------------------------- datos
def cargar():
    con = sqlite3.connect(RAIZ / "data" / "licitaciones.db")
    t = {n: pd.read_sql(f"select * from {n}", con)
         for n in ("licitaciones", "vigentes", "perucompras", "petroperu", "bnacion")}
    con.close()
    return t


# ------------------------------------------------------------ 1. completitud
def g_completitud(t, carpeta):
    L, V, P = t["licitaciones"], t["vigentes"], t["perucompras"]
    vacio = lambda s: s.isna() | s.astype(str).str.strip().isin(["", "---", "None", "nan"])
    ratio = (L.monto_adjudicado / L.monto_referencial.replace(0, np.nan))
    con_ambos = ratio.notna()
    dup = L.nomenclatura.duplicated(keep=False)
    sospechosa = L.marca_detectada.eq("SMART") & L.objeto.str.contains(
        r"smart\s*(tv|card|tarjeta|inteligente)|televisor", case=False, regex=True)
    marca_ok = L.marca_detectada.ne("") & ~sospechosa
    filas = [
        ("Perú Compras · órdenes con contrato resuelto", P.estado_entrega.str.startswith("RESUELTA").sum(), len(P)),
        ("SEACE vigentes · valor referencial «---»", vacio(V.valor_referencial).sum(), len(V)),
        ("SEACE histórico · marca detectada vacía o dudosa", (~marca_ok).sum(), len(L)),
        ("SEACE histórico · proveedor ganador vacío", vacio(L.proveedor_ganador).sum(), len(L)),
        ("SEACE histórico · monto adjudicado vacío", L.monto_adjudicado.isna().sum(), len(L)),
        ("SEACE histórico · precio unitario vacío", L.precio_unitario.isna().sum(), len(L)),
        ("SEACE histórico · adjudicado > referencial", (ratio > 1.001).sum(), int(con_ambos.sum())),
        ("SEACE histórico · nomenclatura repetida", dup.sum(), len(L)),
        ("SEACE histórico · monto referencial en 0", (L.monto_referencial == 0).sum(), len(L)),
        ("SEACE histórico · columna «estado» sin información", vacio(L.estado).sum(), len(L)),
        ("PetroPerú · columna «categoría» sin información", vacio(t["petroperu"].categoria).sum(), len(t["petroperu"])),
        ("Banco de la Nación · columna «categoría» sin información", vacio(t["bnacion"].categoria).sum(), len(t["bnacion"])),
    ]
    df = pd.DataFrame(filas, columns=["etiqueta", "ruido", "total"])
    df["pct"] = df.ruido / df.total * 100
    df = df.sort_values("pct")
    fig, ax = plt.subplots(figsize=(10, 6.4))
    fig.subplots_adjust(left=0.40, right=0.80, top=0.84, bottom=0.17)
    y = np.arange(len(df))
    ax.barh(y, 100 - df.pct, height=0.55, color=AZUL, label="Dato utilizable", edgecolor=SUP, linewidth=2)
    ax.barh(y, df.pct, left=100 - df.pct, height=0.55, color=NARANJA, label="Ruido", edgecolor=SUP, linewidth=2)
    for yi, (p, r, tt) in zip(y, zip(df.pct, df.ruido, df.total)):
        ax.text(101.5, yi, f"{p:.0f}%  ({miles(r)} de {miles(tt)})", va="center", fontsize=8.5, color=TXT)
    ax.set_yticks(y); ax.set_yticklabels(df.etiqueta, fontsize=8.8)
    ax.set_xlim(0, 100); ax.set_xticks([0, 25, 50, 75, 100]); ax.set_xticklabels(["0", "25", "50", "75", "100 %"])
    ax.grid(axis="y", visible=False)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.06), ncol=2, frameon=False)
    graves = int((df.pct > 50).sum())
    titulo(fig, "Qué parte de cada dato sirve de verdad",
           f"Proporción de filas con ruido en cada campo: {graves} de {len(df)} campos tienen más de la mitad inservible.")
    guardar(fig, carpeta, "01_completitud.png",
            "Ruido = vacío, marcador «---», columna sin información, contradicción o duplicado. Marca «dudosa» = «SMART» que viene de «smart TV» o «smart card».")


# --------------------------------------------------------------- 2. el embudo
def g_embudo(t, carpeta):
    import vigentes as V
    from alerta_diaria import fecha
    from datetime import date
    cfg = V.cfg()
    claves = [V.norm(c) for c in cfg["palabras_clave"]]
    excl = [V.norm(x) for x in cfg["palabras_excluir"]]
    df = t["vigentes"]
    pasa = df.apply(lambda r: V.coincide(V.norm(f"{r['objeto']} {r['descripcion']}"), claves, excl), axis=1)
    hoy = date.today()
    abiertas = df.fecha_fin_inscripcion.map(lambda s: (fecha(s) or date(1900, 1, 1)) >= hoy)
    etapas = [("Oportunidades que publica el SEACE", len(df)),
              ("Pasan las palabras clave del rubro", int(pasa.sum())),
              ("…y su inscripción sigue abierta hoy", int((pasa & abiertas).sum()))]
    fig, ax = plt.subplots(figsize=(10, 4.4))
    fig.subplots_adjust(left=0.36, right=0.9, top=0.78, bottom=0.12)
    y = np.arange(len(etapas))[::-1]
    for yi, (n, v), c in zip(y, etapas, (NEUTRO, AZUL, AZUL)):
        ax.barh(yi, v, height=0.5, color=c)
        ax.text(v + len(df) * 0.012, yi, f"{miles(v)}  ({v / len(df):.1%})", va="center", fontsize=10)
    ax.set_yticks(y); ax.set_yticklabels([e[0] for e in etapas])
    ax.set_xlim(0, len(df) * 1.2); ax.grid(axis="y", visible=False)
    ax.xaxis.set_major_formatter(lambda v, _: miles(v))
    titulo(fig, f"De {miles(len(df))} oportunidades, {etapas[2][1]} son del rubro y están abiertas",
           "El ruido principal es de volumen: casi todo lo que publica el SEACE no tiene que ver con pantallas interactivas.")
    guardar(fig, carpeta, "02_embudo_vigentes.png", f"Corte al {hoy:%d/%m/%Y}. Palabras clave de config.yaml.")


# ------------------------------------------------------------ 3. rubro vecino
def g_rubro(t, carpeta):
    from buscar_actas import categoria, normaliza
    L = t["licitaciones"]
    cat = L.objeto.map(lambda x: categoria(normaliza(x))).value_counts().sort_values()
    fig, ax = plt.subplots(figsize=(9, 5))
    fig.subplots_adjust(left=0.2, right=0.92, top=0.8, bottom=0.1)
    colores = [AZUL if k == "INTERACTIVA" else NARANJA if k == "OTRO" else NEUTRO for k in cat.index]
    y = np.arange(len(cat))
    ax.barh(y, cat.values, height=0.55, color=colores)
    for yi, v in zip(y, cat.values):
        ax.text(v + 1.5, yi, f"{v}  ({v / len(L):.0%})", va="center", fontsize=9.5)
    ax.set_yticks(y); ax.set_yticklabels(cat.index); ax.grid(axis="y", visible=False)
    ax.set_xlim(0, cat.max() * 1.18)
    pct = cat.get("INTERACTIVA", 0) / len(L)
    titulo(fig, f"Solo {pct:.0%} del histórico filtrado son paneles interactivos",
           "Licitaciones del histórico por tipo de producto. Azul = lo que busca Brighter · naranja = sin clasificar · gris = rubros vecinos.")
    guardar(fig, carpeta, "03_ruido_de_rubro.png",
            "Las palabras clave son amplias a propósito (LED, televisor, proyector); sirven para vigilar el mercado, no para medir competencia directa.")


# ----------------------------------------------------------------- 4. montos
def g_montos(t, carpeta):
    L = t["licitaciones"]
    adj = L.monto_adjudicado.dropna()
    ratio = (L.monto_adjudicado / L.monto_referencial.replace(0, np.nan)).dropna()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.9))
    fig.subplots_adjust(left=0.07, right=0.97, top=0.78, bottom=0.17, wspace=0.22)
    lim = np.arange(np.floor(np.log10(adj.min())), np.ceil(np.log10(adj.max())) + 0.01, 0.25)
    a1.hist(np.log10(adj), bins=lim, color=AZUL, edgecolor=SUP, linewidth=1.5)
    a1.axvline(np.log10(adj.median()), color=TXT, lw=1.2, ls=(0, (4, 3)))
    a1.text(np.log10(adj.median()) + 0.05, a1.get_ylim()[1] * 0.93, f"mediana S/ {miles(adj.median())}", fontsize=8.5)
    a1.set_xticks(range(3, 9)); a1.set_xticklabels([abrev(10**k) for k in range(3, 9)])
    a1.set_xlabel("Monto adjudicado en soles (escala logarítmica)"); a1.set_ylabel("Procesos"); a1.grid(axis="x", visible=False)
    gigantes = (adj > 1e7).sum()
    a1.set_title(f"{gigantes} proceso{'s' if gigantes != 1 else ''} supera{'n' if gigantes != 1 else ''} S/ 10 millones: máximo S/ {adj.max() / 1e6:,.0f} M", fontsize=10, loc="left", color=TXT)
    cortes = np.arange(0, 1.7, 0.05)
    r_plot = np.where(ratio <= 1.001, ratio - 1e-6, ratio).clip(max=1.65)   # 1,00 exacto no es ruido
    n, b, patches = a2.hist(r_plot, bins=cortes, edgecolor=SUP, linewidth=1.5)
    for p, izq in zip(patches, b[:-1]):
        p.set_facecolor(NARANJA if izq >= 1.0 else AZUL)
    a2.set_xlabel("Adjudicado ÷ referencial"); a2.set_ylabel("Procesos"); a2.grid(axis="x", visible=False)
    a2.set_title(f"{(ratio > 1.001).sum()} de {len(ratio)} adjudicados superan el valor referencial (naranja)", fontsize=10, loc="left", color=TXT)
    titulo(fig, "Los montos tienen valores extremos y contradicciones",
           "Izquierda: un puñado de montos gigantes distorsiona promedios. Derecha: lo normal es adjudicar ≤ 100 % del referencial.")
    guardar(fig, carpeta, "04_montos.png", "Por eso conviene mediana en vez de promedio y revisar a mano lo naranja.")


# ------------------------------------------------------------- 5. Perú Compras
def g_perucompras(t, carpeta):
    P = t["perucompras"]
    est = P.estado_entrega.str.replace(r"\s*\(P\)", "", regex=True).value_counts()
    top = est.head(5)
    otros = est.iloc[5:].sum()
    top = pd.concat([top, pd.Series({"Otros estados": otros})]).sort_values()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11.5, 4.9), gridspec_kw={"width_ratios": [1.15, 1]})
    fig.subplots_adjust(left=0.23, right=0.97, top=0.78, bottom=0.17, wspace=0.55)
    y = np.arange(len(top))
    a1.barh(y, top.values, height=0.55, color=[NARANJA if k.startswith("RESUELTA") else AZUL if k == "PAGADA" else NEUTRO for k in top.index])
    for yi, v in zip(y, top.values):
        a1.text(v + 15, yi, f"{v} ({v / len(P):.0%})", va="center", fontsize=9)
    a1.set_yticks(y); a1.set_yticklabels([k.title() if len(k) < 34 else k[:32].title() + "…" for k in top.index], fontsize=8.5)
    a1.set_xlim(0, top.max() * 1.22); a1.grid(axis="y", visible=False); a1.set_xlabel("Órdenes")
    a1.set_title("Estado de entrega de cada orden", fontsize=10, loc="left")
    m = P.monto_total
    bins = np.arange(np.floor(np.log10(m.min())), np.ceil(np.log10(m.max())) + 0.01, 0.2)
    a2.hist(np.log10(m), bins=bins, color=AZUL, edgecolor=SUP, linewidth=1.3)
    a2.axvline(np.log10(m.median()), color=TXT, lw=1.2, ls=(0, (4, 3)))
    a2.text(np.log10(m.median()) + 0.05, a2.get_ylim()[1] * 0.93, f"mediana S/ {miles(m.median())}", fontsize=8.5)
    a2.set_xticks(range(3, 8)); a2.set_xticklabels([abrev(10**k) for k in range(3, 8)])
    a2.set_xlabel("Monto total de la orden (S/, escala log)"); a2.set_ylabel("Órdenes"); a2.grid(axis="x", visible=False)
    a2.set_title(f"Orden máxima S/ {m.max() / 1e6:.1f} M, {m.max() / m.median():,.0f}× la mediana", fontsize=10, loc="left")
    titulo(fig, f"En Perú Compras, {(P.estado_entrega.str.startswith('RESUELTA').mean()):.0%} de las órdenes quedaron resueltas",
           "Una orden resuelta es un contrato terminado: si se cuenta como compra, se infla el tamaño del mercado.")
    guardar(fig, carpeta, "05_perucompras.png", "Acuerdo Marco 322-BIENES. «Resuelta» en naranja.")


# ------------------------------------------------------- 6. cobertura en el tiempo
def g_tiempo(t, carpeta):
    L = t["licitaciones"].copy()
    L["mes"] = pd.to_datetime(L.fecha).dt.to_period("M")
    serie = L.groupby("mes").size()
    idx = pd.period_range(serie.index.min(), serie.index.max(), freq="M")
    serie = serie.reindex(idx, fill_value=0)
    db = RAIZ / "data" / "analisis.db"
    hay_post = db.exists()
    fig, axs = plt.subplots(1, 2 if hay_post else 1, figsize=(12 if hay_post else 9.5, 4.9), squeeze=False)
    fig.subplots_adjust(left=0.07, right=0.97, top=0.78, bottom=0.2, wspace=0.2)
    a = axs[0][0]
    ult = str(L.fecha.max())[:10]
    colores = [NEUTRO if i == len(serie) - 1 else AZUL for i in range(len(serie))]
    a.bar(range(len(serie)), serie.values, width=0.7, color=colores)
    a.set_xticks(range(0, len(serie), 3)); a.set_xticklabels([str(p) for p in serie.index[::3]], rotation=45, ha="right", fontsize=8.5)
    a.set_ylabel("Procesos del rubro"); a.grid(axis="x", visible=False)
    a.set_title(f"Histórico: procesos por mes (último mes incompleto, hasta {ult})", fontsize=10, loc="left")
    sub = "Los meses de mayor actividad pueden ser estacionales (cierre de presupuesto); el último mes (gris) está incompleto."
    if hay_post:
        con = sqlite3.connect(db)
        pp = pd.read_sql("select anio, ocid, count(*) n from postores group by anio, ocid", con)
        con.close()
        g = pp.groupby("anio").n.agg(["median", "count"])
        b = axs[0][1]
        b.bar(g.index.astype(str), g["median"], width=0.55, color=AZUL)
        for xi, (m_, c_) in enumerate(zip(g["median"], g["count"])):
            b.text(xi, m_ + 0.3, f"{m_:.0f}\n({c_} proc.)", ha="center", fontsize=8.5)
        b.set_ylabel("Postores por proceso (mediana)"); b.grid(axis="x", visible=False)
        b.set_title("Un año con muchos menos postores suele ser peor registro, no menos competencia", fontsize=9.5, loc="left")
        sub = "Izquierda: cobertura del histórico. Derecha: lista de postores publicada por año."
    titulo(fig, "¿Los datos cubren todo el período de forma pareja?", sub)
    guardar(fig, carpeta, "06_cobertura_en_el_tiempo.png")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", default=str(RAIZ / "data" / "graficos"))
    a = ap.parse_args()
    carpeta = Path(a.salida); carpeta.mkdir(parents=True, exist_ok=True)
    t = cargar()
    print(f"Generando gráficos en {carpeta}")
    for g in (g_completitud, g_embudo, g_rubro, g_montos, g_perucompras, g_tiempo):
        g(t, carpeta)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

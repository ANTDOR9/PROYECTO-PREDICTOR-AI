"""Qué empresas tienden a presentarse juntas, y si ese patrón se sostiene.

Medidas por par (A, B), sobre N procesos:
  soporte   procesos donde se presentaron las dos
  P(B|A)    de los procesos de A, en cuántos estuvo B
  lift      P(A y B) / (P(A) P(B)); 1 = lo esperado por azar
  p         cola de la hipergeométrica: probabilidad de ver ese soporte o más
            si A y B se repartieran al azar entre los procesos
  q         p corregido por Benjamini-Hochberg (se prueban cientos de pares)

Advertencia que el reporte repite: un lift alto mide que se junta MÁS de lo
esperado al azar, no por qué. Empresas de una misma región o rubro se juntan
sin ponerse de acuerdo. Sirve para priorizar qué expediente leer.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import hypergeom

from historial import Historial


def _bh(p: np.ndarray) -> np.ndarray:
    n = len(p)
    if n == 0:
        return p
    orden = np.argsort(p)
    q = np.empty(n)
    acum = 1.0
    for rango, i in zip(range(n, 0, -1), orden[::-1]):
        acum = min(acum, p[i] * n / rango)
        q[i] = acum
    return q


def pares(h: Historial, fecha_corte=None, min_soporte: int = 3) -> pd.DataFrame:
    n = h.n_procesos if fecha_corte is None else h.antes_de(fecha_corte)
    H = h.M[:n].astype(np.int32)
    if n == 0:
        return pd.DataFrame()
    f = H.sum(0)
    C = H.T @ H
    a_idx, b_idx = np.where(np.triu(C >= min_soporte, k=1))
    if len(a_idx) == 0:
        return pd.DataFrame()
    c = C[a_idx, b_idx]
    fa, fb = f[a_idx], f[b_idx]
    df = pd.DataFrame({
        "ruc_a": [h.rucs[i] for i in a_idx], "ruc_b": [h.rucs[i] for i in b_idx],
        "nombre_a": [h.nombres.get(h.rucs[i], "") for i in a_idx],
        "nombre_b": [h.nombres.get(h.rucs[i], "") for i in b_idx],
        "soporte": c, "procs_a": fa, "procs_b": fb,
        "p_b_dado_a": c / fa, "p_a_dado_b": c / fb,
        "lift": c * n / (fa * fb), "jaccard": c / (fa + fb - c),
    })
    df["p"] = hypergeom.sf(c - 1, n, fa, fb)
    df["q"] = _bh(df["p"].to_numpy())
    return df.sort_values(["q", "lift"], ascending=[True, False]).reset_index(drop=True)


def estabilidad(h: Historial, fecha_corte, q_max: float = 0.10, min_soporte: int = 3) -> dict:
    """¿Los pares fuertes ANTES del corte siguen juntándose DESPUÉS?

    Para cada par (A→B, con A la menos frecuente) compara, en los procesos
    posteriores al corte donde estuvo A, la tasa real de B contra la tasa de B
    en el resto de procesos posteriores. Si el patrón fuera ruido, la
    diferencia promedio sería cercana a cero.
    """
    tabla = pares(h, fecha_corte, min_soporte)
    if tabla.empty:
        return {"pares": 0}
    fuertes = tabla[(tabla["q"] <= q_max) & (tabla["lift"] > 1)]
    n0 = h.antes_de(fecha_corte)
    T = h.M[n0:]
    if len(T) < 5 or fuertes.empty:
        return {"pares": len(fuertes), "procesos_posteriores": len(T)}
    difs, usados = [], 0
    for _, r in fuertes.iterrows():
        a, b = h.col[r.ruc_a], h.col[r.ruc_b]
        if r.procs_a > r.procs_b:
            a, b = b, a
        con_a, sin_a = T[T[:, a]], T[~T[:, a]]
        if len(con_a) < 2 or len(sin_a) < 2:
            continue
        difs.append(con_a[:, b].mean() - sin_a[:, b].mean())
        usados += 1
    if not difs:
        return {"pares": len(fuertes), "procesos_posteriores": len(T), "evaluables": 0}
    difs = np.array(difs)
    return {"pares": len(fuertes), "evaluables": usados, "procesos_posteriores": len(T),
            "dif_media": float(difs.mean()), "pares_que_siguen": int((difs > 0).sum())}


def companeros(h: Historial, ruc: str, top: int = 8, min_soporte: int = 2) -> pd.DataFrame:
    """Con quién se ha presentado más una empresa, por P(B|A)."""
    if ruc not in h.col:
        return pd.DataFrame()
    a = h.col[ruc]
    fa = h.M[:, a].sum()
    co = h.M[h.M[:, a]].sum(0)
    filas = [(h.rucs[j], h.nombres.get(h.rucs[j], ""), int(co[j]), co[j] / fa)
             for j in np.argsort(-co) if j != a and co[j] >= min_soporte][:top]
    return pd.DataFrame(filas, columns=["ruc", "nombre", "veces_juntas", "p_b_dado_a"])

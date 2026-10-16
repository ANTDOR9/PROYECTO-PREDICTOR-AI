"""¿Qué empresas probablemente se presenten a un proceso nuevo?

Pipeline (los pasos del esquema de aprendizaje, uno por línea de código):
  huecos     SimpleImputer + indicador de "faltaba"  (no se inventa el dato)
  escalas    StandardScaler
  inútil     VarianceThreshold (descarta columnas constantes)
  modelo     LogisticRegression -> probabilidad de participar
  decisión   ranking de candidatas; se muestra la probabilidad, no un sí/no
  comprobar  validar.py: entrena con el pasado y prueba en el futuro, contra
             la línea base "las más frecuentes"

Solo son candidatas las empresas con al menos una participación previa: una
empresa nueva es imposible de predecir con historial, y validar.py informa
qué fracción de los postores reales cayó fuera por eso.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.feature_selection import VarianceThreshold
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from historial import Historial, norm

COLUMNAS = ["log_freq", "log_recientes", "frac_mismo_depto", "log_misma_entidad",
            "tasa_victorias", "log_dias_desde_ultima", "cond_max", "hay_conocidos"]
MIN_HISTORIA = 5     # procesos previos mínimos para generar filas de entrenamiento


def nuevo_modelo() -> Pipeline:
    return Pipeline([
        ("huecos", SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)),
        ("escalas", StandardScaler()),
        ("inutil", VarianceThreshold(0.0)),
        ("modelo", LogisticRegression(max_iter=2000)),
    ])


def features(h: Historial, fecha, entidad, depto, conocidos=()):
    """Matriz (empresas x COLUMNAS) calculada con lo que pasó ANTES de `fecha`."""
    fecha = np.datetime64(pd.Timestamp(fecha), "D")
    n = h.antes_de(fecha)
    if n == 0:
        return None, np.zeros(len(h.rucs), bool)
    H, Wm = h.M[:n], h.W[:n]
    dias = (fecha - h.fechas[:n]).astype(int)
    freq = H.sum(0).astype(float)
    cand = freq > 0
    rec = H[dias <= 365].sum(0)
    e, d = norm(entidad), norm(depto)
    fe = H[h.entidad[:n] == e].sum(0) if e else np.zeros(len(freq))
    if d:
        fd = H[h.depto[:n] == d].sum(0)
        frac_d = np.divide(fd, freq, out=np.full(len(freq), np.nan), where=freq > 0)
    else:
        frac_d = np.full(len(freq), np.nan)
    ultima = n - 1 - np.argmax(H[::-1], axis=0)
    dias_ult = np.where(cand, dias[ultima], np.nan)
    win = np.divide(Wm.sum(0), freq, out=np.zeros(len(freq)), where=freq > 0)
    cond = np.zeros(len(freq))
    Hf = H.astype(np.float32)
    for a in conocidos:
        if freq[a] > 0:
            cond = np.maximum(cond, (Hf[:, a] @ Hf) / freq[a])
    X = np.column_stack([np.log1p(freq), np.log1p(rec), frac_d, np.log1p(fe), win,
                         np.log1p(dias_ult), cond,
                         np.full(len(freq), 1.0 if len(conocidos) else 0.0)])
    for a in conocidos:
        cand[a] = False          # la empresa dada como conocida no se predice
    return X, cand


def datos_entrenamiento(h: Historial, hasta_fecha=None, semilla: int = 0):
    """Una fila por (proceso, empresa candidata). En la mitad de los procesos
    se finge conocer a un participante, para que el modelo aprenda a usar la
    asociación cuando exista esa pista."""
    rng = np.random.default_rng(semilla)
    limite = h.n_procesos if hasta_fecha is None else h.antes_de(hasta_fecha)
    Xs, ys = [], []
    for i in range(MIN_HISTORIA, limite):
        part = np.flatnonzero(h.M[i])
        conocidos = ()
        if len(part) >= 2 and rng.random() < 0.5:
            conocidos = (int(rng.choice(part)),)
        X, cand = features(h, h.fechas[i], h.procs.at[i, "entidad"],
                           h.procs.at[i, "depto"], conocidos)
        if X is None or cand.sum() == 0:
            continue
        Xs.append(X[cand])
        ys.append(h.M[i][cand])
    if not Xs:
        return np.empty((0, len(COLUMNAS))), np.empty(0, bool)
    return np.vstack(Xs), np.concatenate(ys)


def entrenar(h: Historial, hasta_fecha=None, semilla: int = 0) -> Pipeline:
    X, y = datos_entrenamiento(h, hasta_fecha, semilla)
    if len(y) == 0 or y.sum() == 0 or y.all():
        raise ValueError("Historial insuficiente para entrenar (hacen falta varios "
                         "procesos con postores).")
    m = nuevo_modelo()
    m.fit(X, y)
    return m


def predecir(modelo: Pipeline, h: Historial, fecha, entidad="", depto="",
             conocidos_ruc=(), top: int = 10) -> pd.DataFrame:
    conocidos = tuple(h.col[r] for r in conocidos_ruc if r in h.col)
    X, cand = features(h, fecha, entidad, depto, conocidos)
    if X is None or cand.sum() == 0:
        return pd.DataFrame(columns=["ruc", "nombre", "prob", "participaciones_previas"])
    idx = np.flatnonzero(cand)
    prob = modelo.predict_proba(X[idx])[:, 1]
    orden = np.argsort(-prob)[:top]
    return pd.DataFrame({
        "ruc": [h.rucs[idx[o]] for o in orden],
        "nombre": [h.nombres.get(h.rucs[idx[o]], "") for o in orden],
        "prob": prob[orden].round(3),
        "participaciones_previas": [int(np.expm1(X[idx[o], 0]).round()) for o in orden],
    })

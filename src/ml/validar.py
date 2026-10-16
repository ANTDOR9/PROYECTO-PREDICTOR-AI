"""Comprueba si el predictor de postores mejora de verdad.

    python src/ml/validar.py                       # base real: data/analisis.db
    python src/ml/validar.py --test-anio 2026
    python src/ml/validar.py --sintetico           # datos de prueba con estructura
    python src/ml/validar.py --sintetico --azar    # azar puro: NO debe ganar

Entrena con los procesos ANTERIORES al año de prueba y evalúa en ese año,
contra una línea base: "las empresas que más se han presentado". La mejora se
declara real solo si el intervalo de confianza (bootstrap por proceso) de la
diferencia en aciertos queda por encima de cero.
"""
import argparse
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parent))
import asociaciones, historial, predictor, sintetico  # noqa: E402


def evaluar(h, fecha_corte, k=10, semilla=0, escenarios=("sin_conocidos", "un_conocido")):
    modelo = predictor.entrenar(h, fecha_corte, semilla)
    rng = np.random.default_rng(semilla + 1)
    i0 = h.antes_de(fecha_corte)
    res = {}
    for esc in escenarios:
        filas, y_all, p_all, b_all = [], [], [], []
        for i in range(i0, h.n_procesos):
            part = np.flatnonzero(h.M[i])
            conocidos = ()
            if esc == "un_conocido":
                if len(part) < 2:
                    continue
                conocidos = (int(rng.choice(part)),)
            X, cand = predictor.features(h, h.fechas[i], h.procs.at[i, "entidad"],
                                         h.procs.at[i, "depto"], conocidos)
            if X is None or cand.sum() == 0:
                continue
            real = h.M[i].copy()
            for c in conocidos:
                real[c] = False
            n_real = int(real.sum())
            if n_real == 0:
                continue
            idx = np.flatnonzero(cand)
            y = real[idx]
            p = modelo.predict_proba(X[idx])[:, 1]
            base = X[idx, 0]                       # línea base: log de frecuencia
            kk = min(k, len(idx))
            hit_m = y[np.argsort(-p)[:kk]].sum()
            hit_b = y[np.argsort(-base)[:kk]].sum()
            filas.append({"candidatas": len(idx), "reales": n_real,
                          "reales_candidatas": int(y.sum()), "hit_modelo": hit_m,
                          "hit_base": hit_b, "hit_azar": kk * y.sum() / len(idx), "k": kk})
            y_all.append(y); p_all.append(p); b_all.append(base)
        if not filas:
            res[esc] = None
            continue
        f = pd.DataFrame(filas)
        y_c, p_c, b_c = map(np.concatenate, (y_all, p_all, b_all))
        dif = (f["hit_modelo"] - f["hit_base"]).to_numpy(float)
        rng_b = np.random.default_rng(0)
        medias = [rng_b.choice(dif, len(dif)).mean() for _ in range(2000)]
        res[esc] = {
            "procesos": len(f),
            "cobertura_candidatas": f["reales_candidatas"].sum() / f["reales"].sum(),
            "aciertos_top_k": {"modelo": f["hit_modelo"].mean(), "base": f["hit_base"].mean(),
                               "azar": f["hit_azar"].mean(), "k": int(f["k"].iloc[0])},
            "auc": {"modelo": roc_auc_score(y_c, p_c) if 0 < y_c.sum() < len(y_c) else float("nan"),
                    "base": roc_auc_score(y_c, b_c) if 0 < y_c.sum() < len(y_c) else float("nan")},
            "dif_media": dif.mean(), "ic95": (np.percentile(medias, 2.5), np.percentile(medias, 97.5)),
            "procesos_donde_gana": int((dif > 0).sum()), "empates": int((dif == 0).sum()),
        }
    return res


def informe(res, corte):
    print(f"\n=== VALIDACIÓN: entrenado con procesos anteriores a {corte:%Y-%m-%d} ===")
    for esc, r in res.items():
        t = "sin ninguna pista" if esc == "sin_conocidos" else "sabiendo que ya se presentó 1 empresa"
        print(f"\n— Escenario: {t}")
        if r is None:
            print("  (sin procesos evaluables)"); continue
        a = r["aciertos_top_k"]
        print(f"  Procesos de prueba: {r['procesos']}   "
              f"Postores reales que eran candidatas: {r['cobertura_candidatas']:.0%}")
        print(f"  Aciertos en el top-{a['k']} por proceso:  modelo {a['modelo']:.2f} · "
              f"línea base {a['base']:.2f} · azar {a['azar']:.2f}")
        print(f"  AUC:  modelo {r['auc']['modelo']:.3f} · línea base {r['auc']['base']:.3f}")
        lo, hi = r["ic95"]
        print(f"  Diferencia modelo−base: {r['dif_media']:+.2f} aciertos/proceso "
              f"(IC95% {lo:+.2f} a {hi:+.2f}); gana en {r['procesos_donde_gana']} "
              f"de {r['procesos']} procesos, empata en {r['empates']}")
        if r["procesos"] < 15:
            veredicto = "MUY POCOS procesos de prueba: no concluyente"
        elif lo > 0:
            veredicto = "MEJORA REAL sobre la línea base"
        elif hi < 0:
            veredicto = "PEOR que la línea base"
        else:
            veredicto = "SIN MEJORA demostrable (el IC incluye 0)"
        print(f"  >> {veredicto}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(historial.DB))
    ap.add_argument("--categoria", default="INTERACTIVA")
    ap.add_argument("--test-anio", type=int, default=2026)
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--sintetico", action="store_true")
    ap.add_argument("--azar", action="store_true", help="con --sintetico: sin estructura")
    a = ap.parse_args()

    db = a.db
    if a.sintetico:
        db = Path(tempfile.mkdtemp()) / "sint.db"
        sintetico.generar(db, estructura=not a.azar)
    elif not Path(db).exists():
        print(f"No existe {db}. Genera la base con:  python src/postores.py --anios 2023 2024 2025 2026 "
              f"--solo INTERACTIVA\n(o prueba con --sintetico)")
        return 1
    df = historial.cargar(db, a.categoria)
    h = historial.Historial(df)
    corte = pd.Timestamp(f"{a.test_anio}-01-01")
    print(f"Procesos: {h.n_procesos} · empresas: {len(h.rucs)} · "
          f"participaciones: {int(h.M.sum())} · prueba desde {a.test_anio}")
    if h.antes_de(corte) < 10 or h.n_procesos - h.antes_de(corte) < 3:
        print("Hay muy pocos procesos antes/después del corte. Cambia --test-anio.")
        return 1
    informe(evaluar(h, corte, a.k), corte)

    print("\n=== ASOCIACIONES (pares que se presentan juntos) ===")
    t = asociaciones.pares(h, corte)
    if t.empty:
        print("  sin pares con soporte suficiente")
    else:
        top = t[t["q"] <= 0.10].head(8)
        print(f"  Pares con q<=0.10 antes del corte: {(t['q'] <= 0.10).sum()} de {len(t)} evaluados")
        for _, r in top.iterrows():
            print(f"   {r.nombre_a[:28]:28} ↔ {r.nombre_b[:28]:28} juntas {int(r.soporte)} veces · "
                  f"lift {r.lift:.1f} · q={r.q:.3f}")
        e = asociaciones.estabilidad(h, corte)
        print(f"  ¿Se sostienen después del corte?  {e}")
        print("  Ojo: lift alto = se juntan más que el azar, no concertación (misma región/rubro).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

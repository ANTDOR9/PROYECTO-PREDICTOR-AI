"""Estima qué empresas se presentarían a un proceso.

    python src/predecir_postores.py --entidad "UNIVERSIDAD NACIONAL SAN AGUSTIN" --depto AREQUIPA --fecha 2026-11-01
    python src/predecir_postores.py ... --conocidos 20123456789
"""
import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "ml"))
import historial, predictor  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--entidad", default=""); ap.add_argument("--depto", default="")
ap.add_argument("--fecha", required=True); ap.add_argument("--conocidos", nargs="*", default=[])
ap.add_argument("--top", type=int, default=10); ap.add_argument("--db", default=str(historial.DB))
a = ap.parse_args()
h = historial.Historial(historial.cargar(a.db))
m = predictor.entrenar(h)
out = predictor.predecir(m, h, a.fecha, a.entidad, a.depto, a.conocidos, a.top)
print(out.to_string(index=False))
print("\nEstimación del historial, no una afirmación sobre ninguna empresa. Valídala con src/ml/validar.py")

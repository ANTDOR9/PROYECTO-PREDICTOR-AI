"""Compara un requerimiento contra las fichas y lo explica con el modelo local.

    python src/analizar_ia.py --demo
    python src/analizar_ia.py --json data/resultado_extractor.json --expediente 7
    python src/analizar_ia.py --pdf bases.pdf          # extrae con reglas + IA y compara

El dictamen lo calcula siempre el motor de reglas; la IA solo lo redacta.
"""
import argparse, json, sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "ia"))
from evaluar_licitacion import DEMO, evaluar_todas  # noqa: E402
import cliente, explicar, extraer_llm  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--json")
    ap.add_argument("--expediente")
    ap.add_argument("--pdf")
    a = ap.parse_args()

    e = cliente.estado()
    if not (e["servidor"] and e["modelo"]):
        print("El modelo local no está listo. Corre: python src/ia/comprobar_ia.py")
        return 1

    if a.pdf:
        from extractor import localizar
        b = localizar(a.pdf)
        if not b.texto:
            print("No se localizó el requerimiento técnico en el PDF."); return 1
        specs, descartados = extraer_llm.extraer(b.texto)
        req = asdict(specs)
        if descartados:
            print("Descartado por no figurar en el texto:", ", ".join(descartados))
    elif a.json and a.expediente:
        datos = json.loads(Path(a.json).read_text(encoding="utf-8"))
        d = next((x for x in datos if str(x.get("expediente")) == a.expediente and x.get("specs")), None)
        if not d:
            print("Expediente sin specs."); return 1
        req = d["specs"]
    else:
        req = DEMO

    for r in evaluar_todas(req):
        print(f"\n== {r.ficha.marca} {r.ficha.modelo} — {r.dictamen}")
        print(explicar.explicar(r))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

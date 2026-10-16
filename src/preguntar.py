"""Pregunta a tus datos en español.

    python src/preguntar.py "¿Qué empresas se presentaron más veces?"
    python src/preguntar.py            # modo conversación

Tras cada respuesta puedes confirmar que la consulta fue correcta: se guarda y
se usa como ejemplo en preguntas futuras parecidas.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "ia"))
import cliente, consultas as P  # noqa: E402


def responder(q: str) -> None:
    r = P.preguntar(q)
    if not r["ok"]:
        print(f"✗ {r['motivo']}" + (f"\n  SQL: {r['sql']}" if r.get("sql") else ""))
        return
    print(f"\nSQL: {r['sql']}\n")
    print(" | ".join(r["columnas"]))
    for f in r["filas"][:15]:
        print(" | ".join(str(x) for x in f))
    if len(r["filas"]) > 15:
        print(f"... ({len(r['filas'])} filas{'+' if r['truncado'] else ''})")
    print(f"\n→ {r['resumen']}")
    if input("¿Fue correcta? (s = guardar para aprender / Enter = no) ").strip().lower() == "s":
        print("Guardada." if P.aprender(q, r["sql"]) else "Ya la tenía.")


def main() -> int:
    e = cliente.estado()
    if not (e["servidor"] and e["modelo"]):
        print("El modelo local no está listo. Corre: python src/ia/comprobar_ia.py")
        return 1
    if len(sys.argv) > 1:
        responder(" ".join(sys.argv[1:]))
        return 0
    print("Pregunta lo que quieras sobre tus licitaciones y postores (vacío = salir).")
    while (q := input("\n> ").strip()):
        responder(q)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

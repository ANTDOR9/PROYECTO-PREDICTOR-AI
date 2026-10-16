"""Alerta diaria: oportunidades vigentes relevantes, ya filtradas, evaluadas y explicadas.

    python src/alerta_diaria.py                 # usa lo último que haya en la base
    python src/alerta_diaria.py --actualizar    # baja primero las vigentes del SEACE
    python src/alerta_diaria.py --sin-ia        # solo palabras clave y fichas

Por cada oportunidad vigente del rubro:
  1. la IA confirma si es de verdad un panel interactivo (descarta falsos positivos)
  2. cruza el tamaño pedido con las fichas de BTOUCH y la competencia
  3. el predictor estima qué empresas probablemente se presenten
  4. la IA redacta 2-3 líneas: por qué mirarla y qué verificar
Escribe data/alertas/alerta_AAAA-MM-DD.md.
"""
import argparse
import json
import re
import sqlite3
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
for sub in ("", "ia", "ml"):
    sys.path.insert(0, str(RAIZ / "src" / sub) if sub else str(RAIZ / "src"))

import vigentes as V  # noqa: E402
from fichas import por_tamano  # noqa: E402

DB = RAIZ / "data" / "licitaciones.db"
DB_AN = RAIZ / "data" / "analisis.db"
CACHE = RAIZ / "data" / "cache_ia_clasificacion.json"
SALIDA = RAIZ / "data" / "alertas"

DEPTOS = ["AMAZONAS", "ANCASH", "APURIMAC", "AREQUIPA", "AYACUCHO", "CAJAMARCA", "CALLAO",
          "CUSCO", "HUANCAVELICA", "HUANUCO", "ICA", "JUNIN", "LA LIBERTAD", "LAMBAYEQUE",
          "LIMA", "LORETO", "MADRE DE DIOS", "MOQUEGUA", "PASCO", "PIURA", "PUNO",
          "SAN MARTIN", "TACNA", "TUMBES", "UCAYALI"]


def fecha(s):
    try:
        return datetime.strptime(str(s)[:10], "%d/%m/%Y").date()
    except ValueError:
        return None


def depto_de(texto: str) -> str:
    t = V.norm(texto).upper()
    for d in DEPTOS:
        if re.search(rf"\b{d}\b", t):
            return d
    return ""


def pulgadas(texto: str):
    m = re.search(r"(\d{2,3})\s*(?:\"|''|”|pulg)", texto, re.I)
    if m and 40 <= int(m.group(1)) <= 120:
        return int(m.group(1))
    return None


def candidatas(hoy: date):
    cfg = V.cfg()
    claves, excluir = cfg["palabras_clave"], cfg["palabras_excluir"]
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    filas = []
    for r in con.execute("select * from vigentes"):
        fin = fecha(r["fecha_fin_inscripcion"])
        if not fin or fin < hoy:
            continue
        texto = V.norm(f"{r['objeto']} {r['descripcion']}")
        if V.coincide(texto, [V.norm(c) for c in claves], [V.norm(x) for x in excluir]):
            d = dict(r)
            d["dias"] = (fin - hoy).days
            filas.append(d)
    con.close()
    return sorted(filas, key=lambda d: d["dias"])


def clasificar_todas(filas, max_ia):
    from clasificar_llm import clasificar
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    llamadas = 0
    for f in filas:
        k = str(f["id"])
        if k not in cache and llamadas < max_ia:
            cache[k] = clasificar(f["descripcion"] or f["objeto"], f["objeto"] or "")
            llamadas += 1
        f["ia"] = cache.get(k)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return llamadas


def competidores(filas, top):
    """Añade `rivales` a cada fila si hay base de análisis; devuelve un aviso si no."""
    if not DB_AN.exists():
        return "Sin data/analisis.db: no se estimaron competidores (corre src/postores.py)."
    import historial, predictor
    h = historial.Historial(historial.cargar(DB_AN))
    if h.n_procesos < 15:
        return "Historial de postores insuficiente para estimar competidores."
    modelo = predictor.entrenar(h)
    for f in filas:
        f_pres = fecha(f["fecha_presentacion"]) or date.today()
        f["rivales"] = predictor.predecir(modelo, h, f_pres, f["entidad"],
                                          depto_de(f["entidad"]), top=top).to_dict("records")
    return ""


def redactar(f):
    from cliente import chat
    hechos = [f"Entidad: {f['entidad']}", f"Objeto: {f['descripcion']}",
              f"Valor referencial: {f['valor_referencial']}", f"Cierra inscripción en {f['dias']} día(s)",
              f"Tipo: {f['tipo_proceso']}"]
    if f.get("pulg"):
        hechos.append(f"Tamaño pedido: {f['pulg']} pulgadas. Fichas con ese tamaño: "
                      + (", ".join(f"{x.marca} {x.modelo}" for x in f["fichas"]) or "ninguna"))
    if f.get("rivales"):
        hechos.append("Competidores probables (probabilidad estimada): "
                      + ", ".join(f"{r['nombre']} {r['prob']:.0%}" for r in f["rivales"][:5]))
    return chat("Eres analista comercial de una empresa de paneles interactivos BTOUCH. "
                "Con los hechos dados escribe 2 o 3 líneas en español: por qué conviene mirar esta "
                "oportunidad y qué verificar en las bases. No inventes datos que no estén en los hechos.",
                "\n".join(hechos)).strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--actualizar", action="store_true")
    ap.add_argument("--sin-ia", action="store_true")
    ap.add_argument("--max-ia", type=int, default=40, help="máximo de clasificaciones nuevas por corrida")
    ap.add_argument("--rivales", type=int, default=5)
    a = ap.parse_args()

    if a.actualizar:
        subprocess.run([sys.executable, str(RAIZ / "src" / "vigentes.py")], check=True)
    hoy = date.today()
    filas = candidatas(hoy)
    avisos = []

    usar_ia = not a.sin_ia
    if usar_ia:
        import cliente
        e = cliente.estado()
        if not (e["servidor"] and e["modelo"]):
            avisos.append("El modelo local no respondió: se omitió la confirmación por IA y los resúmenes.")
            usar_ia = False
    if usar_ia:
        n = clasificar_todas(filas, a.max_ia)
        sin_clasif = sum(1 for f in filas if not f.get("ia"))
        if sin_clasif:
            avisos.append(f"{sin_clasif} oportunidad(es) sin clasificar por IA (tope --max-ia={a.max_ia}); vuelve a correr.")
        descartadas = [f for f in filas if f.get("ia") and not f["ia"]["es_panel_interactivo"]]
        filas_ok = [f for f in filas if not f.get("ia") or f["ia"]["es_panel_interactivo"]]
    else:
        descartadas, filas_ok = [], filas

    for f in filas_ok:
        f["pulg"] = pulgadas(f"{f['descripcion']} {f['objeto']}")
        f["fichas"] = por_tamano(f["pulg"]) if f["pulg"] else []
    aviso = competidores(filas_ok, a.rivales)
    if aviso:
        avisos.append(aviso)

    L = [f"# Alerta de oportunidades — {hoy:%d/%m/%Y}", ""]
    L.append(f"{len(filas_ok)} oportunidad(es) vigente(s) del rubro"
             + (f"; la IA descartó {len(descartadas)} como falso positivo." if descartadas else "."))
    for av in avisos:
        L.append(f"\n> ⚠️ {av}")
    for f in filas_ok:
        L += ["", f"## {f['nomenclatura']} — cierra en {f['dias']} día(s)",
              f"**{f['entidad']}** · {f['tipo_proceso']} · valor ref.: {f['valor_referencial']}",
              f"{f['descripcion']}", f"[Ficha en el SEACE]({f['enlace']})" if f.get("enlace") else ""]
        if f["pulg"]:
            L.append("Fichas de ese tamaño: " + (", ".join(f"{x.marca} {x.modelo}" for x in f["fichas"])
                                                 or "ninguna en el catálogo"))
        if f.get("rivales"):
            L.append("Competidores probables: " + "; ".join(
                f"{r['nombre']} ({r['prob']:.0%})" for r in f["rivales"]))
        if usar_ia:
            try:
                L += ["", "🤖 " + redactar(f)]
            except Exception as e:  # noqa: BLE001
                L.append(f"(sin resumen de IA: {e})")
    if descartadas:
        L += ["", "---", "Descartadas por la IA (revisa si alguna sí interesa):"]
        L += [f"- {f['nomenclatura']}: {f['descripcion'][:90]} — {f['ia']['motivo']}" for f in descartadas]
    SALIDA.mkdir(parents=True, exist_ok=True)
    ruta = SALIDA / f"alerta_{hoy:%Y-%m-%d}.md"
    ruta.write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L[:12]))
    print(f"\nGuardado en {ruta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

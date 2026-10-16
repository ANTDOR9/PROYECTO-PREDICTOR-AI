"""Alerta diaria de punta a punta con modelo simulado y postores sintéticos.
Ejecutar:  python tests/test_alerta.py"""
import sys, tempfile, json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(RAIZ / "src"), str(RAIZ / "src" / "ia"), str(RAIZ / "src" / "ml")]
import cliente, clasificar_llm, sintetico  # noqa: E402
import alerta_diaria as A  # noqa: E402

tmp = Path(tempfile.mkdtemp())
sintetico.generar(tmp / "an.db", procesos_por_anio=30)
A.DB_AN, A.CACHE, A.SALIDA = tmp / "an.db", tmp / "cache.json", tmp / "alertas"

cliente.estado = lambda cfg=None: {"servidor": True, "modelo": True, "elegido": "falso"}
def falso_json(sistema, usuario, json_modo=False, cfg=None):
    if json_modo:
        panel = "LED" not in usuario            # simula descartar la pantalla LED
        return {"categoria": "INTERACTIVA" if panel else "LED/VIDEOWALL",
                "es_panel_interactivo": panel, "motivo": "simulado"}
    return "Mirar los requisitos de OPS."
clasificar_llm.chat = falso_json
cliente.chat = falso_json

sys.argv = ["alerta_diaria.py"]
assert A.main() == 0
md = next((tmp / "alertas").glob("alerta_*.md")).read_text(encoding="utf-8")
assert "🤖 Mirar los requisitos" in md
assert "Descartadas por la IA" in md and "PANTALLA LED DE GRAN FORMATO" in md
assert "Competidores probables" in md
assert json.loads((tmp / "cache.json").read_text())      # la clasificación quedó en caché
print("OK: alerta diaria verificada")

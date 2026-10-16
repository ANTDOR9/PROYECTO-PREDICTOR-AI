"""Prueba la capa de IA contra un Ollama simulado (no requiere modelo real).
Ejecutar:  python tests/test_ia.py"""
import json, sys, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(RAIZ / "src"), str(RAIZ / "src" / "ia")]

import cliente, extraer_llm, clasificar_llm, explicar  # noqa: E402
from evaluar_licitacion import DEMO, evaluar_todas  # noqa: E402

RESPUESTA = {"msg": ""}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(200); self.end_headers()
        self.wfile.write(json.dumps({"models": [{"name": "falso:1b"}]}).encode())
    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        self.send_response(200); self.end_headers()
        self.wfile.write(json.dumps({"message": {"content": RESPUESTA["msg"]}}).encode())

srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
CFG = {"url": f"http://127.0.0.1:{srv.server_port}", "modelo": "falso:1b",
       "temperatura": 0, "timeout_s": 10, "contexto_tokens": 2048}

TEXTO = "Pantalla interactiva de 86 pulgadas, 4K 3840 x 2160, brillo 410 cd/m2, garantia 36 meses."

# estado
assert cliente.estado(CFG)["modelo"] is True
assert cliente.estado({**CFG, "modelo": "otro"})["modelo"] is False

e = cliente.estado({**CFG, "modelo": "auto"})
assert e["elegido"] == "falso:1b"
assert cliente.resolver_modelo({"modelo": "auto"}, ["nomic-embed-text:latest", "llama3.2:3b"]) == "llama3.2:3b"
assert cliente.resolver_modelo({"modelo": "auto"}, ["nomic-embed-text:latest"]) is None

# extracción: lo respaldado pasa, lo inventado se descarta, tipos se convierten
RESPUESTA["msg"] = json.dumps({"tamano_pulgadas": 86, "brillo_cdm2": "410", "garantia_meses": 36,
                               "ram_gb": 16, "ops_requerido": None})
s, desc = extraer_llm.extraer(TEXTO, CFG)
assert (s.tamano_pulgadas, s.brillo_cdm2, s.garantia_meses) == (86.0, 410.0, 36.0), s
assert s.ram_gb is None and any("ram_gb" in d for d in desc), desc   # 16 no está en el texto

# JSON con relleno alrededor
RESPUESTA["msg"] = 'Claro:\n{"tamano_pulgadas": 86}\nListo.'
assert extraer_llm.extraer(TEXTO, CFG)[0].tamano_pulgadas == 86.0

# clasificación: categoría inválida -> OTRO; no-INTERACTIVA nunca es panel
RESPUESTA["msg"] = json.dumps({"categoria": "INVENTADA", "es_panel_interactivo": True, "motivo": "x"})
r = clasificar_llm.clasificar("SMART CARD DNIe", cfg=CFG)
assert r["categoria"] == "OTRO" and r["es_panel_interactivo"] is False

# explicación: recibe la tabla del motor
RESPUESTA["msg"] = "Podía cumplir."
res = evaluar_todas(DEMO)[0]
assert "Dictamen:" in explicar.tabla(res)
assert explicar.explicar(res, CFG) == "Podía cumplir."

# error del servidor
srv.shutdown()
try:
    cliente.chat("a", "b", cfg=CFG); raise SystemExit("debió fallar")
except cliente.IAError:
    pass
print("OK: capa de IA verificada con servidor simulado")

"""Prueba la cara nueva del asistente: chat, globos de sugerencias, configuración con las
especificaciones del equipo y colores que se leen en modo claro y oscuro.
No necesita Ollama ni red: el servidor de IA y las respuestas son simulados.
Ejecutar:  python tests/test_interfaz.py"""
import json
import re
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
RUTAS = [str(RAIZ / "src"), str(RAIZ / "src" / "ia"), str(RAIZ / "src" / "ml")]
sys.path[:0] = RUTAS

import equipo  # noqa: E402
import estilo  # noqa: E402

# ------------------------------------------------------------------ especificaciones del equipo
s = equipo.especificaciones()
assert {"sistema", "cpu", "nucleos", "ram_total_gb", "ram_libre_gb", "gpus", "vram_gb", "disco_libre_gb"} <= set(s), s
assert s["ram_total_gb"] is None or s["ram_total_gb"] > 0

# sin psutil (en tu equipo puede no estar instalado) debe seguir leyendo la memoria
visto = sys.modules.get("psutil", "ausente")
sys.modules["psutil"] = None                                     # fuerza ImportError
try:
    total, libre = equipo._ram()
finally:
    if visto == "ausente":
        sys.modules.pop("psutil", None)
    else:
        sys.modules["psutil"] = visto
assert total is None or total > 0

assert equipo._parsear_nvidia("NVIDIA GeForce GTX 1650, 4096\nNVIDIA T400, 2048\n") == [
    {"nombre": "NVIDIA GeForce GTX 1650", "vram_gb": 4.0}, {"nombre": "NVIDIA T400", "vram_gb": 2.0}]
assert equipo._parsear_nvidia("") == [] and equipo._parsear_nvidia("No devices were found") == []
cpu, gpus = equipo._parsear_powershell(
    '{"cpu":"Intel(R) Core(TM) i5-10400 CPU @ 2.90GHz","gpu":["Intel(R) UHD Graphics 630","NVIDIA GeForce GTX 1650"]}')
assert cpu.startswith("Intel") and len(gpus) == 2
assert equipo._parsear_powershell('{"cpu":"AMD Ryzen 5","gpu":"AMD Radeon"}')[1] == ["AMD Radeon"]   # una sola tarjeta
assert equipo._parsear_powershell("esto no es json") == ("", [])

# la tarjeta que nvidia-smi ya mostró no se repite al sumar la lista de Windows
original = equipo._correr
equipo._correr = lambda cmd, timeout=8: "NVIDIA GeForce GTX 1650, 4096\n" if cmd[0] == "nvidia-smi" else ""
try:
    _, g = equipo._cpu_y_gpus()
finally:
    equipo._correr = original
assert g == [{"nombre": "NVIDIA GeForce GTX 1650", "vram_gb": 4.0}], g

poco = {"ram_total_gb": 4.0, "ram_libre_gb": 2.0}
medio = {"ram_total_gb": 8.0, "ram_libre_gb": 5.0}
mucho = {"ram_total_gb": 32.0, "ram_libre_gb": 20.0}
assert equipo.recomendar(poco)[0] == "qwen2.5:1.5b-instruct"
assert equipo.recomendar(medio)[0] == "qwen2.5:3b-instruct"
assert equipo.recomendar(mucho)[0] == "qwen2.5:7b-instruct"
assert equipo.ajuste("qwen2.5:7b-instruct", {"ram_total_gb": 10.0, "ram_libre_gb": 6.5}) == "justo"
assert equipo.ajuste("qwen2.5:7b-instruct", medio) == "no" and equipo.ajuste("qwen2.5:7b-instruct", poco) == "no"
assert equipo.ajuste("modelo-raro", medio) == "?"

import requests  # noqa: E402


class _R:
    def raise_for_status(self): pass
    def json(self): return {"models": [{"name": "qwen2.5:1.5b-instruct", "size": 2_000_000_000, "size_vram": 1_000_000_000}]}


viejo_get = requests.get
requests.get = lambda *a, **k: _R()
try:
    mem = equipo.en_memoria()
finally:
    requests.get = viejo_get
assert mem == [{"nombre": "qwen2.5:1.5b-instruct", "tam_gb": 1.9, "gpu_pct": 50}], mem
requests.get = lambda *a, **k: (_ for _ in ()).throw(ConnectionError("apagado"))
try:
    assert equipo.en_memoria() == []                             # Ollama apagado: lista vacía, no error
finally:
    requests.get = viejo_get

# ----------------------------------------------------------------------------- colores / tema
assert estilo.ANCHO in ({"width": "stretch"}, {"use_container_width": True})
for clave, css in estilo.FONDO_ESTADO.items():
    m = re.fullmatch(r"rgba\(\d+, \d+, \d+, (0?\.\d+)\)", css)
    assert m and float(m.group(1)) <= 0.4, f"{clave}: el fondo de una fila debe ser translúcido ({css})"
assert estilo.fondo("ok").startswith("background-color: rgba(") and estilo.fondo("x") == estilo.fondo("neutro")
assert "<style>" in estilo.CSS and "#E6E6E6".lower() not in estilo.CSS.lower()      # sin la pista clara fija de antes
toml = (RAIZ / ".streamlit" / "config.toml").read_text(encoding="utf-8")
assert "[theme.dark]" in toml and "[theme.light]" in toml, "el tema debe definir claro y oscuro"

# ------------------------------------------------------------ interfaz (Streamlit AppTest)
try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    print("OK: especificaciones y colores verificados (la prueba de interfaz se omitió: falta Streamlit)")
    raise SystemExit(0)

tmp = Path(tempfile.mkdtemp())
LISTO = {"servidor": True, "modelo": True, "elegido": "qwen2.5:1.5b-instruct",
         "disponibles": ["qwen2.5:1.5b-instruct", "qwen2.5:3b-instruct"]}
APAGADO = {"servidor": False, "modelo": False, "detalle": "sin conexión"}
SPECS = {"sistema": "Windows 11", "cpu": "Intel(R) Core(TM) i5-10400", "nucleos": 6, "ram_total_gb": 16.0,
         "ram_libre_gb": 9.5, "gpus": [{"nombre": "NVIDIA GeForce GTX 1650", "vram_gb": 4.0}],
         "vram_gb": 4.0, "disco_libre_gb": 120.0}


def guion(estado, preguntar="CONOCIMIENTO"):
    return f"""
import sys, json
sys.path[:0] = {RUTAS!r}
import cliente, consultas, equipo, asistente_app
from pathlib import Path
cliente.estado = lambda cfg=None: {estado!r}
cliente.AJUSTES = Path({str(tmp / "ajustes.json")!r})
equipo.especificaciones = lambda: {SPECS!r}
equipo.en_memoria = lambda url="": [{{"nombre": "qwen2.5:1.5b-instruct", "tam_gb": 1.6, "gpu_pct": 100}}]
APRENDIDAS = Path({str(tmp / "aprendidas.json")!r})
consultas.aprender = lambda p, sql: (APRENDIDAS.write_text(json.dumps([p, sql])) or True)
def falso(q, *a, **k):
    if {preguntar!r} == "ERROR":
        raise cliente.IAError("timed out")
    if {preguntar!r} == "SQL":
        return {{"ok": True, "sql": "SELECT 1 AS n", "nota": "", "columnas": ["n"], "filas": [[1]],
                "truncado": False, "resumen": "Hay 1."}}
    if {preguntar!r} == "PROCESO":
        return {{"ok": True, "origen": "proceso", "sql": "SELECT * FROM vigentes WHERE nomenclatura = 'X'",
                "nota": "Calculado con la fecha de hoy.", "columnas": ["campo", "valor"],
                "filas": [["Proceso", "X"]], "truncado": False, "resumen": "X. Cierre de inscripción: hoy."}}
    return {{"ok": True, "origen": "conocimiento", "sql": "(no es SQL)", "nota": "", "columnas": ["campo", "valor"],
            "filas": [["Término", "Brighter"]], "truncado": False, "resumen": "Brighter vende paneles BTOUCH."}}
consultas.preguntar = falso
asistente_app.render()
"""


def abrir(estado, preguntar="CONOCIMIENTO"):
    at = AppTest.from_string(guion(estado, preguntar), default_timeout=30)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def textos(at):
    return " ".join(m.value for m in at.markdown) + " " + " ".join(c.value for c in at.caption)


def ir_a(at, vista):
    nav = at.segmented_control[0] if len(at.segmented_control) else at.radio[0]
    nav.set_value(vista).run()
    assert not at.exception, [e.value for e in at.exception]


# --- pantalla inicial: el chat manda, con globos de sugerencia
at = abrir(LISTO)
assert at.chat_input, "el chat debe ser lo primero"
t = textos(at)
assert "En qué te ayudo" in t and "IA lista" in t and "qwen2.5:1.5b-instruct" in t
assert not at.metric, "las especificaciones no van en la pantalla del chat"
assert not at.selectbox, "los ajustes no van mezclados con el chat"
if len(at.pills):
    opciones = [o.label if hasattr(o, "label") else o for o in at.pills[0].options]
    assert any("Brighter" in o for o in opciones), opciones

# --- escribir una pregunta
at.chat_input[0].set_value("¿Qué es Brighter?").run()
assert not at.exception, [e.value for e in at.exception]
assert len(at.chat_message) == 2
t = textos(at)
assert "Brighter vende paneles BTOUCH." in t and "base de conocimiento" in t
assert "En qué te ayudo" not in t, "la bienvenida se va cuando empieza la conversación"
assert not any(b.label.startswith("✅") for b in at.button), "una respuesta del glosario no se «aprende» como SQL"

# --- un globo manda su pregunta completa
if len(at.pills):
    at2 = abrir(LISTO)
    primero = at2.pills[0].options[0]
    at2.pills[0].set_value(getattr(primero, "label", primero)).run()
    assert not at2.exception, [e.value for e in at2.exception]
    assert len(at2.chat_message) == 2, "tocar un globo debe hacer la pregunta"

# --- respuesta con SQL: se puede ver cómo se obtuvo y aprenderla
at3 = abrir(LISTO, "SQL")
at3.chat_input[0].set_value("cuántos").run()
assert not at3.exception, [e.value for e in at3.exception]
assert any("Cómo lo obtuve" in e.label for e in at3.expander)
aprender = [b for b in at3.button if b.label.startswith("✅")]
assert aprender, "debe ofrecer aprender la consulta"
aprender[0].click().run()
assert json.loads((tmp / "aprendidas.json").read_text())[0] == "cuántos"

# --- un proceso concreto: lo calcula el código, sin SQL que aprender
at3b = abrir(LISTO, "PROCESO")
at3b.chat_input[0].set_value("cuantos dias quedan en X").run()
assert not at3b.exception, [e.value for e in at3b.exception]
assert "Cierre de inscripción: hoy." in textos(at3b) and "la IA no interviene" in textos(at3b)
assert not any(b.label.startswith("✅") for b in at3b.button) and not any("Cómo lo obtuve" in e.label for e in at3b.expander)

# --- la IA tarda o falla: mensaje claro dentro del chat, sin romper la página
at4 = abrir(LISTO, "ERROR")
at4.chat_input[0].set_value("algo").run()
assert not at4.exception and any("no respondió a tiempo" in e.value for e in at4.error), [e.value for e in at4.error]

# --- Ollama apagado: se avisa, pero el chat sigue disponible
at5 = abrir(APAGADO)
assert "Ollama apagado" in textos(at5) and at5.chat_input
at5.chat_input[0].set_value("¿Qué es Brighter?").run()
assert not at5.exception and len(at5.chat_message) == 2

# --- desde el aviso de «sin IA» se llega directo a la configuración
ir = [b for b in at5.button if b.key == "ir_config"]
assert ir, "con Ollama apagado debe haber un acceso directo a la configuración"
ir[0].click().run()
assert not at5.exception and not at5.chat_input and at5.metric, "el acceso directo debe abrir la configuración"

# --- configuración: especificaciones del equipo y ajustes, en su propio apartado
at6 = abrir(LISTO)
ir_a(at6, "⚙️ Configuración")
assert not at6.chat_input, "en configuración no hay caja de chat"
etiquetas = {m.label for m in at6.metric}
assert {"Procesador", "Disco libre"} <= etiquetas and any("Memoria" in e for e in etiquetas), etiquetas
valores = " ".join(m.value for m in at6.metric)
assert "6 núcleos" in valores and "9.5 / 16.0 GB" in valores and "4.0 GB" in valores and "120.0 GB" in valores, valores
t = textos(at6)
assert "Intel(R) Core(TM) i5-10400" in t and "NVIDIA GeForce GTX 1650" in t
assert any("Modelo recomendado" in i.value for i in at6.info)
assert any("En memoria" in c.value and "tarjeta de video" in c.value for c in at6.caption), "debe decir dónde corre el modelo"
assert {"Modelo", "Dispositivo", "Memoria de contexto"} <= {b.label for b in at6.selectbox}
guardar = [b for b in at6.button if b.label == "Guardar ajustes"][0]
[b for b in at6.selectbox if b.label == "Dispositivo"][0].set_value("cpu")
guardar.click().run()
assert not at6.exception and json.loads((tmp / "ajustes.json").read_text())["dispositivo"] == "cpu"

# --- las otras secciones abren sin romperse
for vista in ("📬 Alerta de hoy", "🎯 Competidores"):
    a = abrir(LISTO)
    ir_a(a, vista)

print("OK: interfaz del asistente, especificaciones del equipo y colores verificados")

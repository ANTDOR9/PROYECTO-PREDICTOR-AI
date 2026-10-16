"""Prueba la consulta por proceso al SEACE y el Comparador sobre procesos vigentes.
No usa la red: la respuesta del SEACE es una copia de una ficha real (tests/fixtures).
Ejecutar:  python tests/test_ficha_seace.py"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(RAIZ / "src"), str(RAIZ / "src" / "ia")]

import ficha_seace as fs  # noqa: E402

FICHA = json.loads((RAIZ / "tests" / "fixtures" / "ficha_1252424.json").read_text(encoding="utf-8"))
tmp = Path(tempfile.mkdtemp())


# ---------------------------------------------------------------- red simulada
class Resp:
    def __init__(self, datos, status=200):
        self._d, self.status_code = datos, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._d


llamadas = []
modo = {"respuesta": FICHA, "falla": False}


def falso_get(url, **kw):
    llamadas.append(url)
    if modo["falla"]:
        raise ConnectionError("sin red")
    return Resp(modo["respuesta"])


import requests  # noqa: E402

requests.get = falso_get

# ------------------------------------------------------------ lectura de la ficha
f = fs.obtener_ficha(1252424, cache_dir=tmp)
assert llamadas == [fs.API.format(id=1252424)]
d = fs.documentos(f)
assert len(d) == 1 and d[0]["filecode"] == "916e60a9-2f56-482d-8b2b-b80d0bde85e0", d
assert d[0]["etapa"] == "Convocatoria" and d[0]["extension"] == "pdf"
assert fs.items(f)[0]["producto"].startswith("PANTALLA INTERACTIVA") and fs.items(f)[0]["cantidad"] == "1"
assert [c["etapa"] for c in fs.cronograma(f)][0] == "Convocatoria"
sin_codigo = {"listaDocumentos": [{"nombreArchivo": "x.pdf", "codigoAlfresco": None}]}
assert fs.documentos(sin_codigo) == []                       # sin fileCode no hay nada que bajar

# ------------------------------------------------------------------------ caché
fs.obtener_ficha("1252424", cache_dir=tmp)
assert len(llamadas) == 1, "dentro de 24 h debe usar la copia guardada, no volver a la red"
fs.obtener_ficha(1252424, forzar=True, cache_dir=tmp)
assert len(llamadas) == 2
ruta = tmp / "1252424.json"
viejo = time.time() - 48 * 3600
os.utime(ruta, (viejo, viejo))
fs.obtener_ficha(1252424, cache_dir=tmp)
assert len(llamadas) == 3, "una copia de más de 24 h se renueva"

# sin red: copia vieja si existe, error claro si no
os.utime(ruta, (viejo, viejo))
modo["falla"] = True
f2 = fs.obtener_ficha(1252424, cache_dir=tmp)
assert f2.get("_desactualizada") is True and f2["nomenclatura"] == "LP-SM-14-2026-MDCC-1"
try:
    fs.obtener_ficha(999, cache_dir=tmp)
    raise SystemExit("debió fallar sin red ni copia")
except fs.FichaError as e:
    assert "999" in str(e)
modo["falla"] = False

# entradas inválidas y respuestas inesperadas
for malo in ("abc", "", None, -5, "../etc"):
    try:
        fs.obtener_ficha(malo, cache_dir=tmp)
        raise SystemExit(f"debió rechazar {malo!r}")
    except fs.FichaError:
        pass
modo["respuesta"] = {"error": "no existe"}
try:
    fs.obtener_ficha(777, cache_dir=tmp)
    raise SystemExit("debió rechazar una respuesta que no es una ficha")
except fs.FichaError:
    pass
assert not (tmp / "777.json").exists(), "una respuesta inválida no se guarda en la caché"
modo["respuesta"] = FICHA

# ------------------------------------------------------------- panel (sin Streamlit)
import panel_expediente as pe  # noqa: E402

docs = pe.documentos_de_ficha(FICHA)
assert docs[0]["clase"] == "bases" and docs[0]["prioridad"] == pe.PRIORIDAD_PANEL["bases"], docs
assert pe._ruta_cache("916e60a9-2f56-482d-8b2b-b80d0bde85e0").name.endswith(".json")
assert pe._ruta_cache("../../etc/passwd") is None and pe._ruta_cache("") is None   # nada fuera de la carpeta
pe.CACHE_ANALISIS = tmp / "cache_analisis"
assert pe._leer_cache("916e60a9-2f56-482d-8b2b-b80d0bde85e0") is None
pe._guardar_cache({"ok": False, "filecode": "916e60a9-2f56-482d-8b2b-b80d0bde85e0"})
assert pe._leer_cache("916e60a9-2f56-482d-8b2b-b80d0bde85e0") is None              # los fallos no se guardan
FC = "916e60a9-2f56-482d-8b2b-b80d0bde85e0"
pe._guardar_cache({"ok": True, "filecode": FC, "specs": {"brillo_cdm2": 410.0}})
assert pe._leer_cache(FC) is None                                                   # copia incompleta: se ignora
pe._guardar_cache({"ok": True, "filecode": FC, "specs": {"brillo_cdm2": 410.0}, "cobertura": 0.5, "resultados": []})
assert pe._leer_cache(FC)["specs"]["brillo_cdm2"] == 410.0
(pe.CACHE_ANALISIS / f"{FC}.json").write_text("{no es json", encoding="utf-8")
assert pe._leer_cache(FC) is None                                                   # copia dañada: se ignora
(pe.CACHE_ANALISIS / f"{FC}.json").unlink()                                         # la interfaz parte sin análisis previo

# ------------------------------------------------ interfaz del panel (Streamlit AppTest)
try:
    from streamlit.testing.v1 import AppTest
except ImportError:                                           # Streamlit no instalado: se omite
    print("OK: consulta por proceso verificada (la prueba de interfaz se omitió: falta Streamlit)")
    raise SystemExit(0)

fila = {"id": 1252424, "nomenclatura": "LP-SM-14-2026-MDCC-1", "entidad": "MUNICIPALIDAD DISTRITAL DE CERRO COLORADO",
        "descripcion": "ADQUISICIÓN DE PANTALLAS INTERACTIVAS", "fecha_fin_inscripcion": "25/10/2026 23:59:00",
        "fecha_presentacion": "26/10/2026 00:01:00", "valor_referencial": None,
        "enlace": "https://prod4.seace.gob.pe/openegocio/#/ficha/idProceso/1252424"}
guion = f"""
import sys
sys.path[:0] = {[str(RAIZ / "src"), str(RAIZ / "src" / "ia")]!r}
import ficha_seace, panel_expediente
ficha_seace.CACHE = __import__("pathlib").Path({str(tmp / "ui")!r})
panel_expediente.render_vigente({fila!r})
"""
at = AppTest.from_string(guion, default_timeout=30)
at.run()
assert not at.exception, [e.value for e in at.exception]
assert any("Cerro Colorado".upper() in m.value.upper() for m in at.markdown), "falta la entidad"
assert at.selectbox, "debe ofrecer elegir el documento del expediente"
assert any("Bases Administrativas" in o or "Bases LP14" in o for o in at.selectbox[0].options), at.selectbox[0].options
assert any("Solo se descarga" in c.value for c in at.caption), "debe aclarar que no baja nada hasta analizar"
n_antes = len(llamadas)
assert any(b.label.startswith("Analizar expediente") for b in at.button)
assert len(llamadas) == n_antes, "mostrar el proceso no debe descargar documentos, solo consultar la ficha"

# proceso que aún no publica documentos
modo["respuesta"] = {**FICHA, "listaDocumentos": []}
os.utime(tmp / "ui" / "1252424.json", (viejo, viejo))
at2 = AppTest.from_string(guion, default_timeout=30)
at2.run()
assert not at2.exception and any("todavía no publica" in i.value for i in at2.info), [i.value for i in at2.info]

# la red del SEACE falla y no hay copia: mensaje claro, sin romper el tablero
modo.update(respuesta=FICHA, falla=True)
guion_sin = guion.replace("ui", "vacio")
at3 = AppTest.from_string(guion_sin, default_timeout=30)
at3.run()
assert not at3.exception and any("No se pudo consultar la ficha" in e.value for e in at3.error), [e.value for e in at3.error]

print("OK: consulta por proceso y Comparador de vigentes verificados")

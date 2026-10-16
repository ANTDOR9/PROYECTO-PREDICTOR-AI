"""Detección: ¿esta convocatoria es un panel interactivo / de qué rubro es?

Complementa a las palabras clave de config.yaml, que dejan pasar falsos
positivos (tarjetas «smart card», fotodocumentadores, quioscos de atención).
El modelo solo ve título y objeto; la decisión de qué hacer con el resultado
queda en el código que lo llame.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cliente import chat  # noqa: E402

CATEGORIAS = ["INTERACTIVA", "LED/VIDEOWALL", "TELEVISOR", "PROYECTOR",
              "SEÑAL/KIOSCO", "AUDIOVISUAL", "OTRO"]

SISTEMA = f"""Clasificas convocatorias públicas peruanas para una empresa que vende \
paneles interactivos educativos (pizarras/pantallas táctiles 4K de 65 a 110 pulgadas).
Responde SOLO JSON: {{"categoria": una de {CATEGORIAS}, "es_panel_interactivo": true/false, \
"motivo": "una frase"}}.
INTERACTIVA solo si el objeto es una pantalla/panel/pizarra táctil o interactiva. \
Tarjetas inteligentes, instrumentos de laboratorio, quioscos de atención y televisores \
comunes NO son INTERACTIVA."""


def clasificar(titulo: str, objeto: str = "", cfg: dict | None = None) -> dict:
    r = chat(SISTEMA, f"Título: {titulo}\nObjeto: {objeto}", json_modo=True, cfg=cfg)
    if r.get("categoria") not in CATEGORIAS:
        r["categoria"] = "OTRO"
    r["es_panel_interactivo"] = bool(r.get("es_panel_interactivo")) and r["categoria"] == "INTERACTIVA"
    return r

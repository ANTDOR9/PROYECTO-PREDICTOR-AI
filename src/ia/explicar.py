"""Explicación en lenguaje natural de un dictamen YA calculado por el motor.

El modelo no cambia veredictos: recibe la tabla de evaluar_licitacion y la
redacta. Si algo no está en la tabla, no puede afirmarlo.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cliente import chat  # noqa: E402
from evaluar_licitacion import Resumen  # noqa: E402

SISTEMA = """Eres analista comercial de una empresa de paneles interactivos. Se te da el \
resultado ya calculado de comparar lo exigido en una licitación contra la ficha de un modelo. \
Redacta en español, en 4 a 6 líneas: si podía presentarse, qué lo deja fuera o lo condiciona, \
y qué conviene revisar a mano. NO cambies ningún veredicto, NO inventes datos que no estén \
en la tabla, y di «sin dato» cuando la ficha no declara algo."""


def tabla(r: Resumen) -> str:
    filas = [f"- {v.etiqueta}: exigido={v.exigido} | ficha={v.ofrecido} | "
             f"{v.resultado} (cat. {v.categoria}) {v.nota}" for v in r.veredictos]
    return (f"Modelo: {r.ficha.marca} {r.ficha.modelo}\nDictamen: {r.dictamen}\n"
            + "\n".join(filas))


def explicar(r: Resumen, cfg: dict | None = None) -> str:
    return chat(SISTEMA, tabla(r), cfg=cfg).strip()

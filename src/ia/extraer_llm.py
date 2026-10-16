"""Extracción del requerimiento técnico con el modelo local.

Devuelve los MISMOS 18 campos que `extractor.Specs`, para que el motor de
evaluación (reglas deterministas) siga siendo quien dictamina. Regla heredada
del proyecto: si el texto no menciona un dato, el campo es null; nunca se
rellena ni se supone.

Cada valor se valida contra el texto: si el modelo devuelve un número que no
aparece en el bloque, se descarta (anti-alucinación).
"""
from __future__ import annotations

import re
import sys
from dataclasses import asdict, fields
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cliente import chat  # noqa: E402
from extractor import Specs, norm  # noqa: E402

TIPOS = {f.name: f.type for f in fields(Specs)}

SISTEMA = """Eres un extractor de especificaciones técnicas de bases de licitaciones \
peruanas de paneles interactivos. Respondes SOLO con un objeto JSON.
Reglas:
- Usa exactamente estas claves: {claves}.
- Si el texto NO menciona un dato, pon null. Nunca inventes ni supongas.
- Números sin unidades (brillo en cd/m2, tiempo en ms, memoria en GB, garantía en meses, \
vida útil en horas).
- certificacion_edla y ops_requerido: true solo si el texto lo exige; si no lo menciona, null.
- Texto libre (resolucion, contraste, cpu, etc.): cópialo breve, tal como está escrito."""


def _numeros(t: str) -> set[str]:
    """Números completos del texto ('1 200', '1.200' y '1200' cuentan igual)."""
    out = set()
    for m in re.findall(r"\d+(?:[.,\s]\d{3})*(?:[.,]\d+)?|\d+", t):
        out.add(re.sub(r"[.,\s]", "", m))
        out.add(m.replace(",", ".").replace(" ", ""))
    return out


def _en_texto(valor, texto_norm: str) -> bool:
    """¿Aparece el dato en el texto? Los números se comparan completos,
    no como subcadena ('16' no está en '2160')."""
    if isinstance(valor, bool):
        return True
    cadena = norm(str(valor))
    nums = re.findall(r"\d+(?:[.,]\d+)?", cadena)
    if nums:
        presentes = _numeros(texto_norm)
        return all(re.sub(r"[.,]", "", n) in presentes or n.replace(",", ".") in presentes
                   for n in nums)
    return cadena[:20] in texto_norm


def extraer(texto: str, cfg: dict | None = None) -> tuple[Specs, list[str]]:
    """Devuelve (Specs, descartados): campos que el modelo dio pero el texto no respalda."""
    claves = ", ".join(TIPOS)
    crudo = chat(SISTEMA.format(claves=claves), texto[:24000], json_modo=True, cfg=cfg)
    tn = norm(texto)
    s, descartados = Specs(), []
    for k in TIPOS:
        v = crudo.get(k)
        if v is None or v == "":
            continue
        if not _en_texto(v, tn):
            descartados.append(f"{k}={v!r}")
            continue
        t = TIPOS[k]
        try:
            if "float" in t:
                v = float(str(v).replace(",", "."))
            elif "int" in t:
                v = int(float(v))
            elif "bool" in t:
                v = bool(v) if isinstance(v, bool) else None
            else:
                v = str(v)
        except (TypeError, ValueError):
            descartados.append(f"{k}={v!r}")
            continue
        setattr(s, k, v)
    return s, descartados


def comparar_con_reglas(texto: str, cfg: dict | None = None) -> dict:
    """Corre reglas e IA sobre el mismo bloque y marca en qué campos discrepan.
    Sirve para medir cuánto aporta el modelo antes de confiar en él."""
    import extractor
    reglas = asdict(extractor.extraer(texto))
    ia, descartados = extraer(texto, cfg)
    ia = asdict(ia)
    return {
        "reglas": reglas, "ia": ia, "descartados_por_ia": descartados,
        "solo_ia": [k for k in ia if ia[k] is not None and reglas[k] is None],
        "solo_reglas": [k for k in ia if reglas[k] is not None and ia[k] is None],
        "discrepan": [k for k in ia if ia[k] is not None and reglas[k] is not None
                      and str(ia[k]).lower() != str(reglas[k]).lower()],
    }

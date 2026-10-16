"""Ficha de UN proceso en el SEACE («Oportunidades de Negocio»): documentos, ítems y cronograma.

Es lo que usa el Comparador para no depender de los paquetes anuales del OECE (de 120 a
155 MB cada uno, que además solo se publican completos). Cuando eliges un proceso de la
lista, se consulta SOLO su ficha (unos pocos KB) y de ahí sale el `fileCode` de cada
documento; el documento que quieras analizar se baja después, aparte, con
`descargar_documento.descargar`.

Endpoint (el mismo que usa la ficha pública del portal; verificado con el proceso
LP-SM-14-2026-MDCC-1):

    https://prod4.seace.gob.pe:8086/api/oportunidades/fichaProceso/idProceso/{id}

`{id}` es la columna `id` de la tabla `vigentes` (idProcedimiento). Los documentos vienen en
`listaDocumentos`; su `codigoAlfresco` es el `fileCode` de SdescargarArchivoAlfresco.

Caché: la ficha se guarda en data/cache_fichas/{id}.json y se reutiliza 24 horas. Si no hay
red pero hay una copia vieja, se usa esa y se marca como desactualizada.

Uso:
    python src/ficha_seace.py 1252424
    python src/ficha_seace.py 1252424 --forzar
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CACHE = RAIZ / "data" / "cache_fichas"
API = "https://prod4.seace.gob.pe:8086/api/oportunidades/fichaProceso/idProceso/{id}"
TTL_HORAS = 24
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


class FichaError(RuntimeError):
    """No se pudo obtener o entender la ficha."""


def _id(id_proceso) -> int:
    try:
        n = int(str(id_proceso).strip())
    except (TypeError, ValueError):
        raise FichaError(f"identificador de proceso inválido: {id_proceso!r}") from None
    if n <= 0:
        raise FichaError(f"identificador de proceso inválido: {id_proceso!r}")
    return n


def _leer_cache(ruta: Path) -> dict | None:
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def obtener_ficha(id_proceso, forzar: bool = False, ttl_horas: float = TTL_HORAS,
                  cache_dir: Path | None = None, timeout: int = 30) -> dict:
    """Devuelve la ficha (dict del SEACE). Añade la clave `_desactualizada` (True) si se tuvo
    que usar una copia vieja porque la red falló."""
    n = _id(id_proceso)
    ruta = (cache_dir or CACHE) / f"{n}.json"
    if not forzar and ruta.exists() and time.time() - ruta.stat().st_mtime < ttl_horas * 3600:
        viva = _leer_cache(ruta)
        if viva:
            return viva

    try:
        import requests
        import urllib3
        urllib3.disable_warnings()          # el servidor :8086 usa certificado propio
        r = requests.get(API.format(id=n), headers={"User-Agent": UA, "Accept": "application/json"},
                         timeout=timeout, verify=False)
        r.raise_for_status()
        datos = r.json()
        if not isinstance(datos, dict) or "listaDocumentos" not in datos:
            raise ValueError("la respuesta no tiene la forma de una ficha")
    except Exception as e:                                       # noqa: BLE001
        vieja = _leer_cache(ruta) if ruta.exists() else None
        if vieja:
            vieja["_desactualizada"] = True
            return vieja
        raise FichaError(f"No se pudo consultar la ficha del proceso {n} en el SEACE: "
                         f"{type(e).__name__}: {e}") from e

    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    tmp.replace(ruta)
    return datos


# ----------------------------------------------------------------- lectura de la ficha
def documentos(ficha: dict) -> list[dict]:
    """Documentos publicados del proceso. Se descartan los que no traen fileCode."""
    out = []
    for d in ficha.get("listaDocumentos") or []:
        fc = (d.get("codigoAlfresco") or "").strip()
        if not fc:
            continue
        out.append({"filecode": fc,
                    "titulo": (d.get("nombreArchivo") or "").strip(),
                    "tipo_doc": (d.get("tipoDocumento") or "").strip(),
                    "etapa": (d.get("etapa") or "").strip(),
                    "extension": (d.get("extension") or "").strip().lower(),
                    "fecha": (d.get("fechaPublicacion") or "").strip()})
    return out


def items(ficha: dict) -> list[dict]:
    """Ítems del procedimiento: qué se compra y cuántos."""
    return [{"nro": i.get("nroItem"), "descripcion": i.get("descripcion") or "",
             "producto": i.get("descripcionCubso") or "", "cantidad": i.get("cantidad"),
             "unidad": i.get("unidadMedia") or "", "departamento": i.get("departamento") or ""}
            for i in ficha.get("listaItems") or []]


def cronograma(ficha: dict) -> list[dict]:
    """Etapas con sus fechas (en el orden en que las publica el SEACE)."""
    return [{"etapa": c.get("descripcionEtapa") or c.get("nombreEtapa") or "",
             "inicio": c.get("fechaInicio") or "", "fin": c.get("fechaFin") or ""}
            for c in ficha.get("listaCronograma") or []]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("id", help="id del proceso (columna `id` de la tabla vigentes)")
    ap.add_argument("--forzar", action="store_true", help="ignora la copia guardada")
    a = ap.parse_args(argv)
    try:
        f = obtener_ficha(a.id, forzar=a.forzar)
    except FichaError as e:
        print(e, file=sys.stderr)
        return 1
    print(f"{f.get('nomenclatura')} · {(f.get('entidadConvocante') or {}).get('nombreOrganismo', '')}")
    print(f"{f.get('descripcionObjeto')}")
    if f.get("_desactualizada"):
        print("(copia guardada: no hubo red)")
    for it in items(f):
        print(f"  ítem {it['nro']}: {it['producto'] or it['descripcion']} · {it['cantidad']} {it['unidad']}")
    docs = documentos(f)
    print(f"{len(docs)} documento(s):")
    for d in docs:
        print(f"  [{d['etapa']}] {d['tipo_doc']} — {d['titulo']}  ({d['filecode']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

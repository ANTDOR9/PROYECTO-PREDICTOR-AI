"""Cliente mínimo para un modelo local servido por Ollama (API REST)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import requests
import yaml

RAIZ = Path(__file__).resolve().parent.parent.parent
AJUSTES = RAIZ / "data" / "ajustes_ia.json"   # lo escribe el interruptor del tablero


class IAError(RuntimeError):
    pass


def config() -> dict:
    cfg = yaml.safe_load((RAIZ / "config.yaml").read_text(encoding="utf-8")) or {}
    base = {"url": "http://localhost:11434", "modelo": "auto",
            "temperatura": 0.0, "timeout_s": 300, "contexto_tokens": 8192,
            "dispositivo": "auto"}
    base.update(cfg.get("ia_local") or {})
    try:   # los ajustes del tablero mandan sobre config.yaml
        base.update(json.loads(AJUSTES.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return base


def guardar_ajustes(**cambios) -> None:
    """Guarda dispositivo ('auto'|'gpu'|'cpu'), modelo, contexto_tokens, timeout_s."""
    try:
        actual = json.loads(AJUSTES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        actual = {}
    actual.update({k: v for k, v in cambios.items() if v is not None})
    AJUSTES.parent.mkdir(parents=True, exist_ok=True)
    AJUSTES.write_text(json.dumps(actual, ensure_ascii=False, indent=1), encoding="utf-8")


def opciones_dispositivo(cfg: dict) -> dict:
    """Traduce el interruptor a opciones de Ollama: gpu = todas las capas en la
    tarjeta de video, cpu = solo procesador, auto = que Ollama reparta."""
    d = str(cfg.get("dispositivo", "auto")).lower()
    return {"num_gpu": 999} if d == "gpu" else {"num_gpu": 0} if d == "cpu" else {}


_NO_CHAT = ("embed", "nomic", "bge", "minilm", "e5-", "rerank")


def _modelos(cfg: dict) -> list[str]:
    r = requests.get(cfg["url"].rstrip("/") + "/api/tags", timeout=5)
    r.raise_for_status()
    return [m.get("name", "") for m in r.json().get("models", [])]


def resolver_modelo(cfg: dict, nombres: list[str] | None = None) -> str | None:
    """Con modelo 'auto' elige uno ya descargado que sirva para chat
    (descarta los de embeddings), prefiriendo familias buenas en español."""
    nombres = _modelos(cfg) if nombres is None else nombres
    if cfg["modelo"] != "auto":
        ok = [n for n in nombres if n == cfg["modelo"] or n.split(":")[0] == cfg["modelo"]]
        return ok[0] if ok else None
    chat_ok = [n for n in nombres if not any(x in n.lower() for x in _NO_CHAT)]
    for pref in ("qwen2.5", "qwen3", "llama3", "gemma", "mistral", "phi"):
        for n in chat_ok:
            if pref in n.lower():
                return n
    return chat_ok[0] if chat_ok else None


RECOMENDADOS = {
    "qwen2.5:3b-instruct": "Liviano (~2 GB). Recomendado para empezar.",
    "qwen2.5:7b-instruct": "Equilibrado (~4,7 GB). Necesita ~8 GB de RAM libre.",
    "qwen2.5:1.5b-instruct": "Muy liviano (~1 GB). Rápido, pero escribe peor el SQL.",
}


def descargar(nombre: str, cfg: dict | None = None):
    """Descarga un modelo en Ollama (equivale a `ollama pull`). Va cediendo
    (estado, fraccion 0..1 o None) para poder mostrar una barra de progreso."""
    cfg = cfg or config()
    try:
        with requests.post(cfg["url"].rstrip("/") + "/api/pull",
                           json={"model": nombre, "stream": True},
                           stream=True, timeout=(5, 600)) as r:
            r.raise_for_status()
            for linea in r.iter_lines():
                if not linea:
                    continue
                d = json.loads(linea)
                if d.get("error"):
                    raise IAError(f"Ollama no pudo descargar {nombre}: {d['error']}")
                tot, hecho = d.get("total"), d.get("completed")
                yield d.get("status", ""), (hecho / tot if tot and hecho is not None else None)
    except requests.RequestException as e:
        raise IAError(f"no se pudo descargar {nombre}: {e}") from e


def estado(cfg: dict | None = None) -> dict:
    """Dice si el servidor responde y si hay un modelo utilizable."""
    cfg = cfg or config()
    try:
        nombres = _modelos(cfg)
    except requests.RequestException as e:
        return {"servidor": False, "modelo": False, "detalle": str(e)}
    elegido = resolver_modelo(cfg, nombres)
    return {"servidor": True, "modelo": bool(elegido), "elegido": elegido,
            "disponibles": nombres}


def _json_en(texto: str):
    """Extrae el primer objeto JSON de una respuesta, aunque venga con relleno."""
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", texto, re.S)
        if m:
            return json.loads(m.group(0))
        raise


def chat(sistema: str, usuario: str, *, json_modo: bool = False,
         cfg: dict | None = None):
    """Una pregunta, una respuesta. Con json_modo devuelve un dict ya parseado."""
    cfg = cfg or config()
    modelo = resolver_modelo(cfg) if cfg["modelo"] == "auto" else cfg["modelo"]
    if not modelo:
        raise IAError("no hay ningún modelo de chat descargado en Ollama")
    cuerpo = {
        "model": modelo,
        "stream": False,
        "messages": [{"role": "system", "content": sistema},
                     {"role": "user", "content": usuario}],
        "options": {"temperature": cfg["temperatura"],
                    "num_ctx": cfg["contexto_tokens"],
                    **opciones_dispositivo(cfg)},
    }
    cuerpo["think"] = False   # modelos "que razonan" (qwen3, deepseek-r1) dejan el contenido vacío
    if json_modo:
        cuerpo["format"] = "json"

    def _pedir(c):
        try:
            r = requests.post(cfg["url"].rstrip("/") + "/api/chat", json=c,
                              timeout=cfg["timeout_s"])
            r.raise_for_status()
        except requests.RequestException as e:
            raise IAError(f"no se pudo consultar el modelo local: {e}") from e
        return r.json().get("message", {}).get("content", "") or ""

    texto = _pedir(cuerpo)
    if not texto.strip():   # vacío: reintenta sin forzar JSON (algunos modelos chicos lo rechazan)
        cuerpo.pop("format", None)
        texto = _pedir(cuerpo)
    if not texto.strip():
        raise IAError("el modelo devolvió una respuesta vacía (suele ser un modelo que no sirve para "
                      f"esta tarea o con poco contexto). Modelo usado: {modelo}")
    if not json_modo:
        return texto
    try:
        return _json_en(texto)
    except json.JSONDecodeError as e:
        raise IAError(f"el modelo no devolvió JSON válido: {texto[:200]!r}") from e

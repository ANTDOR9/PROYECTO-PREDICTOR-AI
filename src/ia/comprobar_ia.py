"""Comprueba que el modelo local esté listo:  python src/ia/comprobar_ia.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cliente import config, estado  # noqa: E402


def main() -> int:
    cfg = config()
    e = estado(cfg)
    if not e["servidor"]:
        print(f"✗ No responde Ollama en {cfg['url']}.\n"
              f"  Instálalo desde https://ollama.com y ábrelo.\n  ({e['detalle']})")
        return 1
    if not e["modelo"]:
        print(f"✗ Ollama responde pero no hay un modelo de chat utilizable ('{cfg['modelo']}').\n"
              f"  Descarga uno:  ollama pull qwen2.5:7b-instruct\n"
              f"  Disponibles: {', '.join(e['disponibles']) or 'ninguno'}")
        return 1
    print(f"✓ Ollama activo. Modelo en uso: '{e['elegido']}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Qué tiene este computador y qué modelos de IA le caben.

Todo es de solo lectura y local: procesador, memoria, tarjeta de video, espacio en disco y
qué modelo tiene cargado Ollama ahora mismo. Nada se instala ni se envía a ninguna parte.

    python src/ia/equipo.py
"""
from __future__ import annotations

import ctypes
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

GB = 1024 ** 3

# Lo que pide cada modelo recomendado: (tamaño en disco GB, memoria RAM libre cómoda GB).
# Son valores aproximados de la cuantización por defecto de Ollama (Q4), no una garantía.
REQUISITOS = {
    "qwen2.5:1.5b-instruct": (1.0, 3.0),
    "qwen2.5:3b-instruct": (1.9, 4.5),
    "qwen2.5:7b-instruct": (4.7, 8.0),
}


def _gb(n_bytes) -> float | None:
    return None if n_bytes is None else round(n_bytes / GB, 1)


def _correr(cmd: list[str], timeout: int = 8) -> str:
    """Ejecuta un comando y devuelve su salida; '' si no existe, falla o tarda demasiado."""
    flags = 0x08000000 if sys.platform == "win32" else 0        # CREATE_NO_WINDOW: sin ventana negra
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout, creationflags=flags)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


# ------------------------------------------------------------------------------- memoria
def _ram() -> tuple[int | None, int | None]:
    """(total, disponible) en bytes. None si no se puede saber."""
    try:
        import psutil
        m = psutil.virtual_memory()
        return int(m.total), int(m.available)
    except Exception:                                            # noqa: BLE001  psutil no es obligatorio
        pass
    if sys.platform == "win32":
        class _MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        try:
            m = _MS()
            m.dwLength = ctypes.sizeof(_MS)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
                return int(m.ullTotalPhys), int(m.ullAvailPhys)
        except (AttributeError, OSError):
            pass
        return None, None
    try:                                                          # Linux
        datos = {}
        for linea in Path("/proc/meminfo").read_text().splitlines():
            k, _, v = linea.partition(":")
            datos[k] = int(v.split()[0]) * 1024
        return datos.get("MemTotal"), datos.get("MemAvailable")
    except (OSError, ValueError, IndexError):
        pass
    total = _correr(["sysctl", "-n", "hw.memsize"]).strip()      # macOS
    return (int(total), None) if total.isdigit() else (None, None)


# -------------------------------------------------------------------- procesador y video
_PS = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
       "$o=[ordered]@{cpu=(Get-CimInstance Win32_Processor|Select-Object -First 1 -ExpandProperty Name);"
       "gpu=@(Get-CimInstance Win32_VideoController|ForEach-Object{$_.Name})};"
       "$o|ConvertTo-Json -Compress")


def _parsear_powershell(salida: str) -> tuple[str, list[str]]:
    try:
        d = json.loads(salida)
    except ValueError:
        return "", []
    gpu = d.get("gpu") or []
    if isinstance(gpu, str):
        gpu = [gpu]
    return (d.get("cpu") or "").strip(), [g.strip() for g in gpu if g and g.strip()]


def _parsear_nvidia(salida: str) -> list[dict]:
    """Salida de `nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits`."""
    out = []
    for linea in salida.strip().splitlines():
        nombre, _, mib = linea.rpartition(",")
        if nombre.strip() and mib.strip().isdigit():
            out.append({"nombre": nombre.strip(), "vram_gb": round(int(mib) / 1024, 1)})
    return out


def _cpu_y_gpus() -> tuple[str, list[dict]]:
    nvidia = _parsear_nvidia(_correr(["nvidia-smi", "--query-gpu=name,memory.total",
                                      "--format=csv,noheader,nounits"]))
    cpu, nombres = "", []
    if sys.platform == "win32":
        cpu, nombres = _parsear_powershell(_correr(["powershell", "-NoProfile", "-NonInteractive",
                                                    "-Command", _PS], timeout=12))
        cpu = cpu or os.environ.get("PROCESSOR_IDENTIFIER", "")
    elif sys.platform.startswith("linux"):
        try:
            for linea in Path("/proc/cpuinfo").read_text().splitlines():
                if linea.lower().startswith("model name"):
                    cpu = linea.partition(":")[2].strip()
                    break
        except OSError:
            pass
    elif sys.platform == "darwin":
        cpu = _correr(["sysctl", "-n", "machdep.cpu.brand_string"]).strip()
    cpu = cpu or platform.processor() or platform.machine()

    gpus = list(nvidia)
    conocidas = {g["nombre"].lower() for g in gpus}
    for n in nombres:                                            # las que nvidia-smi no ve (Intel, AMD…)
        if n.lower() not in conocidas and not any(n.lower() in c or c in n.lower() for c in conocidas):
            gpus.append({"nombre": n, "vram_gb": None})
    return cpu, gpus


def especificaciones() -> dict:
    """Resumen del equipo. Siempre devuelve todas las claves; lo que no se pudo saber queda en None/[]."""
    total, libre = _ram()
    cpu, gpus = _cpu_y_gpus()
    try:
        disco = shutil.disk_usage(Path.home()).free
    except OSError:
        disco = None
    return {"sistema": f"{platform.system()} {platform.release()}".strip(),
            "cpu": cpu, "nucleos": os.cpu_count() or None,
            "ram_total_gb": _gb(total), "ram_libre_gb": _gb(libre),
            "gpus": gpus,
            "vram_gb": max([g["vram_gb"] for g in gpus if g.get("vram_gb")] or [0]) or None,
            "disco_libre_gb": _gb(disco)}


# ------------------------------------------------------------------------ qué le cabe
def ajuste(nombre: str, specs: dict) -> str:
    """'ok' (cómodo), 'justo' (funciona pero apretado), 'no' (no conviene) o '?' (no se sabe)."""
    req = REQUISITOS.get(nombre)
    base = specs.get("ram_libre_gb") or (specs.get("ram_total_gb") or 0) * 0.6
    if not req or not base:
        return "?"
    _, ram = req
    if base >= ram:
        return "ok"
    return "justo" if base >= ram * 0.75 else "no"


def recomendar(specs: dict) -> tuple[str, str]:
    """El modelo más grande que le cabe cómodo, con el motivo en una frase."""
    for nombre in sorted(REQUISITOS, key=lambda n: REQUISITOS[n][1], reverse=True):
        if ajuste(nombre, specs) == "ok":
            ram = specs.get("ram_libre_gb") or round((specs.get("ram_total_gb") or 0) * 0.6, 1)
            return nombre, f"con unos {ram} GB de memoria disponible es el más capaz que corre cómodo"
    return "qwen2.5:1.5b-instruct", "es el más liviano: tu equipo tiene poca memoria libre ahora mismo"


# --------------------------------------------------------------- lo que Ollama tiene cargado
def en_memoria(url: str = "http://localhost:11434", timeout: int = 3) -> list[dict]:
    """Modelos que Ollama mantiene cargados ahora, y qué parte está en la tarjeta de video."""
    try:
        import requests
        r = requests.get(url.rstrip("/") + "/api/ps", timeout=timeout)
        r.raise_for_status()
        modelos = r.json().get("models", [])
    except Exception:                                            # noqa: BLE001
        return []
    out = []
    for m in modelos:
        tam, vram = m.get("size") or 0, m.get("size_vram") or 0
        out.append({"nombre": m.get("name", ""), "tam_gb": _gb(tam),
                    "gpu_pct": round(100 * vram / tam) if tam else 0})
    return out


if __name__ == "__main__":
    s = especificaciones()
    print(json.dumps(s, ensure_ascii=False, indent=1))
    print("Recomendado:", *recomendar(s))

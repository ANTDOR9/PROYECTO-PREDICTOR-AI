"""Los gráficos de ruido se generan con la base incluida.  python tests/test_graficos.py"""
import subprocess, sys, tempfile
from pathlib import Path
R = Path(__file__).resolve().parent.parent
out = Path(tempfile.mkdtemp())
r = subprocess.run([sys.executable, str(R / "src" / "ruido_datos.py"), "--salida", str(out)], capture_output=True, text=True)
assert r.returncode == 0, r.stderr[-400:]
png = sorted(p.name for p in out.glob("*.png"))
assert len(png) == 6 and all((out / p).stat().st_size > 20_000 for p in png), png
print("OK: gráficos generados:", ", ".join(png))

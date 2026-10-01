"""Genera requirements.docker.txt: el lock auditado + hashes de PyPI (deuda J, ADR-015).

Uso (desde backend/): python scripts/hash_lock.py requirements.lock.txt requirements.docker.txt
Incluye los hashes de TODOS los archivos publicados de cada version fijada, asi que
sirve para cualquier plataforma (la imagen es Linux; el lock se genero en Windows).
"""
import json
import re
import sys
import urllib.request

src, dst = sys.argv[1], sys.argv[2]
HEADER = [
    "# GENERADO desde requirements.lock.txt (mismas versiones) + hashes de PyPI, solo para",
    "# la imagen Docker (pip install --require-hashes, deuda J). No editar a mano:",
    "# regenerar con scripts/hash_lock.py. pip-audit audita requirements.lock.txt.",
]
BS = chr(92)
lines = open(src, encoding="utf-8").read().splitlines()
out, n = list(HEADER), 0
for line in lines:
    m = re.match(r"^([A-Za-z0-9_.\-]+)(\[[^\]]*\])?==([^\s;]+)\s*$", line)
    if not m:
        out.append(line)
        continue
    name, ver = m.group(1), m.group(3)
    data = json.load(urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{ver}/json", timeout=60))
    hashes = sorted({f["digests"]["sha256"] for f in data["urls"]})
    out.append(f"{name}=={ver} {BS}")
    for i, h in enumerate(hashes):
        out.append(f"    --hash=sha256:{h}" + (f" {BS}" if i < len(hashes) - 1 else ""))
    n += 1
open(dst, "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
print("paquetes con hash:", n)

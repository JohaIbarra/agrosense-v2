"""CLI de demostracion del ingester (slice 1 demostrable por si solo).

Uso:
    python -m agrosense.adapters.ingester.cli <archivo.xlsx> [--sheet Monitoreo_4]
"""
import argparse
import sys
from collections import Counter

import pandas as pd

from agrosense.adapters.ingester.ingest import ingest_wide
from agrosense.domain.errors import DomainError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ingere formato ancho de campo a long canonico"
    )
    parser.add_argument("archivo", help="Archivo .xlsx del monitoreo")
    parser.add_argument("--sheet", default="Monitoreo_4", help="Nombre de la hoja")
    args = parser.parse_args(argv)

    try:
        df = pd.read_excel(args.archivo, sheet_name=args.sheet)
    except FileNotFoundError:
        print(f"ERROR: archivo no encontrado: {args.archivo}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"ERROR: hoja no encontrada: {e}", file=sys.stderr)
        return 1

    try:
        result = ingest_wide(df)
    except DomainError as e:
        print(f"DOMINIO: {e}", file=sys.stderr)
        return 1

    deaths = sum(1 for o in result.observations if o.alive is False)
    by_campaign = Counter(o.campaign for o in result.observations)
    print(f"Arboles: {len(result.trees)}")
    print(f"Observaciones: {len(result.observations)}  {dict(sorted(by_campaign.items()))}")
    print(f"Muertes registradas: {deaths}")
    print(f"Warnings: {len(result.warnings)}")
    print(f"Mapping version: {result.mapping_version}")
    for w in result.warnings[:10]:
        print(f"  WARN: {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

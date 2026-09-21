"""Carga inicial de la analitica del slice 5 en PostgreSQL.

Lee los efectos de los modelos mixtos ya ajustados (`data/processed/*.csv`) y
reemplaza el contenido de `species_analytics`, `plot_analytics` y
`variance_components`.

Uso:
    python scripts/load_analytics.py                 # carga a DATABASE_URL
    python scripts/load_analytics.py --dry-run       # no escribe, solo reporta
    python scripts/load_analytics.py --processed-dir otra/ruta

Requiere que la migracion `b1c4a7f20e51` este aplicada (`alembic upgrade head`).

Este script NO re-estima nada. Los modelos mixtos (`lme4::glmer` binomial) ya
se corrieron sobre `data/raw/anexo1.xlsx`; los CSV son la fuente de verdad y
este script solo los traduce a filas. Es idempotente: cada corrida borra y
recarga las tres tablas en una sola transaccion.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# El script se ejecuta desde backend/ sin instalar el paquete en modo editable.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agrosense.adapters.analytics.effects_loader import (  # noqa: E402
    AnalyticsBundle,
    build_bundle,
)
from agrosense.adapters.db.models import (  # noqa: E402
    PlotAnalytics,
    SpeciesAnalytics,
    VarianceComponent,
)
from agrosense.adapters.db.repository import AnalyticsRepository  # noqa: E402
from agrosense.adapters.db.session import get_session_factory  # noqa: E402

DEFAULT_PROCESSED = Path(__file__).resolve().parents[1] / "data" / "processed"


def to_orm(bundle: AnalyticsBundle) -> tuple[
    list[SpeciesAnalytics], list[PlotAnalytics], list[VarianceComponent]
]:
    """Traduce las filas del loader a instancias del ORM.

    El loader no conoce SQLAlchemy a proposito: asi la transformacion se
    puede probar (y el `sig_*` verificar) sin levantar una base de datos.
    """
    species = [
        SpeciesAnalytics(
            species_name=r.species_name,
            effect_stall=r.effect_stall,
            se_stall=r.se_stall,
            or_stall=r.or_stall,
            or_stall_lo=r.or_stall_lo,
            or_stall_hi=r.or_stall_hi,
            sig_stall=r.sig_stall,
            effect_mort=r.effect_mort,
            se_mort=r.se_mort,
            or_mort=r.or_mort,
            or_mort_lo=r.or_mort_lo,
            or_mort_hi=r.or_mort_hi,
            sig_mort=r.sig_mort,
            n_observations=r.n_observations,
            n_trees=r.n_trees,
            gremio=r.gremio,
        )
        for r in bundle.species
    ]
    plots = [
        PlotAnalytics(
            plot_code=r.plot_code,
            localidad=r.localidad,
            effect_stall=r.effect_stall,
            se_stall=r.se_stall,
            or_stall=r.or_stall,
            effect_mort=r.effect_mort,
            se_mort=r.se_mort,
            or_mort=r.or_mort,
            n_trees=r.n_trees,
        )
        for r in bundle.plots
    ]
    variance = [
        VarianceComponent(
            model=r.model,
            grouping=r.grouping,
            variance=r.variance,
            sd=r.sd,
            icc=r.icc,
            n_levels=r.n_levels,
            n_observations=r.n_observations,
            n_events=r.n_events,
        )
        for r in bundle.variance
    ]
    return species, plots, variance


def report(bundle: AnalyticsBundle) -> None:
    """Resumen legible de lo que se va a cargar.

    Imprime los conteos que los tests del slice fijan (30 especies, 8
    significativas en estancamiento, 1 en mortalidad) para que una corrida
    manual detecte de inmediato un CSV cambiado.
    """
    sig_stall = [s for s in bundle.species if s.sig_stall]
    sig_mort = [s for s in bundle.species if s.sig_mort]

    print(f"Especies:  {len(bundle.species)}")
    print(f"Parcelas:  {len(bundle.plots)}")
    print(f"Varianza:  {len(bundle.variance)} filas")
    print()
    print(f"Especies con IC significativo (estancamiento): {len(sig_stall)}")
    for s in sorted(sig_stall, key=lambda x: -(x.or_stall or 0)):
        signo = "mas" if (s.or_stall or 1) > 1 else "menos"
        print(
            f"  {s.species_name:<28} OR {s.or_stall:5.2f} "
            f"[{s.or_stall_lo:.2f}, {s.or_stall_hi:.2f}]  se estanca {signo}"
        )
    print()
    print(f"Especies con IC significativo (mortalidad): {len(sig_mort)}")
    for s in sig_mort:
        print(
            f"  {s.species_name:<28} OR {s.or_mort:5.2f} "
            f"[{s.or_mort_lo:.2f}, {s.or_mort_hi:.2f}]"
        )
    print()
    for v in bundle.variance:
        print(
            f"  {v.model:<10} {v.grouping:<8} var={v.variance:.3f} "
            f"ICC={v.icc:.3f}  ({v.n_events}/{v.n_observations} eventos)"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=DEFAULT_PROCESSED,
        help="Directorio con los CSV de los modelos mixtos",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Lee y valida los CSV sin tocar la base de datos",
    )
    args = parser.parse_args(argv)

    try:
        bundle = build_bundle(args.processed_dir)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    report(bundle)

    if args.dry_run:
        print("\n--dry-run: no se escribio nada.")
        return 0

    try:
        session = get_session_factory()()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    try:
        counts = AnalyticsRepository(session).replace_all(*to_orm(bundle))
    finally:
        session.close()

    print(
        f"\nCargado: {counts['species']} especies, {counts['plots']} parcelas, "
        f"{counts['variance']} componentes de varianza."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

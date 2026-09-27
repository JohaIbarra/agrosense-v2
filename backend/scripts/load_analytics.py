"""Carga y publicacion versionada del Referente cientifico (E5).

Lee los efectos de los modelos mixtos ya ajustados (`data/processed/*.csv`) y
PUBLICA una version nueva: crea una fila en `reference_models` y sus tres
tablas de efectos, y desactiva la version anterior sin borrarla (E5,
docs/04-vision-producto.md §6.7 — antes de esto, `replace_all` borraba la
version previa sin rastro).

Uso:
    python scripts/load_analytics.py                    # publica en DATABASE_URL
    python scripts/load_analytics.py --dry-run          # no escribe, solo reporta
    python scripts/load_analytics.py --version v2       # etiqueta explicita
    python scripts/load_analytics.py --processed-dir otra/ruta

Requiere que la migracion `c7e9f2a4b6d8` este aplicada (`alembic upgrade head`).

Este script NO re-estima nada. Los modelos mixtos (`lme4::glmer` binomial) ya
se corrieron sobre `data/raw/anexo1.xlsx`; los CSV son la fuente de verdad y
este script solo los traduce a filas y las publica como una version.
"""
from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agrosense.adapters.analytics.effects_loader import (  # noqa: E402
    AnalyticsBundle,
    build_bundle,
)
from agrosense.adapters.db.models import (  # noqa: E402
    ReferenceModel,
    ReferencePlotEffect,
    ReferenceSpeciesEffect,
    VarianceComponent,
)
from agrosense.adapters.db.repository import ReferenceRepository  # noqa: E402
from agrosense.adapters.db.session import get_session_factory  # noqa: E402

DEFAULT_PROCESSED = Path(__file__).resolve().parents[1] / "data" / "processed"
SOURCE_DATASET = "data/raw/anexo1.xlsx"
METHOD = "lme4::glmer binomial"


def to_orm(bundle: AnalyticsBundle) -> tuple[
    list[ReferenceSpeciesEffect], list[ReferencePlotEffect], list[VarianceComponent]
]:
    """Traduce las filas del loader a instancias del ORM, sin version todavia.

    `reference_model_id` lo asigna `ReferenceRepository.publish_version`,
    que es quien conoce el id recien insertado de `reference_models`.
    """
    species = [
        ReferenceSpeciesEffect(
            species_name=r.species_name,
            effect_stall=r.effect_stall, se_stall=r.se_stall,
            or_stall=r.or_stall, or_stall_lo=r.or_stall_lo, or_stall_hi=r.or_stall_hi,
            sig_stall=r.sig_stall,
            effect_mort=r.effect_mort, se_mort=r.se_mort,
            or_mort=r.or_mort, or_mort_lo=r.or_mort_lo, or_mort_hi=r.or_mort_hi,
            sig_mort=r.sig_mort,
            n_observations=r.n_observations, n_trees=r.n_trees, gremio=r.gremio,
        )
        for r in bundle.species
    ]
    plots = [
        ReferencePlotEffect(
            plot_code=r.plot_code, localidad=r.localidad,
            effect_stall=r.effect_stall, se_stall=r.se_stall, or_stall=r.or_stall,
            effect_mort=r.effect_mort, se_mort=r.se_mort, or_mort=r.or_mort,
            n_trees=r.n_trees,
        )
        for r in bundle.plots
    ]
    variance = [
        VarianceComponent(
            model=r.model, grouping=r.grouping, variance=r.variance, sd=r.sd, icc=r.icc,
            n_levels=r.n_levels, n_observations=r.n_observations, n_events=r.n_events,
        )
        for r in bundle.variance
    ]
    return species, plots, variance


def build_reference_model(bundle: AnalyticsBundle, version: str | None = None) -> ReferenceModel:
    """La fila de `reference_models` para esta corrida.

    `version` por defecto es un timestamp UTC: no hay un numero de version
    humano todavia, y un timestamp es unico y ordenable sin coordinacion.
    """
    return ReferenceModel(
        version=version or datetime.now(UTC).strftime("%Y%m%d%H%M%S"),
        source_dataset=SOURCE_DATASET,
        method=METHOD,
        n_observations=sum(s.n_observations or 0 for s in bundle.species) or None,
        is_active=False,  # lo activa ReferenceRepository.publish_version
    )


def report(bundle: AnalyticsBundle, version: str) -> None:
    sig_stall = [s for s in bundle.species if s.sig_stall]
    sig_mort = [s for s in bundle.species if s.sig_mort]

    print(f"Version a publicar: {version}")
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
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--version", default=None, help="Etiqueta de la version (por defecto, timestamp UTC)."
    )
    args = parser.parse_args(argv)

    try:
        bundle = build_bundle(args.processed_dir)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    model = build_reference_model(bundle, version=args.version)
    report(bundle, model.version)

    if args.dry_run:
        print("\n--dry-run: no se publico nada.")
        return 0

    try:
        session = get_session_factory()()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    try:
        species, plots, variance = to_orm(bundle)
        published = ReferenceRepository(session).publish_version(model, species, plots, variance)
    finally:
        session.close()

    print(
        f"\nPublicado reference_models.id={published.id} (version={published.version}): "
        f"{len(species)} especies, {len(plots)} parcelas, {len(variance)} componentes."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

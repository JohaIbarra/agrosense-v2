"""Repositorios (adapters/db): persisten entidades de dominio via models.

Transaccionalidad de save_ingest: TODO o NADA (regla ADR-004 — sin
persistencia parcial). El commit lo hace el propio repo en el borde de
la operacion completa.
"""
from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from agrosense.adapters.db.models import (
    CampaignFile,
    MonitoringRow,
    ObservationRow,
    PlotAnalytics,
    PlotRow,
    Project,
    PropertyRow,
    SpeciesAnalytics,
    TreeRow,
    VarianceComponent,
)
from agrosense.application.dtos import CampaignData
from agrosense.application.errors import AppError
from agrosense.domain.errors import ProjectLabelMismatchWarning
from agrosense.domain.rules import plot_key, validate_tree_identity


def _fit(value: str | None, width: int) -> str | None:
    """Recorta a `width` un metadato que construye AgroSense.

    Solo para valores DERIVADOS (p. ej. varias cuadrillas unidas con "; "):
    si no caben, es responsabilidad nuestra que quepan. Los datos del arbol y
    de la parcela NO se recortan: un valor demasiado largo ahi se rechaza con
    INVALID_FILE (ver save_ingest), porque recortar un identificador podria
    fusionar dos parcelas distintas.
    """
    if value is None or len(value) <= width:
        return value
    return value[: width - 1] + "…"


# Atributos descriptivos de la parcela que se actualizan con el archivo mas
# reciente (como los del arbol: manda el ultimo archivo, docs/02-domain.md §2.4)
_PLOT_ATTRS = (
    "sampling_unit_code",
    "monitoring_unit",
    "floristic_design",
    "associated_cover",
    "establishment_cover",
)


class ProjectRepository:
    def __init__(self, session: Session):
        self._s = session

    def create(self, name: str, locality: str | None, description: str | None) -> Project:
        exists = self._s.execute(select(Project).where(Project.name == name)).scalar()
        if exists:
            raise AppError("DUPLICATE_NAME", f"Ya existe un proyecto llamado '{name}'.")
        proj = Project(name=name, locality=locality, description=description)
        self._s.add(proj)
        try:
            self._s.commit()
        except IntegrityError as exc:
            # Carrera entre el SELECT y el INSERT: la constraint es la verdad
            self._s.rollback()
            raise AppError(
                "DUPLICATE_NAME", f"Ya existe un proyecto llamado '{name}'."
            ) from exc
        return proj

    def get(self, project_id: int) -> Project | None:
        return self._s.get(Project, project_id)

    def list_all(self) -> list[Project]:
        return list(self._s.scalars(select(Project).order_by(Project.id)).all())

    def campaigns_count(self, project_id: int) -> int:
        return self._s.execute(
            select(func.count()).where(CampaignFile.project_id == project_id)
        ).scalar_one()

    def get_campaigns(self, project_id: int) -> list[CampaignFile]:
        return list(
            self._s.scalars(
                select(CampaignFile)
                .where(CampaignFile.project_id == project_id)
                .order_by(CampaignFile.ingested_at)
            ).all()
        )

    def get_trees(
        self, project_id: int, limit: int = 100, offset: int = 0
    ) -> list[TreeRow]:
        return list(
            self._s.scalars(
                select(TreeRow)
                .where(TreeRow.project_id == project_id)
                .order_by(TreeRow.id)
                .limit(limit)
                .offset(offset)
            ).all()
        )

    def get_observations(self, tree_row_id: int) -> list[ObservationRow]:
        return list(
            self._s.scalars(
                select(ObservationRow)
                .join(MonitoringRow, MonitoringRow.id == ObservationRow.monitoring_id)
                .where(ObservationRow.tree_row_id == tree_row_id)
                .order_by(MonitoringRow.number)
            ).all()
        )

    def get_monitorings(self, project_id: int) -> list[tuple[MonitoringRow, int]]:
        """Monitoreos del proyecto, en orden, con cuantas observaciones tiene cada uno."""
        rows = self._s.execute(
            select(MonitoringRow, func.count(ObservationRow.id))
            .outerjoin(ObservationRow, ObservationRow.monitoring_id == MonitoringRow.id)
            .where(MonitoringRow.project_id == project_id)
            .group_by(MonitoringRow.id)
            .order_by(MonitoringRow.number)
        ).all()
        return [(m, n) for m, n in rows]

    def get_tree_row(
        self, project_id: int, tree_row_id: int
    ) -> TreeRow | None:
        return self._s.scalar(
            select(TreeRow).where(
                TreeRow.id == tree_row_id,
                TreeRow.project_id == project_id,
            )
        )


class CampaignRepository:
    def __init__(self, session: Session):
        self._s = session

    def save_ingest(
        self,
        project_id: int,
        result: CampaignData,
        filename: str,
        sha256: str,
    ) -> dict:
        """Persiste la CampaignData completa en UNA transaccion.

        Idempotente por `(project_id, tree_id)` y por `(arbol, campana)`
        (decision de producto del 2026-09-20, hallazgo R1):

          - mismo sha256  -> DUPLICATE_FILE, no se crea campana;
          - sha distinto  -> campana NUEVA, la anterior intacta; los arboles
            que ya existen se reutilizan (su identidad persiste entre
            campanas, docs/02-domain.md §2.4) y las observaciones que ya
            existen se actualizan: manda el archivo mas reciente.

        Antes se insertaban arboles siempre, asi que el segundo archivo
        chocaba contra uq_tree_project_tree_id y el IntegrityError salia
        como un 500 sin cuerpo.

        Raises:
            AppError("DUPLICATE_FILE"): ese archivo ya se cargo al proyecto.
            AppError("DUPLICATE_TREE"): colision de identidad no prevista.
        """
        dup = self._s.execute(
            select(func.count()).where(
                CampaignFile.project_id == project_id,
                CampaignFile.sha256 == sha256,
            )
        ).scalar_one()
        if dup:
            raise AppError(
                "DUPLICATE_FILE",
                "Este archivo ya fue cargado en el proyecto. Si corrigio datos, "
                "vuelva a exportarlo: el contenido debe cambiar.",
            )

        extra_warnings = self._project_label_warnings(project_id, result)
        meta = result.file_metadata

        try:
            # Orden de las dependencias: predio -> parcela -> arbol, y
            # monitoreo -> observacion. Todo dentro de la misma transaccion.
            property_ids = self._upsert_properties(project_id, result)
            plot_ids = self._upsert_plots(project_id, result, property_ids)
            tree_db_id = self._upsert_trees(project_id, result, plot_ids)
            monitoring_ids = self._upsert_monitorings(project_id, result)
            self._upsert_observations(result, tree_db_id, monitoring_ids)

            deaths = sum(1 for o in result.observations if o.alive is False)
            campaign = CampaignFile(
                project_id=project_id,
                filename=filename,
                sha256=sha256,
                mapping_version=result.mapping_version,
                trees=len(result.trees),
                observations=len(result.observations),
                deaths=deaths,
                source_project_label=_fit(meta.project_label, 500),
                source_event=_fit(meta.event, 200),
                source_field_crew=_fit(meta.field_crew, 500),
                source_recorder=_fit(meta.recorder, 300),
            )
            campaign.monitorings = [
                self._s.get(MonitoringRow, monitoring_ids[n]) for n in result.monitorings
            ]
            self._s.add(campaign)
            self._s.commit()

            return {
                "campaign_id": campaign.id,
                "trees": len(result.trees),
                "observations": len(result.observations),
                "deaths": deaths,
                "warnings": result.warnings,
                "extra_warnings": extra_warnings,
                "monitorings": result.monitorings,
                "mapping_version": result.mapping_version,
            }
        except IntegrityError as exc:
            self._s.rollback()
            raise self._integrity_error(exc) from exc
        except DataError as exc:
            # Postgres rechaza un valor que no cabe en su columna. SQLite no
            # aplica longitudes, asi que solo se ve contra la base real; antes
            # salia como un 500 "error interno".
            self._s.rollback()
            raise AppError(
                "INVALID_FILE",
                "Un valor del archivo es demasiado largo para su campo (por ejemplo, "
                "un nombre de especie, parcela o diseno florístico). Revise que las "
                "celdas contengan solo el dato y no texto pegado por error.",
            ) from exc
        except Exception:
            self._s.rollback()
            raise

    @staticmethod
    def _integrity_error(exc: IntegrityError) -> AppError:
        """Traduce la constraint que fallo a su propio codigo.

        Un solo codigo para todo seria repetir el error de R2 en otra capa:
        inferir el significado de un fallo en vez de distinguirlo. Aqui la
        fuente es el nombre de la constraint, que lo pone el esquema, no
        el usuario.
        """
        detalle = str(getattr(exc, "orig", exc))
        if "uq_campaign_project_file" in detalle:
            return AppError(
                "DUPLICATE_FILE",
                "Este archivo ya fue cargado en el proyecto.",
            )
        if "uq_tree_project_tree_id" in detalle:
            return AppError(
                "DUPLICATE_TREE",
                "El archivo repite identificadores de arbol dentro del proyecto. "
                "Revise que cada ID_MUEST aparezca una sola vez.",
            )
        if "uq_observation_tree_monitoring" in detalle:
            return AppError(
                "DUPLICATE_TREE",
                "El archivo trae dos mediciones del mismo arbol en el mismo "
                "monitoreo. Revise las filas duplicadas.",
            )
        # Constraint no prevista: es un fallo nuestro, no del archivo
        raise exc

    def _project_label_warnings(self, project_id: int, result: CampaignData) -> list:
        """Aviso si el archivo nombra otro proyecto que las cargas anteriores.

        Se compara con la columna `Proyecto` de los ARCHIVOS previos, no con el
        nombre del proyecto en AgroSense (ver ProjectLabelMismatchWarning).
        """
        incoming = result.file_metadata.project_label
        if not incoming:
            return []
        previous = self._s.scalar(
            select(CampaignFile.source_project_label)
            .where(
                CampaignFile.project_id == project_id,
                CampaignFile.source_project_label.is_not(None),
            )
            .order_by(CampaignFile.ingested_at, CampaignFile.id)
            .limit(1)
        )
        if previous and previous != incoming:
            return [ProjectLabelMismatchWarning(incoming, previous)]
        return []

    def _upsert_properties(self, project_id: int, result: CampaignData) -> dict[str, int]:
        """Predios del archivo (`LOCALIDAD`): crea los nuevos, reutiliza los viejos."""
        existing = {
            p.name: p.id
            for p in self._s.scalars(
                select(PropertyRow).where(PropertyRow.project_id == project_id)
            ).all()
        }
        nombres = {t.locality for t in result.trees if t.locality} - existing.keys()
        for name in sorted(nombres):
            fila = PropertyRow(project_id=project_id, name=name)
            self._s.add(fila)
            self._s.flush()
            existing[name] = fila.id
        return existing

    def _upsert_plots(
        self, project_id: int, result: CampaignData, property_ids: dict[str, int]
    ) -> dict[str, int]:
        """Parcelas del archivo, por su clave (`domain.rules.plot_key`).

        Los atributos descriptivos (diseno, coberturas…) se toman del archivo
        mas reciente, igual que los del arbol.
        """
        existing = {
            p.code: p
            for p in self._s.scalars(
                select(PlotRow).where(PlotRow.project_id == project_id)
            ).all()
        }

        primer_arbol: dict[str, object] = {}
        for tree in result.trees:
            key = plot_key(tree)
            if key is not None and key not in primer_arbol:
                primer_arbol[key] = tree

        for key, tree in primer_arbol.items():
            fila = existing.get(key)
            if fila is None:
                fila = PlotRow(project_id=project_id, code=key)
                self._s.add(fila)
                existing[key] = fila
            fila.plot_label = tree.plot_id
            fila.property_id = property_ids.get(tree.locality) if tree.locality else None
            for attr in _PLOT_ATTRS:
                setattr(fila, attr, getattr(tree, attr))
        self._s.flush()
        return {code: fila.id for code, fila in existing.items()}

    def _upsert_monitorings(self, project_id: int, result: CampaignData) -> dict[int, int]:
        """Monitoreos que trae el archivo (decision D1: uno o varios).

        `Responsables` y `Anotador` son de TODO el archivo y el archivo declara
        su monitoreo en `Evento`, asi que se atribuyen al mas reciente que
        trae — no a M1-M3, que los midio otra cuadrilla en otra fecha.
        """
        existing = {
            m.number: m
            for m in self._s.scalars(
                select(MonitoringRow).where(MonitoringRow.project_id == project_id)
            ).all()
        }
        for number in result.monitorings:
            if number not in existing:
                fila = MonitoringRow(project_id=project_id, number=number)
                self._s.add(fila)
                existing[number] = fila

        if result.monitorings:
            ultimo = existing[result.monitorings[-1]]
            meta = result.file_metadata
            if meta.field_crew:
                ultimo.field_crew = _fit(meta.field_crew, 500)
            if meta.recorder:
                ultimo.recorder = _fit(meta.recorder, 300)
        self._s.flush()
        return {number: fila.id for number, fila in existing.items()}

    def _tree_ids(self, project_id: int) -> dict[str, int]:
        """tree_id de campo -> id de fila, para los arboles ya persistidos."""
        rows = self._s.execute(
            select(TreeRow.tree_id, TreeRow.id).where(TreeRow.project_id == project_id)
        ).all()
        return {tree_id: row_id for tree_id, row_id in rows}

    def _upsert_trees(
        self, project_id: int, result: CampaignData, plot_ids: dict[str, int]
    ) -> dict[str, int]:
        """Inserta los arboles nuevos y corrige los descriptivos de los viejos.

        Tres casos por arbol:
          - no existe            -> INSERT;
          - existe y su IDENTIDAD coincide -> se actualizan los atributos
            descriptivos (familia, nombre comun, gremio, elevacion) con el
            archivo mas reciente. El predio y los datos de parcela viven en
            `plots` desde E0;
          - existe y su identidad DIVERGE -> DomainError, la campana se
            rechaza entera. Antes esto se descartaba en silencio y la API
            respondia 201 sin haber corregido nada.

        Resuelve los ids con dos SELECT en vez de pedirlos fila a fila con
        `return_defaults=True`. Ojo con la tentacion de vender eso como el
        arreglo del hallazgo #G: medido contra Supabase, el primer upload
        (con los 856 INSERT) sigue en ~79s. Lo que si baja es el segundo,
        a ~5s, porque ya no inserta arboles. #G sigue abierto.
        """
        existing = {
            row.tree_id: row
            for row in self._s.scalars(
                select(TreeRow).where(TreeRow.project_id == project_id)
            ).all()
        }

        nuevos = []
        for tree in result.trees:
            fila = existing.get(tree.tree_id)
            if fila is None:
                nuevos.append(tree)
                continue
            # Invariante de dominio: la identidad no cambia entre cargas
            validate_tree_identity(fila, tree)
            fila.family = tree.family
            fila.common_name = tree.common_name
            fila.guild = tree.guild
            fila.elevation_m = tree.elevation_m
            key = plot_key(tree)
            if key is not None:
                fila.plot_row_id = plot_ids[key]

        if nuevos:
            self._s.execute(
                insert(TreeRow),
                [
                    {
                        "project_id": project_id,
                        "tree_id": t.tree_id,
                        "species": t.species,
                        "family": t.family,
                        "common_name": t.common_name,
                        "guild": t.guild,
                        "plot_row_id": (
                            plot_ids[plot_key(t)] if plot_key(t) is not None else None
                        ),
                        "coord_x": t.coord_x,
                        "coord_y": t.coord_y,
                        "elevation_m": t.elevation_m,
                    }
                    for t in nuevos
                ],
            )
        self._s.flush()
        return self._tree_ids(project_id)

    def _upsert_observations(
        self,
        result: CampaignData,
        tree_db_id: dict[str, int],
        monitoring_ids: dict[int, int],
    ) -> None:
        """Inserta las observaciones nuevas y actualiza las que ya existian.

        `UNIQUE(tree_row_id, monitoring_id)` admite una fila por arbol y
        monitoreo, asi que un archivo corregido pisa el valor anterior: manda
        el mas reciente. Que archivos entraron y cuando queda en
        `campaign_files`.
        """
        monitoreos = set(monitoring_ids.values())
        previas = {
            (tree_row_id, monitoring_id): obs_id
            for obs_id, tree_row_id, monitoring_id in self._s.execute(
                select(
                    ObservationRow.id,
                    ObservationRow.tree_row_id,
                    ObservationRow.monitoring_id,
                ).where(ObservationRow.monitoring_id.in_(monitoreos))
            ).all()
        }

        a_insertar: list[dict] = []
        a_actualizar: list[dict] = []
        for obs in result.observations:
            fila = {
                "tree_row_id": tree_db_id[obs.tree_id],
                "monitoring_id": monitoring_ids[obs.campaign],
                "height_m": obs.height_m,
                "crown_diameter_m": obs.crown_diameter_m,
                "dap_cm": obs.dap_cm,
                "dap_status": obs.dap_status.value,
                "phytosanitary": obs.phytosanitary,
                "alive": obs.alive,
                "colonization": obs.colonization,
                "field_notes": obs.field_notes,
            }
            obs_id = previas.get((fila["tree_row_id"], fila["monitoring_id"]))
            if obs_id is None:
                a_insertar.append(fila)
            else:
                a_actualizar.append({"id": obs_id, **fila})

        if a_insertar:
            self._s.execute(insert(ObservationRow), a_insertar)
        if a_actualizar:
            self._s.execute(update(ObservationRow), a_actualizar)
        self._s.flush()


class AnalyticsRepository:
    """Lectura y recarga de las tablas analiticas del slice 5.

    Es de solo lectura para la API: las escrituras vienen de
    `scripts/load_analytics.py`, no de un endpoint. Por eso `replace_all` no
    esta expuesto en ninguna route — recargar la analitica es una operacion
    de datos, no una accion de usuario.
    """

    def __init__(self, session: Session):
        self._s = session

    # ── Lectura ────────────────────────────────────────────────────────────

    def list_species(self, gremio: str | None = None) -> list[SpeciesAnalytics]:
        stmt = select(SpeciesAnalytics)
        if gremio is not None:
            stmt = stmt.where(SpeciesAnalytics.gremio == gremio)
        return list(self._s.scalars(stmt.order_by(SpeciesAnalytics.species_name)).all())

    def get_species(self, name: str) -> SpeciesAnalytics | None:
        return self._s.get(SpeciesAnalytics, name)

    def list_plots(self, localidad: str | None = None) -> list[PlotAnalytics]:
        stmt = select(PlotAnalytics)
        if localidad is not None:
            stmt = stmt.where(PlotAnalytics.localidad == localidad)
        return list(self._s.scalars(stmt.order_by(PlotAnalytics.plot_code)).all())

    def list_variance(self) -> list[VarianceComponent]:
        return list(
            self._s.scalars(
                select(VarianceComponent).order_by(
                    VarianceComponent.model, VarianceComponent.grouping
                )
            ).all()
        )

    # ── Recarga (solo desde el script de carga) ────────────────────────────

    def replace_all(
        self,
        species: list[SpeciesAnalytics],
        plots: list[PlotAnalytics],
        variance: list[VarianceComponent],
    ) -> dict[str, int]:
        """Reemplaza las tres tablas en UNA transaccion (ADR-004: todo o nada).

        Es un borrado y recarga completos, no un upsert fila a fila: los
        efectos provienen de un ajuste conjunto sobre todo el panel, asi que
        mezclar filas de dos corridas distintas daria un ranking que no
        corresponde a ningun modelo. Si la carga falla a medias, la tabla
        anterior queda intacta.
        """
        try:
            self._s.query(SpeciesAnalytics).delete()
            self._s.query(PlotAnalytics).delete()
            self._s.query(VarianceComponent).delete()
            self._s.add_all(species)
            self._s.add_all(plots)
            self._s.add_all(variance)
            self._s.commit()
        except Exception:
            self._s.rollback()
            raise
        return {
            "species": len(species),
            "plots": len(plots),
            "variance": len(variance),
        }

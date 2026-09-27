"""Repositorios (adapters/db): persisten entidades de dominio via models.

Transaccionalidad de save_ingest: TODO o NADA (regla ADR-004 — sin
persistencia parcial). El commit lo hace el propio repo en el borde de
la operacion completa.
"""
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from agrosense.adapters.analytics.effects_loader import normalize_level
from agrosense.adapters.db.models import (
    CampaignFile,
    Engineer,
    ImageryLayerRow,
    MonitoringAnalysisRow,
    MonitoringRow,
    ObservationRow,
    PlotRow,
    Project,
    PropertyRow,
    ReferenceModel,
    ReferencePlotEffect,
    ReferenceSpeciesEffect,
    SatelliteIndexValueRow,
    TreeRow,
    VarianceComponent,
)
from agrosense.application.dtos import CampaignData
from agrosense.application.errors import AppError
from agrosense.domain.entities import Observation, StatusSemantic, Tree
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


def _bulk_insert(session: Session, model, rows: list[dict]) -> None:
    """Inserta `rows` en UNA sentencia, cueste lo que cueste el patron de nulos.

    Por que sobre `model.__table__` y no sobre el modelo (regresion #G,
    medida contra Supabase el 2026-09-22): el `insert()` de ORM agrupa las
    filas por el conjunto de columnas NO NULAS y emite una sentencia por
    grupo. En campo cada fila tiene su propio patron de nulos (un arbol sin
    copa, otro sin estado fitosanitario, otro muerto sin medidas), asi que
    3146 observaciones salian en **615 sentencias** = 615 viajes de ida y
    vuelta contra el pooler, 70 de los 92 segundos que tardaba la carga.
    El INSERT de Core compila la lista de columnas una vez y manda todas las
    filas en un solo executemany. Gate: tests/db/test_ingest_statements.py.
    """
    if rows:
        session.execute(insert(model.__table__), rows)


# Atributos descriptivos de la parcela que se actualizan con el archivo mas
# reciente (como los del arbol: manda el ultimo archivo, docs/02-domain.md §2.4)
_PLOT_ATTRS = (
    "sampling_unit_code",
    "monitoring_unit",
    "floristic_design",
    "associated_cover",
    "establishment_cover",
)


class EngineerRepository:
    """Perfiles de ingeniero (E1). La identidad la da el token, no esta tabla."""

    def __init__(self, session: Session):
        self._s = session

    def get(self, engineer_id: str) -> Engineer | None:
        return self._s.get(Engineer, engineer_id)

    def ensure(self, engineer_id: str, email: str | None) -> Engineer:
        """Devuelve el perfil, creandolo en la primera peticion autenticada.

        El email se refresca desde el token: si el ingeniero lo cambia en
        Supabase, AgroSense lo ve en su siguiente peticion.
        """
        eng = self._s.get(Engineer, engineer_id)
        if eng is None:
            eng = Engineer(id=engineer_id, email=email)
            self._s.add(eng)
            try:
                self._s.commit()
            except IntegrityError:
                # Dos peticiones simultaneas del mismo ingeniero nuevo
                self._s.rollback()
                eng = self._s.get(Engineer, engineer_id)
        elif email and eng.email != email:
            eng.email = email
            self._s.commit()
        return eng

    def update(self, engineer: Engineer, **fields) -> Engineer:
        for key, value in fields.items():
            setattr(engineer, key, value)
        self._s.commit()
        return engineer


class ProjectRepository:
    def __init__(self, session: Session):
        self._s = session

    def create(
        self,
        name: str,
        locality: str | None = None,
        description: str | None = None,
        *,
        owner_id: str,
        **fields,
    ) -> Project:
        """Crea un proyecto del ingeniero y le asigna su codigo interno.

        El codigo `AGS-{año}-{id:04d}` sale del id, asi que no hay carrera
        posible entre dos altas simultaneas: se inserta con un marcador unico,
        se obtiene el id y se fija el codigo en la misma transaccion.
        """
        if self._name_taken(owner_id, name):
            raise AppError("DUPLICATE_NAME", f"Ya tiene un proyecto llamado '{name}'.")
        proj = Project(
            name=name,
            locality=locality,
            description=description,
            owner_id=owner_id,
            project_code=f"TMP-{uuid.uuid4().hex}",
            **fields,
        )
        self._s.add(proj)
        try:
            self._s.flush()
            proj.project_code = f"AGS-{proj.created_at.year}-{proj.id:04d}"
            self._s.commit()
        except IntegrityError as exc:
            # Carrera entre el SELECT y el INSERT: la constraint es la verdad
            self._s.rollback()
            raise AppError(
                "DUPLICATE_NAME", f"Ya tiene un proyecto llamado '{name}'."
            ) from exc
        return proj

    def _name_taken(self, owner_id: str, name: str, exclude_id: int | None = None) -> bool:
        stmt = select(Project.id).where(Project.owner_id == owner_id, Project.name == name)
        if exclude_id is not None:
            stmt = stmt.where(Project.id != exclude_id)
        return self._s.scalar(stmt) is not None

    def update(self, project: Project, **fields) -> Project:
        new_name = fields.get("name")
        if new_name and self._name_taken(project.owner_id, new_name, exclude_id=project.id):
            raise AppError("DUPLICATE_NAME", f"Ya tiene un proyecto llamado '{new_name}'.")
        for key, value in fields.items():
            setattr(project, key, value)
        try:
            self._s.commit()
        except IntegrityError as exc:
            self._s.rollback()
            raise AppError("DUPLICATE_NAME", "Ya tiene un proyecto con ese nombre.") from exc
        return project

    def get(self, project_id: int) -> Project | None:
        """Lectura SIN autorizacion: solo para uso interno y tests.

        Toda ruta que atiende a un ingeniero usa `get_owned`.
        """
        return self._s.get(Project, project_id)

    def get_owned(self, project_id: int, owner_id: str) -> Project | None:
        """El proyecto, solo si pertenece al ingeniero. Si no, None (→ 404)."""
        return self._s.scalar(
            select(Project).where(Project.id == project_id, Project.owner_id == owner_id)
        )

    def list_for_owner(self, owner_id: str) -> list[Project]:
        return list(
            self._s.scalars(
                select(Project).where(Project.owner_id == owner_id).order_by(Project.id)
            ).all()
        )

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

    def get_monitoring(self, project_id: int, number: int) -> MonitoringRow | None:
        return self._s.scalar(
            select(MonitoringRow).where(
                MonitoringRow.project_id == project_id, MonitoringRow.number == number
            )
        )

    def monitoring_dates(self, project_id: int) -> dict:
        """{numero: fecha} de los monitoreos del proyecto que ya tienen fecha."""
        rows = self._s.execute(
            select(MonitoringRow.number, MonitoringRow.monitoring_date).where(
                MonitoringRow.project_id == project_id,
                MonitoringRow.monitoring_date.is_not(None),
            )
        ).all()
        return {number: fecha for number, fecha in rows}

    def update_monitoring(self, monitoring: MonitoringRow, **fields) -> MonitoringRow:
        for key, value in fields.items():
            setattr(monitoring, key, value)
        self._s.commit()
        return monitoring

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
            _bulk_insert(
                self._s,
                TreeRow,
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

        _bulk_insert(self._s, ObservationRow, a_insertar)
        if a_actualizar:
            # El UPDATE por clave primaria del ORM ya viaja en un solo
            # executemany (todas las filas traen las mismas claves).
            self._s.execute(update(ObservationRow), a_actualizar)
        self._s.flush()


class ReferenceRepository:
    """Lectura y publicacion versionada del Referente cientifico (E5).

    Publicar SIEMPRE anade una version nueva; nunca borra una anterior. Las
    lecturas (`list_species`, `get_species`, `list_plots`, `list_variance`)
    filtran por la version activa: la API nunca mezcla efectos de dos
    corridas distintas del modelo mixto.
    """

    def __init__(self, session: Session):
        self._s = session

    # ── Lectura ────────────────────────────────────────────────────────────

    def active_model(self) -> ReferenceModel | None:
        return self._s.scalar(select(ReferenceModel).where(ReferenceModel.is_active.is_(True)))

    def list_models(self) -> list[ReferenceModel]:
        return list(
            self._s.scalars(
                select(ReferenceModel).order_by(ReferenceModel.computed_at.desc())
            ).all()
        )

    def list_species(self, gremio: str | None = None) -> list[ReferenceSpeciesEffect]:
        active = self.active_model()
        if active is None:
            return []
        stmt = select(ReferenceSpeciesEffect).where(
            ReferenceSpeciesEffect.reference_model_id == active.id
        )
        if gremio is not None:
            stmt = stmt.where(ReferenceSpeciesEffect.gremio == gremio)
        return list(
            self._s.scalars(stmt.order_by(ReferenceSpeciesEffect.species_name)).all()
        )

    def get_species(self, name: str) -> ReferenceSpeciesEffect | None:
        active = self.active_model()
        if active is None:
            return None
        return self._s.get(ReferenceSpeciesEffect, (active.id, name))

    def list_plots(self, localidad: str | None = None) -> list[ReferencePlotEffect]:
        active = self.active_model()
        if active is None:
            return []
        stmt = select(ReferencePlotEffect).where(
            ReferencePlotEffect.reference_model_id == active.id
        )
        if localidad is not None:
            stmt = stmt.where(ReferencePlotEffect.localidad == localidad)
        return list(self._s.scalars(stmt.order_by(ReferencePlotEffect.plot_code)).all())

    def list_variance(self) -> list[VarianceComponent]:
        active = self.active_model()
        if active is None:
            return []
        return list(
            self._s.scalars(
                select(VarianceComponent)
                .where(VarianceComponent.reference_model_id == active.id)
                .order_by(VarianceComponent.model, VarianceComponent.grouping)
            ).all()
        )

    # ── Publicacion (UC-R2, solo desde scripts/load_analytics.py) ──────────

    def publish_version(
        self,
        model: ReferenceModel,
        species: list[ReferenceSpeciesEffect],
        plots: list[ReferencePlotEffect],
        variance: list[VarianceComponent],
    ) -> ReferenceModel:
        """Publica una version nueva del referente (ADR-004: todo o nada).

        Desactiva TODAS las filas activas (un UPDATE masivo, no solo la que
        devuelve `active_model()`: eso protege contra que alguna otra fila
        quedara activa por fuera de esta clase) e inserta la nueva, ya
        activa, con sus tres tablas de efectos estampadas con su
        `reference_model_id`. La version anterior NO se borra: sigue en la
        base para trazabilidad, solo deja de ser la que leen `list_species` /
        `get_species` / etc. El indice unico parcial
        `uq_reference_models_single_active` (ADR-007) es la garantia de
        ultima instancia: esta desactivacion es la primera.
        """
        try:
            self._s.execute(
                update(ReferenceModel)
                .where(ReferenceModel.is_active.is_(True))
                .values(is_active=False)
            )
            model.is_active = True
            self._s.add(model)
            self._s.flush()  # asigna model.id antes de estampar las filas

            for row in species:
                row.reference_model_id = model.id
            for row in plots:
                row.reference_model_id = model.id
            for row in variance:
                row.reference_model_id = model.id

            self._s.add_all(species)
            self._s.add_all(plots)
            self._s.add_all(variance)
            self._s.commit()
        except Exception:
            self._s.rollback()
            raise
        return model


class ImageryRepository:
    """Capas de imagen de un proyecto (E6b).

    Las capas se identifican SIEMPRE dentro de su proyecto: un id suelto no da
    acceso a la capa de otro.
    """

    def __init__(self, session: Session):
        self._s = session

    def list_for_project(self, project_id: int) -> list[ImageryLayerRow]:
        return list(
            self._s.scalars(
                select(ImageryLayerRow)
                .where(ImageryLayerRow.project_id == project_id)
                .order_by(ImageryLayerRow.id)
            ).all()
        )

    def get(self, project_id: int, layer_id: int) -> ImageryLayerRow | None:
        return self._s.scalar(
            select(ImageryLayerRow).where(
                ImageryLayerRow.project_id == project_id, ImageryLayerRow.id == layer_id
            )
        )

    def name_taken(self, project_id: int, name: str) -> bool:
        return (
            self._s.scalar(
                select(func.count())
                .select_from(ImageryLayerRow)
                .where(ImageryLayerRow.project_id == project_id, ImageryLayerRow.name == name)
            )
            or 0
        ) > 0

    def create(self, project_id: int, **fields) -> ImageryLayerRow:
        row = ImageryLayerRow(project_id=project_id, **fields)
        self._s.add(row)
        self._s.commit()
        self._s.refresh(row)
        return row

    def delete(self, layer: ImageryLayerRow) -> None:
        self._s.delete(layer)
        self._s.commit()


class SatelliteIndexRepository:
    """Lecturas de indices espectrales de un proyecto (E10a)."""

    def __init__(self, session: Session):
        self._s = session

    def list_for_project(self, project_id: int, index_name: str) -> list[SatelliteIndexValueRow]:
        return list(
            self._s.scalars(
                select(SatelliteIndexValueRow)
                .where(
                    SatelliteIndexValueRow.project_id == project_id,
                    SatelliteIndexValueRow.index_name == index_name,
                )
                .order_by(
                    SatelliteIndexValueRow.acquired_at,
                    SatelliteIndexValueRow.property_name,
                )
            ).all()
        )

    def known_scenes(self, project_id: int, index_name: str) -> set[tuple[str, str]]:
        """(predio, escena) ya medidos: no se vuelve a pedir lo que ya esta."""
        filas = self._s.execute(
            select(SatelliteIndexValueRow.property_name, SatelliteIndexValueRow.scene_id).where(
                SatelliteIndexValueRow.project_id == project_id,
                SatelliteIndexValueRow.index_name == index_name,
            )
        ).all()
        return {(p, s) for p, s in filas}

    def save_readings(self, project_id: int, readings: list[dict]) -> int:
        """Guarda lecturas nuevas; las repetidas se ignoran (idempotente)."""
        if not readings:
            return 0
        conocidas = self.known_scenes(project_id, readings[0]["index_name"])
        nuevas = [
            r for r in readings if (r["property_name"], r["scene_id"]) not in conocidas
        ]
        if not nuevas:
            return 0
        _bulk_insert(
            self._s,
            SatelliteIndexValueRow,
            [{"project_id": project_id, **r} for r in nuevas],
        )
        self._s.commit()
        return len(nuevas)


class ProjectAnalysisRepository:
    """Datos del proyecto para el analisis exploratorio y sus snapshots (E3).

    `load_dataset` devuelve ENTIDADES DE DOMINIO (`Tree`, `Observation`), no
    filas del ORM: el motor de analisis no sabe nada de SQLAlchemy, y asi
    recibe exactamente lo mismo que produce la ingesta.
    """

    def __init__(self, session: Session):
        self._s = session

    def load_dataset(self, project_id: int) -> tuple[list[Tree], list[Observation]]:
        """Todos los arboles y observaciones del proyecto, en dos consultas."""
        tree_rows = self._s.execute(
            select(TreeRow, PlotRow, PropertyRow)
            .outerjoin(PlotRow, PlotRow.id == TreeRow.plot_row_id)
            .outerjoin(PropertyRow, PropertyRow.id == PlotRow.property_id)
            .where(TreeRow.project_id == project_id)
            .order_by(TreeRow.id)
        ).all()
        trees: list[Tree] = []
        tree_ids: dict[int, str] = {}
        for t, plot, prop in tree_rows:
            tree_ids[t.id] = t.tree_id
            trees.append(
                Tree(
                    tree_id=t.tree_id,
                    species=t.species,
                    family=t.family,
                    common_name=t.common_name,
                    guild=t.guild,
                    plot_id=plot.plot_label if plot else None,
                    locality=prop.name if prop else None,
                    coord_x=t.coord_x,
                    coord_y=t.coord_y,
                    elevation_m=t.elevation_m,
                    sampling_unit_code=plot.sampling_unit_code if plot else None,
                    monitoring_unit=plot.monitoring_unit if plot else None,
                    floristic_design=plot.floristic_design if plot else None,
                    associated_cover=plot.associated_cover if plot else None,
                    establishment_cover=plot.establishment_cover if plot else None,
                )
            )

        obs_rows = self._s.execute(
            select(
                ObservationRow.tree_row_id,
                MonitoringRow.number,
                ObservationRow.height_m,
                ObservationRow.crown_diameter_m,
                ObservationRow.dap_cm,
                ObservationRow.dap_status,
                ObservationRow.phytosanitary,
                ObservationRow.alive,
                ObservationRow.field_notes,
            )
            .join(MonitoringRow, MonitoringRow.id == ObservationRow.monitoring_id)
            .where(MonitoringRow.project_id == project_id)
            .order_by(ObservationRow.tree_row_id, MonitoringRow.number)
        ).all()
        observations = [
            Observation(
                tree_id=tree_ids[r.tree_row_id],
                campaign=r.number,
                height_m=r.height_m,
                crown_diameter_m=r.crown_diameter_m,
                dap_cm=r.dap_cm,
                dap_status=StatusSemantic(r.dap_status),
                phytosanitary=r.phytosanitary,
                alive=r.alive,
                colonization=None,
                field_notes=r.field_notes,
            )
            for r in obs_rows
            if r.tree_row_id in tree_ids
        ]
        return trees, observations

    def get_snapshot(self, project_id: int, number: int) -> MonitoringAnalysisRow | None:
        return self._s.scalar(
            select(MonitoringAnalysisRow)
            .join(MonitoringRow, MonitoringRow.id == MonitoringAnalysisRow.monitoring_id)
            .where(MonitoringRow.project_id == project_id, MonitoringRow.number == number)
        )

    def save_snapshots(
        self,
        project_id: int,
        snapshots: dict[int, dict],
        analysis_version: str,
        input_hash: str,
    ) -> list[MonitoringAnalysisRow]:
        """Reemplaza los snapshots de esos monitoreos en UNA transaccion."""
        monitorings = {
            m.number: m
            for m in self._s.scalars(
                select(MonitoringRow).where(MonitoringRow.project_id == project_id)
            ).all()
        }
        saved = []
        try:
            for number, payload in snapshots.items():
                monitoring = monitorings[number]
                row = self._s.scalar(
                    select(MonitoringAnalysisRow).where(
                        MonitoringAnalysisRow.monitoring_id == monitoring.id
                    )
                )
                if row is None:
                    row = MonitoringAnalysisRow(project_id=project_id, monitoring_id=monitoring.id)
                    self._s.add(row)
                row.analysis_version = analysis_version
                row.input_hash = input_hash
                row.payload = payload
                row.computed_at = datetime.now(UTC)
                saved.append(row)
            self._s.commit()
        except Exception:
            self._s.rollback()
            raise
        return saved


class ProjectSpeciesRepository:
    """Especies plantadas de un proyecto, para el contraste con el referente
    cientifico (E5, UC-AN3)."""

    def __init__(self, session: Session):
        self._s = session

    def list_species(self, project_id: int) -> list[tuple[str, int]]:
        """(especie, arboles distintos) del proyecto, especie ascendente.

        Normaliza con `normalize_level` (la misma funcion que usa el
        Referente al publicarse, `adapters/analytics/effects_loader.py`):
        la ingesta (`wide_to_long.py`) solo hace `.strip()`, asi que un NBSP
        interno u otro espacio Unicode sobrevive dentro del nombre. Sin
        normalizar aqui, esa especie nunca casaria contra
        `reference_species_effects` y `has_reference` saldria False para una
        especie que SI esta en el referente. Variantes crudas que normalizan
        al mismo nombre se fusionan sumando sus arboles.
        """
        stmt = (
            select(TreeRow.species, func.count(TreeRow.id))
            .where(TreeRow.project_id == project_id)
            .group_by(TreeRow.species)
        )
        counts: dict[str, int] = {}
        for species, count in self._s.execute(stmt).all():
            name = normalize_level(species)
            counts[name] = counts.get(name, 0) + int(count)
        return sorted(counts.items())

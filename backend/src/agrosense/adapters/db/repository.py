"""Repositorios (adapters/db): persisten entidades de dominio via models.

Transaccionalidad de save_ingest: TODO o NADA (regla ADR-004 — sin
persistencia parcial). El commit lo hace el propio repo en el borde de
la operacion completa.
"""
from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from agrosense.adapters.db.models import (
    CampaignFile,
    ObservationRow,
    Project,
    TreeRow,
)
from agrosense.application.dtos import CampaignData
from agrosense.application.errors import AppError
from agrosense.domain.rules import validate_tree_identity


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
                .where(ObservationRow.tree_row_id == tree_row_id)
                .order_by(ObservationRow.campaign)
            ).all()
        )

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

        try:
            tree_db_id = self._upsert_trees(project_id, result)
            self._upsert_observations(project_id, result, tree_db_id)

            deaths = sum(1 for o in result.observations if o.alive is False)
            campaign = CampaignFile(
                project_id=project_id,
                filename=filename,
                sha256=sha256,
                mapping_version=result.mapping_version,
                trees=len(result.trees),
                observations=len(result.observations),
                deaths=deaths,
            )
            self._s.add(campaign)
            self._s.commit()

            return {
                "campaign_id": campaign.id,
                "trees": len(result.trees),
                "observations": len(result.observations),
                "deaths": deaths,
                "warnings": result.warnings,
                "mapping_version": result.mapping_version,
            }
        except IntegrityError as exc:
            self._s.rollback()
            raise self._integrity_error(exc) from exc
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
        if "uq_observation_tree_campaign" in detalle:
            return AppError(
                "DUPLICATE_TREE",
                "El archivo trae dos mediciones del mismo arbol en la misma "
                "campana. Revise las filas duplicadas.",
            )
        # Constraint no prevista: es un fallo nuestro, no del archivo
        raise exc

    def _tree_ids(self, project_id: int) -> dict[str, int]:
        """tree_id de campo -> id de fila, para los arboles ya persistidos."""
        rows = self._s.execute(
            select(TreeRow.tree_id, TreeRow.id).where(TreeRow.project_id == project_id)
        ).all()
        return {tree_id: row_id for tree_id, row_id in rows}

    def _upsert_trees(self, project_id: int, result: CampaignData) -> dict[str, int]:
        """Inserta los arboles nuevos y corrige los descriptivos de los viejos.

        Tres casos por arbol:
          - no existe            -> INSERT;
          - existe y su IDENTIDAD coincide -> se actualizan los atributos
            descriptivos (familia, nombre comun, gremio, localidad, elevacion)
            con el archivo mas reciente;
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
            fila.locality = tree.locality
            fila.elevation_m = tree.elevation_m

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
                        "plot_id": t.plot_id,
                        "locality": t.locality,
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
        self, project_id: int, result: CampaignData, tree_db_id: dict[str, int]
    ) -> None:
        """Inserta las observaciones nuevas y actualiza las que ya existian.

        `UNIQUE(tree_row_id, campaign)` admite una fila por arbol y monitoreo,
        asi que un archivo corregido pisa el valor anterior: manda el mas
        reciente. Que archivos entraron y cuando queda en `campaign_files`.
        """
        previas = {
            (tree_row_id, campana): obs_id
            for obs_id, tree_row_id, campana in self._s.execute(
                select(
                    ObservationRow.id,
                    ObservationRow.tree_row_id,
                    ObservationRow.campaign,
                )
                .join(TreeRow, TreeRow.id == ObservationRow.tree_row_id)
                .where(TreeRow.project_id == project_id)
            ).all()
        }

        a_insertar: list[dict] = []
        a_actualizar: list[dict] = []
        for obs in result.observations:
            fila = {
                "tree_row_id": tree_db_id[obs.tree_id],
                "campaign": obs.campaign,
                "height_m": obs.height_m,
                "crown_diameter_m": obs.crown_diameter_m,
                "dap_cm": obs.dap_cm,
                "dap_status": obs.dap_status.value,
                "phytosanitary": obs.phytosanitary,
                "alive": obs.alive,
                "colonization": obs.colonization,
            }
            obs_id = previas.get((fila["tree_row_id"], obs.campaign))
            if obs_id is None:
                a_insertar.append(fila)
            else:
                a_actualizar.append({"id": obs_id, **fila})

        if a_insertar:
            self._s.execute(insert(ObservationRow), a_insertar)
        if a_actualizar:
            self._s.execute(update(ObservationRow), a_actualizar)
        self._s.flush()

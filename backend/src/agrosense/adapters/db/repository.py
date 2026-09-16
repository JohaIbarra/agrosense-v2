"""Repositorios (adapters/db): persisten entidades de dominio via models.

Transaccionalidad de save_ingest: TODO o NADA (regla ADR-004 — sin
persistencia parcial). El commit lo hace el propio repo en el borde de
la operacion completa.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agrosense.adapters.db.models import CampaignFile, ObservationRow, Project, TreeRow
from agrosense.adapters.ingester.ingest import IngestResult


class ProjectRepository:
    def __init__(self, session: Session):
        self._s = session

    def create(self, name: str, locality: str | None, description: str | None) -> Project:
        exists = self._s.execute(select(Project).where(Project.name == name)).scalar()
        if exists:
            raise ValueError("DUPLICATE_NAME")
        proj = Project(name=name, locality=locality, description=description)
        self._s.add(proj)
        self._s.commit()
        return proj

    def get(self, project_id: int) -> Project | None:
        return self._s.get(Project, project_id)

    def list_all(self) -> list[Project]:
        return list(self._s.scalars(select(Project).order_by(Project.id)).all())

    def campaigns_count(self, project_id: int) -> int:
        return self._s.execute(
            select(func.count()).where(CampaignFile.project_id == project_id)
        ).scalar_one()


class CampaignRepository:
    def __init__(self, session: Session):
        self._s = session

    def save_ingest(
        self,
        project_id: int,
        result: IngestResult,
        filename: str,
        sha256: str,
    ) -> dict:
        """Persiste el IngestResult completo en UNA transaccion.

        Lanza ValueError('DUPLICATE_FILE') si el mismo sha256 ya fue
        ingresado al proyecto (provenance).
        """
        dup = self._s.execute(
            select(func.count()).where(
                CampaignFile.project_id == project_id,
                CampaignFile.sha256 == sha256,
            )
        ).scalar_one()
        if dup:
            raise ValueError("DUPLICATE_FILE")

        try:
            tree_rows = [
                TreeRow(
                    project_id=project_id,
                    tree_id=tree.tree_id,
                    species=tree.species,
                    family=tree.family,
                    common_name=tree.common_name,
                    guild=tree.guild,
                    plot_id=tree.plot_id,
                    locality=tree.locality,
                    coord_x=tree.coord_x,
                    coord_y=tree.coord_y,
                    elevation_m=tree.elevation_m,
                )
                for tree in result.trees
            ]
            self._s.bulk_save_objects(tree_rows, return_defaults=True)
            self._s.flush()

            tree_db_id = {t.tree_id: t.id for t in tree_rows}

            obs_rows = [
                ObservationRow(
                    tree_row_id=tree_db_id[obs.tree_id],
                    campaign=obs.campaign,
                    height_m=obs.height_m,
                    crown_diameter_m=obs.crown_diameter_m,
                    dap_cm=obs.dap_cm,
                    dap_status=obs.dap_status.value,
                    phytosanitary=obs.phytosanitary,
                    alive=obs.alive,
                    colonization=obs.colonization,
                )
                for obs in result.observations
            ]
            # bulk sin defaults (no se necesitan ids de observations)
            self._s.bulk_save_objects(obs_rows)

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
        except Exception:
            self._s.rollback()
            raise

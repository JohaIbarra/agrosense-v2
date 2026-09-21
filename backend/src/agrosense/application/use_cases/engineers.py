"""Casos de uso del perfil del ingeniero (E1).

La identidad (quien es) la prueba el token de Supabase Auth, verificado en el
adapter. Aqui solo se gestiona el PERFIL: nombre, matricula profesional y
organizacion, que firman los informes tecnicos.
"""
from __future__ import annotations

from agrosense.application.dtos import EngineerDTO

PROFILE_FIELDS = ("full_name", "professional_license", "organization")


def _dto(eng) -> EngineerDTO:
    return EngineerDTO(
        id=eng.id,
        email=eng.email,
        full_name=eng.full_name,
        professional_license=eng.professional_license,
        organization=eng.organization,
    )


def ensure_engineer(repo, engineer_id: str, email: str | None) -> EngineerDTO:
    """Perfil del ingeniero autenticado; se crea en su primera peticion."""
    return _dto(repo.ensure(engineer_id, email))


def update_profile(repo, engineer_id: str, **fields) -> EngineerDTO:
    eng = repo.get(engineer_id)
    cambios = {
        k: (v.strip() or None) if isinstance(v, str) else v
        for k, v in fields.items()
        if k in PROFILE_FIELDS
    }
    return _dto(repo.update(eng, **cambios))

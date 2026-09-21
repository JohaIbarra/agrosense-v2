"""Fixtures comunes del smoke contra Supabase (E1).

Desde E1 todo proyecto tiene propietario, asi que el ingeniero de prueba debe
existir en la base real antes de que cualquier smoke cree un proyecto. Se crea
una vez por corrida y se borra al final (sus proyectos ya los limpio cada
test: la FK es RESTRICT a proposito).
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def smoke_engineer():
    if not os.environ.get("DATABASE_URL"):
        yield None
        return
    from agrosense.adapters.db.models import Engineer, Project
    from agrosense.adapters.db.session import get_session_factory
    from tests.auth.keys import ENGINEER_A

    s = get_session_factory()()
    try:
        if s.get(Engineer, ENGINEER_A) is None:
            s.add(Engineer(id=ENGINEER_A, email="smoke@agrosense.test"))
            s.commit()
        yield ENGINEER_A
    finally:
        s.rollback()
        restantes = s.query(Project).filter_by(owner_id=ENGINEER_A).count()
        if restantes == 0:
            eng = s.get(Engineer, ENGINEER_A)
            if eng is not None:
                s.delete(eng)
                s.commit()
        s.close()

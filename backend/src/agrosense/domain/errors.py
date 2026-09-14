"""Errores de dominio: codigos accionables (docs/02-domain.md seccion 5).

Cada error lleva contexto suficiente para que el ingeniero de campo pueda
corregir el dato sin ayuda tecnica: arbol, campana, valor problematico.
"""


class DomainError(Exception):
    """Error de invariante de dominio: la campana se RECHAZA completa."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


class SpeciesMismatchError(DomainError):
    def __init__(self, tree_id: str, found: str, expected: str):
        super().__init__(
            "SPECIES_MISMATCH",
            f"Arbol {tree_id} cambia de especie entre campanas: {expected!r} -> {found!r}",
        )


class DeathViolationError(DomainError):
    def __init__(self, tree_id: str, campaign: int, detail: str = ""):
        extra = f" ({detail})" if detail else ""
        super().__init__(
            "DEATH_VIOLATION",
            f"Arbol {tree_id} muerto revive o crece en campana {campaign}{extra}",
        )


class NegativeMeasurementError(DomainError):
    def __init__(self, field: str, value: float, tree_id: str, campaign: int):
        super().__init__(
            "NEGATIVE_MEASUREMENT",
            f"{field}={value} < 0 en arbol {tree_id}, campana {campaign}",
        )


class NonContiguousCensusError(DomainError):
    def __init__(self, tree_id: str, campaigns: list[int]):
        super().__init__(
            "NON_CONTIGUOUS_CENSUS",
            f"Arbol {tree_id} con censo no contiguo desde el primer censo: {sorted(campaigns)}",
        )


class SuspiciousContractionWarning(Exception):
    """No es error: contraccion >1 cm es error de medicion documentado (~13/652
    casos en el dataset de referencia). La ingesta CONTINUA; se reporta."""

    def __init__(self, tree_id: str, campaign: int, contraction_m: float):
        self.tree_id = tree_id
        self.campaign = campaign
        self.contraction_m = contraction_m
        super().__init__(
            f"Arbol {tree_id} 'encoge' {contraction_m:.3f} m hasta campana {campaign} "
            f"(error de medicion de campo documentado)"
        )

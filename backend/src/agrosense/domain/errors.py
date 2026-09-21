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


class LargeContractionNoted(Exception):
    """Nota descriptiva: la altura del arbol BAJO mas de MAX_CONTRACTION_M.

    NO es un error y NO pide corregir el dato. Una contraccion de altura es
    un hecho biologico posible: dano fisico, poda, ramoneo, quiebre del apice
    o cambio del punto de referencia de la cinta entre cuadrillas. El dato
    original se conserva tal cual se midio.

    Por que importa el matiz (auditoria del 2026-09-21): el dataset de
    referencia solo tiene contracciones en M1->M2 (13 casos, 1-20 cm) y
    CERO en M2->M3 y M3->M4. Esa monotonia perfecta no es biologia, es
    correccion en campo. Un aviso redactado como "sospechoso" empuja a la
    cuadrilla a seguir monotonizando, y el modelo de estancamiento pierde
    justo la senal que busca. De ahi el nombre neutro y el umbral de 5 cm:
    se anota lo llamativo, no se acusa a la medicion.
    """

    def __init__(self, tree_id: str, campaign: int, contraction_m: float):
        self.tree_id = tree_id
        self.campaign = campaign
        self.contraction_m = contraction_m
        super().__init__(
            f"Arbol {tree_id} decrece {contraction_m:.3f} m hasta campana {campaign}. "
            f"Una contraccion de altura no es un error de medicion: puede reflejar "
            f"dano fisico, poda, ramoneo o cambio del punto de referencia. "
            f"NO corregir el dato original; verificar en campo si se quiere confirmar "
            f"la causa."
        )


class SuspiciousRevivalWarning(Exception):
    """No es error: 'Muerto' en campana k y 'Vivo' en k+1 es REPLANTEO
    (practica estandar de restauracion: el individuo muerto se reemplaza
    y el registro de campo reusa el ID; la altura salta). 6/856 casos en
    el dataset de referencia. La ingesta CONTINUA; el arbol queda flaggeado
    para revision (y para el modelo de mortalidad es etiqueta ambigua)."""

    def __init__(self, tree_id: str, campaign: int):
        self.tree_id = tree_id
        self.campaign = campaign
        super().__init__(
            f"Arbol {tree_id} figura 'Muerto' en campana {campaign - 1} y 'Vivo' "
            f"en {campaign}: posible replanteo o error de registro; revisar"
        )


class CensusGapWarning(Exception):
    """No es error: el arbol fue censado, se salto campanas y reaparecio
    (logistica de campo: equipo no encuentra/accede al individuo).
    1/856 casos en el dataset de referencia ([M1, M4]). La ingesta CONTINUA;
    el analisis posterior debe tolerar huecos en la serie."""

    def __init__(self, tree_id: str, campaigns: list[int]):
        self.tree_id = tree_id
        self.campaigns = campaigns
        super().__init__(
            f"Arbol {tree_id} con censo no contiguo: {sorted(campaigns)} "
            f"(se salto campanas entre el primer y ultimo censo)"
        )


class TreeIdentityMismatchError(DomainError):
    """Un tree_id cambia un atributo de IDENTIDAD entre cargas.

    docs/02-domain.md §2.4: un tree_id no puede cambiar de especie, parcela
    ni coordenadas — es la coherencia de identificacion de campo. Si el
    archivo corregido dice otra cosa, o el archivo esta mal o el ID se
    reutilizo para otro individuo; en ambos casos hay que mirarlo, no
    sobrescribir.

    Para la ESPECIE existe SPECIES_MISMATCH, que ya esta en el contrato.
    """

    def __init__(self, tree_id: str, field: str, stored, incoming):
        super().__init__(
            "TREE_IDENTITY_MISMATCH",
            f"Arbol {tree_id}: {field} cambia de {stored!r} a {incoming!r} "
            f"respecto a lo ya cargado. La identidad del arbol no cambia entre "
            f"campanas; revise el archivo o el identificador.",
        )


# ── Avisos a nivel de ARCHIVO (E0) ─────────────────────────────────────────
# No son de un arbol: describen el archivo completo. Llevan `tree_id = ""`
# porque el contrato de WarningItem exige ese campo y no se quiso romperlo.


class EventMismatchWarning(Exception):
    """El archivo declara un monitoreo (`Evento`) distinto del que trae.

    No es error: `Evento` es texto libre de campo («Cuarto monitoreo») y la
    fuente de verdad son las columnas `_M{k}` con datos. Pero si no cuadran,
    el ingeniero puede haber subido el archivo equivocado, y merece saberlo.
    """

    tree_id = ""

    def __init__(self, declared: int, detected_latest: int):
        self.declared = declared
        self.detected_latest = detected_latest
        super().__init__(
            f"El archivo dice ser el monitoreo {declared} (columna Evento), pero "
            f"el monitoreo mas reciente con datos es el {detected_latest}. "
            f"Verifique que sea el archivo correcto."
        )


class ProjectLabelMismatchWarning(Exception):
    """El archivo nombra un proyecto distinto del de cargas anteriores.

    Se compara contra lo que dijeron los ARCHIVOS previos del mismo proyecto,
    no contra el nombre del proyecto en AgroSense: ese lo elige el ingeniero
    («Restauracion Guayabal») y casi nunca coincide con la etiqueta larga del
    contrato que trae el Excel. Compararlos daria un aviso en cada carga.
    """

    tree_id = ""

    def __init__(self, incoming: str, previous: str):
        self.incoming = incoming
        self.previous = previous
        super().__init__(
            f"Este archivo pertenece a «{incoming}», pero las cargas anteriores "
            f"de este proyecto eran de «{previous}». Verifique que lo subio al "
            f"proyecto correcto."
        )


class UnrecognizedColumnsWarning(Exception):
    """El archivo trae columnas que AgroSense no sabe interpretar.

    No es error: la carga sigue con las columnas conocidas. Pero es el caso
    que E0 existe para cerrar: hasta entonces nueve columnas se descartaban
    sin avisar. Si otro proyecto renombra una columna, el ingeniero tiene que
    enterarse en la respuesta, no descubrirlo cuando falte el dato.
    """

    tree_id = ""

    def __init__(self, columns: list[str]):
        self.columns = columns
        muestra = ", ".join(f"«{c}»" for c in columns[:10])
        resto = f" y {len(columns) - 10} mas" if len(columns) > 10 else ""
        super().__init__(
            f"Columnas no reconocidas, se ignoraron: {muestra}{resto}. Si contienen "
            f"datos del monitoreo, revise el nombre de la columna."
        )

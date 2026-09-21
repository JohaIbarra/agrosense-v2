"""Unico lugar del sistema que conoce los nombres REALES del archivo de
campo (typos incluidos: 'Sobrevivemcia M1', 'Diámetro. Copa (m)_M2').

Versionado para provenance (ADR-004): cambiar un alias = nueva version.

Cuatro papeles posibles para una columna (E0):

  - **fija por arbol**: identidad, datos del arbol y de su parcela;
  - **por monitoreo**: la medicion de la campana k, sufijo `_M{k}` / ` M{k}`;
  - **de archivo**: constante en todo el archivo (`Proyecto`, `Evento`…);
  - **ignorada**, SIEMPRE con motivo escrito.

Una columna que no cae en ninguna es un hueco que se reporta, no se descarta
en silencio. Asi fue como se perdieron nueve columnas hasta E0 — entre ellas
`Codigo de unidad muestreo`, la unidad por la que se agrupa la validacion
cruzada.

Los nombres se comparan NORMALIZADOS (sin tildes, sin mayusculas, espacios
colapsados): cada proyecto llega con su propio Excel y una tilde de mas no
puede hacer perder una columna. La cabecera real conserva su forma original
en los valores devueltos.
"""
import math
import re
import unicodedata

MAPPING_VERSION = "2026-09-21-e0"


def normalize_header(name: object) -> str:
    """Forma canonica de una cabecera para compararla.

    Quita tildes (NFKD + marcas combinantes), pasa a minusculas y colapsa
    cualquier espacio en blanco — incluidos los saltos de linea que traen
    algunas cabeceras del formato real.
    """
    s = unicodedata.normalize("NFKD", str(name))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return " ".join(s.split()).casefold()


# ── Columnas fijas por arbol ───────────────────────────────────────────────

_FIXED: dict[str, str] = {
    "ID_MUEST": "tree_id",
    "ID Parcela": "plot_id",
    "LOCALIDAD": "locality",
    "Especie_M1": "species",
    "Familia": "family",
    "NombCom_M1": "common_name",
    "Gremio ecológico de la especie": "guild",
    "Altura": "elevation_m",
    "Coord_X": "coord_x",
    "Coord_Y": "coord_y",
    # E0 — atributos de la parcela (constantes dentro de cada unidad de muestreo)
    "Codigo de unidad muestreo": "sampling_unit_code",
    "Unidad de monitoreo": "monitoring_unit",
    "Diseño floristico": "floristic_design",
    "Cobertura vegetal asociada": "associated_cover",
    "Cobertura donde se establecio el material vegetal": "establishment_cover",
    # E0 — nota de campo; corresponde a la visita mas reciente del archivo
    "Observa": "field_notes",
}

# ── Columnas de archivo (un valor para todo el archivo) ────────────────────

_FILE: dict[str, str] = {
    "Proyecto": "project_label",
    "Evento": "event",
    "Responsables": "field_crew",
    "Anotador": "recorder",
}

# ── Columnas ignoradas a proposito ─────────────────────────────────────────

_EPIFITAS = (
    "colonizacion por epifitas: sin modelo de dominio todavia; se decide en E3 "
    "junto con el analisis exploratorio"
)

IGNORED_COLUMNS: dict[str, str] = {
    "ID Ind.": (
        "numeracion del individuo dentro de su parcela; la identidad del arbol "
        "es ID_MUEST, que ya es unica"
    ),
    # La cabecera real viene TRUNCADA ("Colonizació", sin la n final) y con
    # un salto de linea dentro; se registran la forma real y la correcta.
    "Colonizació Epífitas vasculares": _EPIFITAS,
    "Colonizació Epífitas no vasculares": _EPIFITAS,
    "Colonización Epífitas vasculares": _EPIFITAS,
    "Colonización Epífitas no vasculares": _EPIFITAS,
}

# ── Columnas por monitoreo ─────────────────────────────────────────────────
# Patrones sobre la cabecera NORMALIZADA. El numero de monitoreo NO tiene
# techo: un proyecto puede tener M5, M6… (hasta E0 solo se reconocian M1-M4).

_PER_CAMPAIGN: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^altura total \(m\)_m(\d+)$"), "height_m"),
    (re.compile(r"^diametro\. copa \(m\)_m(\d+)$"), "crown_diameter_m"),
    (re.compile(r"^estado fitosanitario_m(\d+)$"), "phytosanitary"),
    (re.compile(r"^sobrevivencia m(\d+)$"), "alive"),
    (re.compile(r"^sobrevivemcia m(\d+)$"), "alive"),  # typo del formato real
    (re.compile(r"^dap \(cm\) m(\d+)$"), "dap_cm"),
    (re.compile(r"^dap m(\d+)$"), "dap_cm"),
]

# Cabeceras de monitoreo sin sufijo: en el formato real, `DAP (CM)` es el M1
_LEGACY_PER_CAMPAIGN: dict[str, tuple[str, int]] = {
    "DAP (CM)": ("dap_cm", 1),
}

_FIXED_N = {normalize_header(k): v for k, v in _FIXED.items()}
_FILE_N = {normalize_header(k): v for k, v in _FILE.items()}
_IGNORED_N = {normalize_header(k) for k in IGNORED_COLUMNS}
_LEGACY_N = {normalize_header(k): v for k, v in _LEGACY_PER_CAMPAIGN.items()}


def _campaign_role(header: object) -> tuple[str, int] | None:
    """(canonico, numero de monitoreo) si la cabecera es de un monitoreo."""
    norm = normalize_header(header)
    if norm in _LEGACY_N:
        return _LEGACY_N[norm]
    for pattern, canonical in _PER_CAMPAIGN:
        match = pattern.match(norm)
        if match:
            return canonical, int(match.group(1))
    return None


# ── Seams publicos ─────────────────────────────────────────────────────────

def fixed_columns(df_columns: list) -> dict[str, str]:
    """{canonico: nombre_real} para columnas fijas por arbol."""
    result: dict[str, str] = {}
    for real in df_columns:
        canonical = _FIXED_N.get(normalize_header(real))
        if canonical and canonical not in result:
            result[canonical] = real
    return result


def file_columns(df_columns: list) -> dict[str, str]:
    """{canonico: nombre_real} para columnas que describen el archivo."""
    result: dict[str, str] = {}
    for real in df_columns:
        canonical = _FILE_N.get(normalize_header(real))
        if canonical and canonical not in result:
            result[canonical] = real
    return result


def campaign_columns(df_columns: list) -> dict[str, dict[int, str]]:
    """{canonico: {numero_de_monitoreo: nombre_real}} para columnas por monitoreo."""
    result: dict[str, dict[int, str]] = {}
    for real in df_columns:
        role = _campaign_role(real)
        if role is None:
            continue
        canonical, campaign = role
        result.setdefault(canonical, {}).setdefault(campaign, real)
    return result


def map_columns(df_columns: list) -> dict[str, str]:
    """{nombre_real: canonico} para toda columna reconocida (fija o por monitoreo)."""
    mapping: dict[str, str] = {}
    for real in df_columns:
        norm = normalize_header(real)
        if norm in _FIXED_N:
            mapping[real] = _FIXED_N[norm]
        elif norm in _FILE_N:
            mapping[real] = _FILE_N[norm]
        else:
            role = _campaign_role(real)
            if role is not None:
                mapping[real] = role[0]
    return mapping


def unclassified_columns(df_columns: list) -> list:
    """Columnas que no son fijas, ni de monitoreo, ni de archivo, ni ignoradas.

    Las columnas sin cabecera (None o en blanco) no cuentan: son el relleno
    que deja Excel a la derecha de la tabla.
    """
    out = []
    for real in df_columns:
        if real is None or not str(real).strip():
            continue
        norm = normalize_header(real)
        if norm in _FIXED_N or norm in _FILE_N or norm in _IGNORED_N:
            continue
        if _campaign_role(real) is not None:
            continue
        out.append(real)
    return out


# ── Evento: «Cuarto monitoreo» -> 4 ─────────────────────────────────────────

_ORDINALS = {
    "primer": 1, "primero": 1, "segundo": 2, "tercer": 3, "tercero": 3,
    "cuarto": 4, "quinto": 5, "sexto": 6, "septimo": 7, "octavo": 8,
    "noveno": 9, "decimo": 10,
}


def parse_event_number(raw: object) -> int | None:
    """Numero de monitoreo que declara la columna `Evento`, si se entiende.

    Acepta ordinales en palabra («Cuarto monitoreo»), un numero suelto
    («Monitoreo 5») o la forma corta («M3»). Devuelve None si no hay nada
    reconocible: `Evento` es texto libre y solo sirve de verificacion cruzada,
    nunca de fuente.
    """
    if is_blank(raw):
        return None
    norm = normalize_header(raw)
    for word in re.findall(r"[a-z]+", norm):
        if word in _ORDINALS:
            return _ORDINALS[word]
    match = re.search(r"(?:^|[^a-z])m?(\d+)", norm)
    return int(match.group(1)) if match else None


# ── Valores ────────────────────────────────────────────────────────────────

def parse_alive(raw) -> bool | None:
    """'Vivo'->True, 'Muerto'->False, blanco->None. Nunca lanza."""
    if is_blank(raw):
        return None
    s = str(raw).strip()
    if s == "Vivo":
        return True
    if s == "Muerto":
        return False
    return None


def is_blank(v) -> bool:
    """Blanco de campo: None, NaN o string vacio/' '. 0.0 NO es blanco."""
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    return isinstance(v, str) and v.strip() == ""

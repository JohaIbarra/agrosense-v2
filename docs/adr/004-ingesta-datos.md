# ADR-004 — Ingesta de datos: ingester del formato ancho de campo → long canónico

- **Estado:** Aceptado
- **Fecha:** 2026-09-14

## Contexto

Los ingenieros recolectan en campo y arman el archivo como el Anexo 1:
**formato ancho** (una fila por árbol, columnas `X_M1..X_M4` duplicadas por
monitoreo, headers con espacios/acentos: `Diámetro. Copa (m)_M2`,
`Sobrevivemcia M1` con typo). Los blancos tienen semántica (ADR discovered
en domain §1: `sin_censo` vs `bajo_umbral_dap` vs `medido`).

v1 cometía el error inverso: exigía al usuario un dataset ya "limpio" y
feature-engineered (21 columnas con dummies), duplicando trabajo y
acoplando el contrato de upload al modelo.

## Decisión

1. **El contrato de upload acepta el formato ancho de campo** (lo que el
   ingeniero produce), con un mapping de columnas versionado y tolerante
   a variantes de nombre (documento la correspondencia `DAP (CM) M3` ↔
   `DAP_M3`). NO se exige formato long ni dummies al usuario.
2. **Un solo ingester** (`adapters/ingester/`) transforma ancho → long
   canónico: una fila por (árbol, monitoreo), aplicando StatusSemantic
   (blancos → sin_censo / bajo_umbral_dap / medido).
3. El ingester **valida invariantes de dominio** antes de persistir; si
   falla, rechaza la campaña completa con errores accionables (códigos de
   docs/02-domain.md §5) — sin persistencia parcial.
4. Los dummies/one-hot NO se persisten: se derivan en `ml/features.py` donde
   pertenecen (regla anti-target-leakage de v1).
5. Cada archivo crudo se guarda versionado + hash (provenance: regla del
   AGENTS.md).

## Alternativas descartadas

- Exigir CSV long al usuario: empuja trabajo de datos al no-analista.
  (v1 lo hacía y era frágil.)
- Persistir features calculadas en DB: congela el feature engineering;
  la reproducibilidad exige derivar features desde observations canónicas
  con version de código.

## Consecuencias

- El ingester es la pieza más testeada del sistema (contract de entrada
  real, con todos sus typos y blancos).
- Agregar M5/M6 al futuro = añadir columnas al mapping, no rediseño.
- Los análisis siempre parten de Observations canónicas — una sola verdad.

# Spike de generalización — pasos 1 y 2 (2026-09-30)

## 1. Gremio vs especie (`exp_c.py`)

Split E7: entrena ola 2 (M2→M3, 618 árboles, 153 pos), evalúa ola 3 (M3→M4, 717, 157 pos,
prevalencia 0.219). IC 90 % = bootstrap de parcelas del test, diferencia pareada vs A.

| Variante | PR-AUC | × azar | Δ vs A [IC90] |
|---|---|---|---|
| A. actual (todo, con especie) | 0.478 | 2.18 | — |
| B. todo, especie→gremio | 0.425 | 1.94 | −0.051 [−0.086, −0.022] |
| C. todo sin especie ni gremio | 0.411 | 1.88 | −0.063 [−0.098, −0.033] |
| D. especie + tamaño | 0.493 | 2.25 | +0.019 [−0.036, +0.088] |
| E. gremio + tamaño | 0.464 | 2.12 | −0.010 [−0.079, +0.062] |
| F. solo tamaño | 0.467 | 2.13 | −0.008 [−0.079, +0.068] |
| G. gremio + tamaño + historia | 0.446 | 2.04 | −0.030 [−0.063, +0.000] |
| H. regla tasa por especie | 0.382 | 1.75 | −0.092 |
| I. regla tasa por gremio | 0.271 | 1.24 | −0.203 |

Conclusión: el gremio NO aporta sobre el tamaño (E ≈ F). Un modelo de solo tamaño
(altura, copa, esbeltez) iguala al modelo actual dentro del IC y es el candidato más
transferible. Las variables de sitio/historia empeoran fuera de muestra (A < D).

## 2. Datasets externos (verificados contra los archivos reales o la API del repositorio)

| Dataset | Veredicto | Columnas reales / motivo |
|---|---|---|
| Werden 2018, CR bosque seco, enmiendas de suelo — Dryad fd57r / Zenodo 4956588 | **SIRVE** | CC0. 1 445 plántulas plantadas, 32 spp, 13 censos 2014-15. `seedlingID, block, treatment, spCode, surveyNumber, datePlanted, dateMeasured, growthDays, height_cm, diamBot_mm, diamTop_mm, survival`. Coordenada solo del sitio. |
| Werden 2020, CR bosque seco, 6 ha — Dryad jm63xsj6p / Zenodo 4968196 | **SIRVE** | CC0. 3 379 plántulas, 12 spp, 4 censos 2015-17. `seedlingID, plot, subPlot, treatment, strategy, surveyNumber, datePlanted, dateMeasured, sppCode, height, diamBot, diamTop, survival`. Incluye microclima. Mortalidad alta (~80 %). |
| Holl et al., CR sur, regeneración natural — Zenodo 5013556 | **PARCIAL** | CC0. 1 103 reclutas NO plantados, 50 spp, 24 parcelas, 18 censos de presencia + crecimiento anual 2007-13 (`SIZE` en clases). Útil para supervivencia, no para altura. |
| Charles et al., Australia — Zenodo 4963776 | **PARCIAL** | CC0. 25 spp, 48 parcelas, 6 censos 2011-13, con pendiente/aspecto/densidad de madera. Solo supervivencia, sin altura. Fuera del neotrópico. |
| Schubert et al. 2025, CR — Dryad s7h44j1gc | NO | Censo ÚNICO 2022 (`Altura` en clases). Sin remedición. |
| La Selva 1997-2017 — Dryad ncjsxksvr | NO | Bosque secundario, DAP ≥ 5 cm, sin altura, no es siembra. |
| Sardinilla, Panamá — Dryad 6hdr7srbf | NO (público) | Solo stocks de carbono agregados (20 KB). El inventario anual por árbol no está publicado → pedir a autores. |
| PRORENA, Panamá | NO (público) | Solo artículos; no hay datos por árbol en repositorio. |
| Reviva la Primavera, Casanare — GBIF/SiB | NO | Ocurrencias (CC BY-NC), sin remedición por individuo. |
| Fundación Natura, bosque seco Colombia (67 566 árboles) | NO (público) | Solo nota de prensa; no encontré el dataset. Candidato a convenio. |
| "BD de 1 303 parcelas en Nature" (ChatGPT) | NO EXISTE | No encontrado. |

Descarga directa de Dryad bloqueada por anti-bot; se usaron los espejos de Zenodo.

## Fuentes ambientales para Colombia

| Fuente | Resolución real | Verificado |
|---|---|---|
| CHIRPS v3 (lluvia) | 0.05° (~5.5 km), diaria/pentadal, 1981-hoy, 60°N-60°S | sí (UCSB/UCAR) |
| IDEAM DHIME (estaciones) | puntual, 10 min/diaria; gratis sin registro | sí |
| ERA5-Land (temp., humedad suelo) | 0.1° (~9 km), horaria | no re-verificado |
| WorldClim 2.1 | ~1 km, climatología 1970-2000 (no sirve por intervalo) | no re-verificado |
| TerraClimate | ~4 km, mensual | no re-verificado |
| Copernicus DEM GLO-30 (altitud, pendiente) | 30 m | no re-verificado |
| SoilGrids 2.0 | 250 m | no re-verificado |
| TRY (rasgos) | por especie; CC BY 4.0, por solicitud (1-2 días públicos) | sí |
| Global Wood Density DB v2 | por especie, 109 626 registros, CC BY 4.0 (Zenodo 16919510) | sí |

## 3. Modelo propio vs general por nº de monitoreos (`exp_d.py`, Werden 2018)

Monitoreos con altura: censos 1, 4, 8, 10, 11, 12, 13. En el monitoreo k se predice k→k+1;
el modelo propio se entrena con todos los intervalos ya cerrados; el general solo con Anexo 1
(percentil de altura, sin reentrenar). Valores: PR-AUC (× azar). Sin IC: los últimos
intervalos tienen 14-51 positivos.

| Predice | meses | Muerte: general | propio tamaño | propio +esp+trat | Estanc.: general | propio tamaño |
|---|---|---|---|---|---|---|
| 4→8 (2 monit.) | 1.0 | 1.5× | 1.9× | 3.5× | 1.0× | 1.1× |
| 8→10 (3) | 0.9 | 1.5× | 1.8× | 3.0× | 0.9× | 1.1× |
| 10→11 (4) | 7.0 | 1.2× | 1.2× | 1.2× | 0.7× | 1.7× |
| 11→12 (5) | 4.6 | 1.7× | 2.0× | 2.0× | 0.9× | 2.8× |
| 12→13 (6) | 7.2 | 2.5× | 2.8× | 3.0× | 1.1× | 1.8× |

(10→11 = estación seca, 71 % muere: el techo de lift es 1.4×.)
Historia (dh_lag) no mejora y empeora el estancamiento con pocos positivos.

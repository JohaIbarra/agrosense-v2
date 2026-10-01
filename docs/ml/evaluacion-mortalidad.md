# Evaluación del modelo general de mortalidad (E8)

> Generado por `python scripts/train_mortality_general.py`. No editar a mano.

- **Modelo:** `mortality-general-2026-09-30.1` · variables: h_pct · coeficiente -1.13019 · intercepto -0.402254
- **Gate (pre-registrado, ADR-014):** PASA — {'lopo_Anexo 1': True, 'lopo_Werden 2018': True, 'lopo_Werden 2020': True}
- **Azar empírico:** etiquetas del proyecto fuera permutadas 20 veces; umbral lift/azar ≥ 1.2

## Validación dejando un proyecto fuera

| Proyecto fuera | Coeficiente | Mediana lift | Azar empírico | Lift / azar | Intervalos (lift · prevalencia · muertes) |
|---|---|---|---|---|---|
| Anexo 1 | -1.1641 | 1.683× | 1.042× | 1.615 | t0: 1.173× · 0.0455 · 31; t1: 1.683× · 0.0507 · 33; t2: 2.879× · 0.0491 · 37 |
| Werden 2018 | -1.1781 | 1.496× | 1.02× | 1.467 | t0: 1.325× · 0.1603 · 229; t1: 1.537× · 0.0981 · 116; t2: 1.456× · 0.1433 · 156; t3: 1.175× · 0.7054 · 668; t4: 1.698× · 0.1214 · 34; t5: 2.459× · 0.2048 · 51 |
| Werden 2020 | -1.0396 | 1.295× | 1.006× | 1.287 | t0: 1.438× · 0.1577 · 525; t1: 1.166× · 0.6035 · 1668; t2: 1.295× · 0.4665 · 480 |

## Procedencia

- {'name': 'Anexo 1', 'sha256': '28583c3b48874626f3d7d7ae35d485634a8c8089b4c03a5997f5ba756b57a0dd', 'mapping_version': '2026-09-21-e0'}
- {'name': 'Werden 2018', 'doi': '10.5061/dryad.fd57r', 'license': 'CC0-1.0', 'sha256': '0818530bde31b05dd73e4b74e6af881c64250ab2fceb1f8a0fccc68283a3bfc2', 'url': 'https://zenodo.org/records/4956588/files/survival_growth_surveys_Werden_et_al.csv?download=1'}
- {'name': 'Werden 2020', 'doi': '10.5061/dryad.jm63xsj6p', 'license': 'CC0-1.0', 'sha256': '7f5d59d44ef52b95ca0d77a7abd13a8919e761e0d8b2326881c86c2f0daf9df5', 'url': 'https://zenodo.org/records/4968196/files/seedlingSurveys_WerdenEtAl2020_EcolApps.csv?download=1'}
- git_commit: e804f4b15a6d99056e910c7ca3b36520f2a50981
- python: 3.12.1
- sklearn: 1.5.2
- numpy: 1.26.4

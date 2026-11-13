# Huella de carbono del experimento con Rope (Black)

- CodeCarbon: `3.3.2` (`OfflineEmissionsTracker`)
- País (factor de emisión de la red): Colombia (`COL`), 259.511 gCO2eq/kWh
- CPU: Apple M4, 10 hilos, RAM 16.0 GB, macOS-15.6.1-arm64-arm-64bit
- Método de CPU: cpu_load (TDP x carga de CPU; sin sensores de energía)
- Repeticiones de cada operación de Rope: 5
- Fecha: 2026-11-13 14:05

- Intervalo de muestreo: 0.25 s (1 s para el experimento completo)

Unidades: energía en **Wh** (1 Wh = 0,001 kWh); emisiones en **mg de CO2 equivalente** (1 g = 1000 mg). "Máquina" = toda la computadora; "Proceso" = solo el proceso del experimento y sus hijos.

Lo que pasa **durante** cada fase está en `serie_temporal_maquina.csv` y `serie_temporal_proceso.csv` (una fila por muestra) y en `eventos.csv` (momentos marcados dentro de cada operación de Rope).

## Fases de referencia

| Fase | Duración (s) | Energía máquina (Wh) | Emisiones máquina (mg) | Energía proceso (Wh) | Emisiones proceso (mg) |
|---|---|---|---|---|---|
| Reposo (30 s sin hacer nada) | 30.0 | 0.0991 | 25.72 | 0.0298 | 7.72 |
| Línea base: pytest original | 26.7 | 0.0880 | 22.85 | 0.0813 | 21.11 |
| Análisis estático con Rope | 4.6 | 0.0176 | 4.56 | 0.0139 | 3.61 |
| **Experimento completo** | 461.9 | 1.6431 | 426.39 | 1.4454 | 375.09 |

## Operación de Rope (media de 5 repeticiones)

| # | Tipo | Veredicto | Tiempo Rope (s) | Energía máquina (Wh) | Emisiones máquina (mg) | Energía proceso (Wh) | Emisiones proceso (mg) | Energía pytest máquina (Wh) | Emisiones pytest máquina (mg) |
|---|---|---|---|---|---|---|---|---|---|
| 02_rename_funcion | Rename | COMPORTAMIENTO PRESERVADO | 1.757 | 0.00699 ± 0.00296 | 1.814 | 0.00526 ± 0.00210 | 1.366 | 0.0907 | 23.53 |
| 03_rename_funcion_importada | Rename | COMPORTAMIENTO PRESERVADO | 1.755 | 0.00730 ± 0.00450 | 1.895 | 0.00672 ± 0.00544 | 1.743 | 0.0808 | 20.97 |
| 04_rename_metodo | Rename | ROMPE TESTS | 1.323 | 0.00517 ± 0.00486 | 1.341 | 0.00405 ± 0.00341 | 1.051 | 0.0891 | 23.13 |
| 05_rename_clase | Rename | COMPORTAMIENTO PRESERVADO | 1.432 | 0.00559 ± 0.00620 | 1.450 | 0.00440 ± 0.00461 | 1.142 | 0.0856 | 22.21 |
| 06_rename_parametro | Rename | RECHAZADA POR ROPE | 0.054 | 0.00000 ± 0.00000 | 0.000 | 0.00003 ± 0.00000 | 0.009 | — | — |
| 06b_rename_parametro_posicional | Rename | ROMPE TESTS | 1.105 | 0.00474 ± 0.00551 | 1.229 | 0.00330 ± 0.00427 | 0.856 | 0.0913 | 23.70 |
| 07_extract_cache | Extract Method | ROMPE TESTS | 0.112 | 0.00029 ± 0.00003 | 0.076 | 0.00027 ± 0.00003 | 0.071 | 0.0898 | 23.30 |
| 08_extract_stdin | Extract Method | ROMPE TESTS | 0.109 | 0.00029 ± 0.00003 | 0.075 | 0.00027 ± 0.00003 | 0.070 | 0.0909 | 23.59 |
| 09_extract_con_continue | Extract Method | RECHAZADA POR ROPE | 0.045 | 0.00004 ± 0.00008 | 0.009 | 0.00003 ± 0.00000 | 0.008 | — | — |
| 10_extract_bucle | Extract Method | RECHAZADA POR ROPE | 0.144 | 0.00037 ± 0.00006 | 0.096 | 0.00032 ± 0.00005 | 0.082 | — | — |
| 10b_extract_bucle_sin_fstring | Extract Method | ROMPE TESTS | 0.103 | 0.00030 ± 0.00006 | 0.077 | 0.00011 ± 0.00008 | 0.028 | 0.1027 | 26.65 |
| 11_inline_funcion | Inline | COMPORTAMIENTO PRESERVADO | 1.458 | 0.00543 ± 0.00533 | 1.410 | 0.00448 ± 0.00427 | 1.162 | 0.0759 | 19.70 |
| 12_move_funcion | Move | ROMPE TESTS | 1.234 | 0.00424 ± 0.00417 | 1.099 | 0.00382 ± 0.00342 | 0.991 | 0.0764 | 19.82 |
| 13_rename_parcheada | Rename | ROMPE TESTS | 1.410 | 0.00505 ± 0.00500 | 1.310 | 0.00479 ± 0.00479 | 1.243 | 0.0289 | 7.49 |
| 14_rename_parcheada_docs | Rename | COMPORTAMIENTO PRESERVADO | 1.070 | 0.00378 ± 0.00506 | 0.980 | 0.00332 ± 0.00443 | 0.861 | 0.0759 | 19.69 |
| 15_rename_visitante | Rename | ROMPE TESTS | 0.991 | 0.00335 ± 0.00563 | 0.871 | 0.00306 ± 0.00510 | 0.794 | 0.0741 | 19.24 |
| 16_rename_preview | Rename | ROMPE TESTS | 1.232 | 0.00414 ± 0.00660 | 1.075 | 0.00384 ± 0.00606 | 0.997 | 0.0759 | 19.70 |

## Totales

| Concepto | Energía máquina (Wh) | Emisiones máquina (mg) | Energía proceso (Wh) | Emisiones proceso (mg) |
|---|---|---|---|---|
| Una aplicación de cada una de las 17 refactorizaciones con Rope (15.33 s en total) | 0.0571 | 14.81 | 0.0481 | 12.47 |
| Verificación con pytest de las refactorizaciones aplicadas | 1.1279 | 292.69 | 1.0457 | 271.36 |

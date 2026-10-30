# Huella de carbono del experimento con Rope (Black)

- CodeCarbon: `3.3.2` (`OfflineEmissionsTracker`)
- País (factor de emisión de la red): Colombia (`COL`), 259.511 gCO2eq/kWh
- CPU: Apple M4, 10 hilos, RAM 16.0 GB, macOS-15.6.1-arm64-arm-64bit
- Método de CPU: cpu_load (TDP x carga de CPU; sin sensores de energía)
- Repeticiones de cada operación de Rope: 5
- Fecha: 2026-10-30 10:30

Unidades: energía en **Wh** (1 Wh = 0,001 kWh); emisiones en **mg de CO2 equivalente** (1 g = 1000 mg). "Máquina" = toda la computadora; "Proceso" = solo el proceso del experimento y sus hijos.

## Fases de referencia

| Fase | Duración (s) | Energía máquina (Wh) | Emisiones máquina (mg) | Energía proceso (Wh) | Emisiones proceso (mg) |
|---|---|---|---|---|---|
| Reposo (30 s sin hacer nada) | 30.0 | 0.0962 | 24.97 | 0.0266 | 6.89 |
| Línea base: pytest original | 24.2 | 0.0922 | 23.93 | 0.0721 | 18.71 |
| Análisis estático con Rope | 2.6 | 0.0109 | 2.84 | 0.0080 | 2.08 |
| **Experimento completo** | 438.0 | 1.9154 | 497.07 | 1.3110 | 340.21 |

## Operación de Rope (media de 5 repeticiones)

| # | Tipo | Veredicto | Tiempo Rope (s) | Energía máquina (Wh) | Emisiones máquina (mg) | Energía proceso (Wh) | Emisiones proceso (mg) | Energía pytest máquina (Wh) | Emisiones pytest máquina (mg) |
|---|---|---|---|---|---|---|---|---|---|
| 02_rename_funcion | Rename | COMPORTAMIENTO PRESERVADO | 1.172 | 0.00533 ± 0.00077 | 1.382 | 0.00360 ± 0.00053 | 0.934 | 0.0899 | 23.34 |
| 03_rename_funcion_importada | Rename | COMPORTAMIENTO PRESERVADO | 1.279 | 0.00592 ± 0.00431 | 1.537 | 0.00394 ± 0.00267 | 1.023 | 0.0804 | 20.88 |
| 04_rename_metodo | Rename | ROMPE TESTS | 0.709 | 0.00303 ± 0.00378 | 0.787 | 0.00217 ± 0.00257 | 0.564 | 0.1214 | 31.49 |
| 05_rename_clase | Rename | COMPORTAMIENTO PRESERVADO | 1.041 | 0.00430 ± 0.00490 | 1.117 | 0.00318 ± 0.00339 | 0.824 | 0.1147 | 29.77 |
| 06_rename_parametro | Rename | RECHAZADA POR ROPE | 0.049 | 0.00000 ± 0.00000 | 0.000 | 0.00002 ± 0.00000 | 0.005 | — | — |
| 06b_rename_parametro_posicional | Rename | ROMPE TESTS | 1.080 | 0.01338 ± 0.02534 | 3.473 | 0.00322 ± 0.00508 | 0.835 | 0.1387 | 36.01 |
| 07_extract_cache | Extract Method | ROMPE TESTS | 0.098 | 0.00031 ± 0.00011 | 0.079 | 0.00026 ± 0.00003 | 0.067 | 0.0920 | 23.87 |
| 08_extract_stdin | Extract Method | ROMPE TESTS | 0.623 | 0.00281 ± 0.00573 | 0.728 | 0.00186 ± 0.00364 | 0.483 | 0.0911 | 23.65 |
| 09_extract_con_continue | Extract Method | RECHAZADA POR ROPE | 0.031 | 0.00000 ± 0.00000 | 0.000 | 0.00002 ± 0.00000 | 0.004 | — | — |
| 10_extract_bucle | Extract Method | RECHAZADA POR ROPE | 0.061 | 0.00018 ± 0.00014 | 0.047 | 0.00002 ± 0.00000 | 0.005 | — | — |
| 10b_extract_bucle_sin_fstring | Extract Method | ROMPE TESTS | 0.042 | 0.00000 ± 0.00000 | 0.000 | 0.00002 ± 0.00000 | 0.005 | 0.1007 | 26.14 |
| 11_inline_funcion | Inline | COMPORTAMIENTO PRESERVADO | 0.705 | 0.00336 ± 0.00568 | 0.872 | 0.00216 ± 0.00330 | 0.559 | 0.0928 | 24.10 |
| 12_move_funcion | Move | ROMPE TESTS | 1.334 | 0.00716 ± 0.00559 | 1.859 | 0.00408 ± 0.00370 | 1.058 | 0.0954 | 24.76 |
| 13_rename_parcheada | Rename | ROMPE TESTS | 1.584 | 0.00804 ± 0.00947 | 2.087 | 0.00490 ± 0.00485 | 1.271 | 0.0341 | 8.84 |
| 14_rename_parcheada_docs | Rename | COMPORTAMIENTO PRESERVADO | 1.976 | 0.00946 ± 0.01234 | 2.456 | 0.00606 ± 0.00670 | 1.574 | 0.0973 | 25.26 |
| 15_rename_visitante | Rename | ROMPE TESTS | 1.214 | 0.00502 ± 0.00862 | 1.301 | 0.00364 ± 0.00615 | 0.946 | 0.0852 | 22.10 |
| 16_rename_preview | Rename | ROMPE TESTS | 0.438 | 0.00226 ± 0.00060 | 0.586 | 0.00128 ± 0.00008 | 0.333 | 0.0931 | 24.15 |

## Totales

| Concepto | Energía máquina (Wh) | Emisiones máquina (mg) | Energía proceso (Wh) | Emisiones proceso (mg) |
|---|---|---|---|---|
| Una aplicación de cada una de las 17 refactorizaciones con Rope (13.44 s en total) | 0.0706 | 18.31 | 0.0404 | 10.49 |
| Verificación con pytest de las refactorizaciones aplicadas | 1.3269 | 344.35 | 0.9551 | 247.87 |

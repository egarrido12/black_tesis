# Huella de carbono del experimento con LLM (Black)

- CodeCarbon: `3.3.2` (`OfflineEmissionsTracker`)
- País (factor de emisión de la red): Colombia (`COL`), 259.511 gCO2eq/kWh
- CPU: Apple M4, 10 hilos, RAM 16.0 GB, macOS-15.6.1-arm64-arm-64bit
- Método de CPU: cpu_load (TDP x carga de CPU; sin sensores de energía)
- Intervalo de muestreo: 0.25 s

**Solo se mide esta computadora.** La energía de los servidores de Anthropic que generan la respuesta no está incluida; para estimarla están los tokens de cada llamada en `resumen.json`.

Lo que pasa **durante** cada llamada está en `serie_temporal_maquina.csv`, `serie_temporal_proceso.csv` y `eventos.csv` (`peticion_enviada`, `primer_evento`, `inicio_pensamiento`, `inicio_text`, `fin_respuesta`).

## Fases de referencia

| Fase | Duración (s) | Energía máquina (mWh) | Emisiones máquina (mg) | Energía proceso (mWh) | Emisiones proceso (mg) |
|---|---|---|---|---|---|
| Reposo (30 s sin hacer nada) | 30.0 | 96.1 | 24.95 | 30.2 | 7.84 |
| Línea base: pytest original | 27.1 | 93.1 | 24.17 | 81.9 | 21.25 |

## Por corrida (modo proceso)

| Corrida | Veredicto | Tiempo LLM (s) | Energía local durante la llamada (mWh) | Emisiones (mg) | Potencia media (W) | Energía pytest (mWh) | Emisiones pytest (mg) |
|---|---|---|---|---|---|---|---|
| __init___run1 | ROMPE TESTS (solo formato) | 246.8 | 246.7 | 64.0 | 3.60 | 73.1 | 19.0 |
| __init___run2 | ROMPE TESTS (solo formato) | 244.7 | 245.5 | 63.7 | 3.61 | 73.4 | 19.1 |
| __init___run3 | ROMPE TESTS (solo formato) | 235.2 | 234.2 | 60.8 | 3.58 | 73.7 | 19.1 |
| parsing_run1 | COMPORTAMIENTO PRESERVADO | 46.1 | 45.7 | 11.9 | 3.57 | 75.7 | 19.7 |
| parsing_run2 | COMPORTAMIENTO PRESERVADO | 44.0 | 43.9 | 11.4 | 3.59 | 76.7 | 19.9 |
| parsing_run3 | COMPORTAMIENTO PRESERVADO | 51.7 | 50.8 | 13.2 | 3.54 | 75.6 | 19.6 |
| ranges_run1 | COMPORTAMIENTO PRESERVADO | 108.1 | 106.6 | 27.7 | 3.55 | 74.8 | 19.4 |
| ranges_run2 | COMPORTAMIENTO PRESERVADO | 128.5 | 127.1 | 33.0 | 3.56 | 77.3 | 20.1 |
| ranges_run3 | COMPORTAMIENTO PRESERVADO | 111.4 | 111.7 | 29.0 | 3.61 | 72.1 | 18.7 |
| cache_run1 | COMPORTAMIENTO PRESERVADO | 28.9 | 29.6 | 7.7 | 3.67 | 70.6 | 18.3 |
| cache_run2 | COMPORTAMIENTO PRESERVADO | 27.2 | 26.9 | 7.0 | 3.55 | 70.6 | 18.3 |
| cache_run3 | COMPORTAMIENTO PRESERVADO | 29.5 | 29.8 | 7.7 | 3.63 | 71.3 | 18.5 |
| trans_run1 | COMPORTAMIENTO PRESERVADO | 277.8 | 281.7 | 73.1 | 3.65 | 71.2 | 18.5 |
| trans_run2 | COMPORTAMIENTO PRESERVADO | 300.8 | 303.2 | 78.7 | 3.63 | 70.6 | 18.3 |
| trans_run3 | COMPORTAMIENTO PRESERVADO | 310.6 | 312.7 | 81.2 | 3.62 | 70.8 | 18.4 |
| output_run1 | COMPORTAMIENTO PRESERVADO | 27.7 | 28.3 | 7.4 | 3.68 | 70.9 | 18.4 |
| output_run2 | COMPORTAMIENTO PRESERVADO | 27.0 | 27.8 | 7.2 | 3.71 | 71.7 | 18.6 |
| output_run3 | COMPORTAMIENTO PRESERVADO | 24.7 | 25.0 | 6.5 | 3.64 | 71.0 | 18.4 |
| files_run1 | COMPORTAMIENTO PRESERVADO | 55.6 | 57.1 | 14.8 | 3.69 | 70.7 | 18.4 |
| files_run2 | COMPORTAMIENTO PRESERVADO | 55.8 | 57.3 | 14.9 | 3.70 | 71.0 | 18.4 |
| files_run3 | COMPORTAMIENTO PRESERVADO | 54.0 | 55.5 | 14.4 | 3.70 | 71.1 | 18.4 |
| linegen_run1 | COMPORTAMIENTO PRESERVADO | 304.1 | 312.4 | 81.1 | 3.70 | 70.8 | 18.4 |
| linegen_run2 | COMPORTAMIENTO PRESERVADO | 348.0 | 356.5 | 92.5 | 3.69 | 77.0 | 20.0 |
| linegen_run3 | COMPORTAMIENTO PRESERVADO | 283.5 | 291.4 | 75.6 | 3.70 | 109.0 | 28.3 |
| mode_run1 | COMPORTAMIENTO PRESERVADO | 44.7 | 44.8 | 11.6 | 3.60 | 91.3 | 23.7 |
| mode_run2 | COMPORTAMIENTO PRESERVADO | 47.3 | 47.2 | 12.2 | 3.58 | 77.3 | 20.0 |
| mode_run3 | COMPORTAMIENTO PRESERVADO | 48.8 | 49.1 | 12.7 | 3.62 | 80.0 | 20.7 |

## Totales

| Concepto | Tiempo (s) | Energía proceso (mWh) | Emisiones proceso (mg) | Energía máquina (mWh) | Emisiones máquina (mg) |
|---|---|---|---|---|---|
| Esperar las 27 respuestas de Claude (solo lo local) | 3513 | 3548.7 | 920.94 | 11277.8 | 2926.71 |
| Verificar con pytest | — | 2247.8 | 583.33 | — | — |

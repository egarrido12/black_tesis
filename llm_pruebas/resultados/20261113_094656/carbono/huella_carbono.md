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
| Reposo (30 s sin hacer nada) | 30.0 | 96.0 | 24.92 | 28.9 | 7.50 |
| Línea base: pytest original | 26.5 | 96.6 | 25.07 | 80.9 | 20.99 |

## Por corrida (modo proceso)

| Corrida | Veredicto | Tiempo LLM (s) | Energía local durante la llamada (mWh) | Emisiones (mg) | Potencia media (W) | Energía pytest (mWh) | Emisiones pytest (mg) |
|---|---|---|---|---|---|---|---|
| cache_run1 | COMPORTAMIENTO PRESERVADO | 38.5 | 37.3 | 9.7 | 3.48 | 89.0 | 23.1 |

## Totales

| Concepto | Tiempo (s) | Energía proceso (mWh) | Emisiones proceso (mg) | Energía máquina (mWh) | Emisiones máquina (mg) |
|---|---|---|---|---|---|
| Esperar las 1 respuestas de Claude (solo lo local) | 39 | 37.3 | 9.68 | 125.3 | 32.51 |
| Verificar con pytest | — | 89.0 | 23.09 | — | — |

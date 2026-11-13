# Resumen de pruebas con LLM (prompt general) — Black

- Python: `3.12.15`
- SDK anthropic: `2.8.0`
- Modelo solicitado: `claude-sonnet-5-5` (effort `high`)
- Prompt: `prompt_v1.md`
- Corridas por módulo: 1
- Fecha: 2026-11-13 09:49
- Costo total estimado: US$ 0.92

## Línea base

743 passed, 0 failed, 2 skipped, 0 errors

## Corridas

| Corrida | Modelo | +/− líneas | Tests (passed/failed/errors) | Veredicto | Tipo de fallo | Cambios API pública | Tiempo (s) | Tokens salida | Costo (US$) |
|---|---|---|---|---|---|---|---|---|---|
| cache_run1 | claude-sonnet-5-5 | +61 / −43 | 743 / 0 / 0 | **COMPORTAMIENTO PRESERVADO** |  | — | 38.5 | 4881 | 0.9153 |

## Determinismo

| Módulo | Corridas | Diffs distintos |
|---|---|---|
| cache | 1 | 1 |

Las refactorizaciones que el modelo dice haber aplicado están al final de cada `<corrida>_respuesta.md`. La energía y las emisiones están en `carbono/huella_carbono.md`.

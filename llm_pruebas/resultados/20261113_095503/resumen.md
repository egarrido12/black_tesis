# Resumen de pruebas con LLM (prompt general) — Black

- Python: `3.12.15`
- SDK anthropic: `2.8.0`
- Modelo solicitado: `claude-sonnet-5-5` (effort `high`)
- Prompt: `prompt_v1.md`
- Corridas por módulo: 3
- Fecha: 2026-11-13 14:12
- Costo total estimado: US$ 9.11

## Línea base

743 passed, 0 failed, 2 skipped, 0 errors

## Corridas

| Corrida | Modelo | +/− líneas | Tests (passed/failed/errors) | Veredicto | Tipo de fallo | Cambios API pública | Tiempo (s) | Tokens salida | Costo (US$) |
|---|---|---|---|---|---|---|---|---|---|
| __init___run1 | claude-sonnet-5-5 | +823 / −528 | 742 / 1 / 0 | **ROMPE TESTS (solo formato)** |  | — | 246.8 | 44571 | 0.4891 |
| __init___run2 | claude-sonnet-5-5 | +805 / −530 | 742 / 1 / 0 | **ROMPE TESTS (solo formato)** |  | — | 244.7 | 44644 | 1.313 |
| __init___run3 | claude-sonnet-5-5 | +871 / −567 | 742 / 1 / 0 | **ROMPE TESTS (solo formato)** |  | — | 235.2 | 43847 | 0.4818 |
| parsing_run1 | claude-sonnet-5-5 | +139 / −95 | 743 / 0 / 0 | **COMPORTAMIENTO PRESERVADO** |  | — | 46.1 | 7480 | 0.1182 |
| parsing_run2 | claude-sonnet-5-5 | +121 / −94 | 743 / 0 / 0 | **COMPORTAMIENTO PRESERVADO** |  | — | 44.0 | 7205 | 0.1154 |
| parsing_run3 | claude-sonnet-5-5 | +119 / −81 | 743 / 0 / 0 | **COMPORTAMIENTO PRESERVADO** |  | — | 51.7 | 8114 | 0.1245 |
| ranges_run1 | claude-sonnet-5-5 | +292 / −206 | 743 / 0 / 0 | **COMPORTAMIENTO PRESERVADO** |  | — | 108.1 | 17820 | 0.2216 |
| ranges_run2 | claude-sonnet-5-5 | +325 / −247 | 743 / 0 / 0 | **COMPORTAMIENTO PRESERVADO** |  | — | 128.5 | 21356 | 0.2569 |
| ranges_run3 | claude-sonnet-5-5 | +296 / −210 | 743 / 0 / 0 | **COMPORTAMIENTO PRESERVADO** |  | — | 111.4 | 18410 | 0.2275 |
| cache_run1 | claude-sonnet-5-5 | +49 / −43 | 743 / 0 / 0 | **COMPORTAMIENTO PRESERVADO** |  | — | 28.9 | 4489 | 0.0883 |
| cache_run2 | claude-sonnet-5-5 | +48 / −38 | 743 / 0 / 0 | **COMPORTAMIENTO PRESERVADO** |  | — | 27.2 | 4373 | 0.0871 |
| cache_run3 | claude-sonnet-5-5 | +44 / −32 | 743 / 0 / 0 | **COMPORTAMIENTO PRESERVADO** |  | — | 29.5 | 4545 | 0.0888 |
| trans_run1 | claude-sonnet-5-5 | +341 / −266 | 743 / 0 / 0 | **COMPORTAMIENTO PRESERVADO** |  | — | 277.8 | 48492 | 0.5283 |
| trans_run2 | claude-sonnet-5-5 | +487 / −363 | 743 / 0 / 0 | **COMPORTAMIENTO PRESERVADO** |  | — | 300.8 | 51174 | 0.5551 |
| trans_run3 | claude-sonnet-5-5 | +625 / −434 | 743 / 0 / 0 | **COMPORTAMIENTO PRESERVADO** |  | — | 310.6 | 54455 | 0.5879 |
| output_run1 | claude-sonnet-5-5 | +40 / −24 | 743 / 0 / 0 | **COMPORTAMIENTO PRESERVADO** |  | — | 27.7 | 4342 | 0.0868 |
| output_run2 | claude-sonnet-5-5 | +49 / −27 | 743 / 0 / 0 | **COMPORTAMIENTO PRESERVADO** |  | — | 27.0 | 4334 | 0.0867 |
| output_run3 | claude-sonnet-5-5 | +51 / −26 | 743 / 0 / 0 | **COMPORTAMIENTO PRESERVADO** |  | — | 24.7 | 4003 | 0.0834 |
| files_run1 | claude-sonnet-5-5 | +110 / −70 | 743 / 0 / 0 | **COMPORTAMIENTO PRESERVADO** |  | — | 55.6 | 10090 | 0.1443 |
| files_run2 | claude-sonnet-5-5 | +83 / −52 | 743 / 0 / 0 | **COMPORTAMIENTO PRESERVADO** |  | — | 55.8 | 10126 | 0.1446 |
| files_run3 | claude-sonnet-5-5 | +120 / −73 | 743 / 0 / 0 | **COMPORTAMIENTO PRESERVADO** |  | — | 54.0 | 9907 | 0.1424 |
| linegen_run1 | claude-sonnet-5-5 | +660 / −542 | 743 / 0 / 0 | **COMPORTAMIENTO PRESERVADO** |  | — | 304.1 | 60006 | 0.6434 |
| linegen_run2 | claude-sonnet-5-5 | +958 / −757 | 743 / 0 / 0 | **COMPORTAMIENTO PRESERVADO** |  | — | 348.0 | 66449 | 0.7079 |
| linegen_run3 | claude-sonnet-5-5 | +817 / −643 | 743 / 0 / 0 | **COMPORTAMIENTO PRESERVADO** |  | — | 283.5 | 56148 | 0.6049 |
| mode_run1 | claude-sonnet-5-5 | +69 / −172 | 743 / 0 / 0 | **COMPORTAMIENTO PRESERVADO** |  | — | 44.7 | 7030 | 0.9368 |
| mode_run2 | claude-sonnet-5-5 | +121 / −188 | 743 / 0 / 0 | **COMPORTAMIENTO PRESERVADO** |  | — | 47.3 | 7784 | 0.1212 |
| mode_run3 | claude-sonnet-5-5 | +92 / −190 | 743 / 0 / 0 | **COMPORTAMIENTO PRESERVADO** |  | — | 48.8 | 7660 | 0.12 |

## Determinismo

| Módulo | Corridas | Diffs distintos |
|---|---|---|
| __init__ | 3 | 3 |
| cache | 3 | 3 |
| files | 3 | 3 |
| linegen | 3 | 3 |
| mode | 3 | 3 |
| output | 3 | 3 |
| parsing | 3 | 3 |
| ranges | 3 | 3 |
| trans | 3 | 3 |

Las refactorizaciones que el modelo dice haber aplicado están al final de cada `<corrida>_respuesta.md`. La energía y las emisiones están en `carbono/huella_carbono.md`.

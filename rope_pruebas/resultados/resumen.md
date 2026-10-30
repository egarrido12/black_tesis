# Resumen de pruebas con Rope (Black)

- Python: `3.12.15`
- Rope: `1.15.0`
- Fecha: 2026-10-30 10:30

## Línea base

743 passed, 0 failed, 2 skipped, 0 errors

## Refactorizaciones

| # | Tipo | Descripción | Rope | Tiempo (s) | Tests (passed/failed/errors) | Veredicto |
|---|---|---|---|---|---|---|
| 02_rename_funcion | Rename | parsing.lib2to3_parse -> parse_to_tree (usada en 3 módulos y en tests vía black.lib2to3_parse) | aplicada | 1.172 | 743 / 0 / 0 | **COMPORTAMIENTO PRESERVADO** |
| 03_rename_funcion_importada | Rename | ranges.parse_line_ranges -> parse_line_range_specs (también importada por los tests) | aplicada | 1.279 | 743 / 0 / 0 | **COMPORTAMIENTO PRESERVADO** |
| 04_rename_metodo | Rename | Cache.is_changed -> has_changed (llamada sobre instancias obtenidas con Cache.read) | aplicada | 0.709 | 699 / 44 / 0 | **ROMPE TESTS** |
| 05_rename_clase | Rename | trans.StringTransformer -> BaseStringTransformer (clase base abstracta de 5 subclases) | aplicada | 1.041 | 743 / 0 / 0 | **COMPORTAMIENTO PRESERVADO** |
| 06_rename_parametro | Rename | parámetro keyword-only fast de format_file_contents -> skip_safety_checks | error: RefactoringError: Rename refactoring should be performed on resolvable python identifiers. | 0.049 | — | **RECHAZADA POR ROPE** |
| 06b_rename_parametro_posicional | Rename | parámetro posicional src_contents de format_file_contents -> source (control de 06) | aplicada | 1.08 | 742 / 1 / 0 | **ROMPE TESTS** |
| 07_extract_cache | Extract Method | bloque que elige la caché en reformat_one -> _read_cache | aplicada | 0.098 | 742 / 1 / 0 | **ROMPE TESTS** |
| 08_extract_stdin | Extract Method | bloque if/elif/else que detecta stdin en reformat_one -> _detect_stdin (2 valores de salida) | aplicada | 0.623 | 742 / 1 / 0 | **ROMPE TESTS** |
| 09_extract_con_continue | Extract Method | bloque con `continue` dentro del for de get_sources -> _resolve_stdin_source (caso límite) | error: RefactoringError: A break/continue without having a matching for/while loop. | 0.031 | — | **RECHAZADA POR ROPE** |
| 10_extract_bucle | Extract Method | bucle for completo de get_sources -> _collect_sources | error: SyntaxError: f-string: expecting a valid expression after '{' (<string>, line 27) | 0.061 | — | **RECHAZADA POR ROPE** |
| 10b_extract_bucle_sin_fstring | Extract Method | bucle for de output.diff (sin f-strings) -> _append_diff_lines (control de 10) | aplicada | 0.042 | 714 / 29 / 0 | **ROMPE TESTS** |
| 11_inline_funcion | Inline | inline de output._splitlines_no_ff en diff (2 llamadas) | aplicada | 0.705 | 743 / 0 / 0 | **COMPORTAMIENTO PRESERVADO** |
| 12_move_funcion | Move | mover black.re_compile_maybe_verbose a black.files (importada por los tests) | aplicada | 1.334 | 742 / 1 / 0 | **ROMPE TESTS** |
| 13_rename_parcheada | Rename | output.dump_to_file -> write_to_temp_file (los tests la parchean con patch("black.dump_to_file")) | aplicada | 1.584 | 431 / 5 / 307 | **ROMPE TESTS** |
| 14_rename_parcheada_docs | Rename | igual que 13 pero con docs=True (renombra también en strings y comentarios) | aplicada | 1.976 | 743 / 0 / 0 | **COMPORTAMIENTO PRESERVADO** |
| 15_rename_visitante | Rename | LineGenerator.visit_suite -> visit_block (despacho dinámico getattr(self, f"visit_{name}")) | aplicada | 1.214 | 729 / 14 / 0 | **ROMPE TESTS** |
| 16_rename_preview | Rename | Preview.wrap_comprehension_in -> wrap_comprehension_in_clause (nombre también en docs y JSON schema) | aplicada | 0.438 | 742 / 1 / 0 | **ROMPE TESTS** |

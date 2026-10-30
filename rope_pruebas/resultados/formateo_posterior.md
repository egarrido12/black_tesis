# Verificación: ¿el fallo de `test_piping` es solo de formato?

Copia refactorizada por Rope → `black` sobre los archivos modificados → suite completa.

| # | Archivos formateados | Tests con la salida de Rope | Tests después de `black` |
|---|---|---|---|
| 06b_rename_parametro_posicional | `src/black/__init__.py` | 742 / 1 | 743 / 0 |
| 07_extract_cache | `src/black/__init__.py` | 742 / 1 | 743 / 0 |
| 08_extract_stdin | `src/black/__init__.py` | 742 / 1 | 743 / 0 |
| 12_move_funcion | `src/black/__init__.py`, `src/black/files.py` | 742 / 1 | 743 / 0 |

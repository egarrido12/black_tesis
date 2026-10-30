# Clasificación de los avisos de find_errors

Total: 852 avisos.

| Categoría | Cant. | Ejemplos |
|---|---|---|
| Atributo dinámico de `syms` (gramática de blib2to3, creado con setattr) | 416 | `__init__.py:1656` (Unresolved attribute `typedargslist`), `__init__.py:1657` (Unresolved attribute `arglist`), `__init__.py:1658` (Unresolved attribute `varargslist`) |
| Variable de comprensión, generador o lambda | 207 | `__init__.py:150` (Defined later `k`), `__init__.py:150` (Defined later `v`), `__init__.py:150` (Defined later `v`) |
| Parámetro keyword-only (después de `*`) | 176 | `__init__.py:107` (Unresolved variable `check`), `__init__.py:110` (Unresolved variable `color`), `__init__.py:857` (Unresolved variable `root`) |
| Otro atributo no resuelto (tipos de terceros, uniones, objetos dinámicos) | 48 | `__init__.py:610` (Unresolved attribute `get_usage`), `__init__.py:615` (Unresolved attribute `get_usage`), `__init__.py:621` (Unresolved attribute `get_usage`) |
| Otro "Defined later" (variable asignada en un bucle o en otra rama antes de leerse) | 4 | `linegen.py:1828` (Defined later `current_line`), `linegen.py:1830` (Defined later `current_line`), `linegen.py:1899` (Defined later `current_line`) |
| Variable implícita de módulo (`__file__`) | 1 | `__init__.py:88` (Unresolved variable `__file__`) |

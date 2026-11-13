# Pruebas de Black con Rope (y su huella de carbono)

Este documento describe el proceso completo: qué se probó, cómo reproducirlo, qué resultados se obtuvieron y cómo interpretarlos. Es la tercera réplica del experimento, después de PySnooper (`../PySnooper_tesis/rope_pruebas/`) y Cookiecutter (`../cookiecutter_tesis/rope_pruebas/`). Usa la misma metodología y los mismos tipos de refactorización. Como novedad, **mide con [CodeCarbon](https://codecarbon.io) la energía y las emisiones de CO₂ de cada fase**.

- **Proyecto bajo prueba:** Black (commit `408211f4`, versión `0.1.dev2473+g408211f4a`). Paquete en `src/black/`: 25 módulos, unas 16 400 líneas (más `src/blib2to3/` y `src/blackd/`).
- **Herramientas:** [Rope](https://github.com/python-rope/rope) 1.15.0 (refactorización automática) y [CodeCarbon](https://codecarbon.io) 3.3.2 (medición de huella de carbono).
- **Entorno:** Python 3.12.15, pytest 9.2.0, macOS 15.6.1 (Darwin 24.6.0), Apple M4 (10 núcleos, 16 GB de RAM).
- **Fecha de ejecución:** 2026-10-30.

> Black también requiere Python ≥ 3.10. Igual que con Cookiecutter, el entorno se creó con `uv` y Python 3.12.

---

## 1. Objetivo y metodología

Las preguntas son:

1. **¿Conservan el comportamiento de Black las refactorizaciones automáticas de Rope?**
2. **¿Cuánta energía consume y cuánto CO₂ emite aplicar esas refactorizaciones (y verificarlas)?**

La suite de tests de Black (743 tests) sirve como oráculo:

1. **Reposo:** se mide durante 30 s el consumo de la máquina sin hacer nada. Es la referencia para interpretar el resto.
2. **Línea base:** se corre la suite original y se anota el resultado de referencia.
3. **Análisis estático:** se usan las herramientas de análisis de Rope (`find_errors`, `find_occurrences`, `find_definition`) sin modificar código. También se diagnostica cómo hay que configurar Rope para que funcione en Black (sección 4.1).
4. **Refactorizaciones:** cada refactorización se aplica con la API de Rope **sobre una copia limpia e independiente** del proyecto, **5 veces** (cada vez sobre una copia nueva), para medir su energía y comprobar que Rope es determinista. Se guarda el diff y se vuelve a correr la suite completa.
5. **Veredicto:** si el número de tests que pasan es igual al de la línea base y no hay fallos ni errores, la refactorización **preserva el comportamiento**. Si no, **rompe tests**. Si Rope se niega a aplicarla, queda como **rechazada por Rope**. Es el mismo criterio que en PySnooper y Cookiecutter.

Hay tres grupos de casos:

- **02 a 12** reproducen uno por uno los tipos probados en PySnooper y Cookiecutter, con la misma numeración: 5 Rename, 4 Extract Method, 1 Inline y 1 Move.
- **06b y 10b** son **casos de control** que agregué porque 06 y 10 fallaron por motivos que hay que aislar (sección 5.3).
- **13 a 16** son **casos propios de Black**, que nacen de cómo está construido este proyecto: mocks por string (13, 14, igual que en Cookiecutter), despacho dinámico de métodos `visit_*` (15) y nombres de opciones que también viven en documentación y JSON (16).

> El código original en `src/` **nunca se modifica**. Todo se hace en `rope_pruebas/_trabajo/<experimento>/`. Comprobado con `git status` después de cada corrida.

---

## 2. Cómo ejecutarlo

Desde la raíz del repositorio:

```bash
# (una sola vez) crear el entorno con Python 3.12 y las dependencias
~/Library/Python/3.9/bin/uv venv --python 3.12 .venv
~/Library/Python/3.9/bin/uv pip install --python .venv/bin/python -e ".[d,jupyter]" "pytest>=7.4.3" pytest-xdist rope codecarbon

# 1) Línea base "a mano" (opcional, el script también la hace)
.venv/bin/python -m pytest tests -q -rs

# 2) Todo el proceso: reposo + línea base + análisis + refactorizaciones + huella de carbono
caffeinate -dimsu .venv/bin/python -W ignore rope_pruebas/ejecutar_pruebas_rope.py

# 3) Análisis complementarios (usan las copias que dejó el paso 2)
.venv/bin/python rope_pruebas/verificar_formateo.py       # ¿los fallos de test_piping son solo de formato?
.venv/bin/python rope_pruebas/clasificar_find_errors.py   # clasifica los 852 avisos de find_errors
```

El paso 2 tarda unos **8 minutos**. Cada ejecución **borra y regenera** la carpeta `resultados/` (incluida `resultados/carbono/`).

- **`caffeinate -dimsu`** evita que el Mac se suspenda a mitad de la corrida. La suspensión mata los procesos largos y deja las mediciones de energía incompletas.
- **`-W ignore`** silencia cientos de `SyntaxWarning` que Python emite cuando Rope analiza los casos de prueba de `tests/data/` (contienen secuencias de escape inválidas a propósito).
- **Opciones del script:** `--pais COL` (país del factor de emisión, por defecto Colombia), `--repeticiones 5` (repeticiones de cada operación de Rope) y `--reposo 30` (segundos de medición en reposo).

Detalles técnicos del script, distintos de las versiones anteriores:

- **`PYTHONPATH=<copia>/src`**: el `.venv` tiene Black instalado en modo editable apuntando al `src/` original. `PYTHONPATH` hace que se importe la copia refactorizada. El script lo verifica (la ruta aparece en la consola).
- **`Project(..., source_folders=['src'], ignore_syntax_errors=True)`**: ver la sección 4.1.
- **pytest corre en serie** (sin `-n auto` de `pytest-xdist`), igual que en los otros proyectos. Así la medición de energía no depende de cómo xdist reparta los núcleos.
- La copia excluye `.git/`, `.github/`, `.venv/` y `profiling/`, que los tests no usan. **Sí incluye `docs/`**, porque `tests/test_docs.py` la lee (sin ella, ese test se omite y cambia la línea base).

### Estructura de archivos

```
rope_pruebas/
├── README.md                     ← este documento
├── RESUMEN_PRESENTACION.md       ← resumen corto para presentar los resultados
├── ejecutar_pruebas_rope.py      ← script principal (Rope + CodeCarbon)
├── verificar_formateo.py         ← reformatea con Black los casos que solo fallan test_piping
├── clasificar_find_errors.py     ← clasifica los avisos de find_errors por categoría
├── .gitignore                    ← ignora _trabajo/
├── _trabajo/                     ← copias del proyecto, una por experimento (temporal)
└── resultados/
    ├── resumen.md                     ← tabla resumen (se genera sola)
    ├── resumen.json                   ← todos los datos en JSON (incluye cada repetición y cada medición)
    ├── 00_linea_base_pytest.txt       ← salida completa de pytest de la línea base
    ├── 01_analisis_estatico.md        ← diagnóstico de configuración + find_errors / find_occurrences / find_definition
    ├── 01b_clasificacion_find_errors.md
    ├── NN_<nombre>.diff               ← cambios exactos que hizo Rope
    ├── NN_<nombre>_pytest.txt         ← salida de pytest después de la refactorización
    ├── NN_<nombre>_error.txt          ← traceback, si Rope rechazó la refactorización
    ├── NN_<nombre>_black.diff         ← lo que cambia Black al reformatear la salida de Rope
    ├── NN_<nombre>_formateado_pytest.txt
    ├── formateo_posterior.md          ← tabla de verificar_formateo.py
    └── carbono/
        ├── huella_carbono.md          ← tablas de energía y emisiones
        ├── emisiones_maquina.csv      ← CSV estándar de CodeCarbon, modo máquina (una fila por fase)
        ├── emisiones_proceso.csv      ← CSV estándar de CodeCarbon, modo proceso
        ├── serie_temporal_maquina.csv ← una fila por muestra, cada 0,25 s, DURANTE cada fase
        ├── serie_temporal_proceso.csv
        └── eventos.csv                ← momentos marcados dentro de cada operación de Rope
```

---

## 3. Paso 1: línea base (tests de Black sin cambios)

| Resultado | Cantidad |
|---|---|
| Passed | **743** |
| Failed | 0 |
| Skipped | 2 |
| Errors | 0 |

Además pasan 31 *subtests*. Los 2 tests omitidos (`tests/test_no_ipynb.py`) solo corren cuando Jupyter **no** está instalado (opción `--run-optional no_jupyter`). Como el entorno tiene el extra `jupyter`, se omiten. No indican ningún fallo.

**Referencia para comparar: 743 passed / 0 failed / 2 skipped.** La suite tarda unos 24 s en serie.

---

## 4. Paso 2: análisis estático con Rope

Detalle completo en [`resultados/01_analisis_estatico.md`](resultados/01_analisis_estatico.md).

### 4.1 Primer obstáculo: Rope no encuentra el código de Black

Con la configuración por defecto, **Rope no sirve en Black**. Hay dos problemas, uno conocido y uno nuevo:

| Opciones de `Project(...)` | Carpetas de código detectadas | `import black` se resuelve en | Ocurrencias de `lib2to3_parse` |
|---|---|---|---|
| (por defecto) | `.` | el repositorio **original** | aborta con `ModuleSyntaxError` (`tests/data/miscellaneous/invalid_header.py`) |
| `source_folders=['src']` | `src`, `.` | la copia | aborta con `ModuleSyntaxError` |
| `ignore_syntax_errors=True` | `.` | el repositorio **original** | **1 ocurrencia en 1 archivo** |
| `ignore_syntax_errors=True, source_folders=['src']` | `src`, `.` | la copia | **40 ocurrencias en 5 archivos** ✔ |

1. **Archivos `.py` que no son Python válido** (conocido de Cookiecutter). `tests/data/` tiene cientos de casos de prueba de formateo, algunos con sintaxis inválida a propósito. Se resuelve con `ignore_syntax_errors=True`.
2. **El "src layout"** (nuevo). Black pone su paquete en `src/black/`, no en la raíz. Rope no detecta `src/` como carpeta de código y resuelve `import black` con el `sys.path` del intérprete. Por la instalación editable, eso apunta al repositorio original y no a la copia. Así, **Rope cree que `black` es una biblioteca externa** y no ve ningún uso de los símbolos dentro del proyecto: un Rename solo cambia la definición y deja rotos todos los usos. Lo detecté en una prueba en seco: los Rename modificaban **un solo archivo**. Se resuelve con `source_folders=['src']`.

El segundo problema es grave porque **Rope no avisa**: produce un diff aparentemente válido pero incompleto. Muchos proyectos modernos usan el src layout (es la estructura que usa el tutorial oficial de empaquetado de Python), así que esta configuración es necesaria en la práctica.

### 4.2 `find_occurrences`: búsqueda de referencias

| Símbolo | Ocurrencias encontradas | ¿Correcto? |
|---|---|---|
| `parsing.lib2to3_parse` | 40 (definición, re-export en `black/__init__.py`, `debug.py`, y 35 usos en tests, casi todos `black.lib2to3_parse(...)`) | Sí |
| `ranges.parse_line_ranges` | 8 (incluye imports en `tests/util.py` y `tests/test_ranges.py`) | Sí |
| `Cache.is_changed` | 2 (definición y la llamada `self.is_changed` en `cache.py`) | **Incompleto**: no ve `cache.is_changed(src)` en `black/__init__.py` ni las ~25 llamadas de `tests/test_black.py` (ver 5.2, caso 04) |
| `trans.StringTransformer` | 4 (definición + 3 subclases directas) | Sí |
| `output.dump_to_file` | 19 | Sí para el código; no cuenta los 6 strings `"black.dump_to_file"` de los `patch(...)` |
| `LineGenerator.visit_suite` | 1 (solo la definición) | Correcto en lo estático, pero el método **se llama por nombre armado en tiempo de ejecución** (`getattr(self, f"visit_{name}")`), que Rope no puede ver |
| `Preview.wrap_comprehension_in` | 3 | Sí para el código; no ve el nombre en `docs/` ni en `black.schema.json` |

### 4.3 `find_definition`: ir a la definición

Desde `src_node = lib2to3_parse(...)` en `black/__init__.py`, Rope resuelve bien la definición en `src/black/parsing.py:77`, a través del re-export de `black/__init__.py`.

### 4.4 `find_errors`: detección de errores

Rope reporta **852 avisos** en los 25 módulos de `src/black` (`linegen`: la mayor parte, `__init__`: 181). El código funciona y los 743 tests pasan, así que **todos son falsos positivos**.

Con 852 avisos no es práctico revisarlos uno por uno (en Cookiecutter eran 39). Por eso escribí [`clasificar_find_errors.py`](clasificar_find_errors.py), que asigna cada aviso a una categoría mirando el código señalado (con el módulo `ast` de Python). Revisé a mano los casos que no encajaban en ninguna regla y ajusté las reglas hasta clasificarlos todos. Resultado en [`resultados/01b_clasificacion_find_errors.md`](resultados/01b_clasificacion_find_errors.md):

| Categoría | Cant. | Ejemplo | Por qué es falso positivo |
|---|---|---|---|
| Atributo dinámico de `syms` (`syms.atom`, `syms.suite`…) | 416 | `__init__.py:1656` | `blib2to3/pygram.py` crea esos atributos con `setattr` a partir de la gramática. No existen en el código fuente |
| Variable de comprensión, generador o lambda | 207 | `__init__.py:150` (`k`, `v`) | Rope no modela el alcance propio de comprensiones y lambdas (igual que en PySnooper y Cookiecutter) |
| Parámetro keyword-only (después de `*`) | 176 | `__init__.py:857` (`root`) | El parámetro existe; Rope no lo reconoce. **Es la misma causa del rechazo del caso 06** |
| Otros atributos no resueltos | 48 | `__init__.py:1513` (`line_generator.visit`), `cache.py:99` (`hashlib.sha256`) | Tipos genéricos (`Visitor[T]`), decoradores de `click` y algunos módulos de la biblioteca estándar |
| Variable asignada en un bucle antes de leerse | 4 | `linegen.py:1828` (`current_line`) | El flujo garantiza que la variable existe |
| Variable implícita de módulo | 1 | `__init__.py:88` (`__file__`) | `__file__` siempre existe en un módulo |

Dos de estas categorías anticipan fallos de las refactorizaciones: los **parámetros keyword-only** (caso 06) y los **métodos de clases genéricas o devueltos por `Self`** (casos 04 y 15).

---

## 5. Paso 3: refactorizaciones automáticas

### 5.1 Resultados

| # | Tipo | Qué se hizo | Archivos modificados | Tests (passed/failed/errors) | Veredicto |
|---|---|---|---|---|---|
| 02 | Rename | `lib2to3_parse` → `parse_to_tree` (3 módulos + tests vía `black.lib2to3_parse`) | 5 | 743 / 0 / 0 | ✅ Preservado |
| 03 | Rename | `parse_line_ranges` → `parse_line_range_specs` (importada por los tests) | 4 | 743 / 0 / 0 | ✅ Preservado |
| 04 | Rename | método `Cache.is_changed` → `has_changed` | 1 | 699 / **44** / 0 | ❌ Rompe tests |
| 05 | Rename | clase `StringTransformer` → `BaseStringTransformer` (clase base abstracta) | 1 | 743 / 0 / 0 | ✅ Preservado |
| 06 | Rename | parámetro **keyword-only** `fast` de `format_file_contents` → `skip_safety_checks` | — | — | ⛔ Rechazada por Rope |
| 06b | Rename | *(control)* parámetro **posicional** `src_contents` → `source` | 1 | 742 / **1** / 0 | ❌ Rompe tests (solo formato) |
| 07 | Extract Method | bloque que elige la caché en `reformat_one` → `_read_cache` | 1 | 742 / **1** / 0 | ❌ Rompe tests (solo formato) |
| 08 | Extract Method | bloque `if/elif/else` que detecta stdin → `_detect_stdin` (2 valores de salida) | 1 | 742 / **1** / 0 | ❌ Rompe tests (solo formato) |
| 09 | Extract Method | bloque con `continue` dentro del `for` de `get_sources` (caso límite) | — | — | ⛔ Rechazada por Rope |
| 10 | Extract Method | bucle `for` completo de `get_sources` → `_collect_sources` | — | — | ⛔ Rope falla (error interno) |
| 10b | Extract Method | *(control)* bucle de `output.diff`, sin f-strings → `_append_diff_lines` | 1 | 714 / **29** / 0 | ❌ Rompe tests |
| 11 | Inline | `output._splitlines_no_ff` dentro de `diff` (2 llamadas) | 1 | 743 / 0 / 0 | ✅ Preservado |
| 12 | Move | `black.re_compile_maybe_verbose` → `black.files` (importada por los tests) | 3 | 742 / **1** / 0 | ❌ Rompe tests (solo formato) |
| 13 | Rename | `output.dump_to_file` → `write_to_temp_file` (parcheada con `patch("black.dump_to_file")`) | 3 | 431 / **5** / **307** | ❌ Rompe tests |
| 14 | Rename | igual que 13, con `docs=True` | 4 | 743 / 0 / 0 | ✅ Preservado |
| 15 | Rename | `LineGenerator.visit_suite` → `visit_block` (despacho dinámico) | 1 | 729 / **14** / 0 | ❌ Rompe tests |
| 16 | Rename | `Preview.wrap_comprehension_in` → `wrap_comprehension_in_clause` (nombre también en docs y JSON) | 3 | 742 / **1** / 0 | ❌ Rompe tests |

**"Solo formato"** significa que el único test que falla es `test_piping`, que exige que el código fuente de Black esté formateado con Black. Después de pasar `black` por los archivos que modificó Rope, la suite vuelve a **743 / 0** (sección 5.4, verificado con [`verificar_formateo.py`](verificar_formateo.py)).

**Totales:**

| Grupo | Preservan (criterio estricto) | Preservan ignorando el formato | Rompen el comportamiento | Rechazadas por Rope |
|---|---|---|---|---|
| Casos equivalentes a PySnooper/Cookiecutter (02–12, 11 casos) | **4 (36 %)** | **7 (64 %)** | 1 (04) | 3 (06, 09, 10) |
| Controles (06b, 10b) | 0 | 1 | 1 (10b) | 0 |
| Casos propios de Black (13–16) | 1 (14) | 1 | 3 (13, 15, 16) | 0 |
| **Total (17)** | **5 (29 %)** | **9 (53 %)** | **5 (29 %)** | **3 (18 %)** |

- **Determinismo:** en los 17 casos, las 5 repeticiones produjeron **exactamente el mismo diff** (o el mismo error).
- **Tiempo:** cada operación de Rope tardó entre 0,05 s y 1,8 s (media de 5 repeticiones). Las 17 suman 15,3 s.

### 5.2 Rename

**02, 03 y 05: correctos.** Rope actualizó la definición, el re-export de `black/__init__.py` (`from black.parsing import lib2to3_parse`), los imports de los tests y **los 35 usos** (casi todos `black.lib2to3_parse(...)`) de `tests/test_black.py` y `tests/util.py`, que pasan por el atributo del paquete. En 05 renombró la clase y las subclases que la heredan directamente.

**04, Rename de un método: Rope no encuentra a los llamadores** ([diff](resultados/04_rename_metodo.diff)).

```python
cache = Cache.read(mode)          # read() es un @classmethod que devuelve `Self`
if not cache.is_changed(src):     # Rope no sabe que `cache` es un Cache → no lo renombra
```

Rope solo cambió la definición y la llamada `self.is_changed(...)` dentro de la misma clase. No infiere el tipo que devuelve `Cache.read` (anotado como `Self`, de `typing`), así que no reconoce como `Cache` los objetos de `black/__init__.py` ni los de los tests. Resultado: **44 tests fallan** con `AttributeError: 'Cache' object has no attribute 'is_changed'`, que Black muestra como `error: cannot format ...`. Es un **error silencioso**: Rope no marca esas llamadas como dudosas.

En Cookiecutter (`_read_extensions`) y PySnooper (`_is_internal_frame`), el método renombrado solo se llamaba con `self.`. Aquí aparece la limitación de la inferencia de tipos de Rope con llamadas a métodos sobre objetos que vienen de otra función.

**06, parámetro keyword-only: Rope se niega.** `format_file_contents(src_contents, *, fast, mode, lines)`: con el cursor sobre `fast`, Rope responde `RefactoringError: Rename refactoring should be performed on resolvable python identifiers`. **No reconoce los parámetros que van después de `*`**, la misma causa de los 176 avisos de `find_errors` (4.4). Es un fallo seguro porque no modifica nada, pero deja sin poder renombrar un tipo de parámetro muy común en código moderno.

**06b (control): el mismo Rename, sobre un parámetro posicional, funciona.** Rope renombró `src_contents` en la firma y en las 4 líneas del cuerpo que lo usan, y los llamadores no cambian porque lo pasan por posición. El único fallo es de formato: con el nombre más corto, `check_stability_and_equivalence(source, dst_contents, mode=mode, lines=lines)` ahora cabe en una línea y Black la uniría (ver 5.4).

### 5.3 Extract Method

**07 y 08: extracciones correctas que solo fallan por formato.** En 07 Rope extrajo el bloque `if no_cache / elif / else` a `_read_cache(no_cache, cache_dir, mode)`, que devuelve `cache`. En 08, con **dos valores de salida**, Rope detectó bien que el bloque reasigna el parámetro `src` y lo devuelve junto con `is_stdin`:

```python
is_stdin, src = _detect_stdin(src)
```

Es el mismo patrón que rompió el caso 08 de Cookiecutter (un `if/else` con 2 salidas), pero aquí no hay variables de comprensiones ni variables definidas en una sola rama, y Rope lo resuelve bien. Como en los otros proyectos, Rope deja **una sola línea en blanco** antes de la función nueva en vez de las dos de PEP 8, y **no agrega anotaciones de tipo** (`def _read_cache(no_cache, cache_dir, mode):`), que el resto de Black sí usa. Por eso falla `test_piping`.

**09, bloque con `continue`: Rope se niega, y está bien.** Igual que en Cookiecutter: `RefactoringError: A break/continue without having a matching for/while loop`. Es un **fallo seguro**.

**10, bucle completo con f-strings: Rope se cae.** Rope no llega a generar ningún cambio. Lanza un `SyntaxError` interno ([traceback](resultados/10_extract_bucle_error.txt)):

```
out(f'Skipping invalid source: "{${path}}"', fg="red")
SyntaxError: f-string: expecting a valid expression after '{'
```

Antes de extraer, Rope busca código similar en el archivo (`rope/refactor/similarfinder.py`). Para eso convierte el bloque en un patrón reemplazando las variables por comodines `${nombre}` y vuelve a analizarlo con `ast.parse`. Dentro de un f-string, `{path}` se vuelve `{${path}}`, que no es Python válido. Es un **bug de Rope**: cualquier bloque que tenga un f-string con una variable no se puede extraer. No rompe el código (no modifica nada), pero es un error interno, no un rechazo pensado como el de 09.

**10b (control): bucle sin f-strings, y un error silencioso nuevo.** Para tener un caso de bucle comparable con PySnooper y Cookiecutter, extraje el bucle de `output.diff`. Rope lo aplicó ([diff](resultados/10b_extract_bucle_sin_fstring.diff)), pero el resultado falla:

```python
def diff(a, b, a_name, b_name):
    import difflib                     # ← import local, dentro de la función
    ...
    _append_diff_lines(a_lines, b_lines, a_name, b_name, diff_lines)

def _append_diff_lines(a_lines, b_lines, a_name, b_name, diff_lines):
    for line in difflib.unified_diff(...):   # ← NameError: name 'difflib' is not defined
```

`difflib` se importa **dentro** de `diff` . Rope no considera los imports locales como variables que el bloque necesita, así que no los pasa como parámetro ni repite el import. **29 tests fallan** con `NameError`. Rope no da ningún aviso.

### 5.4 Inline y Move, y el problema del formato

**11, Inline: correcto.** Rope reemplazó las 2 llamadas a `_splitlines_no_ff` por su cuerpo y borró la función. Como la función usa una variable local `result`, el cuerpo aparece dos veces seguidas reasignando `result`. Es poco elegante, pero correcto. A diferencia de Cookiecutter, la función no reasigna su parámetro, así que no aparece el bug de sustitución de ese caso.

**12, Move: funciona, pero el diff es muy invasivo** ([diff](resultados/12_move_funcion.diff)). Rope movió la función a `files.py`, agregó `import re` y actualizó los usos. Además:

- **Reescribió bloques de imports que no tenían nada que ver.** Juntó el `from black.files import (...)` de 11 nombres en **una línea de 260 caracteres** y fusionó tres `from black.mode import ...` en uno solo, **borrando el comentario `# re-exported`**.
- En `files.py`, **subió 4 imports por encima** del bloque `if sys.version_info >= (3, 11): import tomllib`, cambiando su orden.
- En `tests/test_black.py`, **borró `import black`, duplicó `import black.files` y eliminó el comentario `# Import other test classes`**. Funciona de casualidad: `import black.files` también deja disponible el nombre `black`.
- Dejó `from black import re_compile_maybe_verbose`, que sigue funcionando solo porque `black/__init__.py` ahora la importa desde `files`.

Todos los tests pasan salvo `test_piping`.

**El problema del formato (06b, 07, 08 y 12).** `tests/test_black.py::BlackTestCase::test_piping` pasa el propio `src/black/__init__.py` por Black y exige que ya esté formateado. Black es el único proyecto de los tres que **se aplica su propio estilo como test**, y Rope nunca reformatea lo que genera. Para separar "rompe el comportamiento" de "rompe el estilo", `verificar_formateo.py` toma la copia que dejó Rope, ejecuta `black` sobre los archivos modificados y vuelve a correr la suite. Formatea con **la misma configuración que usa `test_piping`** (`--config tests/empty.toml`, estilo estable). Hay que indicarla porque Black se formatea a sí mismo con su estilo inestable (`unstable = true` en `pyproject.toml`): sin `--config`, `black` tomaría esa configuración y en algunas construcciones (por ejemplo `frozenset({...})`) dejaría un formato que `test_piping` no acepta. Con los cambios de Rope da lo mismo, pero con los de Claude no (ver `../llm_pruebas/README.md`):

| # | Tests con la salida de Rope | Tests después de `black` | Qué cambió Black |
|---|---|---|---|
| 06b | 742 / 1 | **743 / 0** | une una llamada que ahora cabe en una línea |
| 07 | 742 / 1 | **743 / 0** | agrega la segunda línea en blanco antes de `_read_cache` |
| 08 | 742 / 1 | **743 / 0** | agrega la segunda línea en blanco antes de `_detect_stdin` |
| 12 | 742 / 1 | **743 / 0** | vuelve a partir los imports largos en varias líneas |

Conclusión: en estos 4 casos **Rope preservó el comportamiento**, pero su salida **no cumple el estilo del proyecto**. En PySnooper y Cookiecutter se vieron los mismos problemas de estilo, pero ningún test los detectaba.

### 5.5 Casos propios de Black: referencias que Rope no ve

**13, Rename de una función parcheada por string.** Los tests reemplazan la función con un mock indicando su ruta como texto:

```python
@patch("black.dump_to_file", dump_to_stderr)           # tests/test_black.py (5 veces)
with patch("black.dump_to_file", dump_to_stderr):      # tests/test_format.py (fixture usada por ~300 tests)
```

Rope renombró la definición y sus 18 usos en código (re-export, llamadas en `black/__init__.py` y `black.dump_to_file(...)` en los tests), pero **no los 6 strings**. `patch` falla con `AttributeError: <module 'black'> does not have the attribute 'dump_to_file'`. Como el `patch` de `test_format.py` está en una *fixture* que usan casi todos los tests de formateo, el resultado es **307 errores y 5 fallos**: el peor caso de los tres proyectos.

**14, el mismo Rename con `docs=True`: aquí sí funciona.** Con `docs=True`, Rope también renombró los 6 strings y **los 743 tests pasan**. En Cookiecutter (caso 14) la misma opción no cambiaba nada. La diferencia está en qué nombre empieza el string:

| | String | ¿El primer nombre está importado en ese archivo? | ¿`docs=True` lo renombra? |
|---|---|---|---|
| Cookiecutter | `'cookiecutter.vcs.is_vcs_installed'` | No (solo `from cookiecutter import vcs`) | No |
| Black | `"black.dump_to_file"` | Sí (`import black`) | **Sí** |

`docs=True` solo actúa sobre strings y comentarios donde Rope puede **resolver el nombre en ese ámbito** (`rope/refactor/occurrences.py`, filtro `PyNameFilter`). En Black los tests hacen `import black`, así que la ruta del string coincide con un nombre visible. Conclusión: **`docs=True` sirve para mocks por string solo cuando el string empieza por un nombre importado en ese archivo**. No es una garantía, y depende de cómo estén escritos los imports.

**15, Rename de un método que se llama por nombre armado en tiempo de ejecución.** Los visitantes de Black eligen el método según el tipo de nodo:

```python
# src/black/nodes.py, Visitor.visit
name = type_repr(node.type)               # "suite", "simple_stmt", ...
visitf = getattr(self, f"visit_{name}", None)
if visitf: yield from visitf(node)
else:      yield from self.visit_default(node)
```

Rope renombró `visit_suite` → `visit_block` (único cambio, en `linegen.py`). Desde ese momento, los nodos `suite` **caen en `visit_default`** y se pierde la lógica especial para los cuerpos que son solo `...` (`is_stub_suite`). El código no lanza ningún error: **Black sigue funcionando pero formatea distinto** los archivos `.pyi` y las funciones con cuerpo `...`. Fallan 14 tests (10 casos de `test_simple_format` y 4 de `--pyi`). Es el equivalente en Black del `.format(**locals())` de PySnooper: **un acceso por nombre que el análisis estático no puede seguir**. Sin esos tests, el cambio de comportamiento pasaría inadvertido.

**16, Rename de una opción que también vive fuera de Python.** Rope renombró el miembro del enum y sus 2 usos en código (`linegen.py` y `tests/test_black.py`). Pero el nombre de cada *preview feature* también aparece en:

- `docs/the_black_code_style/future_style.md`, que `tests/test_docs.py` compara con el enum → **1 test falla**.
- `src/black/resources/black.schema.json`, el esquema que validan las herramientas de configuración. **No hay test**: el esquema queda desactualizado en silencio.
- La línea de comandos (`--enable-unstable-feature wrap_comprehension_in`) y los `pyproject.toml` de los usuarios. Su configuración dejaría de funcionar, y **ningún test lo detecta**.

Aquí el nombre de un símbolo Python es, a la vez, **parte de la interfaz pública** (opciones de configuración). Rope no tiene forma de saberlo.

---

## 6. Huella de carbono (CodeCarbon)

Detalle completo en [`resultados/carbono/huella_carbono.md`](resultados/carbono/huella_carbono.md). Los datos crudos están en `resultados/carbono/` y en `resumen.json`. La lógica de medición está en [`../huella_carbono/medicion.py`](../huella_carbono/medicion.py), compartida con el experimento de Claude ([`../llm_pruebas/`](../llm_pruebas/README.md)) para que las dos herramientas se midan exactamente igual.

> **Corrida vigente: 2026-11-13.** Es la segunda versión de la medición: además del total de cada fase, ahora se registra lo que pasa **durante** la ejecución (sección 6.2). Los 17 veredictos fueron idénticos a los de la corrida del 2026-10-30.

### 6.1 Cómo se midió

- **`OfflineEmissionsTracker`** de CodeCarbon, con `country_iso_code="COL"`. El modo *offline* no consulta servicios web para geolocalizar la máquina. Usa el factor de emisión de la red eléctrica de **Colombia según los datos de CodeCarbon: 259,5 gCO₂eq/kWh** (año 2023; la matriz es 66 % renovable, sobre todo hidroeléctrica). Se puede cambiar con `--pais`.
- **Dos trackers en paralelo** en cada fase:
  - **Máquina** (`tracking_mode="machine"`): toda la computadora, incluido el consumo de fondo del sistema y de otras aplicaciones abiertas (VS Code, navegador).
  - **Proceso** (`tracking_mode="process"`): solo el proceso de Python del experimento y sus hijos (pytest). Es **lo atribuible a Rope y a los tests**.
- **Qué se mide en cada refactorización:** (a) **la operación de Rope** (abrir el proyecto, calcular y aplicar los cambios), 5 veces, cada una sobre una copia nueva y **sin incluir el tiempo de copiar** el repositorio; y (b) **la verificación con pytest** (una vez).
- **Muestreo cada 0,25 s** (`measure_power_secs=0.25`) en cada fase, y cada 1 s en el tracker del experimento completo.

**Limitación importante: es una estimación, no una medición física.** El Apple M4 no expone sus sensores de energía sin permisos de administrador (`sudo powermetrics`), así que CodeCarbon usa el modo **`cpu_load`**: estima la potencia de la CPU a partir de su **TDP** (20 W para el M4 según la tabla de CodeCarbon) y del **porcentaje de carga**. En modo máquina usa `potencia = TDP × (0,1 + 0,9 × carga³)`, y en modo proceso, `potencia = TDP × carga del proceso`. La RAM se estima con un modelo fijo (3 W para 16 GB). Los números sirven para **comparar fases entre sí** y para dar un **orden de magnitud**, no como valores absolutos exactos.

### 6.2 Medición durante la ejecución

CodeCarbon normalmente entrega un solo número al terminar (`tracker.stop()`). Para ver lo que pasa **mientras** Rope trabaja, se usa la vía oficial de CodeCarbon para salidas en vivo: un *output handler* propio (subclase de `BaseOutput` con el método `live_out`) y `api_call_interval=1`, con lo que CodeCarbon entrega cada muestra apenas la toma. Eso genera tres archivos:

| Archivo | Qué contiene |
|---|---|
| `serie_temporal_maquina.csv`, `serie_temporal_proceso.csv` | Una fila por muestra (cada 0,25 s): fase, segundos desde el inicio de la fase, hora, energía de la muestra, energía acumulada, **potencia media de la muestra** (W) y emisiones acumuladas. 2265 muestras en esta corrida |
| `eventos.csv` | Momentos marcados dentro de cada operación de Rope: `proyecto_abierto`, `cambios_calculados`, `cambios_aplicados` o `error`. Sirven para ubicar en la serie temporal qué estaba haciendo Rope |
| `emisiones_maquina.csv`, `emisiones_proceso.csv` | El CSV estándar de CodeCarbon, una fila por fase (el total al terminar) |

Ejemplo (caso 02, una repetición, modo proceso): Rope abre el proyecto al instante, tarda **1,19 s en calcular** los cambios (recorre todo el proyecto buscando usos) y **0,25 s en aplicarlos**. Durante ese tiempo el proceso consume **~11 W**, un núcleo de CPU trabajando al máximo. En reposo, el mismo tracker marca ~3,6 W.

Cada operación de Rope quedó cubierta por entre 5 muestras (las que Rope rechaza en 0,05 s) y 25 (el Rename de 02, ~1,8 s).

**Costo de medir más seguido:** con 4 trackers muestreando a la vez (2 de la fase y 2 del experimento completo), las operaciones de Rope tardaron en promedio **0,9 s en vez de 0,8 s** (+14 %) respecto de la corrida con una muestra por segundo. Ese trabajo extra de medición queda incluido en el modo proceso.

### 6.3 Resultados

Unidades: **mWh** (milivatios-hora; 1 Wh = 1000 mWh) y **mg CO₂eq** (miligramos de CO₂ equivalente).

**Fases de referencia:**

| Fase | Duración | Energía máquina | Emisiones máquina | Energía proceso | Emisiones proceso |
|---|---|---|---|---|---|
| Reposo (no hacer nada) | 30 s | 99,1 mWh | 25,7 mg | 29,8 mWh | 7,7 mg |
| Línea base: una corrida de pytest | 27 s | 88,0 mWh | 22,9 mg | 81,3 mWh | 21,1 mg |
| Análisis estático con Rope | 4,6 s | 17,6 mWh | 4,6 mg | 13,9 mWh | 3,6 mg |
| **Experimento completo** | **7 min 42 s** | **1643 mWh** | **426 mg** | **1445 mWh** | **375 mg** |

**Rope frente a la verificación con tests:**

| Concepto | Tiempo | Energía proceso | Emisiones proceso |
|---|---|---|---|
| Aplicar las 17 refactorizaciones con Rope (una vez cada una) | 15,3 s | **48,1 mWh** | **12,5 mg** |
| Una operación de Rope, en promedio | 0,9 s | 2,8 mWh | 0,73 mg |
| Verificar con pytest las 14 refactorizaciones aplicadas | ~6 min | **1046 mWh** | **271 mg** |
| Una corrida de pytest, en promedio | 25 s | 75 mWh | 19,4 mg |

**Por operación de Rope** (media de 5 repeticiones, modo proceso): de **0,03 mWh** (06 y 09, que Rope rechaza en menos de 0,1 s) a **6,7 mWh** (03, Rename que también actualiza los tests). Los Extract Method son baratos (0,1–0,3 mWh) porque solo analizan un archivo. Los Rename, Inline y Move recorren todo el proyecto y cuestan entre 3,1 y 6,7 mWh.

### 6.4 Interpretación

1. **Aplicar una refactorización con Rope es casi gratis en energía.** Una operación promedio emite unos **0,73 mg de CO₂eq** y tarda menos de un segundo. Todo lo que hizo Rope en el experimento (12,5 mg) equivale a lo que la máquina consume **en unos 15 s de reposo** (modo máquina).
2. **Lo caro es verificar.** Correr la suite para comprobar cada refactorización consume **unas 26 veces más energía** que aplicarla (75 frente a 2,8 mWh por caso). Como Rope falla en silencio en varios casos (04, 10b, 13, 15), esa verificación **no es opcional**: el costo real de refactorizar con Rope de forma segura está dominado por los tests.
3. **Durante la ejecución, Rope es intensivo pero breve:** usa un núcleo al máximo (~11 W en modo proceso) durante 1 a 2 s. Es el perfil opuesto al de Claude, donde la computadora espera casi en reposo durante minutos (ver [`../llm_pruebas/README.md`](../llm_pruebas/README.md), sección 6).
4. **El experimento completo emitió 0,38 g de CO₂eq** atribuibles al proceso (0,43 g contando toda la máquina).
5. **Precisión de las operaciones cortas.** Las operaciones de ~1 s tienen una desviación estándar alta (por ejemplo 4,1 ± 3,4 mWh en 04), porque algunas repeticiones tardan bastante más que otras (caché del sistema de archivos, recolección de basura). Por eso se repitió cada operación 5 veces y se informa la media. Con el muestreo cada 0,25 s, las operaciones de ~0,05 s ya no quedan en 0, pero siguen siendo la medición menos precisa.
6. **Variación entre corridas:** la corrida del 2026-10-30 (muestreo cada 1 s) dio 2,4 mWh por operación y 68 mWh por pytest. La de hoy, 2,8 y 75 mWh. Las diferencias (~15 %) son del orden de la variabilidad entre repeticiones, así que conviene citar estos números como orden de magnitud.

---

## 7. Conclusiones

1. **Sin configuración, Rope no funciona en Black** (sección 4.1). Por el src layout hay que indicar `source_folders=['src']`. Si no, Rope produce Renames incompletos **sin avisar**. Además hace falta `ignore_syntax_errors=True`, como en Cookiecutter.
2. **Rename de funciones y clases es confiable cuando todas las referencias son código Python estático:** 02, 03 y 05 preservaron el comportamiento, incluidos los usos a través del re-export `black.lib2to3_parse`.
3. **La inferencia de tipos de Rope es limitada.** No encuentra llamadas a métodos sobre objetos devueltos por un `@classmethod` con `Self` (04) y no reconoce los parámetros keyword-only (06, y 176 avisos de `find_errors`). En un código moderno y muy anotado como Black, estas dos limitaciones pesan más que en PySnooper o Cookiecutter.
4. **Extract Method tiene tres limitaciones nuevas en Black:** se cae con f-strings que contienen variables (10, bug interno), ignora los imports locales (10b, `NameError` silencioso) y no agrega anotaciones de tipo. Los casos con flujo de datos simple (07 y 08, incluso con 2 valores de salida) funcionan.
5. **Las referencias dinámicas siguen siendo el punto ciego del análisis estático:** strings de `mock.patch` (13), métodos elegidos con `getattr` (15) y nombres que son parte de la configuración pública (16). Rope aplica el cambio sin avisar y solo los tests revelan el problema, y en 16 ni siquiera los tests ven el JSON schema desactualizado.
6. **`docs=True` ayuda con los mocks por string solo a veces** (14): funciona si el string empieza por un nombre importado en ese archivo (`import black`), y no en el caso de Cookiecutter.
7. **Rope no respeta el estilo del proyecto:** una línea en blanco en vez de dos, imports fusionados en líneas de 260 caracteres, comentarios borrados (12). Black es el único de los tres proyectos con un test que lo detecta (`test_piping`). **Después de Rope hay que pasar un formateador** (en este caso, el propio Black).
8. **`find_errors` vuelve a tener 100 % de falsos positivos** (852/852), y la mitad (416) se debe a atributos creados dinámicamente con `setattr`.
9. **Huella de carbono:** aplicar una refactorización con Rope cuesta unos 2,8 mWh (0,73 mg CO₂eq); verificarla con la suite cuesta unas 26 veces más (75 mWh, 19,4 mg). El experimento completo emitió 0,38 g de CO₂eq atribuibles.

### Comparación con PySnooper y Cookiecutter

| | PySnooper | Cookiecutter | Black |
|---|---|---|---|
| Tamaño | 964 líneas, 5 módulos, 83 tests | 2806 líneas, 18 módulos, 379 tests | ~16 400 líneas, 25 módulos, 743 tests |
| Casos equivalentes (02–12) que preservan | 8/11 (73 %) | 8/11 (73 %) | **4/11 (36 %)**; 7/11 (64 %) ignorando el formato |
| Rename (02–06) | 5/5 | 5/5 | 3/5 (04 rompe, 06 rechazada) |
| Extract Method (07–10) | 1/4 | 2/4 (+1 rechazada) | 0/4 estricto; 2/4 ignorando el formato (+2 rechazadas) |
| Inline (11) | 1/1 | 0/1 | 1/1 |
| Move (12) | 1/1 | 1/1 | 0/1 estricto; 1/1 ignorando el formato |
| Causa principal de los fallos | `.format(**locals())` en el código | mocks por string; flujo de datos | inferencia de tipos (`Self`, keyword-only); referencias dinámicas (`getattr`, mocks, docs/JSON); estilo |
| Falsos positivos de `find_errors` | 31/31 | 39/39 | 852/852 |
| Obstáculo de configuración | — | archivos `.py` que son plantillas Jinja | src layout + archivos `.py` inválidos en `tests/data` |
| `docs=True` arregla los mocks por string | — | No | **Sí** |
| Huella de carbono medida | — | — | 0,73 mg CO₂eq por operación de Rope |

---

## 8. Cómo agregar una refactorización nueva

En `ejecutar_pruebas_rope.py`:

1. Escribe una función que reciba el proyecto Rope `p` y devuelva los cambios:

   ```python
   def ref_mi_prueba(p):
       r = p.get_resource('src/black/strings.py')
       offset = offset_de(r, 'def normalize_string_quotes', 4)   # apunta al nombre
       return Rename(p, r, offset).get_changes('normalize_quotes')
   ```

   - `offset_de(recurso, marcador, desplazamiento)` busca un texto **único** en el archivo y devuelve su posición. El desplazamiento mueve el cursor hasta el nombre (`'def '` = 4, `'class '` = 6, `'    def '` = 8).
   - Para Extract Method se necesita un rango `(inicio, fin)`. Ver `ref_extract_cache` como ejemplo (`inicio_de_linea` y `linea_anterior` ayudan a calcularlo).
   - **Las rutas empiezan por `src/`** (`src/black/...`), por el src layout.

2. Agrégala a la lista `REFACTORIZACIONES`:

   ```python
   ('17_mi_prueba', 'Rename', 'normalize_string_quotes -> normalize_quotes', ref_mi_prueba),
   ```

3. Vuelve a correr el script. La fila nueva aparece en `resultados/resumen.md` y en `resultados/carbono/huella_carbono.md`.

Opciones de Rope y de CodeCarbon usadas, además de las de PySnooper y Cookiecutter:

| Opción | Dónde | Para qué |
|---|---|---|
| `source_folders=['src']` | `Project(ruta, source_folders=['src'])` | Proyectos con src layout: que Rope encuentre el paquete dentro del proyecto |
| `ignore_syntax_errors=True` | `Project(ruta, ignore_syntax_errors=True)` | Ignorar archivos `.py` que no son Python válido |
| `docs=True` | `Rename(...).get_changes('nuevo', docs=True)` | Renombrar en strings y comentarios, **solo donde el nombre es visible** |
| `OfflineEmissionsTracker(country_iso_code=...)` | `medir()` en el script | Medir sin conexión, con el factor de emisión de un país |
| `tracking_mode='machine' / 'process'` | `MODOS` en el script | Toda la máquina, o solo el proceso y sus hijos |
| `allow_multiple_runs=True` | `medir()` | Permitir trackers simultáneos (el del experimento completo y el de cada fase) |

# Pruebas de Black con un LLM (prompt general) y su huella de carbono

Este documento describe el proceso completo: qué se probó, cómo reproducirlo, qué resultados se obtuvieron, cómo interpretarlos y cómo se comparan con las pruebas de Rope ([`../rope_pruebas/`](../rope_pruebas/README.md)). Es la tercera réplica del experimento, después de PySnooper (`../PySnooper_tesis/llm_pruebas/`) y Cookiecutter (`../cookiecutter_tesis/llm_pruebas/`).

- **Proyecto bajo prueba:** Black (commit `408211f4`), paquete `src/black/` (24 módulos, ~16 400 líneas).
- **Modelo:** **Claude Sonnet 5.5** (`claude-sonnet-5-5`), effort `high`, API de Anthropic (SDK `anthropic` 1.x). En PySnooper y Cookiecutter se usó Opus 5.5; aquí se eligió Sonnet 5.5 para que alcanzara el presupuesto de tokens (ver 1.1).
- **Medición de carbono:** CodeCarbon 3.3.2, durante y al final de cada llamada (módulo compartido [`../huella_carbono/medicion.py`](../huella_carbono/medicion.py)).
- **Entorno:** Python 3.12.15, pytest 9.2.0, macOS 15.6.1, Apple M4 (10 núcleos, 16 GB).
- **Fecha de ejecución:** 2026-11-13.
- **Ejecución principal:** [`resultados/20261113_095503/`](resultados/20261113_095503/) (27 corridas: 9 módulos × 3).
- **Piloto:** [`resultados/20261113_094656/`](resultados/20261113_094656/) (1 corrida de `cache`).

---

## 1. Objetivo y diferencia con Rope

Las preguntas son:

1. **Cuando un LLM refactoriza Black por su cuenta, ¿conserva el comportamiento? ¿Qué refactorizaciones elige?**
2. **¿Cuánta energía consume y cuánto CO₂ emite, medido durante la ejecución y no solo al final?**

| | Rope | LLM |
|---|---|---|
| ¿Quién decide qué refactorizar? | La persona (offset + nombre nuevo) | **El modelo** |
| ¿Quién ejecuta el cambio? | Rope | El modelo |
| Instrucción | Una refactorización concreta por prueba (17 en total) | **Un único prompt general**, igual para todos los módulos |
| Determinismo | Total (5 repeticiones, mismo diff) | No: el mismo prompt da resultados distintos |
| Dónde se gasta la energía | En esta computadora | Sobre todo en los servidores de Anthropic (no medible desde aquí, ver 6) |

### 1.1 Modelo: Sonnet 5.5 en vez de Opus 5.5

El contexto de Black es mucho más grande que el de los otros proyectos (**216 616 tokens** por llamada, contra ~34 500 en Cookiecutter), y para varios módulos hay que devolver archivos de 3000 líneas. Para que alcanzara el presupuesto de tokens se usó **Sonnet 5.5**, que cuesta la mitad que Opus 5.5 (US$ 2 / US$ 10 por millón de tokens de entrada y salida, frente a US$ 4 / US$ 20). **Esto es una diferencia de método con PySnooper y Cookiecutter** y hay que tenerla en cuenta al comparar los tres proyectos.

### 1.2 Alcance: los 9 módulos que tocó Rope

Antes de la corrida principal, `--dry-run` estimó el costo con `count_tokens` (gratis):

| Alcance | Llamadas | Costo mínimo estimado (sin razonamiento) |
|---|---|---|
| Los 24 módulos × 3 | 72 | US$ 10,42 |
| **Los 9 módulos de Rope × 3** | **27** | **US$ 6,00** |
| Los 9 sin `linegen` ni `trans` × 3 | 21 | US$ 3,38 |

Con el costo real del piloto (los tokens de razonamiento sumaron ~1,7 veces el tamaño del archivo), se eligió **los 9 módulos que modificaron las refactorizaciones de Rope** (`__init__`, `parsing`, `ranges`, `cache`, `trans`, `output`, `files`, `linegen`, `mode`), porque son los que permiten comparar caso a caso. Es el mismo criterio que se usó en Cookiecutter para dejar fuera `zipfile`.

---

## 2. Metodología

Es la misma que en PySnooper y Cookiecutter, con los cambios marcados como **(nuevo)**.

1. **Prompt fijo y versionado:** [`prompt_v1.md`](prompt_v1.md), **idéntico al de los otros dos proyectos salvo por la palabra "Black"** (verificado con `diff`). Pide mejorar legibilidad y mantenibilidad sin cambiar el comportamiento, sin cambiar nombres ni firmas públicas, sin agregar funcionalidades ni dependencias, modificando solo el archivo indicado y manteniendo la compatibilidad con las versiones de Python soportadas. También pide devolver el archivo completo y una lista de refactorizaciones según el catálogo de Fowler.
2. **Contexto:** en cada llamada el modelo recibe **los 24 módulos de `src/black/`** (216 616 tokens) como contexto de solo lectura, más `Refactoriza el archivo src/black/<modulo>.py`.
3. **Caché de prompts (nuevo: TTL de 1 hora).** El contexto es idéntico en todas las llamadas y se guarda en caché. Se usó el TTL de 1 hora en vez del de 5 minutos porque una respuesta larga más su corrida de pytest puede superar los 5 minutos, y reescribir 216 616 tokens cuesta ~US$ 0,87.
4. **Repeticiones:** 3 corridas por módulo. Sonnet 5.5 no acepta `temperature`, así que la variabilidad se mide repitiendo.
5. **Evaluación:**
   - se aplica el archivo devuelto sobre una **copia limpia** del proyecto;
   - se guarda el diff;
   - se compara la API pública con `ast` (nombres públicos y firmas);
   - se corre la suite completa (743 tests).

   Si pasan los mismos tests que en la línea base, sin fallos ni errores, el veredicto es **comportamiento preservado**.
6. **Verificación de formato (nuevo).** Si el único test que falla es `test_piping` (exige que `src/black/__init__.py` esté formateado con Black), se pasa `black --config tests/empty.toml` por el archivo y se vuelve a correr la suite. Si entonces pasa todo, el veredicto es **rompe tests (solo formato)**. Es el mismo control que se hizo con Rope ([`../rope_pruebas/verificar_formateo.py`](../rope_pruebas/verificar_formateo.py)).
7. **Huella de carbono (nuevo):** ver sección 6.

> El código original en `src/` **nunca se modifica**. Cada ejecución se guarda en su propia carpeta `resultados/<fecha_hora>/`.

### 2.1 Incidencias durante la ejecución

Se documentan todas porque afectan la lectura de los resultados.

**1. Error en el extractor de código (corregido sin volver a llamar a la API).** El script de Cookiecutter extraía el código de la respuesta con una expresión regular que aceptaba cercas ```` ``` ```` en cualquier posición. `src/black/trans.py` tiene **ejemplos en Markdown dentro de sus docstrings**, con ```` ``` ```` indentados (líneas 332–343 y 2635–2649). La expresión cortaba la respuesta ahí y se quedaba con un pedazo del medio del archivo (2283 de ~2900 líneas), que empezaba con un `"""` indentado. Por eso las 3 corridas de `trans` aparecieron primero como `IndentationError`.

- **Corrección:** ahora las cercas tienen que empezar en la columna 0 (`extraer_codigo`). Se verificó que con el extractor nuevo **solo cambian las 3 corridas de `trans`**; las otras 24 extraen exactamente el mismo código.
- **Reevaluación:** se agregó `--reevaluar CARPETA CORRIDA...`, que vuelve a extraer el código de las respuestas guardadas (`<corrida>_respuesta.md`) y repite los tests **sin llamar a la API**. Cada fila reevaluada guarda en `resumen.json` el campo `reevaluacion` con la fecha, el motivo y el resultado anterior.
- **¿Afecta a PySnooper o Cookiecutter?** No: ninguno de los dos tiene ```` ``` ```` en su código (verificado con `grep`).

**2. Verificación de formato con la configuración equivocada (corregido).** La primera versión de la verificación de formato ejecutaba `black` desde la carpeta del proyecto, así que tomaba el `pyproject.toml` de Black, que usa **`unstable = true`** (Black se formatea a sí mismo con su estilo inestable). Pero `test_piping` usa el estilo **estable** (`--config tests/empty.toml`). Claude escribió construcciones como `frozenset({...})`, que los dos estilos formatean distinto, así que el archivo seguía sin pasar `test_piping`. Se corrigió para formatear con `--config tests/empty.toml`, igual que el test, y se reevaluaron las 3 corridas de `__init__` con `--reevaluar`. La misma corrección se aplicó al script de Rope (sus 4 casos dan igual con las dos configuraciones).

**3. El Mac se quedó sin batería dos veces.** La corrida empezó con el equipo desconectado. `pmset -g log` muestra que a las **10:00** y a las **12:03** entró en hibernación por batería al **1 %** (`Low Power Sleep`), y que despertó al conectarse el cargador (11:01 y 13:52). `caffeinate` no puede impedir una suspensión por batería agotada. Consecuencias:

- **Las 27 llamadas a Claude no se vieron afectadas:** las dos suspensiones ocurrieron después de recibir una respuesta completa (`stop_reason = end_turn`, `intentos = 1`).
- **Dos mediciones de pytest quedaron contaminadas** por la suspensión y el despertar: la de `__init___run1` (64 s en vez de ~25 s) y la de `linegen_run3` (53 s). Sus veredictos son válidos, pero **esas dos mediciones de energía no son confiables**. Después se reevaluó `__init___run1` y su medición vigente es la nueva.
- **Dos escrituras de caché extra:** como las pausas superaron 1 hora, la caché del contexto venció y `__init___run2` y `mode_run1` la volvieron a escribir (~US$ 0,87 cada una, unos US$ 1,75 en total).

**Recomendación para repetir el experimento:** dejar el equipo **conectado a la corriente**, con la tapa abierta, y lanzar el script con `caffeinate -dimsu`.

---

## 3. Cómo ejecutarlo

Requiere una API key de Anthropic en `ANTHROPIC_API_KEY` (en este equipo está en `~/.zshrc`).

```bash
# ver el prompt y estimar el costo, sin generar nada (count_tokens es gratis)
.venv/bin/python llm_pruebas/ejecutar_pruebas_llm.py --dry-run --modulos __init__ parsing ranges cache trans output files linegen mode

# la ejecución que se usó en la tesis (~1 h de API, ~US$ 9)
caffeinate -dimsu .venv/bin/python -W ignore llm_pruebas/ejecutar_pruebas_llm.py \
    --corridas 3 --modulos __init__ parsing ranges cache trans output files linegen mode

# repetir la evaluación de corridas ya pagadas (sin llamar a la API)
.venv/bin/python llm_pruebas/ejecutar_pruebas_llm.py --reevaluar 20261113_095503 trans_run1 trans_run2 trans_run3

# continuar una ejecución interrumpida
.venv/bin/python llm_pruebas/ejecutar_pruebas_llm.py --reanudar 20261113_095503 --modulos ...
```

Opciones: `--modelo` (por defecto `claude-sonnet-5-5`), `--effort` (`high`), `--corridas` (3), `--modulos`, `--pais` (`COL`).

### Estructura de archivos

```
llm_pruebas/
├── README.md                       ← este documento
├── prompt_v1.md                    ← prompt de sistema (idéntico al de PySnooper y Cookiecutter salvo "Black")
├── ejecutar_pruebas_llm.py         ← script (llamadas, evaluación, reevaluación, carbono)
├── .gitignore                      ← ignora _trabajo/
├── _trabajo/                       ← copias del proyecto, una por corrida (temporal)
└── resultados/<fecha_hora>/
    ├── prompt.md                   ← copia del prompt usado
    ├── resumen.md / resumen.json   ← tabla y todos los datos (tokens, costo, tests, carbono, reevaluaciones)
    ├── 00_linea_base_pytest.txt
    ├── <modulo>_runN_respuesta.md  ← respuesta completa del modelo (código + refactorizaciones aplicadas)
    ├── <modulo>_runN.py            ← archivo extraído
    ├── <modulo>_runN.diff          ← diff contra el original
    ├── <modulo>_runN_pytest.txt    ← salida de pytest
    ├── <modulo>_runN_formateado_pytest.txt   ← salida tras `black`, si solo fallaba test_piping
    └── carbono/
        ├── huella_carbono.md       ← tablas de energía y emisiones
        ├── serie_temporal_maquina.csv / serie_temporal_proceso.csv  ← muestras cada 0,25 s DURANTE cada fase
        ├── eventos.csv             ← momentos del streaming de cada llamada
        └── emisiones_maquina.csv / emisiones_proceso.csv  ← CSV estándar de CodeCarbon, una fila por fase
```

---

## 4. Resultados

### 4.1 Línea base

**743 passed / 0 failed / 2 skipped** (igual que en `rope_pruebas/`).

### 4.2 Resultados por módulo (3 corridas cada uno)

| Módulo | Tamaño | Veredicto de las 3 corridas | Líneas +/− (media) | Tiempo de respuesta (media) | Tokens de salida (media) | Costo (3 corridas) |
|---|---|---|---|---|---|---|
| `__init__` | 1955 líneas | 🎨 🎨 🎨 solo formato | +833 / −541 | 242 s | 44 354 | US$ 2,28 |
| `parsing` | 295 | ✅ ✅ ✅ | +126 / −90 | 47 s | 7 599 | US$ 0,36 |
| `ranges` | 783 | ✅ ✅ ✅ | +304 / −221 | 116 s | 19 195 | US$ 0,71 |
| `cache` | 157 | ✅ ✅ ✅ | +47 / −37 | 29 s | 4 469 | US$ 0,26 |
| `trans` | 2849 | ✅ ✅ ✅ | +484 / −354 | 296 s | 51 373 | US$ 1,67 |
| `output` | 135 | ✅ ✅ ✅ | +46 / −25 | 26 s | 4 226 | US$ 0,26 |
| `files` | 466 | ✅ ✅ ✅ | +104 / −65 | 55 s | 10 041 | US$ 0,43 |
| `linegen` | 3001 | ✅ ✅ ✅ | +811 / −647 | 312 s | 60 867 | US$ 1,96 |
| `mode` | 377 | ✅ ✅ ✅ | +94 / −183 | 47 s | 7 491 | US$ 1,18* |

\* Incluye una reescritura de caché por la segunda suspensión del equipo (2.1). Lo mismo pasa con `__init__`.

**Totales:**

- **24 de 27 corridas (89 %) pasan los 743 tests** tal como las devuelve el modelo.
- **Las 3 restantes (`__init__`) fallan solo `test_piping`.** Después de `black --config tests/empty.toml`, pasan 743/0. **Ninguna de las 27 corridas cambió el comportamiento de Black.**
- **Ninguna corrida cambió la API pública** (verificación automática con `ast`).
- **Ningún rechazo, ninguna respuesta truncada** (`stop_reason = end_turn` en las 27), y **ningún fallback**: todas las respondió `claude-sonnet-5-5`.
- **No determinista:** las 3 corridas de cada módulo dieron **3 diffs distintos** en los 9 módulos.
- **Costo:** US$ 9,11 la corrida principal + US$ 0,92 el piloto = **US$ 10,03**. Tokens: 628 854 de salida (incluido el razonamiento) y 5,85 millones de entrada, casi todos leídos desde la caché.

### 4.3 El problema de formato de `__init__`

Las 3 corridas de `__init__` reescriben unas 1300 líneas del archivo y dejan construcciones como esta:

```python
_LINE_GENERATION_FEATURE_CANDIDATES = frozenset({
    Feature.PARENTHESIZED_CONTEXT_MANAGERS,
    ...
})
```

Ese es el formato del **estilo inestable** de Black ("abrazar" los paréntesis), el mismo con que Black se formatea a sí mismo (`unstable = true` en `pyproject.toml`). Pero `test_piping` formatea `__init__.py` con el **estilo estable**, que pide `frozenset(\n    {\n ...}\n)`. Es decir, el modelo imitó el estilo que veía en el código, pero ese estilo no es compatible con el test. Con Rope pasó lo mismo por motivos distintos (una línea en blanco en vez de dos, imports en una sola línea). En ambos casos se resuelve pasando `black` con la configuración del test.

### 4.4 Qué refactorizaciones eligió el modelo

Conteo automático de las listas "Refactorizaciones aplicadas" de 25 de las 27 respuestas (264 entradas). Las otras dos (`__init___run2` y `linegen_run2`) presentan esa sección como tabla en vez de lista y no entran en el conteo. Una entrada puede combinar varias refactorizaciones (por ejemplo "Extract Method + Decompose Conditional"), así que la suma supera el total:

| Refactorización (Fowler) | Entradas que la mencionan |
|---|---|
| **Extract Method / Extract Function** | **153** |
| Remove Duplicated Code | 21 |
| Replace Magic Literal / Introduce Constant | 16 |
| Decompose Conditional | 14 |
| Rename Variable | 14 |
| Consolidate (Duplicate) Conditional | 13 |
| Replace Nested Conditional with Guard Clauses | 9 |
| Remove Dead Code | 7 |
| Introduce Explaining Variable | 6 |
| Inline Temp / Inline Variable | 6 |
| Move Function / Method (dentro del mismo archivo) | 4 |
| Substitute Algorithm | 4 |
| Introduce Type Alias | 2 |

Igual que en PySnooper y Cookiecutter, el modelo eligió **casi siempre Extract Method**. **Nunca renombró nada público** (el prompt lo prohíbe) **ni movió código a otro archivo** (el prompt pide modificar solo el archivo indicado). Por eso los Rename públicos y el Move de Rope no tienen equivalente aquí.

---

## 5. Comparación caso a caso con Rope

| Caso de Rope | Qué hizo Rope | Qué hizo Claude en el mismo lugar |
|---|---|---|
| **07** Extract del bloque de caché en `reformat_one` | ✅ correcto, pero sin tipos y con 1 línea en blanco | **Lo extrajo en las 3 corridas** (`_read_cache`), con anotaciones de tipo y retornos tempranos: `def _read_cache(mode: Mode, no_cache: bool, cache_dir: Path \| None) -> Cache \| None` |
| **08** Extract con 2 salidas (detección de stdin) | ✅ correcto (`is_stdin, src = _detect_stdin(src)`) | **Lo extrajo en las 3 corridas** (`_detect_stdin_source` / `_resolve_stdin_source`), con la misma firma de 2 valores de salida y tipada: `-> tuple[bool, Path]` |
| **09** Extract de un bloque con `continue` | ⛔ Rope se niega | **Lo hizo en las 3 corridas**, transformando el `continue`: el helper devuelve `None` y el bucle hace `if resolved is None: continue` (corrida 2) |
| **10** Extract del bucle con f-strings | ⛔ Rope se cae (bug con `{${path}}`) | **Partió el bucle en 2–3 helpers** (`_checked_file_source`, `_gen_directory_sources`, `_source_root`...) con los f-strings intactos. Todos los tests pasan |
| **10b** Extract del bucle de `output.diff` | ❌ olvida el `import difflib` local | **No tocó `diff()`** en ninguna corrida: el `import difflib` sigue en su lugar |
| **04** Rename de `Cache.is_changed` | ❌ no encuentra las llamadas (44 fallos) | No lo renombró (es público). Lo simplificó por dentro con cláusulas de guarda |
| **11** Inline de `_splitlines_no_ff` | ✅ | No lo tocó (sigue en las 3 corridas) |
| **15** Rename de `visit_suite` (despacho con `getattr`) | ❌ Black formatea distinto | No renombró ningún `visit_*`. Extrajo helpers que empiezan con `_visit_` (`_visit_fstring_or_tstring`...), que el despacho no toma. Las respuestas no lo mencionan, así que no se sabe si fue intencional |
| **16** Rename de una opción `Preview` | ❌ desactualiza docs y JSON | No cambió el enum `Preview`. Sí reescribió la tabla `VERSION_TO_FEATURES` de `mode.py` derivándola versión por versión (−183 líneas), y los tests pasan |

**Lectura:** en los lugares donde Rope falló por **flujo de control** (09), por un **bug propio** (10) o por **formato**, Claude aplicó la misma refactorización correctamente. En los lugares donde Rope falló por **referencias dinámicas** (04, 13, 15, 16), Claude **no se expuso**: el prompt le prohíbe cambiar nombres públicos, y esos casos eran justamente Renames públicos. Es la misma conclusión que en PySnooper (`.format(**locals())`) y Cookiecutter: **el modelo evita los cambios peligrosos; Rope los aplica si se le piden.** La comparación no es simétrica: a Rope se le pidieron refactorizaciones concretas, algunas difíciles a propósito, y al modelo no.

---

## 6. Huella de carbono

### 6.1 Qué se mide y qué no

**CodeCarbon solo puede medir esta computadora.** En una llamada a Claude, el trabajo pesado (procesar 216 616 tokens de contexto y generar la respuesta) ocurre en los servidores de Anthropic. Lo que se mide aquí es **el costo local de esperar la respuesta**: el proceso de Python con la conexión abierta recibiendo el streaming, más el fondo del sistema.

Para que la comparación con Rope sea justa, las dos herramientas se miden con **el mismo módulo** ([`../huella_carbono/medicion.py`](../huella_carbono/medicion.py)): mismos dos modos (máquina y proceso), mismo país (Colombia, 259,5 gCO₂eq/kWh), mismo muestreo cada 0,25 s, misma estimación `cpu_load` (sin sensores físicos en el M4; ver `../rope_pruebas/README.md`, 6.1).

**Para estimar la energía de los servidores** se guardan los tokens de cada llamada en `resumen.json` (`tokens.input`, `output`, `cache_read`, `cache_write`). No se incluye una estimación en este documento porque requiere elegir una fuente publicada de energía por token. Queda pendiente para la tesis.

### 6.2 Medición durante la ejecución

Además del total de cada fase, se guarda una muestra cada 0,25 s (`serie_temporal_*.csv`) y estos eventos del streaming (`eventos.csv`):

| Evento | Cuándo |
|---|---|
| `peticion_enviada` | Se abre la conexión de streaming |
| `primer_evento` | Llega el primer evento (`message_start`) |
| `inicio_pensamiento` | Empieza el bloque de razonamiento (`thinking`) |
| `inicio_text` | Empieza el texto de la respuesta (el código) |
| `fin_respuesta` | Termina el mensaje (con su `stop_reason`) |
| `error_de_red` | Si hubo que reintentar (no ocurrió) |

Tiempos típicos: el primer evento llega en **1–8 s**. El modelo razona en silencio hasta que empieza el texto: **10–20 s** en los módulos chicos y **65–130 s** en `__init__`, `trans` y `linegen`. Después escribe el archivo completo.

### 6.3 Resultados

**Fases de referencia (misma corrida):**

| Fase | Duración | Energía máquina | Energía proceso | Potencia media proceso |
|---|---|---|---|---|
| Reposo (no hacer nada) | 30 s | 96,1 mWh | 30,2 mWh | 3,62 W |
| Línea base: una corrida de pytest | 27 s | 93,1 mWh | 81,9 mWh | ~11 W |

**Llamadas a Claude (27 corridas):**

| Concepto | Valor |
|---|---|
| Tiempo total esperando respuestas | 3513 s (58,5 min) |
| Energía local, modo proceso | **3549 mWh** (921 mg CO₂eq): 879 mWh de CPU y 2669 mWh del modelo fijo de RAM |
| Energía local, modo máquina | **11 278 mWh** (2927 mg CO₂eq) |
| Potencia media durante la espera | **3,64 W (proceso)** y 11,56 W (máquina) |
| Por llamada, en promedio | 130 s, **131 mWh** (34 mg) en modo proceso |
| Verificar con pytest (27 corridas) | 2029 mWh (proceso) |

**Por módulo (media de 3 corridas, modo proceso):** de 27 mWh / 7 mg (`output`, 26 s) a 320 mWh / 83 mg (`linegen`, 312 s). La energía es casi exactamente proporcional al tiempo de espera, porque la potencia es constante.

### 6.4 Interpretación

1. **Mientras espera a Claude, la computadora está prácticamente en reposo.** La potencia media durante las llamadas (3,64 W en modo proceso, 11,56 W en modo máquina) es la misma que en reposo (3,62 W y 11,5 W). El proceso de Python solo recibe texto por la red. **La medición local no captura el costo real del LLM**, que está en el centro de datos.
2. **La mayor parte de lo que se "mide" en modo proceso es el modelo fijo de RAM de CodeCarbon** (3 W constantes, el 75 %). Solo 0,9 W corresponden a CPU. Por eso la energía local de una llamada depende casi solo de **cuánto tarda**, no de cuánto trabaja.
3. **Rope y Claude tienen perfiles opuestos** (con el mismo método de medición):

   | | Rope | Claude (solo lo local) |
   |---|---|---|
   | Duración por operación | ~0,9 s | ~130 s |
   | Potencia del proceso | **~11 W** (un núcleo al máximo) | **~3,6 W** (en reposo) |
   | Energía local por operación | **2,8 mWh** (0,73 mg) | **131 mWh** (34 mg) |
   | Dónde está el resto del costo | — (todo es local) | En los servidores (no medido) |
   | Costo económico por operación | 0 | ~US$ 0,34 |

   Aun midiendo solo la espera local, una llamada a Claude consume **unas 47 veces más energía local** que una operación de Rope, simplemente porque tarda ~140 veces más.
4. **Verificar sigue siendo necesario y cuesta lo mismo con las dos herramientas:** ~75 mWh por corrida de pytest. Con Rope, la verificación es la mayor parte del costo local (26 veces la refactorización). Con Claude, la espera local ya supera a la verificación (131 frente a 75 mWh por corrida), sin contar los servidores.

---

## 7. Conclusiones

1. **Claude Sonnet 5.5 preservó el comportamiento en las 27 corridas.** 24 pasan todos los tests tal como vienen. Las 3 de `__init__` solo fallan el test de formato propio de Black, y pasan después de `black`.
2. **Hizo correctamente las extracciones que Rope no pudo** (09, `continue`; 10, f-strings), transformando el flujo de control a mano (retorno de `None` y `continue` en el llamador).
3. **Evitó todos los cambios de los casos en que Rope falló en silencio** (04, 13, 15, 16), porque eran Renames de nombres públicos y el prompt lo prohíbe. No es una prueba de que el modelo detectaría esas trampas, sino de que no se expuso a ellas.
4. **Escribió con mejor estilo que Rope:** anotaciones de tipo, docstrings, dos líneas en blanco entre funciones. Pero imitó el estilo *inestable* con que Black se formatea a sí mismo, que no es el que exige `test_piping`.
5. **No es determinista:** 3 diffs distintos en cada uno de los 9 módulos.
6. **Cambios mucho más grandes que los de Rope:** ~1300 líneas tocadas en `__init__` y ~1450 en `linegen` por corrida, frente a unas pocas decenas de líneas por caso de Rope. Revisar un cambio así a mano es costoso. La garantía viene de la suite de tests.
7. **Huella de carbono:** la medición durante la ejecución muestra que **esperar a Claude cuesta localmente lo mismo que el reposo**. El costo energético relevante del LLM está en los servidores y no se puede medir con CodeCarbon desde el cliente. Lo local medido (131 mWh y 34 mg CO₂eq por llamada) es igual unas 47 veces mayor que una operación de Rope.
8. **Incidencias de método** (2.1): el extractor de código y la verificación de formato tenían errores, ambos corregidos y reevaluados sin volver a pagar. Las suspensiones por batería contaminaron 2 mediciones de pytest y costaron ~US$ 1,75 extra en caché.

### Comparación de los tres proyectos (LLM)

| | PySnooper | Cookiecutter | Black |
|---|---|---|---|
| Modelo | Opus 5.5 | Opus 5.5 | **Sonnet 5.5** |
| Corridas | 15 | 51 | 27 (9 módulos de Rope × 3) |
| Contexto por llamada | — | ~34 500 tokens | 216 616 tokens |
| Preservan comportamiento (tests tal cual) | 15/15 | 51/51 | 24/27 |
| Preservan comportamiento (ignorando formato) | 15/15 | 51/51 | **27/27** |
| Costo | ~US$ 2,55 | US$ 6,80 | US$ 10,03 (con piloto) |
| Hizo correctamente lo que Rope rompió o rechazó | Sí (07/08/09) | Sí (08, 09) | Sí (09, 10) |
| Huella de carbono medida | — | — | 131 mWh por llamada (solo lo local) |

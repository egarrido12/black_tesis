# Rope en Black: resumen para presentar

Tercer proyecto del experimento "refactorización con Rope frente a un LLM", después de PySnooper y Cookiecutter. Detalle completo y evidencia en [`README.md`](README.md) y en [`resultados/`](resultados/).

---

## 1. Qué se hizo

- **Proyecto:** Black, el formateador de código Python (~16 400 líneas, 25 módulos, **743 tests**).
- **Herramienta:** Rope 1.15.0, a través de su API de Python, desde un script ([`ejecutar_pruebas_rope.py`](ejecutar_pruebas_rope.py)).
- **Método:** cada refactorización se aplica sobre una **copia limpia** del proyecto y se corre la suite completa. Si pasan los mismos 743 tests, **se preservó el comportamiento**.
- **17 refactorizaciones:** 11 iguales a las de PySnooper y Cookiecutter (02–12), 2 de control (06b, 10b) y 4 propias de Black (13–16).
- **Huella de carbono:** cada operación se midió con **CodeCarbon**, 5 repeticiones por caso.

---

## 2. Antes de empezar: Rope no funcionaba en Black

| Configuración de Rope | Usos encontrados de `lib2to3_parse` |
|---|---|
| Por defecto | ❌ se cae (archivos `.py` inválidos en `tests/data`) |
| `ignore_syntax_errors=True` | ⚠️ **1 de 40**, sin ningún aviso |
| `+ source_folders=['src']` | ✅ 40 de 40 |

Black guarda su código en `src/black/` (el llamado "src layout"). Rope no lo detecta y busca `black` fuera del proyecto. **Sin esa línea de configuración, todos los Rename quedaban incompletos sin avisar.**

---

## 3. Resultados: las 17 pruebas

| # | Refactorización | Qué hizo Rope | Tests | Resultado |
|---|---|---|---|---|
| 02 | Rename de función `lib2to3_parse` | 5 archivos, 40 cambios, incluidos los tests | 743/0 | ✅ |
| 03 | Rename de función importada por tests | 4 archivos | 743/0 | ✅ |
| 04 | Rename de método `Cache.is_changed` | **solo 1 archivo**; no ve las llamadas en `__init__` ni en los tests | 699/**44** | ❌ |
| 05 | Rename de clase base `StringTransformer` | clase + subclases | 743/0 | ✅ |
| 06 | Rename de parámetro keyword-only `fast` | se niega: "not a resolvable identifier" | — | ⛔ |
| 06b | Rename de parámetro posicional (control) | firma y cuerpo | 742/1 | 🎨 solo formato |
| 07 | Extract Method (bloque de caché) | función nueva `_read_cache` | 742/1 | 🎨 solo formato |
| 08 | Extract Method con 2 salidas | `is_stdin, src = _detect_stdin(src)` | 742/1 | 🎨 solo formato |
| 09 | Extract Method con `continue` | se niega (correcto) | — | ⛔ |
| 10 | Extract Method de bucle con f-strings | **se cae** por un bug interno | — | ⛔ |
| 10b | Extract Method de bucle sin f-strings (control) | olvida el `import difflib` local → `NameError` | 714/**29** | ❌ |
| 11 | Inline de `_splitlines_no_ff` | copia el cuerpo 2 veces | 743/0 | ✅ |
| 12 | Move de `re_compile_maybe_verbose` | mueve bien, pero reescribe imports y borra comentarios | 742/1 | 🎨 solo formato |
| 13 | Rename de función parcheada por string | no cambia los `patch("black.dump_to_file")` | 431/5/**307 errores** | ❌ |
| 14 | El mismo Rename con `docs=True` | sí cambia los strings | 743/0 | ✅ |
| 15 | Rename de `visit_suite` (llamado con `getattr`) | Black sigue funcionando pero **formatea distinto** | 729/**14** | ❌ |
| 16 | Rename de una opción `Preview` | no actualiza la documentación ni el JSON schema | 742/1 | ❌ |

✅ preserva · ❌ rompe comportamiento · ⛔ Rope la rechaza · 🎨 solo falla `test_piping`, el test que exige que el código de Black esté formateado con Black. Después de pasar `black`, vuelve a 743/0 (verificado).

**En números:**

- **5 de 17 (29 %)** pasan todos los tests tal como los deja Rope.
- **9 de 17 (53 %)** preservan el comportamiento si se pasa un formateador después.
- **5 de 17 (29 %)** cambian el comportamiento, **todas sin ningún aviso** de Rope.
- **3 de 17 (18 %)** Rope no las aplica.
- Rope es **determinista**: 5 repeticiones, mismo diff exacto.

---

## 4. Cómo falla Rope: los cuatro patrones

**1. Inferencia de tipos limitada (04, 06).** No sabe qué tipo devuelve `Cache.read()`, que está anotado como `Self`, ni reconoce los parámetros que van después de `*`.

```python
cache = Cache.read(mode)
if not cache.is_changed(src):   # ← Rope no lo renombra → AttributeError en 44 tests
```

**2. Referencias por nombre armado en tiempo de ejecución (13, 15, 16).**

```python
patch("black.dump_to_file", ...)              # 13: el nombre está en un string
getattr(self, f"visit_{name}")                 # 15: el nombre se arma al ejecutar
--enable-unstable-feature wrap_comprehension_in   # 16: el nombre es una opción pública
```

**3. Extract Method incompleto (10, 10b).** Se cae con f-strings (`{path}` → `{${path}}`) e ignora los imports locales.

**4. No respeta el estilo (06b, 07, 08, 12).** Pone 1 línea en blanco en vez de 2, no agrega anotaciones de tipo, junta imports en una línea de 260 caracteres y borra comentarios como `# re-exported`.

---

## 5. Huella de carbono (CodeCarbon)

Factor de la red eléctrica de Colombia: 259,5 gCO₂eq/kWh. Apple M4. Es una estimación por carga de CPU (sin sensores físicos).

| | Tiempo | Energía | CO₂eq |
|---|---|---|---|
| **Una refactorización con Rope** (promedio) | 0,8 s | 2,4 mWh | **0,6 mg** |
| **Una verificación con pytest** (promedio) | 24 s | 68 mWh | **17,7 mg** |
| Las 17 refactorizaciones con Rope | 13,4 s | 40 mWh | 10,5 mg |
| Experimento completo | 7 min 18 s | 1311 mWh | **0,34 g** |

**Mensaje:** aplicar la refactorización es casi gratis. **Verificarla cuesta ~28 veces más**, y como Rope falla en silencio, esa verificación no se puede omitir.

---

## 6. Comparación con los otros dos proyectos

| | PySnooper | Cookiecutter | Black |
|---|---|---|---|
| Tamaño | 964 líneas · 83 tests | 2806 líneas · 379 tests | ~16 400 líneas · 743 tests |
| Casos 02–12 que preservan | 8/11 (73 %) | 8/11 (73 %) | **4/11 (36 %)** · 7/11 ignorando el formato |
| Rename (02–06) | 5/5 | 5/5 | 3/5 |
| Extract Method (07–10) | 1/4 | 2/4 | 0/4 · 2/4 ignorando el formato |
| Inline / Move | 1/1 · 1/1 | 0/1 · 1/1 | 1/1 · 0/1 (1/1 ignorando el formato) |
| Punto ciego principal | `.format(**locals())` | mocks por string | tipos (`Self`, `*`), `getattr`, mocks, estilo |
| Falsos positivos de `find_errors` | 31/31 | 39/39 | 852/852 |

**Conclusión:** cuanto más grande, moderno y dinámico es el proyecto, peor le va a Rope. Funciona bien con Renames de funciones y clases referenciadas de forma estática. Falla en silencio cuando la referencia depende de tipos, strings o nombres armados en tiempo de ejecución.

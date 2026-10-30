"""Pruebas de Black con Rope (refactorización automática) + huella de carbono.

Réplica del experimento hecho sobre PySnooper (../PySnooper_tesis/rope_pruebas)
y Cookiecutter (../cookiecutter_tesis/rope_pruebas), con los mismos tipos de
refactorización y la misma numeración (02-12), más cuatro casos propios de
Black (13-16). Además mide con CodeCarbon (https://codecarbon.io) la energía
y las emisiones de CO2 equivalente de cada fase.

Flujo:
  0. Reposo: mide el consumo de la máquina sin hacer nada (referencia).
  1. Línea base: corre la suite de tests original de Black.
  2. Análisis estático con Rope (sin modificar código): find_errors,
     find_occurrences y find_definition.
  3. Refactorizaciones: cada una se aplica con la API de Rope sobre una
     copia limpia del proyecto, REPETICIONES veces (cada vez sobre una copia
     nueva) para medir la energía de Rope y comprobar que el diff es siempre
     el mismo. Se guarda el diff y se vuelve a correr la suite de tests.
     Si los tests siguen pasando, la refactorización preservó el
     comportamiento.

Cada fase se mide con dos trackers de CodeCarbon en paralelo:
  - "maquina" (tracking_mode='machine'): toda la máquina, incluido el
    consumo de fondo del sistema operativo y otras aplicaciones.
  - "proceso" (tracking_mode='process'): solo este proceso de Python y sus
    hijos (pytest), es decir, lo atribuible al experimento.

El código original en ../src NUNCA se modifica.

Uso (desde la raíz del repositorio):
    caffeinate -dimsu .venv/bin/python rope_pruebas/ejecutar_pruebas_rope.py
    .venv/bin/python rope_pruebas/ejecutar_pruebas_rope.py --pais COL --repeticiones 5
"""
import argparse
import contextlib
import json
import os
import platform
import re
import shutil
import statistics
import subprocess
import sys
import time
import traceback
from pathlib import Path

import codecarbon
import rope
from codecarbon import OfflineEmissionsTracker
from rope.base.project import Project
from rope.contrib import findit, finderrors
from rope.refactor.extract import ExtractMethod
from rope.refactor.inline import create_inline
from rope.refactor.move import create_move
from rope.refactor.rename import Rename

AQUI = Path(__file__).resolve().parent
REPO = AQUI.parent
TRABAJO = AQUI / '_trabajo'
RESULTADOS = AQUI / 'resultados'
CARBONO = RESULTADOS / 'carbono'
PYTHON = sys.executable

IGNORAR = shutil.ignore_patterns(
    '.git', '.github', '.venv', '.pytest_cache', '.mypy_cache', '.tox',
    '*.egg-info', '__pycache__', '.ropeproject', '.claude', 'rope_pruebas',
    'llm_pruebas', 'profiling',
)

# Modos de CodeCarbon que se miden en paralelo (etiqueta -> tracking_mode).
MODOS = {'maquina': 'machine', 'proceso': 'process'}

# Se fijan en main() a partir de los argumentos.
PAIS = 'COL'
REPETICIONES = 5
SEGUNDOS_REPOSO = 30


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def copia_limpia(nombre):
    """Copia el repositorio (sin .git/.venv/profiling) a _trabajo/<nombre>."""
    destino = TRABAJO / nombre
    if destino.exists():
        shutil.rmtree(destino)
    shutil.copytree(REPO, destino, ignore=IGNORAR)
    return destino


def entorno(carpeta):
    """Variables de entorno para que se importe el black de la copia.

    El .venv tiene black instalado en modo editable apuntando a ../src del
    repositorio original; PYTHONPATH va antes en sys.path y lo tapa.
    """
    env = dict(os.environ)
    env['PYTHONPATH'] = str(carpeta / 'src')
    return env


def correr_pytest(carpeta):
    """Corre pytest en `carpeta` y devuelve (resumen, salida completa)."""
    # Sin -n (pytest-xdist): la suite corre en serie, igual que en PySnooper
    # y Cookiecutter, y la medición de energía no depende de cuántos núcleos
    # reparta xdist.
    proc = subprocess.run(
        [PYTHON, '-m', 'pytest', 'tests', '-q', '-rs', '-p', 'no:cacheprovider'],
        cwd=carpeta, capture_output=True, text=True, env=entorno(carpeta),
    )
    salida = proc.stdout + proc.stderr
    # Línea final de pytest, p. ej. "743 passed, 2 skipped, 31 subtests passed in 23.81s".
    finales = [l for l in salida.splitlines() if re.search(r'\d+ (passed|failed|errors?)\b.* in [\d.]+s', l)]
    final = finales[-1] if finales else ''
    resumen = {'returncode': proc.returncode}
    for clave in ('passed', 'failed', 'skipped', 'error', 'errors'):
        m = re.search(r'(\d+) ' + clave + r'\b', final)
        resumen[clave] = int(m.group(1)) if m else 0
    resumen['errors'] += resumen.pop('error')
    return resumen, salida


def verificar_import(carpeta):
    """Confirma que se importa el black de la copia, no el del repositorio."""
    proc = subprocess.run(
        [PYTHON, '-c', 'import black; print(black.__file__)'],
        cwd=carpeta, capture_output=True, text=True, env=entorno(carpeta),
    )
    ruta = proc.stdout.strip()
    assert ruta.startswith(str(carpeta)), ruta
    return ruta


def abrir_proyecto(carpeta, configurado=True):
    """Abre la copia como proyecto Rope.

    Con `configurado=False` se abre con la configuración por defecto de Rope
    (solo para el diagnóstico de la sección 2). Las dos opciones son:

    - source_folders=['src']: Black usa el "src layout" (el paquete está en
      src/black). Rope solo detecta la raíz como carpeta de código y resuelve
      `import black` por el sys.path del intérprete, que (por la instalación
      editable) apunta al repositorio ORIGINAL. Sin esta opción, Rope no ve
      ningún uso de los símbolos dentro de la copia.
    - ignore_syntax_errors=True: tests/data/ contiene casos de prueba de
      formateo con sintaxis que Rope no puede analizar.
    """
    if not configurado:
        return Project(str(carpeta))
    return Project(str(carpeta), ignore_syntax_errors=True, source_folders=['src'])


def offset_de(recurso, marcador, desplazamiento=0):
    """Offset (en caracteres) de `marcador` dentro del archivo."""
    codigo = recurso.read()
    assert codigo.count(marcador) == 1, 'marcador ambiguo o ausente: %r' % marcador
    return codigo.index(marcador) + desplazamiento


def inicio_de_linea(recurso, marcador):
    codigo = recurso.read()
    return codigo.rfind('\n', 0, offset_de(recurso, marcador)) + 1


def linea_anterior(recurso, offset):
    """Inicio de la línea anterior a `offset` (para excluir una línea en blanco)."""
    return recurso.read().rfind('\n', 0, offset - 1) + 1


# ---------------------------------------------------------------------------
# Medición de huella de carbono (CodeCarbon)
# ---------------------------------------------------------------------------

def datos_tracker(d):
    """Convierte el EmissionsData de CodeCarbon en un dict con unidades útiles."""
    return {
        'duracion_s': round(d.duration, 3),
        'energia_Wh': d.energy_consumed * 1000,
        'energia_cpu_Wh': d.cpu_energy * 1000,
        'energia_ram_Wh': d.ram_energy * 1000,
        'emisiones_mgCO2eq': d.emissions * 1e6,
        'potencia_cpu_W': d.cpu_power,
        'potencia_ram_W': d.ram_power,
        'agua_L': getattr(d, 'water_consumed', None),
    }


@contextlib.contextmanager
def medir(nombre, registro):
    """Mide la energía y emisiones del bloque `with` con los dos modos.

    Al salir, `registro` queda con una clave por modo ('maquina', 'proceso').
    Cada medición se agrega también a resultados/carbono/emisiones_<modo>.csv,
    el CSV estándar de CodeCarbon.
    """
    trackers = {
        etiqueta: OfflineEmissionsTracker(
            project_name=nombre,
            country_iso_code=PAIS,
            tracking_mode=modo,
            measure_power_secs=1,
            output_dir=str(CARBONO),
            output_file='emisiones_%s.csv' % etiqueta,
            save_to_file=True,
            log_level='error',
            allow_multiple_runs=True,
        )
        for etiqueta, modo in MODOS.items()
    }
    for t in trackers.values():
        t.start()
    try:
        yield registro
    finally:
        for etiqueta, t in trackers.items():
            t.stop()
            registro[etiqueta] = datos_tracker(t.final_emissions_data)


def info_carbono():
    """Metadatos de la medición (hardware detectado, factor de emisión)."""
    t = OfflineEmissionsTracker(country_iso_code=PAIS, save_to_file=False,
                                log_level='error', allow_multiple_runs=True)
    t.start()
    time.sleep(1)
    t.stop()
    d = t.final_emissions_data
    return {
        'codecarbon': codecarbon.__version__,
        'pais': d.country_name,
        'pais_iso': PAIS,
        'intensidad_gCO2eq_kWh': round(d.emissions / d.energy_consumed * 1000, 3),
        'cpu': d.cpu_model,
        'cpu_count': d.cpu_count,
        'ram_GB': round(d.ram_total_size, 1),
        'os': d.os,
        'metodo_cpu': 'cpu_load (TDP x carga de CPU; sin sensores de energía)',
        'measure_power_secs': 1,
    }


def reposo():
    """Consumo de la máquina sin hacer nada, para poner en contexto el resto."""
    med = {}
    with medir('reposo', med):
        time.sleep(SEGUNDOS_REPOSO)
    print('[reposo] %d s  maquina=%.4f Wh  proceso=%.4f Wh' % (
        SEGUNDOS_REPOSO, med['maquina']['energia_Wh'], med['proceso']['energia_Wh']))
    return med


# ---------------------------------------------------------------------------
# 1. Línea base
# ---------------------------------------------------------------------------

def linea_base():
    carpeta = copia_limpia('00_linea_base')
    ruta = verificar_import(carpeta)
    med = {}
    with medir('00_linea_base_pytest', med):
        resumen, salida = correr_pytest(carpeta)
    (RESULTADOS / '00_linea_base_pytest.txt').write_text(salida)
    print('[linea base] %s  (black importado desde %s)' % (resumen, ruta))
    return resumen, med


# ---------------------------------------------------------------------------
# 2. Análisis estático
# ---------------------------------------------------------------------------

SIMBOLOS = [
    # (archivo, marcador, desplazamiento hasta el nombre)
    ('src/black/parsing.py', 'def lib2to3_parse', 4),
    ('src/black/ranges.py', 'def parse_line_ranges', 4),
    ('src/black/cache.py', 'def is_changed', 4),
    ('src/black/trans.py', 'class StringTransformer', 6),
    ('src/black/output.py', 'def dump_to_file', 4),
    ('src/black/linegen.py', '    def visit_suite', 8),
    ('src/black/mode.py', '    wrap_comprehension_in = auto()', 4),
]


def diagnostico_configuracion(carpeta):
    """Qué ve Rope de lib2to3_parse según cómo se abra el proyecto.

    Documenta por qué abrir_proyecto() necesita source_folders e
    ignore_syntax_errors (sección 4.1 del README).
    """
    lineas = ['## Configuración del proyecto Rope', '',
              'Ocurrencias de `parsing.lib2to3_parse` encontradas por `find_occurrences` '
              'según las opciones con que se abre el proyecto:', '',
              '| Opciones de `Project(...)` | Carpetas de código detectadas | `import black` se resuelve en | Resultado |',
              '|---|---|---|---|']
    variantes = [
        ('(por defecto)', {}),
        ("source_folders=['src']", {'source_folders': ['src']}),
        ('ignore_syntax_errors=True', {'ignore_syntax_errors': True}),
        ("ignore_syntax_errors=True, source_folders=['src']",
         {'ignore_syntax_errors': True, 'source_folders': ['src']}),
    ]
    filas = {}
    for etiqueta, opciones in variantes:
        proyecto = Project(str(carpeta), **opciones)
        carpetas = ', '.join('`%s`' % (f.path or '.') for f in proyecto.get_source_folders())
        modulo = proyecto.find_module('black')
        ruta = Path(modulo.real_path)
        donde = ('la copia (`%s`)' % ruta.relative_to(carpeta) if ruta.is_relative_to(carpeta)
                 else 'el repositorio ORIGINAL (`%s`)' % ruta)
        recurso = proyecto.get_resource('src/black/parsing.py')
        try:
            encontradas = findit.find_occurrences(
                proyecto, recurso, offset_de(recurso, 'def lib2to3_parse', 4))
            archivos = sorted({o.resource.path for o in encontradas})
            resultado = '%d ocurrencias en %d archivos' % (len(encontradas), len(archivos))
            filas[etiqueta] = len(encontradas)
        except Exception as e:
            resultado = '`%s`: %s' % (type(e).__name__, e)
            filas[etiqueta] = resultado
        proyecto.close()
        lineas.append('| `%s` | %s | %s | %s |' % (etiqueta, carpetas, donde, resultado))
    lineas.append('')
    return lineas, filas


def analisis_estatico():
    carpeta = copia_limpia('01_analisis')
    med = {}
    with medir('01_analisis_estatico', med):
        lineas = ['# Análisis estático con Rope %s' % rope.VERSION, '']
        diagnostico, configuraciones = diagnostico_configuracion(carpeta)
        lineas += diagnostico
        proyecto = abrir_proyecto(carpeta)

        lineas += ['## find_errors (rope.contrib.finderrors)', '',
                   '| Módulo | Errores reportados |', '|---|---|']
        errores_totales = []
        for archivo in sorted((carpeta / 'src' / 'black').glob('*.py')):
            rel = archivo.relative_to(carpeta).as_posix()
            errores = finderrors.find_errors(proyecto, proyecto.get_resource(rel))
            errores_totales += [(rel, e.lineno, e.error) for e in errores]
            lineas.append('| `%s` | %d |' % (rel, len(errores)))
        lineas.append('')
        for rel, lineno, error in errores_totales:
            lineas.append('- `%s:%d` — %s' % (rel, lineno, error))
        if errores_totales:
            lineas.append('')

        lineas += ['## find_occurrences (rope.contrib.findit)', '']
        ocurrencias = {}
        for rel, marcador, desp in SIMBOLOS:
            recurso = proyecto.get_resource(rel)
            offset = offset_de(recurso, marcador, desp)
            nombre = re.match(r'\w+', recurso.read()[offset:]).group(0)
            encontradas = findit.find_occurrences(proyecto, recurso, offset)
            ocurrencias[nombre] = len(encontradas)
            lineas.append('### `%s` (%d ocurrencias)' % (nombre, len(encontradas)))
            lineas.append('')
            for o in encontradas:
                lineas.append('- `%s:%d`%s' % (o.resource.path, o.lineno,
                                              ' (dudosa)' if o.unsure else ''))
            lineas.append('')

        lineas += ['## find_definition (rope.contrib.findit)', '']
        recurso = proyecto.get_resource('src/black/__init__.py')
        offset = offset_de(recurso, 'src_node = lib2to3_parse(', 11)
        definicion = findit.find_definition(proyecto, recurso.read(), offset, recurso)
        lineas.append('Desde `src/black/__init__.py` (`src_node = lib2to3_parse(...)`) '
                      'Rope resuelve la definición en `%s:%d`.'
                      % (definicion.resource.path, definicion.lineno))
        lineas.append('')
        proyecto.close()

    (RESULTADOS / '01_analisis_estatico.md').write_text('\n'.join(lineas))
    print('[analisis] errores=%d ocurrencias=%s' % (len(errores_totales), ocurrencias))
    return {'errores': len(errores_totales), 'ocurrencias': ocurrencias,
            'definicion': '%s:%d' % (definicion.resource.path, definicion.lineno),
            'configuraciones': configuraciones, 'carbono': med}


# ---------------------------------------------------------------------------
# 3. Refactorizaciones
# ---------------------------------------------------------------------------
# Cada función recibe el proyecto Rope y devuelve un objeto ChangeSet.

def ref_rename_funcion(p):
    # Usada en 3 módulos y, a través de `black.lib2to3_parse`, en los tests.
    r = p.get_resource('src/black/parsing.py')
    return Rename(p, r, offset_de(r, 'def lib2to3_parse', 4)).get_changes('parse_to_tree')


def ref_rename_funcion_importada(p):
    r = p.get_resource('src/black/ranges.py')
    return Rename(p, r, offset_de(r, 'def parse_line_ranges', 4)).get_changes('parse_line_range_specs')


def ref_rename_metodo(p):
    # Los llamadores obtienen la instancia con Cache.read(...), que devuelve
    # `Self`: Rope tiene que inferir el tipo para encontrarlos.
    r = p.get_resource('src/black/cache.py')
    return Rename(p, r, offset_de(r, 'def is_changed', 4)).get_changes('has_changed')


def ref_rename_clase(p):
    r = p.get_resource('src/black/trans.py')
    return Rename(p, r, offset_de(r, 'class StringTransformer', 6)).get_changes('BaseStringTransformer')


def ref_rename_parametro(p):
    # Parámetro keyword-only: todos los llamadores usan `fast=...`.
    r = p.get_resource('src/black/__init__.py')
    marcador = '    *,\n    fast: bool,\n    mode: Mode,\n    lines: Collection[tuple[int, int]] = (),\n) -> FileContent:'
    return Rename(p, r, offset_de(r, marcador, len('    *,\n    '))).get_changes('skip_safety_checks')


def ref_rename_parametro_posicional(p):
    # Mismo parámetro de 06 pero el primero, que va antes del `*`.
    r = p.get_resource('src/black/__init__.py')
    return Rename(p, r, offset_de(r, 'def format_file_contents(\n    src_contents', 29)).get_changes('source')


def ref_extract_cache(p):
    # Bloque de reformat_one que decide qué caché leer (1 valor de salida).
    r = p.get_resource('src/black/__init__.py')
    inicio = inicio_de_linea(r, '            if no_cache:\n                cache = None')
    fin = inicio_de_linea(r, '            if cache is not None:\n                if not cache.is_changed(src):')
    return ExtractMethod(p, r, inicio, fin).get_changes('_read_cache')


def ref_extract_stdin(p):
    # Bloque if/elif/else de reformat_one que detecta stdin y reasigna el
    # parámetro `src` (2 valores de salida: is_stdin y src).
    r = p.get_resource('src/black/__init__.py')
    inicio = inicio_de_linea(r, '        if str(src) == "-":\n            is_stdin = True')
    fin = linea_anterior(r, inicio_de_linea(r, '        if is_stdin:\n            if src.suffix == ".pyi":'))
    return ExtractMethod(p, r, inicio, fin).get_changes('_detect_stdin')


def ref_extract_con_continue(p):
    # Bloque dentro del for de get_sources que contiene `continue`:
    # caso límite (flujo de control que salta fuera del bloque).
    r = p.get_resource('src/black/__init__.py')
    inicio = inicio_de_linea(r, '        if s == "-" and stdin_filename:')
    fin = linea_anterior(r, inicio_de_linea(r, '        # When the sources share no common parent'))
    return ExtractMethod(p, r, inicio, fin).get_changes('_resolve_stdin_source')


def ref_extract_bucle(p):
    # Bucle completo de get_sources (los `continue` quedan dentro de su for;
    # lee 12 variables locales y muta `sources`).
    r = p.get_resource('src/black/__init__.py')
    inicio = inicio_de_linea(r, '    for s in src:\n        if s == "-" and stdin_filename:')
    fin = linea_anterior(r, inicio_de_linea(r, '    return sources\n\n\ndef reformat_code'))
    return ExtractMethod(p, r, inicio, fin).get_changes('_collect_sources')


def ref_extract_bucle_sin_fstring(p):
    # Bucle de output.diff sin f-strings (lee 4 variables, muta diff_lines).
    r = p.get_resource('src/black/output.py')
    inicio = inicio_de_linea(r, '    for line in difflib.unified_diff(')
    fin = inicio_de_linea(r, '    return "".join(diff_lines)\n\n\ndef color_diff')
    return ExtractMethod(p, r, inicio, fin).get_changes('_append_diff_lines')


def ref_inline_funcion(p):
    r = p.get_resource('src/black/output.py')
    return create_inline(p, r, offset_de(r, 'def _splitlines_no_ff', 4)).get_changes()


def ref_move_funcion(p):
    # Función pública que los tests importan desde `black`.
    r = p.get_resource('src/black/__init__.py')
    destino = p.get_resource('src/black/files.py')
    return create_move(p, r, offset_de(r, 'def re_compile_maybe_verbose', 4)).get_changes(destino)


def ref_rename_parcheada(p):
    # Los tests hacen patch("black.dump_to_file", ...): la referencia está en
    # un string y Rope no la ve.
    r = p.get_resource('src/black/output.py')
    return Rename(p, r, offset_de(r, 'def dump_to_file', 4)).get_changes('write_to_temp_file')


def ref_rename_parcheada_docs(p):
    # Igual que 13, pero con docs=True: Rope también renombra en strings y
    # comentarios.
    r = p.get_resource('src/black/output.py')
    return Rename(p, r, offset_de(r, 'def dump_to_file', 4)).get_changes('write_to_temp_file', docs=True)


def ref_rename_visitante(p):
    # Visitor.visit despacha con getattr(self, f"visit_{name}"): el nombre
    # del método se arma en tiempo de ejecución.
    r = p.get_resource('src/black/linegen.py')
    return Rename(p, r, offset_de(r, '    def visit_suite', 8)).get_changes('visit_block')


def ref_rename_preview(p):
    # Miembro del enum Preview: su nombre también aparece en el JSON schema y
    # en la documentación (docs/the_black_code_style/future_style.md).
    r = p.get_resource('src/black/mode.py')
    return Rename(p, r, offset_de(r, '    wrap_comprehension_in = auto()', 4)).get_changes('wrap_comprehension_in_clause')


REFACTORIZACIONES = [
    ('02_rename_funcion', 'Rename', 'parsing.lib2to3_parse -> parse_to_tree (usada en 3 módulos y en tests vía black.lib2to3_parse)', ref_rename_funcion),
    ('03_rename_funcion_importada', 'Rename', 'ranges.parse_line_ranges -> parse_line_range_specs (también importada por los tests)', ref_rename_funcion_importada),
    ('04_rename_metodo', 'Rename', 'Cache.is_changed -> has_changed (llamada sobre instancias obtenidas con Cache.read)', ref_rename_metodo),
    ('05_rename_clase', 'Rename', 'trans.StringTransformer -> BaseStringTransformer (clase base abstracta de 5 subclases)', ref_rename_clase),
    ('06_rename_parametro', 'Rename', 'parámetro keyword-only fast de format_file_contents -> skip_safety_checks', ref_rename_parametro),
    ('06b_rename_parametro_posicional', 'Rename', 'parámetro posicional src_contents de format_file_contents -> source (control de 06)', ref_rename_parametro_posicional),
    ('07_extract_cache', 'Extract Method', 'bloque que elige la caché en reformat_one -> _read_cache', ref_extract_cache),
    ('08_extract_stdin', 'Extract Method', 'bloque if/elif/else que detecta stdin en reformat_one -> _detect_stdin (2 valores de salida)', ref_extract_stdin),
    ('09_extract_con_continue', 'Extract Method', 'bloque con `continue` dentro del for de get_sources -> _resolve_stdin_source (caso límite)', ref_extract_con_continue),
    ('10_extract_bucle', 'Extract Method', 'bucle for completo de get_sources -> _collect_sources', ref_extract_bucle),
    ('10b_extract_bucle_sin_fstring', 'Extract Method', 'bucle for de output.diff (sin f-strings) -> _append_diff_lines (control de 10)', ref_extract_bucle_sin_fstring),
    ('11_inline_funcion', 'Inline', 'inline de output._splitlines_no_ff en diff (2 llamadas)', ref_inline_funcion),
    ('12_move_funcion', 'Move', 'mover black.re_compile_maybe_verbose a black.files (importada por los tests)', ref_move_funcion),
    ('13_rename_parcheada', 'Rename', 'output.dump_to_file -> write_to_temp_file (los tests la parchean con patch("black.dump_to_file"))', ref_rename_parcheada),
    ('14_rename_parcheada_docs', 'Rename', 'igual que 13 pero con docs=True (renombra también en strings y comentarios)', ref_rename_parcheada_docs),
    ('15_rename_visitante', 'Rename', 'LineGenerator.visit_suite -> visit_block (despacho dinámico getattr(self, f"visit_{name}"))', ref_rename_visitante),
    ('16_rename_preview', 'Rename', 'Preview.wrap_comprehension_in -> wrap_comprehension_in_clause (nombre también en docs y JSON schema)', ref_rename_preview),
]


def resumir_repeticiones(mediciones):
    """Media y desviación estándar de las mediciones de las repeticiones."""
    resumen = {}
    for etiqueta in MODOS:
        filas = [m[etiqueta] for m in mediciones]
        resumen[etiqueta] = {}
        for clave in ('duracion_s', 'energia_Wh', 'emisiones_mgCO2eq'):
            valores = [f[clave] for f in filas]
            resumen[etiqueta][clave] = statistics.mean(valores)
            resumen[etiqueta][clave + '_sd'] = (statistics.stdev(valores)
                                                if len(valores) > 1 else 0.0)
    return resumen


def ejecutar_rope(nombre, funcion):
    """Aplica la refactorización una vez sobre una copia nueva, midiendo Rope.

    Devuelve (carpeta, cambios o None, excepción o None, tiempo, medición).
    Solo se mide Rope (abrir el proyecto, calcular y aplicar los cambios);
    la copia del repositorio queda fuera de la medición.
    """
    carpeta = copia_limpia(nombre)
    med, cambios, error = {}, None, None
    t0 = time.perf_counter()
    with medir(nombre + '_rope', med):
        proyecto = abrir_proyecto(carpeta)
        try:
            cambios = funcion(proyecto)
            proyecto.do(cambios)
        except Exception as e:
            error = e
            traza = traceback.format_exc()
        proyecto.close()
    tiempo = time.perf_counter() - t0
    if error is not None:
        error.traza = traza
    return carpeta, cambios, error, tiempo, med


def aplicar(nombre, tipo, descripcion, funcion, base):
    fila = {'id': nombre, 'tipo': tipo, 'descripcion': descripcion}
    tiempos, mediciones, descripciones = [], [], set()
    for _ in range(REPETICIONES):
        carpeta, cambios, error, tiempo, med = ejecutar_rope(nombre, funcion)
        tiempos.append(tiempo)
        mediciones.append(med)
        descripciones.add(cambios.get_description() if error is None
                          else '%s: %s' % (type(error).__name__, error))
    fila['tiempo_rope_s'] = round(statistics.mean(tiempos), 3)
    fila['tiempos_rope_s'] = [round(t, 3) for t in tiempos]
    fila['determinista'] = len(descripciones) == 1
    fila['carbono'] = {'rope': resumir_repeticiones(mediciones),
                       'rope_repeticiones': mediciones}

    if error is not None:
        fila['estado_rope'] = 'error: %s: %s' % (type(error).__name__, error)
        fila['veredicto'] = 'RECHAZADA POR ROPE'
        (RESULTADOS / (nombre + '_error.txt')).write_text(error.traza)
        print('[%s] Rope rechazó: %s' % (nombre, fila['estado_rope']))
        return fila
    fila['estado_rope'] = 'aplicada'
    fila['archivos_modificados'] = sorted(r.path for r in cambios.get_changed_resources())
    (RESULTADOS / (nombre + '.diff')).write_text(cambios.get_description())

    med = {}
    with medir(nombre + '_pytest', med):
        resumen, salida = correr_pytest(carpeta)
    fila['carbono']['pytest'] = med
    (RESULTADOS / (nombre + '_pytest.txt')).write_text(salida)
    fila['tests'] = resumen
    igual = (resumen['passed'] == base['passed'] and resumen['failed'] == 0
             and resumen['errors'] == 0)
    fila['veredicto'] = 'COMPORTAMIENTO PRESERVADO' if igual else 'ROMPE TESTS'
    print('[%s] %s  %s  rope=%.3fs' % (nombre, fila['veredicto'], resumen,
                                       fila['tiempo_rope_s']))
    return fila


# ---------------------------------------------------------------------------
# Reporte
# ---------------------------------------------------------------------------

def escribir_resumen(base, analisis, filas):
    lineas = [
        '# Resumen de pruebas con Rope (Black)', '',
        '- Python: `%s`' % sys.version.split()[0],
        '- Rope: `%s`' % rope.VERSION,
        '- Fecha: %s' % time.strftime('%Y-%m-%d %H:%M'), '',
        '## Línea base', '',
        '%(passed)d passed, %(failed)d failed, %(skipped)d skipped, %(errors)d errors' % base, '',
        '## Refactorizaciones', '',
        '| # | Tipo | Descripción | Rope | Tiempo (s) | Tests (passed/failed/errors) | Veredicto |',
        '|---|---|---|---|---|---|---|',
    ]
    for f in filas:
        t = f.get('tests')
        tests = '%d / %d / %d' % (t['passed'], t['failed'], t['errors']) if t else '—'
        lineas.append('| %s | %s | %s | %s | %s | %s | **%s** |' % (
            f['id'], f['tipo'], f['descripcion'], f['estado_rope'],
            f['tiempo_rope_s'], tests, f['veredicto']))
    lineas.append('')
    (RESULTADOS / 'resumen.md').write_text('\n'.join(lineas))


def fmt(valor, decimales=4):
    return ('%.' + str(decimales) + 'f') % valor


def escribir_huella(info, med_reposo, med_base, analisis, filas, med_total):
    """Genera resultados/carbono/huella_carbono.md."""
    L = [
        '# Huella de carbono del experimento con Rope (Black)', '',
        '- CodeCarbon: `%s` (`OfflineEmissionsTracker`)' % info['codecarbon'],
        '- País (factor de emisión de la red): %s (`%s`), %s gCO2eq/kWh'
        % (info['pais'], info['pais_iso'], info['intensidad_gCO2eq_kWh']),
        '- CPU: %s, %d hilos, RAM %s GB, %s' % (info['cpu'], info['cpu_count'],
                                                 info['ram_GB'], info['os']),
        '- Método de CPU: %s' % info['metodo_cpu'],
        '- Repeticiones de cada operación de Rope: %d' % REPETICIONES,
        '- Fecha: %s' % time.strftime('%Y-%m-%d %H:%M'), '',
        'Unidades: energía en **Wh** (1 Wh = 0,001 kWh); emisiones en **mg de CO2 '
        'equivalente** (1 g = 1000 mg). "Máquina" = toda la computadora; '
        '"Proceso" = solo el proceso del experimento y sus hijos.', '',
        '## Fases de referencia', '',
        '| Fase | Duración (s) | Energía máquina (Wh) | Emisiones máquina (mg) | Energía proceso (Wh) | Emisiones proceso (mg) |',
        '|---|---|---|---|---|---|',
    ]

    def fila_ref(nombre, med):
        m, p = med['maquina'], med['proceso']
        L.append('| %s | %s | %s | %s | %s | %s |' % (
            nombre, fmt(m['duracion_s'], 1), fmt(m['energia_Wh']),
            fmt(m['emisiones_mgCO2eq'], 2), fmt(p['energia_Wh']),
            fmt(p['emisiones_mgCO2eq'], 2)))

    fila_ref('Reposo (%d s sin hacer nada)' % SEGUNDOS_REPOSO, med_reposo)
    fila_ref('Línea base: pytest original', med_base)
    fila_ref('Análisis estático con Rope', analisis['carbono'])
    fila_ref('**Experimento completo**', med_total)
    L += ['', '## Operación de Rope (media de %d repeticiones)' % REPETICIONES, '',
          '| # | Tipo | Veredicto | Tiempo Rope (s) | Energía máquina (Wh) | Emisiones máquina (mg) | Energía proceso (Wh) | Emisiones proceso (mg) | Energía pytest máquina (Wh) | Emisiones pytest máquina (mg) |',
          '|---|---|---|---|---|---|---|---|---|---|']
    tot = {'rope_m': 0, 'rope_p': 0, 'rope_m_mg': 0, 'rope_p_mg': 0,
           'py_m': 0, 'py_m_mg': 0, 'py_p': 0, 'py_p_mg': 0, 'rope_s': 0}
    for f in filas:
        rm, rp = f['carbono']['rope']['maquina'], f['carbono']['rope']['proceso']
        py = f['carbono'].get('pytest')
        tot['rope_m'] += rm['energia_Wh']
        tot['rope_p'] += rp['energia_Wh']
        tot['rope_m_mg'] += rm['emisiones_mgCO2eq']
        tot['rope_p_mg'] += rp['emisiones_mgCO2eq']
        tot['rope_s'] += f['tiempo_rope_s']
        if py:
            tot['py_m'] += py['maquina']['energia_Wh']
            tot['py_m_mg'] += py['maquina']['emisiones_mgCO2eq']
            tot['py_p'] += py['proceso']['energia_Wh']
            tot['py_p_mg'] += py['proceso']['emisiones_mgCO2eq']
        L.append('| %s | %s | %s | %s | %s ± %s | %s | %s ± %s | %s | %s | %s |' % (
            f['id'], f['tipo'], f['veredicto'], fmt(f['tiempo_rope_s'], 3),
            fmt(rm['energia_Wh'], 5), fmt(rm['energia_Wh_sd'], 5),
            fmt(rm['emisiones_mgCO2eq'], 3),
            fmt(rp['energia_Wh'], 5), fmt(rp['energia_Wh_sd'], 5),
            fmt(rp['emisiones_mgCO2eq'], 3),
            fmt(py['maquina']['energia_Wh']) if py else '—',
            fmt(py['maquina']['emisiones_mgCO2eq'], 2) if py else '—'))
    L += ['', '## Totales', '',
          '| Concepto | Energía máquina (Wh) | Emisiones máquina (mg) | Energía proceso (Wh) | Emisiones proceso (mg) |',
          '|---|---|---|---|---|',
          '| Una aplicación de cada una de las %d refactorizaciones con Rope (%s s en total) | %s | %s | %s | %s |' % (
              len(filas), fmt(tot['rope_s'], 2), fmt(tot['rope_m']), fmt(tot['rope_m_mg'], 2),
              fmt(tot['rope_p']), fmt(tot['rope_p_mg'], 2)),
          '| Verificación con pytest de las refactorizaciones aplicadas | %s | %s | %s | %s |' % (
              fmt(tot['py_m']), fmt(tot['py_m_mg'], 2), fmt(tot['py_p']), fmt(tot['py_p_mg'], 2)),
          '']
    (CARBONO / 'huella_carbono.md').write_text('\n'.join(L))
    return tot


def main():
    global PAIS, REPETICIONES, SEGUNDOS_REPOSO
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--pais', default=PAIS,
                        help='código ISO-3 del país para el factor de emisión (por defecto COL)')
    parser.add_argument('--repeticiones', type=int, default=REPETICIONES,
                        help='veces que se repite cada operación de Rope (por defecto 5)')
    parser.add_argument('--reposo', type=int, default=SEGUNDOS_REPOSO,
                        help='segundos de medición en reposo (por defecto 30)')
    args = parser.parse_args()
    PAIS, REPETICIONES, SEGUNDOS_REPOSO = args.pais, args.repeticiones, args.reposo

    RESULTADOS.mkdir(exist_ok=True)
    shutil.rmtree(CARBONO, ignore_errors=True)
    for viejo in RESULTADOS.iterdir():
        viejo.unlink()
    CARBONO.mkdir()

    info = info_carbono()
    print('[carbono] %s' % info)
    med_reposo = reposo()
    med_total = {}
    with medir('experimento_completo', med_total):
        base, med_base = linea_base()
        analisis = analisis_estatico()
        filas = [aplicar(*r, base=base) for r in REFACTORIZACIONES]
    escribir_resumen(base, analisis, filas)
    totales = escribir_huella(info, med_reposo, med_base, analisis, filas, med_total)
    (RESULTADOS / 'resumen.json').write_text(json.dumps(
        {'python': sys.version.split()[0], 'rope': rope.VERSION,
         'plataforma': platform.platform(), 'repeticiones_rope': REPETICIONES,
         'linea_base': base, 'analisis': analisis, 'refactorizaciones': filas,
         'carbono': {'info': info, 'reposo': med_reposo, 'linea_base': med_base,
                     'experimento_completo': med_total, 'totales': totales}},
        indent=2, ensure_ascii=False))
    print('\nResultados en %s' % RESULTADOS)


if __name__ == '__main__':
    main()

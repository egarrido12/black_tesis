"""Pruebas de Black con un LLM (refactorización con un prompt general) + huella de carbono.

Réplica del experimento hecho sobre PySnooper (../PySnooper_tesis/llm_pruebas)
y Cookiecutter (../cookiecutter_tesis/llm_pruebas). A diferencia de
rope_pruebas/, aquí NO se le indica al modelo qué refactorización hacer:
recibe un prompt general (prompt_v1.md) y decide él mismo qué cambiar en cada
módulo.

Flujo:
  0. Reposo: mide el consumo de la máquina sin hacer nada (referencia).
  1. Línea base: corre la suite de tests original de Black.
  2. Para cada módulo y cada corrida: se envía el prompt + el paquete
     completo como contexto, se extrae el archivo refactorizado, se aplica
     sobre una copia limpia del proyecto, se guarda el diff, se compara la
     API pública (con ast) y se vuelve a correr la suite de tests. Si el
     único test que falla es test_piping (exige que src/black/__init__.py
     esté formateado con Black), se pasa `black` por el archivo y se vuelve a
     correr la suite, igual que en rope_pruebas/verificar_formateo.py.
  3. Se escribe un resumen (tests, tipo de fallo, API, tokens, costo,
     determinismo, energía y emisiones).

La llamada al modelo y cada corrida de pytest se miden con CodeCarbon
(../huella_carbono/medicion.py) durante la ejecución (serie temporal cada
0,25 s, con eventos como "primer_evento" o "inicio_texto" del streaming) y al
final. CodeCarbon solo puede medir ESTA máquina: la energía que gastan los
servidores de Anthropic al generar la respuesta no se mide. Por eso se
guardan los tokens de cada llamada, para poder estimarla aparte.

El código original en ../src NUNCA se modifica. Cada ejecución se guarda en
resultados/<fecha_hora>/ para no sobrescribir corridas pagadas.

Uso (desde la raíz del repositorio, con ANTHROPIC_API_KEY exportada):
    .venv/bin/python llm_pruebas/ejecutar_pruebas_llm.py --dry-run
    caffeinate -dimsu .venv/bin/python -W ignore llm_pruebas/ejecutar_pruebas_llm.py
    .venv/bin/python llm_pruebas/ejecutar_pruebas_llm.py --corridas 3 --modulos cache output
    .venv/bin/python llm_pruebas/ejecutar_pruebas_llm.py --reanudar 20261113_101500
"""
import argparse
import ast
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import anthropic

AQUI = Path(__file__).resolve().parent
REPO = AQUI.parent
PAQUETE = REPO / 'src' / 'black'
TRABAJO = AQUI / '_trabajo'
RESULTADOS = AQUI / 'resultados'
PYTHON = sys.executable
PROMPT = AQUI / 'prompt_v1.md'

sys.path.insert(0, str(REPO / 'huella_carbono'))
from medicion import MODOS, Medidor  # noqa: E402

MODULOS = sorted(p.stem for p in PAQUETE.glob('*.py'))

IGNORAR = shutil.ignore_patterns(
    '.git', '.github', '.venv', '.pytest_cache', '.mypy_cache', '.tox',
    '*.egg-info', '__pycache__', '.ropeproject', '.claude', 'rope_pruebas',
    'llm_pruebas', 'huella_carbono', 'profiling',
)

# El único test que revisa el formato del propio código de Black.
TEST_FORMATO = 'tests/test_black.py::BlackTestCase::test_piping'

# USD por millón de tokens: (input, output, escritura de caché de 1 h, lectura de caché)
PRECIOS = {
    'claude-opus-5-5': (4.00, 20.00, 8.00, 0.20),
    'claude-sonnet-5-5': (2.00, 10.00, 4.00, 0.20),
    'claude-haiku-5-5': (0.10, 0.50, 0.20, 0.01),
}

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


def correr_pytest(carpeta):
    """Corre pytest en `carpeta` y devuelve (resumen, salida completa)."""
    # PYTHONPATH tapa la instalación editable del .venv (que apunta al src/
    # del repositorio original). Sin -n: la suite corre en serie, igual que en
    # rope_pruebas/, para que la medición de energía sea comparable.
    env = dict(os.environ, PYTHONPATH=str(carpeta / 'src'))
    proc = subprocess.run(
        [PYTHON, '-m', 'pytest', 'tests', '-q', '-rsfE', '-p', 'no:cacheprovider'],
        cwd=carpeta, capture_output=True, text=True, env=env,
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
    resumen['fallidos'] = sorted(set(re.findall(r'^(?:FAILED|ERROR) (\S+?)(?: - |$)', salida, re.M)))
    return resumen, salida


def contexto_paquete():
    """Todos los módulos de src/black/ como bloques <archivo>."""
    partes = []
    for ruta in sorted(PAQUETE.glob('*.py')):
        rel = ruta.relative_to(REPO).as_posix()
        partes.append('<archivo ruta="%s">\n%s\n</archivo>' % (rel, ruta.read_text()))
    return 'Código actual del paquete black:\n\n' + '\n\n'.join(partes)


def extraer_codigo(texto):
    """Devuelve el bloque ```python más largo de la respuesta (o None).

    Las cercas ``` tienen que empezar en la columna 0. src/black/trans.py
    tiene ejemplos en Markdown dentro de sus docstrings (con ``` indentados);
    la versión de Cookiecutter aceptaba cercas en cualquier posición y cortaba
    el archivo en esos ejemplos.
    """
    bloques = re.findall(r'^```(?:python|py)?[ \t]*\n(.*?)^```[ \t]*$', texto, re.DOTALL | re.M)
    return max(bloques, key=len) if bloques else None


def costo(modelo, uso):
    precios = PRECIOS.get(modelo)
    if not precios:
        return None
    p_in, p_out, p_cw, p_cr = precios
    return round((uso['input'] * p_in + uso['output'] * p_out
                  + uso['cache_write'] * p_cw + uso['cache_read'] * p_cr) / 1e6, 4)


def clasificar_fallo(codigo, salida_pytest):
    try:
        compile(codigo, '<llm>', 'exec')
    except SyntaxError as e:
        return 'sintaxis: %s' % e
    if re.search(r'ImportError|cannot import name|has no attribute|'
                 r'error(s)? during collection', salida_pytest):
        return 'API rota (import/atributo)'
    return 'comportamiento'


def api_publica(codigo):
    """Nombres públicos de nivel de módulo y firmas de funciones/métodos públicos.

    Devuelve {nombre: firma} donde firma es la lista de parámetros (o 'valor'
    para asignaciones e imports, 'clase' para clases).
    """
    def firma(nodo):
        a = nodo.args
        partes = [p.arg for p in a.posonlyargs] + ['/'] * bool(a.posonlyargs)
        partes += [p.arg for p in a.args]
        partes += ['*' + a.vararg.arg] if a.vararg else (['*'] if a.kwonlyargs else [])
        partes += [p.arg for p in a.kwonlyargs]
        partes += ['**' + a.kwarg.arg] if a.kwarg else []
        return '(%s)' % ', '.join(partes)

    api = {}
    for nodo in ast.parse(codigo).body:
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            api[nodo.name] = firma(nodo)
        elif isinstance(nodo, ast.ClassDef):
            api[nodo.name] = 'clase'
            for hijo in nodo.body:
                if (isinstance(hijo, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and (not hijo.name.startswith('_') or hijo.name.startswith('__'))):
                    api['%s.%s' % (nodo.name, hijo.name)] = firma(hijo)
        elif isinstance(nodo, (ast.Assign, ast.AnnAssign)):
            objetivos = nodo.targets if isinstance(nodo, ast.Assign) else [nodo.target]
            for t in objetivos:
                if isinstance(t, ast.Name):
                    api[t.id] = 'valor'
        elif isinstance(nodo, (ast.Import, ast.ImportFrom)):
            for alias in nodo.names:
                api[(alias.asname or alias.name).split('.')[0]] = 'import'
    return {k: v for k, v in api.items() if not k.split('.')[0].startswith('_')}


def cambios_api(original, nuevo):
    """Lista de cambios en la API pública: eliminados y firmas distintas."""
    try:
        antes, despues = api_publica(original), api_publica(nuevo)
    except SyntaxError:
        return ['(no se pudo analizar: error de sintaxis)']
    cambios = []
    for nombre, f in sorted(antes.items()):
        if nombre not in despues:
            cambios.append('eliminado %s %s' % (f, nombre))
        elif despues[nombre] != f:
            cambios.append('firma %s: %s -> %s' % (nombre, f, despues[nombre]))
    return cambios


# ---------------------------------------------------------------------------
# Llamada al LLM
# ---------------------------------------------------------------------------

def es_error_de_red(e):
    # Un corte a mitad del streaming llega como excepción cruda del cliente
    # HTTP, sin envolver en anthropic.APIConnectionError.
    return (isinstance(e, (anthropic.APIConnectionError, OSError))
            or type(e).__module__.split('.')[0].startswith('httpx'))


def pedir_con_reintentos(cliente, args, sistema, contexto, modulo, medidor, intentos=4):
    """Como pedir_refactorizacion, pero reintenta ante errores de red."""
    for intento in range(1, intentos + 1):
        try:
            texto, meta = pedir_refactorizacion(cliente, args, sistema, contexto, modulo, medidor)
            meta['intentos'] = intento
            return texto, meta
        except Exception as e:
            if not es_error_de_red(e) or intento == intentos:
                raise
            espera = 30 * intento
            medidor.marcar('error_de_red', type(e).__name__)
            print('[%s] error de red (%s: %s), reintento %d en %ds'
                  % (modulo, type(e).__name__, e, intento, espera))
            time.sleep(espera)


def pedir_refactorizacion(cliente, args, sistema, contexto, modulo, medidor):
    """Envía el prompt general para `modulo` y devuelve (texto, metadatos).

    Recorre los eventos del streaming para marcar en eventos.csv cuándo llega
    el primer evento, cuándo empieza el razonamiento y cuándo el texto.
    """
    t0 = time.perf_counter()
    medidor.marcar('peticion_enviada')
    marcas = {}
    with cliente.beta.messages.stream(
        model=args.modelo,
        max_tokens=128000,
        system=sistema,
        output_config={'effort': args.effort},
        # Si el modelo rechaza la petición, la API la reintenta con otro
        # modelo; se registra en `modelo_respuesta` para poder detectarlo.
        betas=['server-side-fallback-2026-07-01'],
        fallbacks='default',
        messages=[{'role': 'user', 'content': [
            # Prefijo idéntico en todas las llamadas -> se reutiliza la caché.
            # TTL de 1 h: una respuesta larga más su pytest pueden pasar de los
            # 5 min de la caché por defecto, y reescribir ~216k tokens cuesta más.
            {'type': 'text', 'text': contexto,
             'cache_control': {'type': 'ephemeral', 'ttl': '1h'}},
            {'type': 'text', 'text': 'Refactoriza el archivo `src/black/%s.py`.' % modulo},
        ]}],
    ) as stream:
        for evento in stream:
            if 'primer_evento' not in marcas:
                marcas['primer_evento'] = time.perf_counter() - t0
                medidor.marcar('primer_evento', evento.type)
            if evento.type == 'content_block_start':
                tipo = evento.content_block.type
                clave = 'inicio_' + ('pensamiento' if tipo == 'thinking' else tipo)
                if clave not in marcas:
                    marcas[clave] = time.perf_counter() - t0
                    medidor.marcar(clave)
        respuesta = stream.get_final_message()
    medidor.marcar('fin_respuesta', respuesta.stop_reason)
    texto = ''.join(b.text for b in respuesta.content if b.type == 'text')
    u = respuesta.usage
    uso = {
        'input': u.input_tokens,
        'output': u.output_tokens,
        'cache_write': u.cache_creation_input_tokens or 0,
        'cache_read': u.cache_read_input_tokens or 0,
    }
    meta = {
        'modelo_respuesta': respuesta.model,
        'stop_reason': respuesta.stop_reason,
        'message_id': respuesta.id,
        'tiempo_llm_s': round(time.perf_counter() - t0, 1),
        'tiempos_stream_s': {k: round(v, 2) for k, v in marcas.items()},
        'tokens': uso,
        'costo_usd': costo(respuesta.model, uso),
    }
    return texto, meta


# ---------------------------------------------------------------------------
# Una corrida
# ---------------------------------------------------------------------------

def verificar_formato(carpeta, rel):
    """Pasa `black` por el archivo refactorizado y vuelve a correr la suite.

    Se formatea con la misma configuración que usa test_piping
    (tests/empty.toml, estilo estable). Sin --config, Black tomaría el
    pyproject.toml del proyecto, que usa `unstable = true`, y dejaría las
    construcciones que los dos estilos formatean distinto.
    """
    destino = TRABAJO / (carpeta.name + '_formateado')
    if destino.exists():
        shutil.rmtree(destino)
    shutil.copytree(carpeta, destino)
    subprocess.run([PYTHON, '-m', 'black', '-q', '--config', 'tests/empty.toml', rel],
                   cwd=destino, check=True)
    resumen, salida = correr_pytest(destino)
    return resumen, salida


def corrida(cliente, args, sistema, contexto, modulo, n, base, salida_dir, medidor):
    nombre = '%s_run%d' % (modulo, n)
    fila = {'id': nombre, 'modulo': modulo, 'corrida': n, 'carbono': {}}
    try:
        with medidor.medir(nombre + '_llm', fila['carbono'].setdefault('llm', {})):
            texto, meta = pedir_con_reintentos(cliente, args, sistema, contexto, modulo, medidor)
    except anthropic.APIStatusError as e:
        fila['veredicto'] = 'ERROR API %s' % e.status_code
        fila['detalle'] = str(e.message)
        print('[%s] %s' % (nombre, fila['veredicto']))
        return fila
    fila.update(meta)
    (salida_dir / (nombre + '_respuesta.md')).write_text(texto)
    return evaluar(fila, texto, base, salida_dir, medidor)


def evaluar(fila, texto, base, salida_dir, medidor, sufijo=''):
    """Aplica el código de la respuesta a una copia limpia y corre la suite.

    `sufijo` distingue en los CSV de carbono las fases de una reevaluación
    (--reevaluar) de las de la corrida original.
    """
    nombre, modulo, meta = fila['id'], fila['modulo'], fila
    if meta['stop_reason'] == 'refusal':
        fila['veredicto'] = 'RECHAZADA POR EL MODELO'
        print('[%s] %s' % (nombre, fila['veredicto']))
        return fila
    codigo = extraer_codigo(texto)
    if codigo is None:
        fila['veredicto'] = 'SIN CÓDIGO EN LA RESPUESTA'
        print('[%s] %s' % (nombre, fila['veredicto']))
        return fila

    rel = 'src/black/%s.py' % modulo
    original = (REPO / rel).read_text()
    (salida_dir / (nombre + '.py')).write_text(codigo)
    diff = ''.join(difflib.unified_diff(
        original.splitlines(True), codigo.splitlines(True),
        'a/' + rel, 'b/' + rel))
    (salida_dir / (nombre + '.diff')).write_text(diff)
    fila['lineas_agregadas'] = sum(1 for l in diff.splitlines()
                                   if l.startswith('+') and not l.startswith('+++'))
    fila['lineas_eliminadas'] = sum(1 for l in diff.splitlines()
                                    if l.startswith('-') and not l.startswith('---'))
    fila['sin_cambios'] = not diff
    fila['cambios_api_publica'] = cambios_api(original, codigo)

    carpeta = copia_limpia(nombre)
    (carpeta / rel).write_text(codigo)
    with medidor.medir(nombre + '_pytest' + sufijo, fila['carbono'].setdefault('pytest', {})):
        resumen, salida = correr_pytest(carpeta)
    (salida_dir / (nombre + '_pytest.txt')).write_text(salida)
    fila['tests'] = resumen
    igual = (resumen['passed'] == base['passed'] and resumen['failed'] == 0
             and resumen['errors'] == 0)
    if igual:
        fila['veredicto'] = 'COMPORTAMIENTO PRESERVADO'
    elif resumen['fallidos'] == [TEST_FORMATO] and resumen['errors'] == 0:
        with medidor.medir(nombre + '_pytest_formateado' + sufijo,
                           fila['carbono'].setdefault('pytest_formateado', {})):
            tras_black, salida_black = verificar_formato(carpeta, rel)
        (salida_dir / (nombre + '_formateado_pytest.txt')).write_text(salida_black)
        fila['tests_tras_black'] = tras_black
        ok = (tras_black['passed'] == base['passed'] and tras_black['failed'] == 0
              and tras_black['errors'] == 0)
        fila['veredicto'] = 'ROMPE TESTS (solo formato)' if ok else 'ROMPE TESTS'
        if not ok:
            fila['tipo_fallo'] = clasificar_fallo(codigo, salida)
    else:
        fila['veredicto'] = 'ROMPE TESTS'
        fila['tipo_fallo'] = clasificar_fallo(codigo, salida)
    if meta['stop_reason'] == 'max_tokens':
        fila['veredicto'] += ' (respuesta truncada)'
    e_llm = fila['carbono']['llm']['proceso']['energia_Wh'] * 1000
    print('[%s] %s  %s/%s  %ss  $%s  llm=%.1f mWh  api=%s' % (
        nombre, fila['veredicto'], resumen['passed'], resumen['failed'],
        meta['tiempo_llm_s'], meta['costo_usd'], e_llm,
        fila['cambios_api_publica'] or 'sin cambios'))
    return fila


# ---------------------------------------------------------------------------
# Reporte
# ---------------------------------------------------------------------------

def determinismo(filas, salida_dir):
    """Cuántos diffs distintos produjo cada módulo entre sus corridas."""
    res = {}
    for modulo in sorted({f['modulo'] for f in filas}):
        diffs = [(salida_dir / (f['id'] + '.diff')).read_text()
                 for f in filas if f['modulo'] == modulo
                 and (salida_dir / (f['id'] + '.diff')).exists()]
        res[modulo] = {'corridas': len(diffs), 'diffs_distintos': len(set(diffs))}
    return res


def mwh(med, fase, modo='proceso'):
    """Energía en mWh de una fase de la corrida (o None si no se midió)."""
    d = med.get(fase, {}).get(modo)
    return d['energia_Wh'] * 1000 if d else None


def mg(med, fase, modo='proceso'):
    d = med.get(fase, {}).get(modo)
    return d['emisiones_mgCO2eq'] if d else None


def f1(valor):
    return '—' if valor is None else '%.1f' % valor


def escribir_resumen(args, base, filas, salida_dir, info, referencias):
    det = determinismo(filas, salida_dir)
    total = sum(f.get('costo_usd') or 0 for f in filas)
    lineas = [
        '# Resumen de pruebas con LLM (prompt general) — Black', '',
        '- Python: `%s`' % sys.version.split()[0],
        '- SDK anthropic: `%s`' % anthropic.__version__,
        '- Modelo solicitado: `%s` (effort `%s`)' % (args.modelo, args.effort),
        '- Prompt: `%s`' % PROMPT.name,
        '- Corridas por módulo: %d' % args.corridas,
        '- Fecha: %s' % time.strftime('%Y-%m-%d %H:%M'),
        '- Costo total estimado: US$ %.2f' % total, '',
        '## Línea base', '',
        '%(passed)d passed, %(failed)d failed, %(skipped)d skipped, %(errors)d errors' % base, '',
        '## Corridas', '',
        '| Corrida | Modelo | +/− líneas | Tests (passed/failed/errors) | Veredicto | Tipo de fallo | Cambios API pública | Tiempo (s) | Tokens salida | Costo (US$) |',
        '|---|---|---|---|---|---|---|---|---|---|',
    ]
    for f in filas:
        t = f.get('tests')
        tests = '%d / %d / %d' % (t['passed'], t['failed'], t['errors']) if t else '—'
        lineas_diff = ('+%d / −%d' % (f['lineas_agregadas'], f['lineas_eliminadas'])
                       if 'lineas_agregadas' in f else '—')
        api = '; '.join(f.get('cambios_api_publica') or []) or '—'
        lineas.append('| %s | %s | %s | %s | **%s** | %s | %s | %s | %s | %s |' % (
            f['id'], f.get('modelo_respuesta', '—'), lineas_diff, tests,
            f['veredicto'], f.get('tipo_fallo', ''), api, f.get('tiempo_llm_s', '—'),
            f.get('tokens', {}).get('output', '—'), f.get('costo_usd', '—')))
    lineas += ['', '## Determinismo', '',
               '| Módulo | Corridas | Diffs distintos |', '|---|---|---|']
    for modulo, d in det.items():
        lineas.append('| %s | %d | %d |' % (modulo, d['corridas'], d['diffs_distintos']))
    lineas += ['', 'Las refactorizaciones que el modelo dice haber aplicado están al final '
               'de cada `<corrida>_respuesta.md`. La energía y las emisiones están en '
               '`carbono/huella_carbono.md`.', '']
    (salida_dir / 'resumen.md').write_text('\n'.join(lineas))

    # Huella de carbono.
    L = [
        '# Huella de carbono del experimento con LLM (Black)', '',
        '- CodeCarbon: `%s` (`OfflineEmissionsTracker`)' % info['codecarbon'],
        '- País (factor de emisión de la red): %s (`%s`), %s gCO2eq/kWh'
        % (info['pais'], info['pais_iso'], info['intensidad_gCO2eq_kWh']),
        '- CPU: %s, %d hilos, RAM %s GB, %s' % (info['cpu'], info['cpu_count'],
                                                 info['ram_GB'], info['os']),
        '- Método de CPU: %s' % info['metodo_cpu'],
        '- Intervalo de muestreo: %s s' % info['intervalo_muestreo_s'], '',
        '**Solo se mide esta computadora.** La energía de los servidores de Anthropic '
        'que generan la respuesta no está incluida; para estimarla están los tokens '
        'de cada llamada en `resumen.json`.', '',
        'Lo que pasa **durante** cada llamada está en `serie_temporal_maquina.csv`, '
        '`serie_temporal_proceso.csv` y `eventos.csv` (`peticion_enviada`, '
        '`primer_evento`, `inicio_pensamiento`, `inicio_text`, `fin_respuesta`).', '',
        '## Fases de referencia', '',
        '| Fase | Duración (s) | Energía máquina (mWh) | Emisiones máquina (mg) | Energía proceso (mWh) | Emisiones proceso (mg) |',
        '|---|---|---|---|---|---|',
    ]
    for nombre, med in referencias:
        if not med:
            continue
        m, p = med['maquina'], med['proceso']
        L.append('| %s | %.1f | %.1f | %.2f | %.1f | %.2f |' % (
            nombre, m['duracion_s'], m['energia_Wh'] * 1000, m['emisiones_mgCO2eq'],
            p['energia_Wh'] * 1000, p['emisiones_mgCO2eq']))
    L += ['', '## Por corrida (modo proceso)', '',
          '| Corrida | Veredicto | Tiempo LLM (s) | Energía local durante la llamada (mWh) | Emisiones (mg) | Potencia media (W) | Energía pytest (mWh) | Emisiones pytest (mg) |',
          '|---|---|---|---|---|---|---|---|']
    tot = {'llm_mWh': 0, 'llm_mg': 0, 'py_mWh': 0, 'py_mg': 0, 'llm_s': 0,
           'llm_maquina_mWh': 0, 'llm_maquina_mg': 0}
    for f in filas:
        med = f.get('carbono', {})
        e_llm, e_py = mwh(med, 'llm'), mwh(med, 'pytest')
        d_llm = med.get('llm', {}).get('proceso')
        if d_llm:
            tot['llm_mWh'] += e_llm
            tot['llm_mg'] += mg(med, 'llm')
            tot['llm_s'] += d_llm['duracion_s']
            tot['llm_maquina_mWh'] += mwh(med, 'llm', 'maquina')
            tot['llm_maquina_mg'] += mg(med, 'llm', 'maquina')
        for fase in ('pytest', 'pytest_formateado'):
            if mwh(med, fase) is not None:
                tot['py_mWh'] += mwh(med, fase)
                tot['py_mg'] += mg(med, fase)
        potencia = (d_llm['energia_Wh'] * 3600 / d_llm['duracion_s']) if d_llm and d_llm['duracion_s'] else None
        L.append('| %s | %s | %s | %s | %s | %s | %s | %s |' % (
            f['id'], f['veredicto'], f.get('tiempo_llm_s', '—'), f1(e_llm), f1(mg(med, 'llm')),
            '—' if potencia is None else '%.2f' % potencia, f1(e_py), f1(mg(med, 'pytest'))))
    L += ['', '## Totales', '',
          '| Concepto | Tiempo (s) | Energía proceso (mWh) | Emisiones proceso (mg) | Energía máquina (mWh) | Emisiones máquina (mg) |',
          '|---|---|---|---|---|---|',
          '| Esperar las %d respuestas de Claude (solo lo local) | %.0f | %.1f | %.2f | %.1f | %.2f |' % (
              len(filas), tot['llm_s'], tot['llm_mWh'], tot['llm_mg'],
              tot['llm_maquina_mWh'], tot['llm_maquina_mg']),
          '| Verificar con pytest | — | %.1f | %.2f | — | — |' % (tot['py_mWh'], tot['py_mg']),
          '']
    (salida_dir / 'carbono' / 'huella_carbono.md').write_text('\n'.join(L))

    (salida_dir / 'resumen.json').write_text(json.dumps(
        {'python': sys.version.split()[0], 'anthropic': anthropic.__version__,
         'modelo': args.modelo, 'effort': args.effort, 'prompt': PROMPT.read_text(),
         'linea_base': base, 'determinismo': det, 'costo_total_usd': round(total, 4),
         'carbono': {'info': info, 'referencias': dict(referencias), 'totales': tot},
         'corridas': filas},
        indent=2, ensure_ascii=False))


def estimar(cliente, args, sistema, contexto):
    """Estimación de costo sin generar nada (count_tokens es gratis)."""
    n_ctx = cliente.messages.count_tokens(
        model=args.modelo, system=sistema,
        messages=[{'role': 'user', 'content': contexto}]).input_tokens
    p_in, p_out, p_cw, p_cr = PRECIOS[args.modelo]
    salida = 0
    for modulo in args.modulos:
        texto = (PAQUETE / (modulo + '.py')).read_text() or ' '
        salida += cliente.messages.count_tokens(
            model=args.modelo, messages=[{'role': 'user', 'content': texto}]).input_tokens
    llamadas = len(args.modulos) * args.corridas
    salida_total = salida * args.corridas
    costo_ctx = (n_ctx * p_cw + n_ctx * p_cr * (llamadas - 1)) / 1e6
    costo_salida = salida_total * p_out / 1e6
    print('Contexto: %d tokens. %d llamadas. Salida mínima (archivos completos): %d tokens.'
          % (n_ctx, llamadas, salida_total))
    print('Costo mínimo estimado: US$ %.2f (contexto %.2f + salida %.2f), '
          'sin contar los tokens de razonamiento.' % (costo_ctx + costo_salida, costo_ctx, costo_salida))


def reevaluar(args, carpeta, ids):
    """Repite la evaluación de corridas ya pagadas a partir de su respuesta guardada."""
    salida_dir = RESULTADOS / carpeta
    previo = json.loads((salida_dir / 'resumen.json').read_text())
    args.modelo, args.effort = previo['modelo'], previo['effort']
    args.corridas = max(f['corrida'] for f in previo['corridas'])
    base = previo['linea_base']
    info = previo['carbono']['info']
    referencias = list(previo['carbono']['referencias'].items())
    medidor = Medidor(salida_dir / 'carbono', pais=info['pais_iso'])
    filas = previo['corridas']
    for i, fila in enumerate(filas):
        if fila['id'] not in ids:
            continue
        anterior = {k: fila.get(k) for k in ('veredicto', 'tipo_fallo', 'tests')}
        for clave in ('tipo_fallo', 'tests_tras_black'):
            fila.pop(clave, None)
        fila['carbono'] = {'llm': fila['carbono']['llm']}
        texto = (salida_dir / (fila['id'] + '_respuesta.md')).read_text()
        filas[i] = evaluar(fila, texto, base, salida_dir, medidor, sufijo='_reevaluacion')
        filas[i]['reevaluacion'] = {'fecha': time.strftime('%Y-%m-%d %H:%M'),
                                    'motivo': 'extractor de código corregido (cercas ``` en columna 0)',
                                    'resultado_anterior': anterior}
    escribir_resumen(args, base, filas, salida_dir, info, referencias)
    print('\nResultados en %s' % salida_dir)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--modelo', default='claude-sonnet-5-5')
    parser.add_argument('--effort', default='high',
                        choices=['low', 'medium', 'high', 'xhigh', 'max'])
    parser.add_argument('--corridas', type=int, default=3)
    parser.add_argument('--modulos', nargs='+', default=MODULOS, choices=MODULOS)
    parser.add_argument('--pais', default='COL',
                        help='código ISO-3 del país para el factor de emisión (por defecto COL)')
    parser.add_argument('--dry-run', action='store_true',
                        help='muestra el prompt y estima el costo sin generar nada')
    parser.add_argument('--reevaluar', nargs='+', metavar=('CARPETA', 'CORRIDA'),
                        help='vuelve a extraer el código de las respuestas ya guardadas en '
                             'resultados/CARPETA y repite los tests de las CORRIDAS indicadas, '
                             'sin llamar a la API')
    parser.add_argument('--reanudar', metavar='CARPETA',
                        help='continúa una ejecución interrumpida en resultados/CARPETA, '
                             'sin repetir (ni volver a pagar) las corridas ya hechas')
    args = parser.parse_args()

    sistema = PROMPT.read_text()
    contexto = contexto_paquete()
    cliente = anthropic.Anthropic()
    if args.dry_run:
        print('=== SYSTEM ===\n%s\n=== USER ===\n%s...\n\nRefactoriza el archivo '
              '`src/black/%s.py`.\n' % (sistema, contexto[:500], args.modulos[0]))
        estimar(cliente, args, sistema, contexto)
        return

    if args.reevaluar:
        reevaluar(args, args.reevaluar[0], args.reevaluar[1:])
        return

    filas = []
    if args.reanudar:
        salida_dir = RESULTADOS / args.reanudar
        previo = json.loads((salida_dir / 'resumen.json').read_text())
        assert previo['prompt'] == sistema, 'el prompt cambió desde la ejecución original'
        assert (previo['modelo'], previo['effort']) == (args.modelo, args.effort)
        filas = [f for f in previo['corridas'] if not f['veredicto'].startswith('ERROR')]
        print('[reanudar] %d corridas ya hechas en %s' % (len(filas), salida_dir))
    else:
        salida_dir = RESULTADOS / time.strftime('%Y%m%d_%H%M%S')
        salida_dir.mkdir(parents=True)
        (salida_dir / 'prompt.md').write_text(sistema)
    hechas = {f['id'] for f in filas}

    medidor = Medidor(salida_dir / 'carbono', pais=args.pais)
    info = medidor.info()
    med_reposo, med_base = {}, {}
    with medidor.medir('reposo', med_reposo):
        time.sleep(SEGUNDOS_REPOSO)
    print('[reposo] %d s  proceso=%.1f mWh' % (SEGUNDOS_REPOSO, med_reposo['proceso']['energia_Wh'] * 1000))

    carpeta = copia_limpia('00_linea_base')
    with medidor.medir('00_linea_base_pytest', med_base):
        base, salida = correr_pytest(carpeta)
    (salida_dir / '00_linea_base_pytest.txt').write_text(salida)
    print('[linea base] %s' % {k: v for k, v in base.items() if k != 'fallidos'})
    referencias = [('Reposo (%d s sin hacer nada)' % SEGUNDOS_REPOSO, med_reposo),
                   ('Línea base: pytest original', med_base)]

    for modulo in args.modulos:
        for n in range(1, args.corridas + 1):
            if '%s_run%d' % (modulo, n) in hechas:
                continue
            filas.append(corrida(cliente, args, sistema, contexto, modulo, n, base,
                                 salida_dir, medidor))
            escribir_resumen(args, base, filas, salida_dir, info, referencias)
    escribir_resumen(args, base, filas, salida_dir, info, referencias)
    print('\nResultados en %s' % salida_dir)


if __name__ == '__main__':
    main()

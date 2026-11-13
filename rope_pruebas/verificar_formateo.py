"""Verifica si un fallo de test_piping es solo de formato.

`tests/test_black.py::BlackTestCase::test_piping` formatea el propio
src/black/__init__.py y exige que ya esté formateado con Black. Rope no
reformatea el código que genera, así que cualquier refactorización de
__init__.py puede romper ese test sin cambiar el comportamiento.

Para cada caso de CASOS, este script toma la copia que dejó
ejecutar_pruebas_rope.py en _trabajo/<caso>, la duplica en
_trabajo/<caso>_formateado, pasa Black (el del .venv) por los archivos que
Rope modificó y vuelve a correr la suite completa.

Uso (después de ejecutar_pruebas_rope.py, desde la raíz del repositorio):
    .venv/bin/python rope_pruebas/verificar_formateo.py
"""
import json
import shutil
import subprocess
import sys

from ejecutar_pruebas_rope import RESULTADOS, TRABAJO, correr_pytest

PYTHON = sys.executable
CASOS = ['06b_rename_parametro_posicional', '07_extract_cache',
         '08_extract_stdin', '12_move_funcion']


def main():
    filas = {f['id']: f for f in json.loads((RESULTADOS / 'resumen.json').read_text())['refactorizaciones']}
    lineas = ['# Verificación: ¿el fallo de `test_piping` es solo de formato?', '',
              'Copia refactorizada por Rope → `black` sobre los archivos modificados → suite completa.', '',
              '| # | Archivos formateados | Tests con la salida de Rope | Tests después de `black` |',
              '|---|---|---|---|']
    for caso in CASOS:
        origen, destino = TRABAJO / caso, TRABAJO / (caso + '_formateado')
        if destino.exists():
            shutil.rmtree(destino)
        shutil.copytree(origen, destino)
        archivos = [a for a in filas[caso]['archivos_modificados'] if a.startswith('src/')]
        # Misma configuración que test_piping (estilo estable); sin --config,
        # Black tomaría el `unstable = true` del pyproject.toml del proyecto.
        opciones = ['--config', 'tests/empty.toml']
        cambio = subprocess.run([PYTHON, '-m', 'black', '--diff', '-q', *opciones, *archivos],
                                cwd=destino, capture_output=True, text=True).stdout
        (RESULTADOS / (caso + '_black.diff')).write_text(cambio)
        subprocess.run([PYTHON, '-m', 'black', '-q', *opciones, *archivos], cwd=destino, check=True)
        resumen, salida = correr_pytest(destino)
        (RESULTADOS / (caso + '_formateado_pytest.txt')).write_text(salida)
        antes = filas[caso]['tests']
        lineas.append('| %s | %s | %d / %d | %d / %d |' % (
            caso, ', '.join('`%s`' % a for a in archivos), antes['passed'], antes['failed'],
            resumen['passed'], resumen['failed']))
        print('[%s] antes %d/%d  después de black %d/%d' % (
            caso, antes['passed'], antes['failed'], resumen['passed'], resumen['failed']))
    lineas.append('')
    (RESULTADOS / 'formateo_posterior.md').write_text('\n'.join(lineas))


if __name__ == '__main__':
    main()

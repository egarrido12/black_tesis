"""Clasifica los avisos de find_errors de resultados/01_analisis_estatico.md.

Con 852 avisos no es práctico revisarlos uno por uno (como en Cookiecutter,
39 avisos). Cada aviso se asigna a la primera regla que cumple, mirando la
línea de código señalada en la copia _trabajo/01_analisis. Los que no cumplen
ninguna regla quedan como "sin clasificar" y se revisan a mano.

Uso (después de ejecutar_pruebas_rope.py, desde la raíz del repositorio):
    .venv/bin/python rope_pruebas/clasificar_find_errors.py
"""
import ast
import collections
import json
import re

from ejecutar_pruebas_rope import RESULTADOS, TRABAJO

COPIA = TRABAJO / '01_analisis'


def parametros_keyword_only(arbol):
    """{(lineno de cada línea de la función): nombres keyword-only}."""
    mapa = collections.defaultdict(set)
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            nombres = {a.arg for a in nodo.args.kwonlyargs}
            if nombres:
                for linea in range(nodo.lineno, nodo.end_lineno + 1):
                    mapa[linea] |= nombres
    return mapa


def variables_de_comprension(arbol):
    """{lineno: nombres ligados por comprensiones o lambdas que abarcan esa línea}."""
    mapa = collections.defaultdict(set)
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Lambda):
            nombres = {a.arg for a in nodo.args.args}
            for linea in range(nodo.lineno, nodo.end_lineno + 1):
                mapa[linea] |= nombres
        if isinstance(nodo, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            nombres = {n.id for g in nodo.generators for n in ast.walk(g.target)
                       if isinstance(n, ast.Name)}
            for linea in range(nodo.lineno, nodo.end_lineno + 1):
                mapa[linea] |= nombres
    return mapa


def clasificar(linea, tipo, nombre, kwonly, comp):
    if nombre in comp:
        return 'Variable de comprensión, generador o lambda'
    if nombre == '__file__':
        return 'Variable implícita de módulo (`__file__`)'
    if nombre in kwonly:
        return 'Parámetro keyword-only (después de `*`)'
    if tipo == 'Unresolved attribute' and re.search(r'\bsyms\.%s\b' % nombre, linea):
        return 'Atributo dinámico de `syms` (gramática de blib2to3, creado con setattr)'
    if tipo == 'Unresolved attribute' and re.search(r'\btoken\.%s\b' % nombre, linea):
        return 'Atributo de `token` (constantes generadas)'
    if tipo == 'Unresolved attribute':
        return 'Otro atributo no resuelto (tipos de terceros, uniones, objetos dinámicos)'
    if tipo == 'Defined later':
        return 'Otro "Defined later" (variable asignada en un bucle o en otra rama antes de leerse)'
    return 'Otra variable no resuelta'


def main():
    texto = (RESULTADOS / '01_analisis_estatico.md').read_text()
    avisos = re.findall(r'^- `([^`]+):(\d+)` — (Unresolved attribute|Unresolved variable|Defined later) (\w+)$',
                        texto, re.M)
    cache = {}
    categorias = collections.Counter()
    ejemplos = collections.defaultdict(list)
    for archivo, lineno, tipo, nombre in avisos:
        if archivo not in cache:
            codigo = (COPIA / archivo).read_text()
            arbol = ast.parse(codigo)
            cache[archivo] = (codigo.splitlines(), parametros_keyword_only(arbol),
                              variables_de_comprension(arbol))
        lineas, kwonly, comp = cache[archivo]
        n = int(lineno)
        cat = clasificar(lineas[n - 1], tipo, nombre, kwonly[n], comp[n])
        categorias[cat] += 1
        if len(ejemplos[cat]) < 3:
            ejemplos[cat].append('`%s:%s` (%s `%s`)' % (archivo.replace('src/black/', ''), lineno, tipo, nombre))

    salida = ['# Clasificación de los avisos de find_errors', '',
              'Total: %d avisos.' % len(avisos), '',
              '| Categoría | Cant. | Ejemplos |', '|---|---|---|']
    for cat, cant in categorias.most_common():
        salida.append('| %s | %d | %s |' % (cat, cant, ', '.join(ejemplos[cat])))
    salida.append('')
    (RESULTADOS / '01b_clasificacion_find_errors.md').write_text('\n'.join(salida))
    print('\n'.join(salida))
    return json.dumps(categorias)


if __name__ == '__main__':
    main()

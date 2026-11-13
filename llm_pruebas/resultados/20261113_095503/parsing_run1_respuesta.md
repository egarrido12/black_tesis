```python
"""
Parse Python code and perform AST validation.
"""

import ast
import sys
import warnings
from collections.abc import Collection, Iterator

from black.mode import VERSION_TO_FEATURES, Feature, TargetVersion, supports_feature
from black.nodes import syms
from blib2to3 import pygram
from blib2to3.pgen2 import driver
from blib2to3.pgen2.grammar import Grammar
from blib2to3.pgen2.parse import ParseError
from blib2to3.pgen2.tokenize import TokenError
from blib2to3.pytree import Leaf, Node

_INDENT = "    "


class InvalidInput(ValueError):
    """Raised when input source code fails all parse attempts."""

    lineno: int | None = None
    column: int | None = None
    context: str | None = None
    details: str | None = None

    def __init__(
        self,
        message: str,
        lineno: int | None = None,
        column: int | None = None,
        context: str | None = None,
        details: str | None = None,
    ) -> None:
        super().__init__(message, lineno, column, context, details)
        self.lineno = lineno
        self.column = column
        self.context = context
        self.details = details

    def __str__(self) -> str:
        return str(self.args[0])


def get_grammars(target_versions: set[TargetVersion]) -> list[Grammar]:
    if not target_versions:
        # No target_version specified, so try all grammars.
        return [
            # Python 3.7-3.9
            pygram.python_grammar_async_keywords,
            # Python 3.0-3.6
            pygram.python_grammar,
            # Python 3.10+
            pygram.python_grammar_soft_keywords,
        ]

    grammars = []
    # If we have to parse both, try to parse async as a keyword first
    if not supports_feature(
        target_versions, Feature.ASYNC_IDENTIFIERS
    ) and not supports_feature(target_versions, Feature.PATTERN_MATCHING):
        # Python 3.7-3.9
        grammars.append(pygram.python_grammar_async_keywords)
    if not supports_feature(target_versions, Feature.ASYNC_KEYWORDS):
        # Python 3.0-3.6
        grammars.append(pygram.python_grammar)
    if any(Feature.PATTERN_MATCHING in VERSION_TO_FEATURES[v] for v in target_versions):
        # Python 3.10+
        grammars.append(pygram.python_grammar_soft_keywords)

    # At least one of the above branches must have been taken, because every Python
    # version has exactly one of the two 'ASYNC_*' flags
    return grammars


def _target_version_suffix(target_versions: Collection[TargetVersion]) -> str:
    """Describe the newest target version for use in error messages."""
    if not target_versions:
        return ""
    max_tv = max(target_versions, key=lambda tv: tv.value)
    return f" for target version {max_tv.pretty()}"


def _get_faulty_line(src_txt: str, lineno: int) -> str:
    lines = src_txt.splitlines()
    try:
        return lines[lineno - 1]
    except IndexError:
        return "<line number missing in source>"


def _make_invalid_input(
    src_txt: str,
    lineno: int,
    column: int,
    target_version_suffix: str,
    error_description: str,
) -> InvalidInput:
    """Build the `InvalidInput` for a failed parse attempt.

    `error_description` is the last line of the details, e.g. "ParseError: ...".
    """
    faulty_line = _get_faulty_line(src_txt, lineno)
    context = f"cannot parse{target_version_suffix}"
    details = "\n".join((
        "",
        f"    {faulty_line}",
        f"    {' ' * (column - 1)}^",
        error_description,
    ))
    error_msg = f"{context}: {lineno}:{column}{details}"
    return InvalidInput(error_msg, lineno, column, context, details)


def lib2to3_parse(
    src_txt: str, target_versions: Collection[TargetVersion] = ()
) -> Node:
    """Given a string with source, return the lib2to3 Node."""
    if not src_txt.endswith("\n"):
        src_txt += "\n"

    grammars = get_grammars(set(target_versions))
    tv_str = _target_version_suffix(target_versions)

    errors = {}
    for grammar in grammars:
        drv = driver.Driver(grammar)
        try:
            result = drv.parse_string(src_txt, False)
            break

        except ParseError as pe:
            lineno, column = pe.context[1]
            errors[grammar.version] = _make_invalid_input(
                src_txt, lineno, column, tv_str, f"ParseError: {pe.msg}"
            )

        except TokenError as te:
            lineno, column = te.args[1]
            errors[grammar.version] = _make_invalid_input(
                src_txt, lineno, column, tv_str, f"TokenError: {te.args[0]}"
            )

    else:
        # Choose the latest version when raising the actual parsing error.
        assert len(errors) >= 1
        exc = errors[max(errors)]
        raise exc from None

    if isinstance(result, Leaf):
        result = Node(syms.file_input, [result])
    return result


class ASTSafetyError(Exception):
    """Raised when Black's generated code is not equivalent to the old AST."""


class SourceASTParseError(Exception):
    """Raised when the source file cannot be parsed by ast.parse().

    This is not a bug in Black — Black's lib2to3-based parser is more lenient
    than Python's ast.parse(), so it may accept code that ast.parse() rejects.
    In blackd, this should be reported as a 400 Bad Request.
    """


def _parse_single_version(
    src: str, version: tuple[int, int], *, type_comments: bool
) -> ast.AST:
    filename = "<unknown>"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        warnings.simplefilter("ignore", DeprecationWarning)
        return ast.parse(
            src, filename, feature_version=version, type_comments=type_comments
        )


def _parse_with_first_working_version(
    src: str, versions: list[tuple[int, int]], *, type_comments: bool
) -> tuple[ast.AST | None, str]:
    """Try `versions` in order and return `(tree, first_error_message)`.

    `tree` is None when every version fails to parse.
    """
    first_error = ""
    for version in versions:
        try:
            return _parse_single_version(src, version, type_comments=type_comments), (
                first_error
            )
        except SyntaxError as e:
            if not first_error:
                first_error = str(e)
    return None, first_error


def parse_ast(src: str) -> ast.AST:
    # TODO: support Python 4+ ;)
    # Newest version first.
    versions = sorted(
        ((3, minor) for minor in range(3, sys.version_info[1] + 1)), reverse=True
    )

    tree, first_error = _parse_with_first_working_version(
        src, versions, type_comments=True
    )
    if tree is not None:
        return tree

    # Try to parse without type comments
    tree, _ = _parse_with_first_working_version(src, versions, type_comments=False)
    if tree is not None:
        return tree

    raise SyntaxError(first_error)


def _normalize(lineend: str, value: str) -> str:
    # To normalize, we strip any leading and trailing space from
    # each line...
    stripped: list[str] = [i.strip() for i in value.splitlines()]
    normalized = lineend.join(stripped)
    # ...and remove any blank lines at the beginning and end of
    # the whole string
    return normalized.strip()


def stringify_ast(node: ast.AST) -> Iterator[str]:
    """Simple visitor generating strings to compare ASTs by content."""
    return _stringify_ast(node, [])


def _stringify_ast_with_new_parent(
    node: ast.AST, parent_stack: list[ast.AST], new_parent: ast.AST
) -> Iterator[str]:
    parent_stack.append(new_parent)
    yield from _stringify_ast(node, parent_stack)
    parent_stack.pop()


def _drop_unicode_kind(node: ast.AST) -> None:
    """Remove the `u` string prefix marker, which doesn't affect equivalence."""
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.kind == "u"
    ):
        # It's a quirk of history that we strip the u prefix over here. We used to
        # rewrite the AST nodes for Python version compatibility and we never copied
        # over the kind
        node.kind = None


def _fields_to_compare(node: ast.AST) -> list[str]:
    # TypeIgnore has only one field 'lineno' which breaks this comparison
    if isinstance(node, ast.TypeIgnore):
        return []
    return sorted(node._fields)


def _stringify_list_field(
    node: ast.AST, field: str, items: list[object], parent_stack: list[ast.AST]
) -> Iterator[str]:
    for item in items:
        # Ignore nested tuples within del statements, because we may insert
        # parentheses and they change the AST.
        if field == "targets" and isinstance(node, ast.Delete) and isinstance(
            item, ast.Tuple
        ):
            for elt in _unwrap_tuples(item):
                yield from _stringify_ast_with_new_parent(elt, parent_stack, node)

        elif isinstance(item, ast.AST):
            yield from _stringify_ast_with_new_parent(item, parent_stack, node)


def _normalize_field_value(
    node: ast.AST, field: str, value: object, parent_stack: list[ast.AST]
) -> object:
    if (
        isinstance(node, ast.Constant)
        and field == "value"
        and isinstance(value, str)
        and len(parent_stack) >= 2
        # Any standalone string, ideally this would
        # exactly match black.nodes.is_docstring
        and isinstance(parent_stack[-1], ast.Expr)
    ):
        # Constant strings may be indented across newlines, if they are
        # docstrings; fold spaces after newlines when comparing. Similarly,
        # trailing and leading space may be removed.
        return _normalize("\n", value)
    if field == "type_comment" and isinstance(value, str):
        # Trailing whitespace in type comments is removed.
        return value.rstrip()
    return value


def _stringify_ast(node: ast.AST, parent_stack: list[ast.AST]) -> Iterator[str]:
    _drop_unicode_kind(node)

    indent = _INDENT * len(parent_stack)
    field_indent = indent + _INDENT
    node_name = node.__class__.__name__

    yield f"{indent}{node_name}("

    for field in _fields_to_compare(node):
        try:
            value: object = getattr(node, field)
        except AttributeError:
            continue

        yield f"{field_indent}{field}="

        if isinstance(value, list):
            yield from _stringify_list_field(node, field, value, parent_stack)

        elif isinstance(value, ast.AST):
            yield from _stringify_ast_with_new_parent(value, parent_stack, node)

        else:
            normalized = _normalize_field_value(node, field, value, parent_stack)
            yield f"{field_indent}{normalized!r},  # {value.__class__.__name__}"

    yield f"{indent})  # /{node_name}"


def _unwrap_tuples(node: ast.Tuple) -> Iterator[ast.AST]:
    for elt in node.elts:
        if isinstance(elt, ast.Tuple):
            yield from _unwrap_tuples(elt)
        else:
            yield elt
```

## Refactorizaciones aplicadas

- **Extract Method** (`_make_invalid_input`, `_get_faulty_line`, `_target_version_suffix`), en `lib2to3_parse`: los manejadores de `ParseError` y `TokenError` eran casi idénticos. Repetían la obtención de la línea defectuosa, la construcción de `context`, `details` y `error_msg`, y la creación de `InvalidInput`. Ahora cada `except` solo extrae `lineno`/`column` y el texto de error propio. El cálculo del sufijo "for target version X" también salió a su propia función.
- **Extract Method** (`_parse_with_first_working_version`), en `parse_ast`: los dos bucles de intentos por versión, con y sin `type_comments`, se unificaron en un helper. El helper conserva la semántica de `first_error`, incluido el caso en que un mensaje vacío se reemplaza por el siguiente error.
- **Remove Duplication / Introduce Explaining Variable** (`versions` ordenado una sola vez), en `parse_ast`: la lista se ordena una vez en orden descendente, en lugar de llamar a `sorted(..., reverse=True)` en cada bucle.
- **Extract Method** (`_drop_unicode_kind`, `_fields_to_compare`, `_stringify_list_field`, `_normalize_field_value`), en `_stringify_ast`: la función mezclaba normalización del prefijo `u`, selección de campos, tratamiento de listas (incluido el caso especial de `del` con tuplas) y normalización de valores de docstrings y type comments. Cada responsabilidad tiene ahora un nombre propio.
- **Replace Nested Conditional with Guard / Simplify Loop** (`_fields_to_compare`): el `break` dentro del bucle por ser `TypeIgnore` se reemplazó por devolver una lista vacía de campos. El resultado es el mismo, porque el `break` se ejecutaba antes de emitir nada.
- **Introduce Explaining Variable / Replace Magic Literal** (`indent`, `field_indent`, `node_name`, `_INDENT`): se eliminaron las repeticiones de `"    " * len(parent_stack)` y de `node.__class__.__name__`. El texto emitido es idéntico, incluida la concatenación `"#" " {tipo}"`, que ahora es `"# {tipo}"`.

Se mantuvieron sin cambios los nombres y firmas públicos (`InvalidInput`, `get_grammars`, `lib2to3_parse`, `ASTSafetyError`, `SourceASTParseError`, `parse_ast`, `stringify_ast`) y los helpers privados existentes (`_parse_single_version`, `_normalize`, `_stringify_ast`, `_stringify_ast_with_new_parent`, `_unwrap_tuples`). Los imports y las dependencias no cambian.
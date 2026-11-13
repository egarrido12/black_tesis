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
_MISSING_LINE_PLACEHOLDER = "<line number missing in source>"


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
    """Return the " for target version ..." fragment used in parse error messages."""
    if not target_versions:
        return ""
    max_tv = max(target_versions, key=lambda tv: tv.value)
    return f" for target version {max_tv.pretty()}"


def _make_invalid_input(
    src_txt: str,
    lineno: int,
    column: int,
    context: str,
    error_description: str,
) -> InvalidInput:
    """Build an `InvalidInput` pointing at `lineno`:`column` of `src_txt`."""
    lines = src_txt.splitlines()
    try:
        faulty_line = lines[lineno - 1]
    except IndexError:
        faulty_line = _MISSING_LINE_PLACEHOLDER
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
    context = f"cannot parse{_target_version_suffix(target_versions)}"

    errors = {}
    for grammar in grammars:
        drv = driver.Driver(grammar)
        try:
            result = drv.parse_string(src_txt, False)
            break

        except ParseError as pe:
            lineno, column = pe.context[1]
            errors[grammar.version] = _make_invalid_input(
                src_txt, lineno, column, context, f"ParseError: {pe.msg}"
            )

        except TokenError as te:
            lineno, column = te.args[1]
            errors[grammar.version] = _make_invalid_input(
                src_txt, lineno, column, context, f"TokenError: {te.args[0]}"
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
    """Try each of `versions` in order and return `(tree, first_error)`.

    `tree` is None if every version failed. `first_error` is the message of the
    first SyntaxError encountered (empty if there was none).
    """
    first_error = ""
    for version in versions:
        try:
            return (
                _parse_single_version(src, version, type_comments=type_comments),
                first_error,
            )
        except SyntaxError as e:
            if not first_error:
                first_error = str(e)
    return None, first_error


def parse_ast(src: str) -> ast.AST:
    # TODO: support Python 4+ ;)
    # Newest feature version first.
    versions = [(3, minor) for minor in range(sys.version_info[1], 2, -1)]

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


def _drop_unicode_prefix_marker(node: ast.AST) -> None:
    """Forget the `u` prefix of a string constant, which has no semantic effect."""
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.kind == "u"
    ):
        # It's a quirk of history that we strip the u prefix over here. We used to
        # rewrite the AST nodes for Python version compatibility and we never copied
        # over the kind
        node.kind = None


def _is_tuple_delete_target(node: ast.AST, field: str, item: object) -> bool:
    """Is `item` a tuple among the targets of a `del` statement?

    Nested tuples within del statements are ignored, because Black may insert
    parentheses and they change the AST.
    """
    return (
        field == "targets" and isinstance(node, ast.Delete) and isinstance(item, ast.Tuple)
    )


def _normalized_field_value(
    node: ast.AST, field: str, value: object, parent_stack: list[ast.AST]
) -> object:
    """Return `value` normalized for comparison where whitespace is irrelevant."""
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
    _drop_unicode_prefix_marker(node)

    indent = _INDENT * len(parent_stack)
    field_indent = indent + _INDENT

    yield f"{indent}{node.__class__.__name__}("

    for field in sorted(node._fields):
        # TypeIgnore has only one field 'lineno' which breaks this comparison
        if isinstance(node, ast.TypeIgnore):
            break

        try:
            value: object = getattr(node, field)
        except AttributeError:
            continue

        yield f"{field_indent}{field}="

        if isinstance(value, list):
            for item in value:
                if _is_tuple_delete_target(node, field, item):
                    assert isinstance(item, ast.Tuple)
                    for elt in _unwrap_tuples(item):
                        yield from _stringify_ast_with_new_parent(
                            elt, parent_stack, node
                        )

                elif isinstance(item, ast.AST):
                    yield from _stringify_ast_with_new_parent(item, parent_stack, node)

        elif isinstance(value, ast.AST):
            yield from _stringify_ast_with_new_parent(value, parent_stack, node)

        else:
            normalized = _normalized_field_value(node, field, value, parent_stack)
            yield f"{field_indent}{normalized!r},  # {value.__class__.__name__}"

    yield f"{indent})  # /{node.__class__.__name__}"


def _unwrap_tuples(node: ast.Tuple) -> Iterator[ast.AST]:
    for elt in node.elts:
        if isinstance(elt, ast.Tuple):
            yield from _unwrap_tuples(elt)
        else:
            yield elt

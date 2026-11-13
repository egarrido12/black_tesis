```python
"""Nice output for Black.

The double calls are for patching purposes in tests.
"""

import json
import os
import re
import tempfile
from typing import Any, Final

from click import echo, style
from mypy_extensions import mypyc_attr

_ANSI_RESET: Final = "\033[0m"

# Ordered from most to least specific: "+++" must be checked before "+", and
# "---" before "-", so file headers are not coloured as added/removed lines.
_DIFF_LINE_STYLES: Final = (
    (("+++", "---"), "\033[1m"),  # bold
    (("@@",), "\033[36m"),  # cyan
    (("+",), "\033[32m"),  # green
    (("-",), "\033[31m"),  # red
)


def _style_with_defaults(
    message: str, defaults: dict[str, Any], styles: dict[str, Any]
) -> str:
    """Style `message`, using `defaults` for any style the caller didn't set."""
    return style_output(message, **{**defaults, **styles})


@mypyc_attr(patchable=True)
def _out(message: str | None = None, nl: bool = True, **styles: Any) -> None:
    if message is not None:
        message = _style_with_defaults(message, {"bold": True}, styles)
    echo(message, nl=nl, err=True)


@mypyc_attr(patchable=True)
def _err(message: str | None = None, nl: bool = True, **styles: Any) -> None:
    if message is not None:
        message = _style_with_defaults(message, {"fg": "red"}, styles)
    echo(message, nl=nl, err=True)


@mypyc_attr(patchable=True)
def out(message: str | None = None, nl: bool = True, **styles: Any) -> None:
    _out(message, nl=nl, **styles)


def err(message: str | None = None, nl: bool = True, **styles: Any) -> None:
    _err(message, nl=nl, **styles)


def _cell_source(notebook: dict[str, Any], cell_number: int) -> str:
    """Return the source of cell `cell_number` as text ending in a newline."""
    return "".join(notebook["cells"][cell_number]["source"]) + "\n"


def ipynb_diff(a: str, b: str, a_name: str, b_name: str) -> str:
    """Return a unified diff string between each cell in notebooks `a` and `b`."""
    a_nb = json.loads(a)
    b_nb = json.loads(b)
    diff_lines = [
        diff(
            _cell_source(a_nb, cell_number),
            _cell_source(b_nb, cell_number),
            f"{a_name}:cell_{cell_number}",
            f"{b_name}:cell_{cell_number}",
        )
        for cell_number, cell in enumerate(a_nb["cells"])
        if cell["cell_type"] == "code"
    ]
    return "".join(diff_lines)


_line_pattern = re.compile(r"(.*?(?:\r\n|\n|\r|$))")


def _splitlines_no_ff(source: str) -> list[str]:
    """Split a string into lines ignoring form feed and other chars.

    This mimics how the Python parser splits source code.

    A simplified version of the function with the same name in Lib/ast.py
    """
    result = [match[0] for match in _line_pattern.finditer(source)]
    if result[-1] == "":
        result.pop(-1)
    return result


def diff(a: str, b: str, a_name: str, b_name: str) -> str:
    """Return a unified diff string between strings `a` and `b`."""
    import difflib

    a_lines = _splitlines_no_ff(a)
    b_lines = _splitlines_no_ff(b)
    diff_lines = []
    for line in difflib.unified_diff(
        a_lines, b_lines, fromfile=a_name, tofile=b_name, n=5
    ):
        # Work around https://bugs.python.org/issue2142
        # See:
        # https://www.gnu.org/software/diffutils/manual/html_node/Incomplete-Lines.html
        if line[-1] == "\n":
            diff_lines.append(line)
        else:
            diff_lines.append(line + "\n")
            diff_lines.append("\\ No newline at end of file\n")
    return "".join(diff_lines)


def _colorize_diff_line(line: str) -> str:
    """Wrap a single diff line in the ANSI color matching its kind."""
    for prefixes, ansi_code in _DIFF_LINE_STYLES:
        if line.startswith(prefixes):
            return ansi_code + line + _ANSI_RESET
    return line


def color_diff(contents: str) -> str:
    """Inject the ANSI color codes to the diff."""
    if not _color_enabled():
        return contents
    return "\n".join(_colorize_diff_line(line) for line in contents.split("\n"))


def style_output(message: str, **styles: Any) -> str:
    if not _color_enabled():
        return message
    return style(message, **styles)


def _color_enabled() -> bool:
    return "NO_COLOR" not in os.environ


@mypyc_attr(patchable=True)
def dump_to_file(*output: str, ensure_final_newline: bool = True) -> str:
    """Dump `output` to a temporary file. Return path to the file."""
    with tempfile.NamedTemporaryFile(
        mode="w", prefix="blk_", suffix=".log", delete=False, encoding="utf8"
    ) as f:
        for text in output:
            f.write(text)
            if ensure_final_newline and text and text[-1] != "\n":
                f.write("\n")
    return f.name
```

## Refactorizaciones aplicadas

- **Extract Method** (`_style_with_defaults`): se extrae de `_out` y `_err`. Ambas repetían el patrón "si el estilo no fue indicado, poner un valor por defecto, y luego llamar a `style_output`". Ahora cada función solo declara su valor por defecto (`bold=True` en `_out`, `fg="red"` en `_err`). `{**defaults, **styles}` da la misma precedencia que el `if "x" not in styles` original, y los estilos del llamador ya no se mutan. `_out` y `_err` mantienen nombre, firma y decorador `@mypyc_attr(patchable=True)`, porque los tests los parchean.

- **Extract Method** (`_cell_source`): se extrae de `ipynb_diff`. Reemplaza las dos expresiones casi idénticas `"".join(x_nb["cells"][n]["source"]) + "\n"`, así la comprensión de lista queda más corta y legible.

- **Extract Method** (`_colorize_diff_line`) y **Replace Conditional with Table/Lookup** (`_DIFF_LINE_STYLES`): en `color_diff`, la cadena `if/elif` con códigos ANSI literales pasa a una tabla ordenada de prefijos a código ANSI. El orden se mantiene (`+++`/`---` antes de `+`/`-`) y se documenta en un comentario. `color_diff` queda como un `join` sobre las líneas, sin mutar la lista en el bucle.

- **Replace Magic Literal** (`_ANSI_RESET` y los códigos de la tabla): los literales `"\033[...m"` repetidos se nombran y agrupan en un solo lugar.

- **Rename Variable** (`lines` → `text` en `dump_to_file`): `lines` designaba cada argumento de `*output`, que no es una lista de líneas, y se confundía con otros usos del nombre en el proyecto.

- Sin cambios deliberados: la importación perezosa de `difflib` en `diff`, `_splitlines_no_ff`, `_line_pattern`, `_color_enabled`, `style_output` y las firmas públicas (`out`, `err`, `ipynb_diff`, `diff`, `color_diff`, `style_output`, `dump_to_file`), para preservar el comportamiento y la compatibilidad con mypyc y los tests.
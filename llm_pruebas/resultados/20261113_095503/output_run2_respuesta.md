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


def _echo_to_stderr(
    message: str | None,
    nl: bool,
    styles: dict[str, Any],
    default_style_name: str,
    default_style_value: Any,
) -> None:
    """Echo `message` to stderr, styled with `styles` plus one default style.

    The default style is only applied when the caller didn't specify it.
    """
    if message is not None:
        styles.setdefault(default_style_name, default_style_value)
        message = style_output(message, **styles)
    echo(message, nl=nl, err=True)


@mypyc_attr(patchable=True)
def _out(message: str | None = None, nl: bool = True, **styles: Any) -> None:
    _echo_to_stderr(message, nl, styles, "bold", True)


@mypyc_attr(patchable=True)
def _err(message: str | None = None, nl: bool = True, **styles: Any) -> None:
    _echo_to_stderr(message, nl, styles, "fg", "red")


@mypyc_attr(patchable=True)
def out(message: str | None = None, nl: bool = True, **styles: Any) -> None:
    _out(message, nl=nl, **styles)


def err(message: str | None = None, nl: bool = True, **styles: Any) -> None:
    _err(message, nl=nl, **styles)


def _joined_cell_source(notebook: dict[str, Any], cell_number: int) -> str:
    """Return the source of the given notebook cell as a single string."""
    return "".join(notebook["cells"][cell_number]["source"]) + "\n"


def ipynb_diff(a: str, b: str, a_name: str, b_name: str) -> str:
    """Return a unified diff string between each cell in notebooks `a` and `b`."""
    a_nb = json.loads(a)
    b_nb = json.loads(b)
    diff_lines = [
        diff(
            _joined_cell_source(a_nb, cell_number),
            _joined_cell_source(b_nb, cell_number),
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


_ANSI_RESET: Final = "\033[0m"
# Ordered (line prefixes, ANSI style code) rules; the first matching rule wins,
# so the file headers ("+++"/"---") must come before the "+"/"-" rules.
_DIFF_COLOR_RULES: Final = (
    (("+++", "---"), "\033[1m"),  # bold
    (("@@",), "\033[36m"),  # cyan
    (("+",), "\033[32m"),  # green
    (("-",), "\033[31m"),  # red
)


def _colorize_diff_line(line: str) -> str:
    """Wrap `line` in the ANSI color matching its role in a unified diff."""
    for prefixes, style_code in _DIFF_COLOR_RULES:
        if line.startswith(prefixes):
            return style_code + line + _ANSI_RESET
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
        for chunk in output:
            f.write(chunk)
            if ensure_final_newline and chunk and chunk[-1] != "\n":
                f.write("\n")
    return f.name
```

## Refactorizaciones aplicadas

- **Extract Method + Pull Up/Consolidate Duplicate Code** (`_out`, `_err` → nuevo `_echo_to_stderr`): ambas funciones repetían la misma estructura (aplicar un estilo por defecto si no se pasó, estilizar, hacer `echo` a stderr) y solo diferían en la clave y el valor por defecto (`bold=True` vs `fg="red"`). Ahora comparten un helper. `_out` y `_err` siguen existiendo con el mismo nombre, firma y `@mypyc_attr(patchable=True)`, porque los tests las parchean. El `if "x" not in styles: styles["x"] = v` pasó a `styles.setdefault(...)`, que hace lo mismo.

- **Extract Method** (`ipynb_diff` → nuevo `_joined_cell_source`): se repetía la expresión `"".join(<nb>["cells"][n]["source"]) + "\n"` para ambos cuadernos. Ahora el nombre del helper explica lo que hace.

- **Extract Method + Replace Conditional with Table-Driven Logic** (`color_diff` → `_colorize_diff_line` y `_DIFF_COLOR_RULES`): la cadena `if/elif` con códigos ANSI escritos en línea se convirtió en una tabla ordenada de reglas (prefijos → código). El orden se mantiene, así que `+++`/`---` siguen ganando a `+`/`-`. `line.startswith("+++") or line.startswith("---")` pasó a `startswith(tuple)`. Además se eliminó la mutación de la lista por índice (`lines[i] = line`) en favor de un `"\n".join(...)`.

- **Replace Magic Literal** (`_ANSI_RESET`, `_DIFF_COLOR_RULES`): las secuencias de escape `"\033[0m"`, `"\033[1m"`, etc. tienen ahora nombre y se declaran una sola vez como `Final`.

- **Rename Variable** (`dump_to_file`: `lines` → `chunk`): el nombre anterior sugería líneas, pero cada elemento de `output` es un fragmento de texto arbitrario. En `ipynb_diff`, el parámetro de la comprensión se dejó como `cell` porque solo se usa para leer `cell_type`.

No cambié `diff`, `_splitlines_no_ff`, `_line_pattern`, `style_output` ni `_color_enabled`. Ya eran claros, y las comprobaciones como `line[-1] == "\n"` se conservaron tal cual para mantener el comportamiento idéntico.
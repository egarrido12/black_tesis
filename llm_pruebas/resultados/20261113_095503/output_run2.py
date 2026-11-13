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

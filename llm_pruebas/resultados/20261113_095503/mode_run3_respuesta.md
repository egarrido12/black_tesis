```python
"""Data structures configuring Black behavior.

Mostly around Python language feature support per version and Black configuration
chosen by the user.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from hashlib import sha256
from operator import attrgetter
from typing import Final

from black.const import DEFAULT_LINE_LENGTH


class TargetVersion(Enum):
    PY33 = 3
    PY34 = 4
    PY35 = 5
    PY36 = 6
    PY37 = 7
    PY38 = 8
    PY39 = 9
    PY310 = 10
    PY311 = 11
    PY312 = 12
    PY313 = 13
    PY314 = 14
    PY315 = 15

    def pretty(self) -> str:
        assert self.name[:2] == "PY"
        return f"Python {self.name[2]}.{self.name[3:]}"


class Feature(Enum):
    F_STRINGS = 2
    NUMERIC_UNDERSCORES = 3
    TRAILING_COMMA_IN_CALL = 4
    TRAILING_COMMA_IN_DEF = 5
    # The following two feature-flags are mutually exclusive, and exactly one should be
    # set for every version of python.
    ASYNC_IDENTIFIERS = 6
    ASYNC_KEYWORDS = 7
    ASSIGNMENT_EXPRESSIONS = 8
    POS_ONLY_ARGUMENTS = 9
    RELAXED_DECORATORS = 10
    PATTERN_MATCHING = 11
    UNPACKING_ON_FLOW = 12
    ANN_ASSIGN_EXTENDED_RHS = 13
    EXCEPT_STAR = 14
    VARIADIC_GENERICS = 15
    DEBUG_F_STRINGS = 16
    PARENTHESIZED_CONTEXT_MANAGERS = 17
    TYPE_PARAMS = 18
    # FSTRING_PARSING = 19  # unused
    TYPE_PARAM_DEFAULTS = 20
    UNPARENTHESIZED_EXCEPT_TYPES = 21
    T_STRINGS = 22
    LAZY_IMPORTS = 23
    UNPACKING_IN_COMPREHENSIONS = 24
    UNPARENTHESIZED_WALRUS_IN_SETS = 25
    FORCE_OPTIONAL_PARENTHESES = 50

    # __future__ flags
    FUTURE_ANNOTATIONS = 51


FUTURE_FLAG_TO_FEATURE: Final = {
    "annotations": Feature.FUTURE_ANNOTATIONS,
}


# Features are cumulative from Python 3.7 onwards: each version supports everything
# the previous one did plus the features it introduced. Python 3.3-3.6 are listed
# explicitly in VERSION_TO_FEATURES because they use `ASYNC_IDENTIFIERS` instead of
# `ASYNC_KEYWORDS` and therefore don't form a strict chain with 3.7+.
_PY37_FEATURES: Final = {
    Feature.F_STRINGS,
    Feature.NUMERIC_UNDERSCORES,
    Feature.TRAILING_COMMA_IN_CALL,
    Feature.TRAILING_COMMA_IN_DEF,
    Feature.ASYNC_KEYWORDS,
    Feature.FUTURE_ANNOTATIONS,
}
_PY38_FEATURES: Final = _PY37_FEATURES | {
    Feature.DEBUG_F_STRINGS,
    Feature.ASSIGNMENT_EXPRESSIONS,
    Feature.POS_ONLY_ARGUMENTS,
    Feature.UNPACKING_ON_FLOW,
    Feature.ANN_ASSIGN_EXTENDED_RHS,
}
_PY39_FEATURES: Final = _PY38_FEATURES | {
    Feature.RELAXED_DECORATORS,
    Feature.PARENTHESIZED_CONTEXT_MANAGERS,
}
_PY310_FEATURES: Final = _PY39_FEATURES | {
    Feature.UNPARENTHESIZED_WALRUS_IN_SETS,
    Feature.PATTERN_MATCHING,
}
_PY311_FEATURES: Final = _PY310_FEATURES | {
    Feature.EXCEPT_STAR,
    Feature.VARIADIC_GENERICS,
}
_PY312_FEATURES: Final = _PY311_FEATURES | {Feature.TYPE_PARAMS}
_PY313_FEATURES: Final = _PY312_FEATURES | {Feature.TYPE_PARAM_DEFAULTS}
_PY314_FEATURES: Final = _PY313_FEATURES | {
    Feature.UNPARENTHESIZED_EXCEPT_TYPES,
    Feature.T_STRINGS,
}
_PY315_FEATURES: Final = _PY314_FEATURES | {
    Feature.LAZY_IMPORTS,
    Feature.UNPACKING_IN_COMPREHENSIONS,
}


# Every entry gets its own set instance, so mutating one never affects another.
VERSION_TO_FEATURES: dict[TargetVersion, set[Feature]] = {
    TargetVersion.PY33: {Feature.ASYNC_IDENTIFIERS},
    TargetVersion.PY34: {Feature.ASYNC_IDENTIFIERS},
    TargetVersion.PY35: {Feature.TRAILING_COMMA_IN_CALL, Feature.ASYNC_IDENTIFIERS},
    TargetVersion.PY36: {
        Feature.F_STRINGS,
        Feature.NUMERIC_UNDERSCORES,
        Feature.TRAILING_COMMA_IN_CALL,
        Feature.TRAILING_COMMA_IN_DEF,
        Feature.ASYNC_IDENTIFIERS,
    },
    TargetVersion.PY37: set(_PY37_FEATURES),
    TargetVersion.PY38: set(_PY38_FEATURES),
    TargetVersion.PY39: set(_PY39_FEATURES),
    TargetVersion.PY310: set(_PY310_FEATURES),
    TargetVersion.PY311: set(_PY311_FEATURES),
    TargetVersion.PY312: set(_PY312_FEATURES),
    TargetVersion.PY313: set(_PY313_FEATURES),
    TargetVersion.PY314: set(_PY314_FEATURES),
    TargetVersion.PY315: set(_PY315_FEATURES),
}


def supports_feature(target_versions: set[TargetVersion], feature: Feature) -> bool:
    if not target_versions:
        raise ValueError("At least one target Python version must be specified.")

    return all(feature in VERSION_TO_FEATURES[version] for version in target_versions)


class Preview(Enum):
    """Individual preview style features."""

    # NOTE: string_processing requires wrap_long_dict_values_in_parens
    # for https://github.com/psf/black/issues/3117 to be fixed.
    string_processing = auto()
    hug_parens_with_braces_and_square_brackets = auto()
    wrap_comprehension_in = auto()
    simplify_power_operator_hugging = auto()
    wrap_long_dict_values_in_parens = auto()
    fix_if_guard_explosion_in_case_statement = auto()
    pyi_overload_group_blank_lines = auto()
    fix_unnecessary_parens_in_indexed_assignment = auto()
    pyi_blank_line_before_decorated_class = auto()
    pyi_blank_line_after_function_docstring = auto()
    hug_comparator = auto()
    parenthesize_tuple_in_yield = auto()
    fmt_off_class_blank_lines = auto()
    remove_redundant_generator_parentheses = auto()
    symmetric_collection_operations = auto()
    normalize_tstring_prefix = auto()
    remove_redundant_list_parentheses = auto()
    remove_redundant_unpacking_parentheses = auto()
    remove_redundant_subscript_parentheses = auto()
    fix_magic_trailing_comma_trailer_split = auto()
    keep_dict_keys_with_operators = auto()
    blank_line_after_stub_method = auto()
    keep_commented_expressions_together = auto()
    avoid_parens_for_unbreakable_rhs_in_assignments = auto()
    parenthesize_expressions_with_comments = auto()
    keep_trailers_on_bracket_comment_overflow = auto()
    remove_redundant_comparison_parentheses = auto()
    remove_redundant_top_level_parentheses = auto()


UNSTABLE_FEATURES: set[Preview] = {
    # Many issues, see summary in https://github.com/psf/black/issues/4208
    Preview.string_processing,
    # See issue #4036 (crash), #4098, #4099 (proposed tweaks)
    Preview.hug_parens_with_braces_and_square_brackets,
}


_MAX_CACHE_KEY_PART_LENGTH: Final = 32


def _short_hash(text: str) -> str:
    """Return a hex digest of `text`, truncated to a cache-key-friendly length."""
    return sha256(text.encode()).hexdigest()[:_MAX_CACHE_KEY_PART_LENGTH]


@dataclass
class Mode:
    target_versions: set[TargetVersion] = field(default_factory=set)
    line_length: int = DEFAULT_LINE_LENGTH
    string_normalization: bool = True
    is_pyi: bool = False
    is_ipynb: bool = False
    skip_source_first_line: bool = False
    magic_trailing_comma: bool = True
    python_cell_magics: set[str] = field(default_factory=set)
    preview: bool = False
    unstable: bool = False
    enabled_features: set[Preview] = field(default_factory=set)

    def __contains__(self, feature: Preview) -> bool:
        """
        Provide `Preview.FEATURE in Mode` syntax that mirrors the ``preview`` flag.

        In unstable mode, all features are enabled. In preview mode, all features
        except those in UNSTABLE_FEATURES are enabled. Any features in
        `self.enabled_features` are also enabled.
        """
        return (
            self.unstable
            or feature in self.enabled_features
            or (self.preview and feature not in UNSTABLE_FEATURES)
        )

    def _target_versions_cache_key_part(self) -> str:
        """Cache key component describing the target versions."""
        if not self.target_versions:
            return "-"
        version_str = ",".join(
            str(version.value)
            for version in sorted(self.target_versions, key=attrgetter("value"))
        )
        if len(version_str) > _MAX_CACHE_KEY_PART_LENGTH:
            version_str = _short_hash(version_str)
        return version_str

    def _features_and_magics_cache_key_part(self) -> str:
        """Cache key component describing enabled features and cell magics."""
        features_and_magics = (
            ",".join(sorted(f.name for f in self.enabled_features))
            + "@"
            + ",".join(sorted(self.python_cell_magics))
        )
        return _short_hash(features_and_magics)

    def get_cache_key(self) -> str:
        flags = (
            self.string_normalization,
            self.is_pyi,
            self.is_ipynb,
            self.skip_source_first_line,
            self.magic_trailing_comma,
            self.preview,
            self.unstable,
        )
        parts = [
            self._target_versions_cache_key_part(),
            str(self.line_length),
            *(str(int(flag)) for flag in flags),
            self._features_and_magics_cache_key_part(),
        ]
        return ".".join(parts)

    def __hash__(self) -> int:
        return hash((
            frozenset(self.target_versions),
            self.line_length,
            self.string_normalization,
            self.is_pyi,
            self.is_ipynb,
            self.skip_source_first_line,
            self.magic_trailing_comma,
            frozenset(self.python_cell_magics),
            self.preview,
            self.unstable,
            frozenset(self.enabled_features),
        ))
```

## Refactorizaciones aplicadas

- **Extract Variable / Replace Duplicate Code with Composition** — `VERSION_TO_FEATURES` y las nuevas constantes privadas `_PY37_FEATURES` … `_PY315_FEATURES`. Cada versión repetía la lista completa de la anterior (más de 200 líneas con mucha duplicación). Ahora cada versión se define como la anterior más sus novedades. Se han verificado uno a uno los conjuntos resultantes contra los originales. PY33–PY36 siguen explícitos porque usan `ASYNC_IDENTIFIERS` y no forman una cadena estricta con 3.7+. Cada entrada del diccionario público recibe su propia copia (`set(...)`), así que sigue siendo `dict[TargetVersion, set[Feature]]` con conjuntos mutables independientes.

- **Extract Function** — `_short_hash` (función privada de módulo). Sustituye al patrón duplicado `sha256(...).encode().hexdigest()[:_MAX_CACHE_KEY_PART_LENGTH]`.

- **Extract Method** — `Mode._target_versions_cache_key_part` y `Mode._features_and_magics_cache_key_part`, extraídos de `get_cache_key`. Cada método calcula un fragmento de la clave. `get_cache_key` queda como un ensamblado de partes y los métodos son privados, así que la API pública no cambia.

- **Replace Loop/Repetition with Collection Pipeline** — En `get_cache_key`, las siete conversiones repetidas `str(int(self.x))` pasan a una tupla `flags` procesada con una expresión generadora. Se conserva el orden de la clave.

- **Consolidate Conditional Expression** — `Mode.__contains__`. Los tres `if`/`return` consecutivos se unifican en una sola expresión booleana con el mismo orden de evaluación y cortocircuito, y el mismo resultado.

- **Reemplazar condicional por retorno temprano** (variante de Replace Nested Conditional with Guard Clauses) — En `_target_versions_cache_key_part`, el caso sin versiones devuelve `"-"` de inmediato, en lugar del `if/else` que asignaba a una variable intermedia.

No se tocaron `TargetVersion`, `Feature`, `Preview`, `UNSTABLE_FEATURES`, `FUTURE_FLAG_TO_FEATURE`, `supports_feature` ni `Mode.__hash__`, y los campos del dataclass `Mode` son los mismos. Los métodos nuevos no son campos, por lo que no afectan a `repr`, `eq` ni al hash.
```python
"""Data structures configuring Black behavior.

Mostly around Python language feature support per version and Black configuration
chosen by the user.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from hashlib import sha256
from operator import attrgetter
from typing import Final, NamedTuple

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


class _FeatureChange(NamedTuple):
    """Features gained and lost by a Python version relative to the previous one."""

    version: TargetVersion
    added: frozenset[Feature] = frozenset()
    removed: frozenset[Feature] = frozenset()


# Listed in ascending version order: the features supported by a version are those
# of the previous version, minus `removed`, plus `added`.
_FEATURE_CHANGES: Final = (
    _FeatureChange(
        TargetVersion.PY33,
        added=frozenset({Feature.ASYNC_IDENTIFIERS}),
    ),
    _FeatureChange(TargetVersion.PY34),
    _FeatureChange(
        TargetVersion.PY35,
        added=frozenset({Feature.TRAILING_COMMA_IN_CALL}),
    ),
    _FeatureChange(
        TargetVersion.PY36,
        added=frozenset({
            Feature.F_STRINGS,
            Feature.NUMERIC_UNDERSCORES,
            Feature.TRAILING_COMMA_IN_DEF,
        }),
    ),
    _FeatureChange(
        TargetVersion.PY37,
        added=frozenset({Feature.ASYNC_KEYWORDS, Feature.FUTURE_ANNOTATIONS}),
        removed=frozenset({Feature.ASYNC_IDENTIFIERS}),
    ),
    _FeatureChange(
        TargetVersion.PY38,
        added=frozenset({
            Feature.DEBUG_F_STRINGS,
            Feature.ASSIGNMENT_EXPRESSIONS,
            Feature.POS_ONLY_ARGUMENTS,
            Feature.UNPACKING_ON_FLOW,
            Feature.ANN_ASSIGN_EXTENDED_RHS,
        }),
    ),
    _FeatureChange(
        TargetVersion.PY39,
        added=frozenset({
            Feature.RELAXED_DECORATORS,
            Feature.PARENTHESIZED_CONTEXT_MANAGERS,
        }),
    ),
    _FeatureChange(
        TargetVersion.PY310,
        added=frozenset({
            Feature.UNPARENTHESIZED_WALRUS_IN_SETS,
            Feature.PATTERN_MATCHING,
        }),
    ),
    _FeatureChange(
        TargetVersion.PY311,
        added=frozenset({Feature.EXCEPT_STAR, Feature.VARIADIC_GENERICS}),
    ),
    _FeatureChange(
        TargetVersion.PY312,
        added=frozenset({Feature.TYPE_PARAMS}),
    ),
    _FeatureChange(
        TargetVersion.PY313,
        added=frozenset({Feature.TYPE_PARAM_DEFAULTS}),
    ),
    _FeatureChange(
        TargetVersion.PY314,
        added=frozenset({
            Feature.UNPARENTHESIZED_EXCEPT_TYPES,
            Feature.T_STRINGS,
        }),
    ),
    _FeatureChange(
        TargetVersion.PY315,
        added=frozenset({
            Feature.LAZY_IMPORTS,
            Feature.UNPACKING_IN_COMPREHENSIONS,
        }),
    ),
)


def _build_version_to_features() -> dict[TargetVersion, set[Feature]]:
    """Accumulate `_FEATURE_CHANGES` into the full feature set of each version.

    Every version gets its own independent (mutable) set.
    """
    version_to_features: dict[TargetVersion, set[Feature]] = {}
    current: set[Feature] = set()
    for change in _FEATURE_CHANGES:
        current = (current - change.removed) | change.added
        version_to_features[change.version] = set(current)
    return version_to_features


VERSION_TO_FEATURES: dict[TargetVersion, set[Feature]] = _build_version_to_features()


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


def _short_digest(text: str) -> str:
    """Return a SHA-256 hex digest of `text`, truncated to fit a cache key part."""
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
        if self.unstable:
            return True
        if feature in self.enabled_features:
            return True
        return self.preview and feature not in UNSTABLE_FEATURES

    def get_cache_key(self) -> str:
        if self.target_versions:
            version_str = ",".join(
                str(version.value)
                for version in sorted(self.target_versions, key=attrgetter("value"))
            )
        else:
            version_str = "-"
        if len(version_str) > _MAX_CACHE_KEY_PART_LENGTH:
            version_str = _short_digest(version_str)

        features_and_magics = _short_digest(
            ",".join(sorted(f.name for f in self.enabled_features))
            + "@"
            + ",".join(sorted(self.python_cell_magics))
        )

        # The order of these flags is part of the cache key format.
        boolean_options = (
            self.string_normalization,
            self.is_pyi,
            self.is_ipynb,
            self.skip_source_first_line,
            self.magic_trailing_comma,
            self.preview,
            self.unstable,
        )
        parts = [
            version_str,
            str(self.line_length),
            *(str(int(option)) for option in boolean_options),
            features_and_magics,
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

- **Replace Data Table with Incremental Derivation** (variante de *Replace Conditional/Duplicate Code with Data*) — `VERSION_TO_FEATURES`, nuevos `_FeatureChange`, `_FEATURE_CHANGES`.
  - Motivo: la tabla original repetía casi por completo el mismo conjunto de `Feature` en cada versión, unas 200 líneas en las que era fácil olvidar una entrada.
  - Ahora cada versión declara solo lo que añade o quita respecto a la anterior.
  - Por ejemplo, PY37 cambia `ASYNC_IDENTIFIERS` por `ASYNC_KEYWORDS` y añade `FUTURE_ANNOTATIONS`.
  - Los conjuntos resultantes son idénticos a los originales; lo comprobé versión por versión.

- **Extract Function** — `_build_version_to_features()`.
  - Motivo: encapsula la acumulación de cambios. Devuelve un `set` independiente por versión, igual que antes, de modo que ningún conjunto se comparte entre versiones y el orden de claves es el mismo. `VERSION_TO_FEATURES` conserva su nombre y su tipo.

- **Introduce Parameter Object / Replace Primitive with Object** — `_FeatureChange` (`NamedTuple`).
  - Motivo: agrupa versión, características añadidas y características retiradas en un registro con nombre en lugar de tuplas posicionales.

- **Extract Function** (eliminación de duplicación) — `_short_digest()`.
  - Elementos afectados: `Mode.get_cache_key`.
  - Motivo: `sha256(...).hexdigest()[:_MAX_CACHE_KEY_PART_LENGTH]` aparecía dos veces, con el truncado partido en varias líneas. Ahora hay un único punto que define cómo se trunca una parte de la clave.

- **Replace Repeated Expression with Loop / Collapse Parameters** — `get_cache_key`.
  - Elementos afectados: los siete `str(int(self.x))` consecutivos, ahora una tupla `boolean_options` expandida con un generador.
  - Motivo: menos repetición; se documenta con un comentario que el orden forma parte del formato de la clave de caché.

- **Eliminación de variable temporal redundante** (*Inline Temp*) — `features_and_magics` en `get_cache_key`.
  - Motivo: se calcula con una sola asignación en lugar de dos reasignaciones sucesivas de la misma variable.

No se tocaron `TargetVersion`, `Feature`, `Preview`, `supports_feature`, `UNSTABLE_FEATURES`, `FUTURE_FLAG_TO_FEATURE`, `__contains__`, `__hash__` ni los campos de `Mode`, de modo que su comportamiento, el formato de la clave de caché y las firmas públicas son idénticos.
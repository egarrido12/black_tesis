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


def _build_version_to_features() -> dict[TargetVersion, set[Feature]]:
    """Build the feature set of every target version.

    From Python 3.7 on, each version supports everything the previous one did
    plus a few additions, so the sets are derived incrementally. Every version
    gets its own independent (mutable) set.
    """
    py36 = {
        Feature.F_STRINGS,
        Feature.NUMERIC_UNDERSCORES,
        Feature.TRAILING_COMMA_IN_CALL,
        Feature.TRAILING_COMMA_IN_DEF,
        Feature.ASYNC_IDENTIFIERS,
    }
    # `async` became a proper keyword in 3.7, replacing the identifier behavior.
    py37 = (py36 - {Feature.ASYNC_IDENTIFIERS}) | {
        Feature.ASYNC_KEYWORDS,
        Feature.FUTURE_ANNOTATIONS,
    }
    py38 = py37 | {
        Feature.DEBUG_F_STRINGS,
        Feature.ASSIGNMENT_EXPRESSIONS,
        Feature.POS_ONLY_ARGUMENTS,
        Feature.UNPACKING_ON_FLOW,
        Feature.ANN_ASSIGN_EXTENDED_RHS,
    }
    py39 = py38 | {
        Feature.RELAXED_DECORATORS,
        Feature.PARENTHESIZED_CONTEXT_MANAGERS,
    }
    py310 = py39 | {
        Feature.UNPARENTHESIZED_WALRUS_IN_SETS,
        Feature.PATTERN_MATCHING,
    }
    py311 = py310 | {
        Feature.EXCEPT_STAR,
        Feature.VARIADIC_GENERICS,
    }
    py312 = py311 | {Feature.TYPE_PARAMS}
    py313 = py312 | {Feature.TYPE_PARAM_DEFAULTS}
    py314 = py313 | {
        Feature.UNPARENTHESIZED_EXCEPT_TYPES,
        Feature.T_STRINGS,
    }
    py315 = py314 | {
        Feature.LAZY_IMPORTS,
        Feature.UNPACKING_IN_COMPREHENSIONS,
    }
    return {
        TargetVersion.PY33: {Feature.ASYNC_IDENTIFIERS},
        TargetVersion.PY34: {Feature.ASYNC_IDENTIFIERS},
        TargetVersion.PY35: {Feature.TRAILING_COMMA_IN_CALL, Feature.ASYNC_IDENTIFIERS},
        TargetVersion.PY36: py36,
        TargetVersion.PY37: py37,
        TargetVersion.PY38: py38,
        TargetVersion.PY39: py39,
        TargetVersion.PY310: py310,
        TargetVersion.PY311: py311,
        TargetVersion.PY312: py312,
        TargetVersion.PY313: py313,
        TargetVersion.PY314: py314,
        TargetVersion.PY315: py315,
    }


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


def _short_sha256(text: str) -> str:
    """Return the sha256 hex digest of `text`, truncated to a cache key part."""
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

    def _target_versions_cache_key_part(self) -> str:
        """Cache key part for the target versions ("-" if none were given)."""
        if not self.target_versions:
            return "-"
        version_str = ",".join(
            str(version.value)
            for version in sorted(self.target_versions, key=attrgetter("value"))
        )
        if len(version_str) > _MAX_CACHE_KEY_PART_LENGTH:
            return _short_sha256(version_str)
        return version_str

    def _features_and_magics_cache_key_part(self) -> str:
        """Hashed cache key part for the enabled features and cell magics."""
        features = ",".join(sorted(f.name for f in self.enabled_features))
        magics = ",".join(sorted(self.python_cell_magics))
        return _short_sha256(f"{features}@{magics}")

    def get_cache_key(self) -> str:
        parts = [
            self._target_versions_cache_key_part(),
            str(self.line_length),
            str(int(self.string_normalization)),
            str(int(self.is_pyi)),
            str(int(self.is_ipynb)),
            str(int(self.skip_source_first_line)),
            str(int(self.magic_trailing_comma)),
            str(int(self.preview)),
            str(int(self.unstable)),
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

```python
"""Functions related to Black's formatting by line ranges feature."""

import difflib
from collections.abc import Collection, Iterator, Sequence
from dataclasses import dataclass

from black.comments import FMT_SKIP, contains_fmt_directive
from black.nodes import (
    LN,
    STANDALONE_COMMENT,
    Leaf,
    Node,
    Visitor,
    first_leaf,
    furthest_ancestor_with_last_leaf,
    last_leaf,
    syms,
)
from blib2to3.pgen2.token import ASYNC, NEWLINE


def _parse_line_range(lines_str: str) -> tuple[int, int]:
    """Parse and validate a single `START-END` range."""
    parts = lines_str.split("-")
    if len(parts) != 2:
        raise ValueError(
            "Incorrect --line-ranges format, expect 'START-END', found"
            f" {lines_str!r}"
        )
    try:
        start = int(parts[0])
        end = int(parts[1])
    except ValueError:
        raise ValueError(
            "Incorrect --line-ranges value, expect integer ranges, found"
            f" {lines_str!r}"
        ) from None
    if start < 1 or end < 1:
        raise ValueError(
            "Incorrect --line-ranges value, "
            f"expect positive integers, found {lines_str!r}"
        )
    if start > end:
        raise ValueError(
            "Incorrect --line-ranges value, expect START <= END, "
            f"found {lines_str!r}"
        )
    return start, end


def parse_line_ranges(line_ranges: Sequence[str]) -> list[tuple[int, int]]:
    return [_parse_line_range(lines_str) for lines_str in line_ranges]


def is_valid_line_range(lines: tuple[int, int]) -> bool:
    """Returns whether the line range is valid."""
    return lines[0] <= lines[1]


def _count_source_lines(src_contents: str) -> int:
    """Return the number of lines in `src_contents`, counting an unterminated last
    line."""
    src_line_count = src_contents.count("\n")
    if not src_contents.endswith("\n"):
        src_line_count += 1
    return src_line_count


def sanitized_lines(
    lines: Collection[tuple[int, int]], src_contents: str
) -> Collection[tuple[int, int]]:
    """Returns the valid line ranges for the given source.

    This removes ranges that are entirely outside the valid lines.

    Other ranges are normalized so that the start values are at least 1 and the
    end values are at most the (1-based) index of the last source line.
    """
    if not src_contents:
        return []
    good_lines = []
    src_line_count = _count_source_lines(src_contents)
    for start, end in lines:
        if start > src_line_count:
            continue
        # line-ranges are 1-based
        start = max(start, 1)
        if end < start:
            continue
        end = min(end, src_line_count)
        good_lines.append((start, end))
    return good_lines


def _edits_confined_to_ranges(
    lines: Collection[tuple[int, int]],
    original_source: str,
    modified_source: str,
) -> bool:
    """Return True if the edits keep line numbers stable and stay inside `lines`.

    Equal-length edits confined to the requested ranges cannot shift their line
    numbers. Diffing repeated text can move them anyway, hence this shortcut.
    """
    if len(lines) <= 1:
        return False
    original_lines = original_source.splitlines(keepends=True)
    modified_lines = modified_source.splitlines(keepends=True)
    if len(original_lines) != len(modified_lines) or not all(
        1 <= start <= end <= len(original_lines) for start, end in lines
    ):
        return False
    selected_lines = {line for start, end in lines for line in range(start - 1, end)}
    return all(
        index in selected_lines or original == modified
        for index, (original, modified) in enumerate(
            zip(original_lines, modified_lines, strict=True)
        )
    )


def _map_range_start(line: int, mapping: "_LinesMapping") -> int:
    """Map the first line of a range through `mapping`."""
    if mapping.is_changed_block:
        # When the line falls into a changed block, expands to the whole block.
        return mapping.modified_start
    return line - mapping.original_start + mapping.modified_start


def _map_range_end(line: int, mapping: "_LinesMapping") -> int:
    """Map the last line of a range through `mapping`."""
    if mapping.is_changed_block:
        # When the line falls into a changed block, expands to the whole block.
        return mapping.modified_end
    return line - mapping.original_start + mapping.modified_start


def adjusted_lines(
    lines: Collection[tuple[int, int]],
    original_source: str,
    modified_source: str,
) -> list[tuple[int, int]]:
    """Returns the adjusted line ranges based on edits from the original code.

    This computes the new line ranges by diffing original_source and
    modified_source, and adjust each range based on how the range overlaps with
    the diffs.

    Note the diff can contain lines outside of the original line ranges. This can
    happen when the formatting has to be done in adjacent to maintain consistent
    local results. For example:

    1. def my_func(arg1, arg2,
    2.             arg3,):
    3.   pass

    If it restricts to line 2-2, it can't simply reformat line 2, it also has
    to reformat line 1:

    1. def my_func(
    2.     arg1,
    3.     arg2,
    4.     arg3,
    5. ):
    6.   pass

    In this case, we will expand the line ranges to also include the whole diff
    block.

    Args:
      lines: a collection of line ranges.
      original_source: the original source.
      modified_source: the modified source.
    """
    if _edits_confined_to_ranges(lines, original_source, modified_source):
        return sorted(lines)

    lines_mappings = _calculate_lines_mappings(original_source, modified_source)

    new_lines = []
    # Keep an index of the current search. Since the lines and lines_mappings are
    # sorted, this makes the search complexity linear.
    current_mapping_index = 0
    for start, end in sorted(lines):
        start_mapping_index = _find_lines_mapping_index(
            start,
            lines_mappings,
            current_mapping_index,
        )
        end_mapping_index = _find_lines_mapping_index(
            end,
            lines_mappings,
            start_mapping_index,
        )
        current_mapping_index = start_mapping_index
        if start_mapping_index >= len(lines_mappings) or end_mapping_index >= len(
            lines_mappings
        ):
            # Protect against invalid inputs.
            continue
        new_range = (
            _map_range_start(start, lines_mappings[start_mapping_index]),
            _map_range_end(end, lines_mappings[end_mapping_index]),
        )
        if is_valid_line_range(new_range):
            new_lines.append(new_range)
    return new_lines


def convert_unchanged_lines(src_node: Node, lines: Collection[tuple[int, int]]) -> None:
    r"""Converts unchanged lines to STANDALONE_COMMENT.

    The idea is similar to how `# fmt: on/off` is implemented. It also converts the
    nodes between those markers as a single `STANDALONE_COMMENT` leaf node with
    the unformatted code as its value. `STANDALONE_COMMENT` is a "fake" token
    that will be formatted as-is with its prefix normalized.

    Here we perform two passes:

    1. Visit the top-level statements, and convert them to a single
       `STANDALONE_COMMENT` when unchanged. This speeds up formatting when some
       of the top-level statements aren't changed.
    2. Convert unchanged "unwrapped lines" to `STANDALONE_COMMENT` nodes line by
       line. "unwrapped lines" are divided by the `NEWLINE` token. e.g. a
       multi-line statement is *one* "unwrapped line" that ends with `NEWLINE`,
       even though this statement itself can span multiple lines, and the
       tokenizer only sees the last '\n' as the `NEWLINE` token.

    NOTE: During pass (2), comment prefixes and indentations are ALWAYS
    normalized even when the lines aren't changed. This is fixable by moving
    more formatting to pass (1). However, it's hard to get it correct when
    incorrect indentations are used. So we defer this to future optimizations.
    """
    lines_set = frozenset(n for start, end in lines for n in range(start, end + 1))
    replacements = _NodeReplacements()
    visitor = _TopLevelStatementsVisitor(lines_set, replacements)
    _ = list(visitor.visit(src_node))  # Consume all results.
    replacements.apply()
    _convert_unchanged_line_by_line(src_node, lines_set)


class _NodeReplacements:
    """Collects STANDALONE_COMMENT conversions and applies them per parent.

    Converting a node splices a `STANDALONE_COMMENT` leaf in place of a run of
    sibling nodes. Doing that one node at a time with `Base.remove` /
    `insert_child` scans and shifts the parent's children list on every call, so
    converting the many sibling blocks of one parent (a long if/elif chain, a
    match with many cases, a module with many top-level statements) is O(n^2).
    Recording the conversions and rewriting each parent's children in a single
    pass makes it O(n).
    """

    def __init__(self) -> None:
        # id(parent) -> (parent, {id(child): standalone to splice in}, {ids to drop})
        # A run's nodes can live under more than one parent (an `async` statement
        # keeps the `ASYNC` leaf on the grandparent), so the standalone replaces
        # the run's first node under its own parent while the remaining nodes are
        # just dropped from wherever they sit.
        self._by_parent: dict[int, tuple[Node, dict[int, Leaf], set[int]]] = {}
        # NEWLINE leaves already inside a recorded run, so the line-by-line pass
        # doesn't record an overlapping conversion for them.
        self.covered_newlines: set[int] = set()
        # Nodes already scheduled for removal. When conversions immediately
        # mutated the tree, a second conversion touching an already-removed node
        # was a no-op (`Base.remove` returned None); recording defers the
        # mutation, so we skip such nodes explicitly to keep that behaviour.
        self._recorded: set[int] = set()
        # A leaf's prefix (indentation, blank lines, comments) moves onto its
        # STANDALONE_COMMENT. When an inner and an outer node that share the same
        # first leaf are both converted (a decorator inside a decorated block),
        # the earlier conversion clears the prefix off the leaf, so the later one
        # would see an empty prefix. Remember the taken prefix keyed by the leaf
        # so both conversions reuse the original.
        self._taken_prefixes: dict[int, str] = {}

    def _entry(self, parent: Node) -> tuple[Node, dict[int, Leaf], set[int]]:
        return self._by_parent.setdefault(id(parent), (parent, {}, set()))

    def take_prefix(self, first: Leaf) -> str:
        cached = self._taken_prefixes.get(id(first))
        if cached is not None:
            return cached
        prefix = first.prefix
        first.prefix = ""
        # Immediate conversion replaced the whole run with a freshly built
        # STANDALONE_COMMENT leaf, whose synthesized position is line 0. Recording
        # the conversion leaves the original leaf in place, so mirror that line 0
        # here: when a later, enclosing node shares this first leaf (a decorated
        # block over an already-recorded decorator), _get_line_range sees the run
        # as starting at line 0, matching the immediate behaviour.
        first.lineno = 0
        self._taken_prefixes[id(first)] = prefix
        return prefix

    def is_recorded(self, node: LN) -> bool:
        return id(node) in self._recorded

    def record(self, run: list[LN], standalone: Leaf) -> None:
        first = run[0]
        first_parent = first.parent
        if first_parent is None or id(first) in self._recorded:
            return
        for node in run:
            self._recorded.add(id(node))
            for leaf in node.leaves():
                if leaf.type == NEWLINE:
                    self.covered_newlines.add(id(leaf))
            parent = node.parent
            if parent is not None:
                self._entry(parent)[2].add(id(node))
        self._entry(first_parent)[1][id(first)] = standalone

    def apply(self) -> None:
        for parent, replaced, removed in self._by_parent.values():
            new_children: list[LN] = []
            for child in parent.children:
                standalone = replaced.get(id(child))
                if standalone is not None:
                    standalone.parent = parent
                    new_children.append(standalone)
                    child.parent = None
                elif id(child) in removed:
                    child.parent = None
                else:
                    new_children.append(child)
            parent.children = new_children
            parent.invalidate_sibling_maps()


def _contains_standalone_comment(node: LN) -> bool:
    if isinstance(node, Leaf):
        return node.type == STANDALONE_COMMENT
    return any(_contains_standalone_comment(child) for child in node.children)


def _is_body_on_clause_line(node: LN) -> bool:
    """Is `node` a body on the same line as its clause, in a statement with other
    clauses? For example `b()` in `if a: b()` or `c()` in `else: c()`."""
    parent = node.parent
    return (
        node.type == syms.simple_stmt
        and parent is not None
        and parent.type not in {syms.file_input, syms.suite}
        and any(
            child is not node and child.type in {syms.suite, syms.simple_stmt}
            for child in parent.children
        )
    )


class _TopLevelStatementsVisitor(Visitor[None]):
    """
    A node visitor that converts unchanged top-level statements to
    STANDALONE_COMMENT.

    This is used in addition to _convert_unchanged_line_by_line, to
    speed up formatting when there are unchanged top-level
    classes/functions/statements.
    """

    def __init__(
        self, lines_set: frozenset[int], replacements: "_NodeReplacements"
    ) -> None:
        self._lines_set = lines_set
        self._replacements = replacements

    def visit_simple_stmt(self, node: Node) -> Iterator[None]:
        # This is only called for top-level statements, since `visit_suite`
        # won't visit its children nodes.
        yield from []
        newline_leaf = last_leaf(node)
        if not newline_leaf:
            return
        assert (
            newline_leaf.type == NEWLINE
        ), f"Unexpectedly found leaf.type={newline_leaf.type}"
        # We need to find the furthest ancestor with the NEWLINE as the last
        # leaf, since a `suite` can simply be a `simple_stmt` when it puts
        # its body on the same line. Example: `if cond: pass`.
        ancestor = furthest_ancestor_with_last_leaf(newline_leaf)
        if _is_body_on_clause_line(ancestor):
            # Not the last clause; it's converted with its clause line by line.
            return
        if not _get_line_range(ancestor).intersection(self._lines_set):
            _convert_node_to_standalone_comment(
                ancestor, self._replacements, self._lines_set
            )

    def visit_suite(self, node: Node) -> Iterator[None]:
        yield from []
        # If there is a STANDALONE_COMMENT node, it means parts of the node tree
        # have fmt on/off/skip markers. Those STANDALONE_COMMENT nodes can't
        # be simply converted by calling str(node). So we just don't convert
        # here.
        if _contains_standalone_comment(node):
            return
        semantic_parent = _semantic_parent_of_suite(node)
        if semantic_parent is not None and not _get_line_range(
            semantic_parent
        ).intersection(self._lines_set):
            _convert_node_to_standalone_comment(
                semantic_parent, self._replacements, self._lines_set
            )


def _semantic_parent_of_suite(suite: Node) -> Node | None:
    """Find the semantic parent of `suite`.

    For `async_stmt` and `async_funcdef`, the ASYNC token is defined on a separate
    level by the grammar, so the parent is one level higher.
    """
    semantic_parent = suite.parent
    if (
        semantic_parent is not None
        and semantic_parent.prev_sibling is not None
        and semantic_parent.prev_sibling.type == ASYNC
    ):
        semantic_parent = semantic_parent.parent
    return semantic_parent


def _preceding_siblings(
    node: LN, stop_types: Collection[int]
) -> tuple[list[LN], LN | None]:
    """Collect the previous siblings of `node`, in source order, up to a sibling
    whose type is in `stop_types`.

    Returns the collected siblings and the sibling that stopped the walk (None if
    the walk ran out of siblings).
    """
    nodes: list[LN] = []
    sibling = node.prev_sibling
    while sibling and sibling.type not in stop_types:
        nodes.append(sibling)
        sibling = sibling.prev_sibling
    nodes.reverse()
    return nodes, sibling


def _clause_nodes_to_ignore(parent: Node) -> list[LN]:
    """Return the clause-side nodes checked together with a body.

    The `suite` node is defined as:
      suite: simple_stmt | NEWLINE INDENT stmt+ DEDENT
    We check `simple_stmt` and `stmt+` separately against the lines set.
    """
    # NOTE: Multiple suite nodes can exist as siblings in e.g. `if_stmt`.
    nodes_to_ignore, parent_sibling = _preceding_siblings(
        parent, stop_types={syms.suite, syms.simple_stmt}
    )
    if parent.type == syms.simple_stmt:
        # A body on its clause's line is checked with the clause.
        nodes_to_ignore.extend(parent.children[:-1])
    # Special case for `async_stmt` and `async_funcdef` where the ASYNC
    # token is on the grandparent node.
    grandparent = parent.parent
    if (
        parent_sibling is None
        and grandparent is not None
        and grandparent.prev_sibling is not None
        and grandparent.prev_sibling.type == ASYNC
    ):
        nodes_to_ignore.insert(0, grandparent.prev_sibling)
    return nodes_to_ignore


def _convert_nodes_if_unselected(
    nodes: list[LN],
    newline: Leaf,
    replacements: "_NodeReplacements",
    lines_set: frozenset[int],
) -> None:
    """Convert `nodes` unless they intersect the requested lines."""
    if not _get_line_range(nodes).intersection(lines_set):
        _convert_nodes_to_standalone_comment(
            nodes,
            newline=newline,
            replacements=replacements,
            lines_set=lines_set,
        )


def _convert_unchanged_unwrapped_line(
    newline: Leaf, replacements: "_NodeReplacements", lines_set: frozenset[int]
) -> None:
    """Convert the "unwrapped line" ending with `newline` if it is unchanged."""
    parent = newline.parent
    if parent and parent.type == syms.match_stmt:
        # The `suite` node is defined as:
        #   match_stmt: "match" subject_expr ':' NEWLINE INDENT case_block+ DEDENT
        # Here we need to check `subject_expr`. The `case_block+` will be
        # checked by their own NEWLINEs.
        nodes_to_ignore, _ = _preceding_siblings(newline, stop_types=frozenset())
        _convert_nodes_if_unselected(nodes_to_ignore, newline, replacements, lines_set)
    elif parent and (parent.type == syms.suite or _is_body_on_clause_line(parent)):
        _convert_nodes_if_unselected(
            _clause_nodes_to_ignore(parent), newline, replacements, lines_set
        )
    else:
        ancestor = furthest_ancestor_with_last_leaf(newline)
        # Consider multiple decorators as a whole block, as their
        # newlines have different behaviors than the rest of the grammar.
        if (
            ancestor.type == syms.decorator
            and ancestor.parent
            and ancestor.parent.type == syms.decorators
        ):
            ancestor = ancestor.parent
        if not _get_line_range(ancestor).intersection(lines_set):
            _convert_node_to_standalone_comment(ancestor, replacements, lines_set)


def _convert_unchanged_line_by_line(node: Node, lines_set: frozenset[int]) -> None:
    """Converts unchanged to STANDALONE_COMMENT line by line."""
    replacements = _NodeReplacements()
    for leaf in node.leaves():
        if leaf.type != NEWLINE:
            # We only consider "unwrapped lines", which are divided by the NEWLINE
            # token.
            continue
        if id(leaf) in replacements.covered_newlines:
            # This NEWLINE is inside a run already scheduled for conversion (e.g.
            # a second decorator on a stacked decorator block).
            continue
        _convert_unchanged_unwrapped_line(leaf, replacements, lines_set)
    replacements.apply()


def _standalone_comment_needs_newline(
    leaf: Leaf, next_leaf: Leaf | None, text: str
) -> bool:
    """Whether a newline must be added between `leaf` and `next_leaf`."""
    return (
        leaf.type == STANDALONE_COMMENT
        and next_leaf is not None
        and (
            # A comment-only fmt:off/on block ends with the `# fmt: on` comment.
            # A newline in the next leaf's prefix is a blank line after it.
            leaf.fmt_pass_converted_first_leaf is None
            or (not str(next_leaf).startswith("\n") and _ends_with_fmt_skip(text))
        )
    )


def _str_with_standalone_comments(*nodes: LN) -> str:
    """Like `"".join(str(node) for node in nodes)`, but a nested STANDALONE_COMMENT
    that ends in a comment is followed by a newline.

    A STANDALONE_COMMENT made by `# fmt: skip` handling, or by a `# fmt: off` /
    `# fmt: on` block that only holds comments, can end with the comment and has no
    trailing newline: the line generator puts one after it. Joining it straight to
    the next leaf would append that leaf (e.g. a closing bracket) to the comment's
    line and turn it into part of the comment.
    """
    leaves = [leaf for node in nodes for leaf in node.leaves()]
    parts = []
    for leaf, next_leaf in zip(leaves, [*leaves[1:], None], strict=True):
        text = str(leaf)
        if _standalone_comment_needs_newline(leaf, next_leaf, text):
            text += "\n"
        parts.append(text)
    return "".join(parts)


def _ends_with_fmt_skip(text: str) -> bool:
    """Whether the last line of a STANDALONE_COMMENT value ends in a `# fmt: skip`.

    Only that directive makes such a value end in a comment without a trailing
    newline. Any other `#` is ignored: it may be inside a string.
    """
    last_line = text.rpartition("\n")[2]
    comment_start = last_line.find("#")
    return comment_start != -1 and contains_fmt_directive(
        last_line[comment_start:], FMT_SKIP
    )


def _make_unchanged_standalone_comment(
    value: str,
    prefix: str,
    first: Leaf,
    first_lineno: int,
    lines_set: frozenset[int],
) -> Leaf:
    """Build the STANDALONE_COMMENT that stands in for unchanged code."""
    return Leaf(
        STANDALONE_COMMENT,
        value,
        prefix=prefix,
        fmt_pass_converted_first_leaf=first,
        line_ranges_first_lineno=first_lineno,
        line_ranges_selected=lines_set,
    )


def _convert_node_to_standalone_comment(
    node: LN, replacements: "_NodeReplacements", lines_set: frozenset[int]
) -> None:
    """Convert node to STANDALONE_COMMENT by modifying the tree inline."""
    parent = node.parent
    if not parent or replacements.is_recorded(node):
        return
    first = first_leaf(node)
    last = last_leaf(node)
    if not first or not last:
        return
    if first is last:
        # This can happen on the following edge cases:
        # 1. A block of `# fmt: off/on` code except the `# fmt: on` is placed
        #    on the end of the last line instead of on a new line.
        # 2. A single backslash on its own line followed by a comment line.
        # Ideally we don't want to format them when not requested, but fixing
        # isn't easy. These cases are also badly formatted code, so it isn't
        # too bad we reformat them.
        return
    # The prefix contains comments and indentation whitespaces. They are
    # reformatted accordingly to the correct indentation level.
    # This also means the indentation will be changed on the unchanged lines, and
    # this is actually required to not break incremental reformatting.
    first_lineno = first.lineno
    prefix = replacements.take_prefix(first)
    # For a single-line decorated item the decorator and the item need a newline
    # between them. The conversions are recorded and applied in a single pass
    # instead of mutating the tree per node, so the decorator here is still its
    # own child node carrying its trailing NEWLINE, which already separates it
    # from the item; there's nothing to add back. (A decorated item spanning
    # multiple lines is handled by the earlier suite case in
    # _convert_unchanged_line_by_line, which manages the newlines itself.)
    # Remove the '\n', as STANDALONE_COMMENT will have '\n' appended when
    # generating the formatted code.
    value = _str_with_standalone_comments(node)[:-1]
    replacements.record(
        [node],
        _make_unchanged_standalone_comment(
            value, prefix, first, first_lineno, lines_set
        ),
    )


def _convert_nodes_to_standalone_comment(
    nodes: Sequence[LN],
    *,
    newline: Leaf,
    replacements: "_NodeReplacements",
    lines_set: frozenset[int],
) -> None:
    """Convert nodes to STANDALONE_COMMENT by modifying the tree inline."""
    if not nodes:
        return
    parent = nodes[0].parent
    first = first_leaf(nodes[0])
    if not parent or not first or replacements.is_recorded(nodes[0]):
        return
    first_lineno = first.lineno
    prefix = replacements.take_prefix(first)
    value = _str_with_standalone_comments(*nodes)
    # The prefix comment on the NEWLINE leaf is the trailing comment of the statement.
    if newline.prefix:
        value += newline.prefix
        newline.prefix = ""
    replacements.record(
        list(nodes),
        _make_unchanged_standalone_comment(
            value, prefix, first, first_lineno, lines_set
        ),
    )


def _leaf_line_end(leaf: Leaf) -> int:
    """Returns the line number of the leaf node's last line."""
    if leaf.type == NEWLINE:
        return leaf.lineno
    else:
        # Leaf nodes like multiline strings can occupy multiple lines.
        return leaf.lineno + str(leaf).count("\n")


def _get_line_range(node_or_nodes: LN | list[LN]) -> set[int]:
    """Returns the line range of this node or list of nodes."""
    if isinstance(node_or_nodes, list):
        if not node_or_nodes:
            return set()
        first_node, last_node = node_or_nodes[0], node_or_nodes[-1]
    else:
        # For a Leaf, `first_leaf` and `last_leaf` return the leaf itself.
        first_node = last_node = node_or_nodes
    first = first_leaf(first_node)
    last = last_leaf(last_node)
    if first and last:
        return set(range(first.lineno, _leaf_line_end(last) + 1))
    return set()


@dataclass
class _LinesMapping:
    """1-based lines mapping from original source to modified source.

    Lines [original_start, original_end] from original source
    are mapped to [modified_start, modified_end].

    The ranges are inclusive on both ends.
    """

    original_start: int
    original_end: int
    modified_start: int
    modified_end: int
    # Whether this range corresponds to a changed block, or an unchanged block.
    is_changed_block: bool


def _common_prefix_length(original_lines: list[str], modified_lines: list[str]) -> int:
    """Number of identical lines at the start of both sources."""
    prefix = 0
    while (
        prefix < min(len(original_lines), len(modified_lines))
        and original_lines[prefix] == modified_lines[prefix]
    ):
        prefix += 1
    return prefix


def _common_suffix_length(
    original_lines: list[str], modified_lines: list[str], prefix: int
) -> int:
    """Number of identical lines at the end of both sources, not overlapping the
    common `prefix`."""
    suffix = 0
    while (
        suffix < min(len(original_lines), len(modified_lines)) - prefix
        and original_lines[-suffix - 1] == modified_lines[-suffix - 1]
    ):
        suffix += 1
    return suffix


def _matching_blocks(
    original_lines: list[str], modified_lines: list[str]
) -> list[difflib.Match]:
    """Return the blocks of lines the two sources have in common.

    The result ends with the usual zero-sized sentinel block.
    """
    # SequenceMatcher can align repeated unchanged lines at a different position,
    # making a change in the middle look like an insertion at the start and a
    # deletion at the end. Anchor the common edges before diffing the middle.
    prefix = _common_prefix_length(original_lines, modified_lines)
    suffix = _common_suffix_length(original_lines, modified_lines, prefix)

    original_middle_end = len(original_lines) - suffix
    modified_middle_end = len(modified_lines) - suffix
    # The first formatting pass re-indents the bodies of the statements it
    # formats, so the same line can have a different indentation in the two
    # sources. Comparing the lines without indentation keeps them matched.
    matcher = difflib.SequenceMatcher(
        None,
        [line.strip() for line in original_lines[prefix:original_middle_end]],
        [line.strip() for line in modified_lines[prefix:modified_middle_end]],
    )
    matching_blocks = []
    if prefix:
        matching_blocks.append(difflib.Match(0, 0, prefix))
    matching_blocks.extend(
        difflib.Match(block.a + prefix, block.b + prefix, block.size)
        for block in matcher.get_matching_blocks()
        if block.size
    )
    if suffix:
        matching_blocks.append(
            difflib.Match(original_middle_end, modified_middle_end, suffix)
        )
    matching_blocks.append(difflib.Match(len(original_lines), len(modified_lines), 0))
    return matching_blocks


def _calculate_lines_mappings(
    original_source: str,
    modified_source: str,
) -> Sequence[_LinesMapping]:
    """Returns a sequence of _LinesMapping by diffing the sources.

    For example, given the following diff:
        import re
      - def func(arg1,
      -   arg2, arg3):
      + def func(arg1, arg2, arg3):
          pass
    It returns the following mappings:
      original -> modified
       (1, 1)  ->  (1, 1), is_changed_block=False (the "import re" line)
       (2, 3)  ->  (2, 2), is_changed_block=True (the diff)
       (4, 4)  ->  (3, 3), is_changed_block=False (the "pass" line)

    You can think of this visually as if it brings up a side-by-side diff, and tries
    to map the line ranges from the left side to the right side:

      (1, 1)->(1, 1)    1. import re          1. import re
      (2, 3)->(2, 2)    2. def func(arg1,     2. def func(arg1, arg2, arg3):
                        3.   arg2, arg3):
      (4, 4)->(3, 3)    4.   pass             3.   pass

    Args:
      original_source: the original source.
      modified_source: the modified source.
    """
    original_lines = original_source.splitlines(keepends=True)
    modified_lines = modified_source.splitlines(keepends=True)
    matching_blocks = _matching_blocks(original_lines, modified_lines)

    lines_mappings: list[_LinesMapping] = []
    # matching_blocks is a sequence of "same block of code ranges", see
    # https://docs.python.org/3/library/difflib.html#difflib.SequenceMatcher.get_matching_blocks
    # Each block corresponds to a _LinesMapping with is_changed_block=False,
    # and the ranges between two blocks corresponds to a _LinesMapping with
    # is_changed_block=True,
    # NOTE: matching_blocks is 0-based, but _LinesMapping is 1-based.
    last_index = len(matching_blocks) - 1
    # An empty block at the origin stands in for the block "before" the first one.
    previous_block = difflib.Match(0, 0, 0)
    for i, block in enumerate(matching_blocks):
        # The lines before the first matching block are not part of any matching
        # block, so that range is a changed block (a line that only exists on one
        # side has no counterpart to map onto). It is only emitted when non-empty.
        if i > 0 or block.a != 0 or block.b != 0:
            lines_mappings.append(
                _LinesMapping(
                    original_start=previous_block.a + previous_block.size + 1,
                    original_end=block.a,
                    modified_start=previous_block.b + previous_block.size + 1,
                    modified_end=block.b,
                    is_changed_block=True,
                )
            )
        if i < last_index:
            lines_mappings.append(
                _LinesMapping(
                    original_start=block.a + 1,
                    original_end=block.a + block.size,
                    modified_start=block.b + 1,
                    modified_end=block.b + block.size,
                    is_changed_block=False,
                )
            )
        previous_block = block
    return lines_mappings


def _find_lines_mapping_index(
    original_line: int,
    lines_mappings: Sequence[_LinesMapping],
    start_index: int,
) -> int:
    """Returns the original index of the lines mappings for the original line."""
    index = start_index
    while index < len(lines_mappings):
        mapping = lines_mappings[index]
        if mapping.original_start <= original_line <= mapping.original_end:
            return index
        index += 1
    return index
```

## Refactorizaciones aplicadas

Los nombres y firmas públicos (`parse_line_ranges`, `is_valid_line_range`, `sanitized_lines`, `adjusted_lines`, `convert_unchanged_lines`) y los nombres privados ya existentes no cambian. No he ejecutado la suite de tests, así que la equivalencia de comportamiento está razonada pero no verificada.

1. **Extract Method**: `_parse_line_range` (desde `parse_line_ranges`).
   - Antes, el bucle mezclaba iteración, parseo y cuatro validaciones, con un `try/except/else` anidado.
   - Ahora `parse_line_ranges` es una comprensión de lista. Los mensajes de error y el orden de las validaciones son idénticos.

2. **Extract Method**: `_count_source_lines` (desde `sanitized_lines`).
   - Da nombre al cálculo del número de líneas, incluida la última línea sin salto final.

3. **Extract Method** y **Decompose Conditional**: `_edits_confined_to_ranges` (desde `adjusted_lines`).
   - Reemplaza tres `if` anidados con una función con salidas tempranas (guard clauses), que devuelve `True` solo si el atajo es aplicable.

4. **Extract Method** y **Remove Duplicate Code**: `_map_range_start` y `_map_range_end` (desde `adjusted_lines`).
   - Las dos ramas simétricas "bloque cambiado / bloque sin cambios" se convierten en funciones con nombre.
   - El bucle de `adjusted_lines` queda solo con la gestión de índices y la validación del rango.

5. **Extract Method**: `_convert_unchanged_unwrapped_line` (desde `_convert_unchanged_line_by_line`).
   - El cuerpo del bucle tenía tres ramas largas (`match_stmt`, suite o cuerpo en línea de cláusula, y caso general).
   - Ahora el bucle solo filtra los `NEWLINE` y delega, y `replacements.apply()` queda en el mismo sitio.

6. **Extract Method**: `_preceding_siblings` (desde las dos ramas de `_convert_unchanged_line_by_line`).
   - Sustituye los dos bucles `while ... insert(0, ...)` idénticos por un acumulador con `append` y `reverse`, con el mismo resultado.
   - También devuelve el hermano que detuvo el recorrido, que la rama del `async` necesita.

7. **Extract Method**: `_clause_nodes_to_ignore` (desde la segunda rama).
   - Encapsula la lógica de hermanos previos, cuerpo en línea y caso especial de `ASYNC` en el abuelo.

8. **Extract Method** y **Remove Duplicate Code**: `_convert_nodes_if_unselected`.
   - Las ramas `match_stmt` y suite repetían el patrón "si el rango no interseca, convertir".

9. **Extract Method**: `_semantic_parent_of_suite` (desde `_TopLevelStatementsVisitor.visit_suite`).
   - Nombra la resolución del padre semántico, que salta el `ASYNC` hermano.

10. **Extract Method** y **Decompose Conditional**: `_standalone_comment_needs_newline` (desde `_str_with_standalone_comments`).
    - La condición booleana de tres niveles pasa a una función con nombre, y el bucle queda legible.

11. **Extract Method** y **Remove Duplicate Code**: `_make_unchanged_standalone_comment`.
    - `_convert_node_to_standalone_comment` y `_convert_nodes_to_standalone_comment` construían el mismo `Leaf` con seis argumentos.
    - El orden `first.lineno` → `take_prefix` se mantiene, porque `take_prefix` pone `lineno = 0`.

12. **Consolidate Duplicate Conditional Fragments**: `_get_line_range`.
    - Las tres ramas (lista, `Leaf`, `Node`) calculaban `first`, `last` y el `range` casi igual.
    - Se unifican con `first_leaf` y `last_leaf` sobre el primer y último nodo. Para un `Leaf` ambas funciones devuelven el propio leaf, así que el resultado no cambia.

13. **Extract Method**: `_common_prefix_length`, `_common_suffix_length` y `_matching_blocks` (desde `_calculate_lines_mappings`).
    - Separan el cálculo de bloques coincidentes (anclaje de extremos y `SequenceMatcher`) de la construcción de los `_LinesMapping`.

14. **Introduce Null Object / Replace Special Case**: bucle de `_calculate_lines_mappings`.
    - Se usa un `difflib.Match(0, 0, 0)` inicial como `previous_block`, lo que elimina la rama especial del índice 0. Los valores producidos son los mismos.
    - La condición `i > 0 or block.a != 0 or block.b != 0` conserva la regla de no emitir un bloque inicial vacío, pero sí los bloques vacíos entre coincidencias.

15. **Substitute Algorithm** (simplificación): `_contains_standalone_comment`.
    - El `for ... return True` con `return False` final se reescribe como `any(...)`.

16. **Add Type Annotation**: `_TopLevelStatementsVisitor.__init__` recibe `-> None`.
    - Es un cambio sin efecto en tiempo de ejecución.
#!/usr/bin/env python3
"""Cross reference in Jupyter notebook files."""
import argparse
import itertools
import re
import sys
from pathlib import Path
from typing import Iterable, List, Match, Sequence, Set, Tuple, TypeVar

T = TypeVar("T")


def remove_duplicates(seq: Sequence[T]) -> Sequence[T]:
    """Remove duplicates from the given sequence with preserving the order.

    >>> remove_duplicates((1, 2, 3, 1, 2, 4, 5))
    (1, 2, 3, 4, 5)
    """
    # See https://stackoverflow.com/a/480227
    seen: Set[T] = set()
    seen_add = seen.add
    return tuple(x for x in seq if not (x in seen or seen_add(x)))


def pairwise(seq: Iterable[T]) -> Iterable[Tuple[T, T]]:
    """Return successive overlapping pairs.

    >>> tuple(pairwise((1, 2, 3, 4, 5)))
    ((1, 2), (2, 3), (3, 4), (4, 5))
    """
    # See "Itertools Recipes",
    # https://docs.python.org/3.7/library/itertools.html#itertools-recipes
    a, b = itertools.tee(seq)
    next(b, None)
    return zip(a, b)


def n_files_str(nfiles: int) -> str:
    """Format `n files`.

    >>> n_files_str(0)
    'no files'
    >>> n_files_str(1)
    '1 file'
    >>> n_files_str(2)
    '2 files'
    """
    if nfiles == 0:
        return "no files"
    elif nfiles == 1:
        return "1 file"
    else:
        return f"{nfiles} files"


def relabel_tags(input_lines: Sequence[str], tag1: str, tag2: str) -> Sequence[str]:
    """Relabel special markup tags."""
    # Search for "{{{{TAG1 NAME}}}}".
    # Labels are sorted in the order of appearance of tag1.
    n = 0
    label_map = {}

    tag1_pattern = "{{{{" + tag1 + " ([^}]+)}}}}"

    for line in input_lines:
        labels = re.findall(tag1_pattern, line)
        for i in labels:
            n += 1
            label_map[i] = str(n)

    if not label_map:
        # No tag found. No relabeling needed.
        return input_lines

    # Perform relabeling.

    tag_pattern = "{{{{(" + tag1 + "|" + tag2 + ") ([^}]+)}}}}"

    def relabel_func(m: Match[str]) -> str:
        name = m.group(2)
        if name in label_map:
            name = label_map[name]
        return "{{{{" + m.group(1) + " " + name + "}}}}"

    output_lines = []
    for line in input_lines:
        line = re.sub(tag_pattern, relabel_func, line)
        output_lines.append(line)

    return output_lines


def make_footnotes(input_lines: Sequence[str], errors: List[str]) -> Sequence[str]:
    """Make footnotes in Markdown."""
    # Markdown:
    #   This is a footnote.[^1]
    #   [^1]: The footnote text.
    # HTML:
    #   This is a footnote.<a name="cite_ref-1"></a>[<sup>[1]</sup>](#cite_note-1)
    #   <a name="cite_note-1"></a>1.&nbsp;[^](#cite_ref-1) The footnote text.

    # Introduce special markups in the intermediate stage:
    #   This is a footnote.{{{{TO_FOOTNOTE 1}}}}
    #   {{{{FOOTNOTE 1}}}} The footnote text.

    output_lines = []

    for line in input_lines:
        # The negative lookbehind assertion "(?<!`)" avoids "`[^abc]`", which may appear
        # in a Markdown text explaining regular expressions.
        line = re.sub(
            r"(?<!`)\[\^([^\]]+)\]\s*:",
            r"{{{{FOOTNOTE \1}}}}",
            line,
        )
        line = re.sub(
            r"(?<!`)\[\^([^\]]+)\]",
            r"{{{{TO_FOOTNOTE \1}}}}",
            line,
        )
        # Convert HTML footnotes back with the special markups.
        # Note that in double double quotation marks are escaped in JSON files.
        line = re.sub(
            r"<a name=\\\"cite_ref-([^\"]+)\\\"></a>"
            r"\[<sup>\[\1\]</sup>\]\(#cite_note-\1\)",
            r"{{{{TO_FOOTNOTE \1}}}}",
            line,
        )
        line = re.sub(
            r"<a name=\\\"cite_note-([^\"]+)\\\"></a>\1\.&nbsp;\[\^\]\(#cite_ref-\1\)",
            r"{{{{FOOTNOTE \1}}}}",
            line,
        )
        # Catch also old HTML code, like
        #   [<sup id="cite_ref-1">[1]</sup>](#cite_note-1)
        #   <span id="cite_note-1">1.</span> [^](#cite_ref-1)
        line = re.sub(
            r"\[<sup id=\\\"cite_ref-([^\"]+)\\\">\[\1\]</sup>\]\(#cite_note-\1\)",
            r"{{{{TO_FOOTNOTE \1}}}}",
            line,
        )
        line = re.sub(
            r"<span id=\\\"cite_note-([^\"]+)\\\">\1\.</span> \[\^\]\(#cite_ref-\1\)",
            r"{{{{FOOTNOTE \1}}}}",
            line,
        )

        output_lines.append(line)

    # Relabeling.

    output_lines = list(relabel_tags(output_lines, "TO_FOOTNOTE", "FOOTNOTE"))

    # Convert to HTML.

    input_lines = output_lines
    output_lines = []

    for line in input_lines:
        line = re.sub(
            r"{{{{TO_FOOTNOTE ([^}]+)}}}}",
            r"<a name=\"cite_ref-\1\"></a>[<sup>[\1]</sup>](#cite_note-\1)",
            line,
        )
        line = re.sub(
            r"{{{{FOOTNOTE ([^}]+)}}}}",
            r"<a name=\"cite_note-\1\"></a>\1.&nbsp;[^](#cite_ref-\1)",
            line,
        )
        output_lines.append(line)

    # Check if footnotes are consistent.

    cites = []
    footnotes = []

    for line in input_lines:
        cites += re.findall(r"{{{{TO_FOOTNOTE ([^}]+)}}}}", line)
        footnotes += re.findall(r"{{{{FOOTNOTE ([^}]+)}}}}", line)

    cites_set = set(cites)
    footnotes_set = set(footnotes)

    cites_not_found = []
    footnotes_not_found = []

    for i in remove_duplicates(cites):
        if i not in footnotes_set:
            cites_not_found.append(i)

    for i in remove_duplicates(footnotes):
        if i not in cites_set:
            footnotes_not_found.append(i)

    cites_duplicates = []
    footnotes_duplicates = []

    cites_seen = set()
    footnotes_seen = set()

    for i in cites:
        if i in cites_seen:
            cites_duplicates.append(i)
        else:
            cites_seen.add(i)

    for i in footnotes:
        if i in footnotes_seen:
            footnotes_duplicates.append(i)
        else:
            footnotes_seen.add(i)

    wrongly_ordered = []

    for i, j in pairwise(footnotes):
        if i.isdigit() and j.isdigit() and int(i) > int(j):
            wrongly_ordered.append((i, j))

    if cites_not_found:
        errors.append(f"Footnotes not found: {', '.join(cites_not_found)}")

    if footnotes_not_found:
        errors.append(f"Footnotes not referenced: {', '.join(footnotes_not_found)}")

    if cites_duplicates:
        errors.append(
            f"Duplicated references of footnotes: {', '.join(cites_duplicates)}"
        )

    if footnotes_duplicates:
        errors.append(f"Duplicated footnotes: {', '.join(footnotes_duplicates)}")

    if wrongly_ordered:
        errors.append(
            "Wrongly ordered footnotes: "
            f"{', '.join(f'({i}, {j})' for i, j in wrongly_ordered)}"
        )

    return output_lines


def make_eqrefs(input_lines: Sequence[str], errors: List[str]) -> Sequence[str]:
    """Make equation references in Markdown."""
    # Markdown:
    #   \tag{1}
    #   \eqref{1}
    # HTML:
    #   \tag{1}
    #   <!-- eqref -->(1)

    # Note that both \tag and \eqref (and \label) are recognized by MathJax,
    # but cross reference doesn't work for different cells.

    # Introduce special markups in the intermediate stage:
    #   {{{{TAG 1}}}}
    #   {{{{EQREF 1}}}}

    output_lines = []

    for line in input_lines:
        line = re.sub(r"\\\\tag\{([^}]+)\}", r"{{{{TAG \1}}}}", line)
        line = re.sub(r"\\\\eqref\{([^}]+)\}", r"{{{{EQREF \1}}}}", line)

        # Convert HTML back to the markups.
        line = re.sub(r"<!-- eqref -->\(([^)]+)\)", r"{{{{EQREF \1}}}}", line)

        output_lines.append(line)

    # Relabeling.

    output_lines = list(relabel_tags(output_lines, "TAG", "EQREF"))

    # Convert to HTML.

    input_lines = output_lines
    output_lines = []

    for line in input_lines:
        line = re.sub(
            r"{{{{TAG ([^}]+)}}}}",
            r"\\\\tag{\1}",
            line,
        )
        line = re.sub(
            r"{{{{EQREF ([^}]+)}}}}",
            r"<!-- eqref -->(\1)",
            line,
        )
        output_lines.append(line)

    # Check the consistency.

    tags = []
    eqrefs = []

    for line in input_lines:
        tags += re.findall(r"{{{{TAG ([^}]+)}}}}", line)
        eqrefs += re.findall(r"{{{{EQREF ([^}]+)}}}}", line)

    tags_set = set(tags)

    eqrefs_not_found = []

    for i in remove_duplicates(eqrefs):
        if i not in tags_set:
            eqrefs_not_found.append(i)

    tags_duplicates = []

    tags_seen = set()

    for i in tags:
        if i in tags_seen:
            tags_duplicates.append(i)
        else:
            tags_seen.add(i)

    if eqrefs_not_found:
        errors.append(f"Tags not found: {', '.join(eqrefs_not_found)}")

    if tags_duplicates:
        errors.append(f"Duplicated tags: {', '.join(tags_duplicates)}")

    return output_lines


def process_file(path: Path, errors: List[str]) -> bool:
    """Process the specified file."""
    local_errors: List[str] = []

    input_lines = path.read_text().splitlines()

    output_lines = make_footnotes(input_lines, local_errors)
    output_lines = make_eqrefs(output_lines, local_errors)

    if local_errors:
        errors.append(f"Error: in file {path}:")
        errors.extend(local_errors)

    if input_lines != output_lines:
        path.write_text("\n".join(output_lines) + "\n")
        return True

    return False


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "files", type=Path, nargs="*", help="source files to be processed"
    )
    args = parser.parse_args()

    n_files = 0
    n_changed = 0
    errors: List[str] = []

    def do_process_file(path: Path) -> None:
        nonlocal n_files, n_changed
        n_files += 1
        if process_file(path, errors):
            print(f"Changed: {path}")
            n_changed += 1

    for source_path in args.files:
        if source_path.is_dir():
            # glob excluding hidden files
            for path in source_path.glob("**/*.ipynb"):
                if not any(part.startswith(".") for part in path.parts):
                    do_process_file(path)
        else:
            do_process_file(source_path)

    print(
        f"{n_files_str(n_files).capitalize()} processed. "
        f"{n_files_str(n_changed).capitalize()} changed."
    )

    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        exit(1)


if __name__ == "__main__":
    main()

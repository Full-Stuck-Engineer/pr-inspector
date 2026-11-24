"""Application service for extracting search symbols and queries from file diffs."""

import re

from pr_inspector.domain.entities import FileDiff
from pr_inspector.infrastructure.search.bm25 import tokenize_code

_DEF_RE = re.compile(r"(?:async\s+)?def\s+([a-zA-Z0-9_]+)")
_CLASS_RE = re.compile(r"class\s+([a-zA-Z0-9_]+)")
_IMPORT_FROM_RE = re.compile(r"^\s*from\s+([a-zA-Z0-9_.]+)\s+import\s+(.+)")
_IMPORT_RE = re.compile(r"^\s*import\s+([a-zA-Z0-9_., ]+)")
_CALL_RE = re.compile(r"([a-zA-Z0-9_]+)\s*\(")

_STOPWORDS = {
    "self",
    "cls",
    "none",
    "true",
    "false",
    "return",
    "yield",
    "async",
    "await",
    "def",
    "class",
    "import",
    "from",
    "as",
    "in",
    "is",
    "and",
    "or",
    "not",
    "for",
    "while",
    "try",
    "except",
    "finally",
    "raise",
    "if",
    "elif",
    "else",
    "pass",
    "break",
    "continue",
    "with",
    "lambda",
    "int",
    "str",
    "float",
    "bool",
    "list",
    "dict",
    "set",
    "tuple",
    "optional",
    "any",
    "union",
}


class DiffSymbolExtractor:
    """Extracts function, class, and import symbols from diff hunks to form search queries."""

    def extract_symbols(self, diffs: list[FileDiff]) -> list[str]:
        """Extract prioritized symbol names from file diffs."""
        definitions: list[str] = []
        imports: list[str] = []
        identifiers: list[str] = []
        seen: set[str] = set()

        for file_diff in diffs:
            for hunk in file_diff.hunks:
                # 1. Hunk header definitions (e.g. @@ ... @@ def func_name(...))
                if hunk.header:
                    def_match = _DEF_RE.search(hunk.header)
                    if def_match:
                        sym = def_match.group(1)
                        if sym not in seen and sym.lower() not in _STOPWORDS:
                            seen.add(sym)
                            definitions.append(sym)

                    class_match = _CLASS_RE.search(hunk.header)
                    if class_match:
                        sym = class_match.group(1)
                        if sym not in seen and sym.lower() not in _STOPWORDS:
                            seen.add(sym)
                            definitions.append(sym)

                # 2. Changed lines inspection
                for line in hunk.lines:
                    text = line.content

                    # Check for function definition
                    def_match = _DEF_RE.search(text)
                    if def_match:
                        sym = def_match.group(1)
                        if sym not in seen and sym.lower() not in _STOPWORDS:
                            seen.add(sym)
                            definitions.append(sym)

                    # Check for class definition
                    class_match = _CLASS_RE.search(text)
                    if class_match:
                        sym = class_match.group(1)
                        if sym not in seen and sym.lower() not in _STOPWORDS:
                            seen.add(sym)
                            definitions.append(sym)

                    # Check for function/method calls
                    for call_match in _CALL_RE.finditer(text):
                        sym = call_match.group(1)
                        if len(sym) > 2 and sym not in seen and sym.lower() not in _STOPWORDS:
                            seen.add(sym)
                            definitions.append(sym)

                    # Check for from-imports
                    from_match = _IMPORT_FROM_RE.match(text)
                    if from_match:
                        mod = from_match.group(1).split(".")[-1]
                        if mod not in seen and mod.lower() not in _STOPWORDS:
                            seen.add(mod)
                            imports.append(mod)
                        for target in from_match.group(2).split(","):
                            clean_target = target.strip().split()[0]
                            if (
                                clean_target
                                and clean_target not in seen
                                and clean_target.lower() not in _STOPWORDS
                            ):
                                seen.add(clean_target)
                                imports.append(clean_target)

                    # Check for simple imports
                    import_match = _IMPORT_RE.match(text)
                    if import_match:
                        for target in import_match.group(1).split(","):
                            clean_target = target.strip().split()[0].split(".")[-1]
                            if (
                                clean_target
                                and clean_target not in seen
                                and clean_target.lower() not in _STOPWORDS
                            ):
                                seen.add(clean_target)
                                imports.append(clean_target)

                    # Extract significant identifiers on added/deleted lines
                    if line.line_type in ("add", "del"):
                        for token in tokenize_code(text):
                            if (
                                len(token) > 2
                                and token.lower() not in _STOPWORDS
                                and token not in seen
                            ):
                                seen.add(token)
                                identifiers.append(token)

        return definitions + imports + identifiers

    def build_search_query(self, diffs: list[FileDiff], max_terms: int = 15) -> str:
        """Construct a focused query string from extracted diff symbols."""
        symbols = self.extract_symbols(diffs)
        selected = symbols[:max_terms]
        return " ".join(selected)

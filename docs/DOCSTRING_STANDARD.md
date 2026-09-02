# Python documentation standard

The Python source is part of the preservation record for this project. A future
maintainer should be able to understand why a parser, formatter, validator, or
writer exists without reconstructing its intent from a generated disc image.

## Supported scope

The automated contract applies to maintained modules and their public top-level
classes, functions, and methods. Private and nested helpers require docstrings
when their behavior is non-obvious, binary-format-sensitive, stateful, or
otherwise benefits from an explicit contract. This avoids ceremonial prose on
self-explanatory implementation details while preserving documentation where it
protects reverse-engineered behavior.

## Formatting profile

Python 3.12 is the minimum supported interpreter. Ruff owns generic linting and
modernization checks with the repository's 88-column target. Source text uses
UTF-8, LF line endings, a final newline, and no trailing whitespace.

## Docstrings

For maintained public APIs:

1. Write a concise summary ending in punctuation.
2. Put a blank line after the summary in a multi-line docstring.
3. Describe purpose and project context rather than restating the symbol name.
4. Document inputs and outputs whose units, ownership, shape, or constraints are
   not obvious from type annotations.
5. Identify meaningful filesystem writes, subprocesses, mutation, and caches.
6. State recoverable failure conditions where doing so helps callers.
7. Record assumptions that protect disc layout, determinism, translation data,
   renderer behavior, or retail provenance.

Private helpers should be documented when the reason for their existence is not
clear from their name, types, module documentation, and nearby comments. Binary
format constants and unusual algorithms should retain strong explanations even
when their symbols are private.

## Explanatory comments

Comments should explain why a non-obvious step exists, especially around disc
geometry, reverse-engineered formats, renderer behavior, or deterministic
output. Avoid narrating obvious Python syntax or duplicating a docstring.

## Review checklist

1. Run `python -m tools.source_checks --root . --strict-release`.
2. Confirm public API documentation still describes behavior.
3. Confirm non-obvious private binary/renderer logic still has useful context.
4. Keep comments synchronized with the implementation.
5. For documentation-only edits, verify executable behavior is unchanged.

Automation enforces structural coverage on maintained public APIs; human review
remains responsible for technical accuracy and useful context.

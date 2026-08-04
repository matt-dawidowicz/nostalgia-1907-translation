# Python documentation standard

The Python source is part of the preservation record for this project. A
developer should be able to understand why a parser, formatter, validator, or
writer exists without reconstructing its intent from a generated disc image.
This guide defines the minimum documentation contract for maintained code.

## Supported scope

The contract applies to:

- the unified `nostalgia1907.py` command-line interface;
- the production modules in `work/clean_rebuild/`;
- translation analysis, comparison, and validation modules;
- the US BIOS-language test variant builder; and
- maintained tests for those components.

Historical investigation scripts are evidence from earlier reverse-engineering
work. They are not production dependencies and are not retroactively rewritten
to this standard.

## Formatting profile

Maintained Python uses Black 24.10.0 with its 88-column profile and Python 3.10
target. This is the project's current PEP 8 profile: four-space indentation,
standardized whitespace, a final newline, and no trailing whitespace. The
repository's dependency-free style audit enforces 88-column executable lines
and PEP 257 coverage; Black is the mechanical formatter used before review.
Atomic serialized strings (such as generated HTML, CSS, hashes, and fixture
data) remain intact when splitting them would reduce auditability or risk
changing generated evidence.

## Docstrings

Use PEP 257 conventions for every maintained module, class, function, method,
property, and nested helper:

1. Write a short imperative summary that ends with punctuation.
2. Put a blank line after the summary in a multi-line docstring.
3. Describe purpose and project context, not a restatement of the Python name.
4. Document inputs and outputs whose meaning, units, shape, ownership, or
   constraints are not fully expressed by the type annotation.
5. Identify filesystem writes, subprocesses, mutable arguments, caches, and
   other side effects.
6. State expected failure conditions and the exception type when callers can
   reasonably recover from or diagnose them.
7. Record assumptions and design decisions that protect disc layout,
   determinism, canonical translation data, or retail-media provenance.

Use the following sections when they add information:

```python
def example(path: Path, *, strict: bool) -> dict[str, object]:
    """Parse one hash-guarded project artifact.

    The parser rejects malformed data before returning so downstream writers
    never need to operate on a partially validated structure.

    Args:
        path: UTF-8 JSON file to parse.
        strict: Whether unknown keys are rejected.

    Returns:
        A normalized mapping whose required fields have been validated.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        ValueError: If the file violates the documented schema.

    Side Effects:
        Reads ``path`` but does not modify it.
    """
```

`Args`, `Returns`, `Yields`, `Raises`, `Side Effects`, `Assumptions`, and
`Notes` are descriptive conventions rather than a requirement to include empty
sections. A trivial pure helper may use a one-line docstring when its type
annotations and surrounding module documentation fully describe the contract.

Do not use docstrings to excuse unsafe behavior. Hash checks, bounds checks,
fixed-size checks, and deterministic ordering must remain executable
invariants.

## Explanatory comments

Follow PEP 8 comment conventions:

- write complete sentences with normal capitalization and punctuation;
- place a block comment immediately above the code it explains;
- explain why a non-obvious step is required, especially for disc geometry,
  reverse-engineered formats, renderer behavior, or deterministic output;
- keep comments synchronized with the implementation; and
- avoid narrating obvious syntax or duplicating the docstring.

Binary constants should name their source or role. A comment such as “skip 16”
is insufficient; explain that the 16 bytes are a raw-sector sync and header,
and identify the function that validates them.

## Review checklist

Before committing a Python change:

1. Run the documentation contract tests.
2. Read the rendered diff and verify every summary still describes behavior.
3. Confirm changed arguments, return shapes, side effects, and failure modes
   are reflected in the docstring.
4. Confirm comments describe the current algorithm rather than an abandoned
   investigation.
5. Prove that documentation-only edits leave executable ASTs unchanged.

The automated test enforces complete callable coverage and basic PEP 257
structure. Human review remains responsible for accuracy and useful context.

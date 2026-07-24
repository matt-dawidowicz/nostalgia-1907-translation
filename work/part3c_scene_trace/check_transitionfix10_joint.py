#!/usr/bin/env python3
"""Check joint row reflows for dynamic indexes 294 and 302."""

from __future__ import annotations

import json
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))

import analyze_transitionfix10_row_reflows as audit  # noqa: E402
from mes_probe import parse_mes  # noqa: E402


def main() -> None:
    """Print exact encodings with both candidate slots excluded."""
    data = audit.MES.read_bytes()
    info, _ = parse_mes(data, audit.MES)
    available = audit.available_tokens(
        audit.FONT.read_bytes(), data[info.split_offset :], {294, 302}
    )
    result = {
        "Iryu's true": audit.encode_line("Iryu's true", available, 8),
        "Iryu is not": audit.encode_line("Iryu is not", available, 8),
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

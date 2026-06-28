"""Pure argv utilities for CLI flags.

Used to normalize --headed / --start-bedroom (and similar store_true flags)
from any position in argv so that pre-subcommand placement works reliably.
"""

from __future__ import annotations
from typing import Tuple, List


def pop_store_true_flag(argv: List[str] | None, flag: str) -> Tuple[bool, List[str]]:
    """Remove a store_true flag (e.g. '--headed') from argv regardless of position.

    Returns (present, cleaned_argv).

    The original argv list is not mutated; a new list is returned.
    """
    if argv is None:
        argv = []
    cleaned: List[str] = []
    present = False
    i = 0
    n = len(argv)
    while i < n:
        tok = argv[i]
        if tok == flag:
            present = True
            i += 1
            continue
        # also handle --flag=value form if ever used for booleans (defensive)
        if tok.startswith(flag + "="):
            present = True
            i += 1
            continue
        cleaned.append(tok)
        i += 1
    return present, cleaned

"""Fix console script bins for src-layout + uv venv so bare `uv run poke-*` works.

After `uv sync`, run `uv run poke-fix` (or python -m src.run._fix_bins) to patch
.venv/bin/poke-agent and poke-runner. This inserts the project/src on sys.path
before the 'from src...' so the shebang python (often symlinked system python)
can import src.

This makes the primary shipped poke-* entrypoints accept --headed etc.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def fix() -> None:
    """Patch poke-* bins in the current venv (or .venv) to support 'import src'."""
    venv = os.environ.get("VIRTUAL_ENV")
    if not venv:
        venv = str(Path.cwd() / ".venv")
    bin_dir = Path(venv) / "bin"
    patched = []
    for name in ("poke-agent", "poke-runner"):
        bin_path = bin_dir / name
        if not bin_path.exists():
            continue
        text = bin_path.read_text(encoding="utf-8")
        if "sys.path.insert" in text and "parents[2]" in text:
            patched.append(name)
            continue
        lines = text.splitlines(keepends=True)
        new_lines: list[str] = []
        inserted = False
        for i, line in enumerate(lines):
            if not inserted and line.strip().startswith("from src"):
                # insert path code right before the from
                new_lines.append("import sys\n")
                new_lines.append("from pathlib import Path\n")
                new_lines.append("sys.path.insert(0, str(Path(__file__).resolve().parents[2]))\n")
                inserted = True
            new_lines.append(line)
        if inserted:
            bin_path.write_text("".join(new_lines), encoding="utf-8")
            try:
                bin_path.chmod(0o755)
            except Exception:
                pass
            patched.append(name)
    if patched:
        print(f"Patched poke bins: {', '.join(patched)}")
    else:
        print("No poke bins needed patching (or not present)")


if __name__ == "__main__":
    fix()
    sys.exit(0)
